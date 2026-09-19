"""Independent regressions derived from source review, not checkpoint reports."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models import Membership, RoleEnum, Lead, Contact, Company
from tests.test_checkpoint3 import crm, post  # noqa: F401


@pytest.mark.parametrize(
    "resource,role", [("deals", RoleEnum.SALES_EXECUTIVE), ("campaigns", RoleEnum.MARKETING)]
)
async def test_other_delete_permissions(client, db_session, crm, resource, role):
    from app.models import Deal, Campaign

    row = (
        Deal(
            tenant_id=crm["tenant"],
            title="Protected",
            pipeline_id=crm["pipeline"].id,
            stage_id=crm["stage"].id,
            owner_id=crm["user"],
        )
        if resource == "deals"
        else Campaign(
            tenant_id=crm["tenant"],
            name="Protected",
            type="broadcast",
            sender_name="Audit",
            sender_email="audit@example.com",
            created_by_id=crm["user"],
        )
    )
    db_session.add(row)
    member = await db_session.scalar(
        select(Membership).where(
            Membership.tenant_id == crm["tenant"], Membership.user_id == crm["user"]
        )
    )
    member.role = role
    await db_session.commit()
    response = await client.delete(f"/api/v1/{resource}/{row.id}", headers=crm["headers"])
    assert response.status_code == 403, response.text


async def test_assigned_scope_across_search_intelligence_tools_and_customer(
    client, db_session, crm
):
    from app.models import Note, Task, Conversation, Message
    from app.services.automation.context import snapshot
    from app.services.ai.workforce_tools import validate_ownership
    from fastapi import HTTPException

    member = await db_session.scalar(
        select(Membership).where(
            Membership.tenant_id == crm["tenant"], Membership.user_id == crm["user"]
        )
    )
    member.role = RoleEnum.SALES_EXECUTIVE
    private = Lead(
        tenant_id=crm["tenant"], title="Secretquery private", contact_id=crm["contact"].id
    )
    visible = Lead(
        tenant_id=crm["tenant"],
        title="Secretquery visible",
        contact_id=crm["contact"].id,
        owner_id=crm["user"],
    )
    db_session.add_all([private, visible])
    await db_session.flush()
    note = Note(
        tenant_id=crm["tenant"],
        content="Secretquery note",
        lead_id=private.id,
        contact_id=crm["contact"].id,
        author_id=crm["user"],
    )
    task = Task(
        tenant_id=crm["tenant"],
        title="Secretquery task",
        lead_id=private.id,
        contact_id=crm["contact"].id,
        owner_id=crm["user"],
    )
    conversation = Conversation(
        tenant_id=crm["tenant"],
        subject="Secretquery conversation",
        lead_id=private.id,
        contact_id=crm["contact"].id,
    )
    db_session.add_all([note, task, conversation])
    await db_session.flush()
    message = Message(
        tenant_id=crm["tenant"], conversation_id=conversation.id, body="Secretquery message"
    )
    db_session.add(message)
    await db_session.commit()
    hidden = {str(x.id) for x in (private, note, task, conversation, message)}
    search = await client.get("/api/v1/operations/search?q=Secretquery", headers=crm["headers"])
    assert search.status_code == 200, search.text
    assert not hidden.intersection(str(x["id"]) for x in search.json()["items"])
    assert str(visible.id) in {str(x["id"]) for x in search.json()["items"]}
    view = await client.get(
        f"/api/v1/operations/customers/contacts/{crm['contact'].id}", headers=crm["headers"]
    )
    assert view.status_code == 200, view.text
    assert all(
        str(x["id"]) not in hidden for rows in view.json()["sections"].values() for x in rows
    )
    intelligence = await client.get(
        f"/api/v1/automation/intelligence/lead/lead/{private.id}", headers=crm["headers"]
    )
    assert intelligence.status_code == 403, intelligence.text
    from app.services.automation.intelligence import inspect_entity

    for operation in (
        inspect_entity(db_session, crm["tenant"], crm["user"], "lead", "lead", private.id),
        snapshot(
            db_session,
            crm["tenant"],
            crm["user"],
            {"entity_type": "lead", "entity_id": str(private.id)},
        ),
        validate_ownership(
            db_session, crm["tenant"], crm["user"], "get_lead", {"lead_id": str(private.id)}
        ),
    ):
        with pytest.raises(HTTPException) as error:
            await operation
        assert error.value.status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "leads?status=bogus",
        "leads?source=bogus",
        "tasks?status=bogus",
        "auth/switch-tenant/not-a-uuid",
    ],
)
async def test_invalid_enum_and_uuid_are_validation_errors(client, auth_headers, path):
    response = await client.request(
        "POST" if "switch-tenant" in path else "GET", "/api/v1/" + path, headers=auth_headers
    )
    assert response.status_code == 422, response.text


async def test_lead_source_crud_contract(client, crm):
    listing = await client.get("/api/v1/integrations/lead-sources", headers=crm["headers"])
    assert listing.status_code == 200, listing.text
    invalid = await post(client, crm, "/integrations/lead-sources", {})
    assert invalid.status_code == 422, invalid.text
    created = await post(
        client,
        crm,
        "/integrations/lead-sources",
        {"source_key": "audit-source", "display_name": "Before", "source_type": "webhook"},
    )
    assert created.status_code == 201, created.text
    updated = await post(
        client,
        crm,
        "/integrations/lead-sources/" + created.json()["id"],
        {"display_name": "After"},
        method="PATCH",
    )
    assert updated.status_code == 200, updated.text
    listing = await client.get("/api/v1/integrations/lead-sources", headers=crm["headers"])
    assert any(row["display_name"] == "After" for row in listing.json())


@pytest.mark.parametrize("change", ["paused", "cancelled", "suppressed", "permission"])
async def test_campaign_rechecks_send_boundary(client, db_session, crm, monkeypatch, change):
    from app.models import OperationJob, Campaign, Contact
    import app.services.crm.jobs as jobs

    created = await post(
        client,
        crm,
        "/campaigns",
        {"name": "Boundary audit", "sender_name": "Audit", "sender_email": "audit@example.com"},
    )
    assert created.status_code == 201, created.text
    campaign_id = UUID(created.json()["id"])
    configured = await post(
        client,
        crm,
        f"/operations/campaigns/{campaign_id}/plan",
        {
            "integration_id": str(crm["integration"].id),
            "contact_ids": [str(crm["contact"].id)],
            "subject": "Hello",
            "body": "Hello",
        },
        method="PUT",
    )
    assert configured.status_code == 200, configured.text
    started = await post(client, crm, f"/operations/campaigns/{campaign_id}/launch")
    assert started.status_code == 200, started.text
    job = await db_session.scalar(select(OperationJob).where(OperationJob.kind == "campaign_send"))
    original = jobs.access_token
    changed = False

    async def change_during_token_access(db, tenant, integration):
        nonlocal changed
        token = await original(db, tenant, integration)
        if not changed:
            changed = True
            if change in {"paused", "cancelled"}:
                campaign = await db.get(Campaign, campaign_id)
                from app.models import CampaignStatusEnum

                campaign.status = CampaignStatusEnum(change)
            elif change == "suppressed":
                contact = await db.get(Contact, crm["contact"].id)
                contact.email_opted_out = True
            else:
                member = await db.scalar(
                    select(Membership).where(
                        Membership.tenant_id == tenant, Membership.user_id == crm["user"]
                    )
                )
                member.role = RoleEnum.VIEWER
            await db.flush()
        return token

    monkeypatch.setattr(jobs, "access_token", change_during_token_access)
    await jobs.execute_job(db_session, crm["tenant"], job.id)
    assert not crm["mock"].sent
    assert job.status != "running"


async def test_new_workspace_has_creator_owner_and_can_be_selected(
    client, db_session, test_user, auth_headers, crm
):
    response = await client.post(
        "/api/v1/tenants",
        headers=auth_headers,
        json={"name": "New workspace", "slug": "audit-" + uuid4().hex},
    )
    assert response.status_code == 201, response.text
    tenant_id = UUID(response.json()["id"])
    member = await db_session.scalar(
        select(Membership).where(
            Membership.tenant_id == tenant_id, Membership.user_id == test_user.id
        )
    )
    assert member is not None and member.role == RoleEnum.OWNER
    switched = await client.post(f"/api/v1/auth/switch-tenant/{tenant_id}", headers=auth_headers)
    assert switched.status_code == 200, switched.text


@pytest.mark.parametrize("resource", ["leads", "contacts", "companies"])
async def test_write_permission_does_not_allow_deletion(
    client, db_session, test_user, test_tenant, auth_headers, resource
):
    member = await db_session.scalar(
        select(Membership).where(
            Membership.tenant_id == test_tenant.id, Membership.user_id == test_user.id
        )
    )
    member.role = RoleEnum.MARKETING
    row = {
        "leads": lambda: Lead(title="Protected lead"),
        "contacts": lambda: Contact(first_name="Protected", last_name="Contact"),
        "companies": lambda: Company(name="Protected company"),
    }[resource]()
    row.tenant_id = test_tenant.id
    db_session.add(row)
    await db_session.commit()
    response = await client.delete(f"/api/v1/{resource}/{row.id}", headers=auth_headers)
    assert response.status_code == 403, response.text
    assert await db_session.get(type(row), row.id) is not None


async def test_task_reopening_clears_completion_timestamp(
    client, db_session, test_tenant, auth_headers
):
    company = Company(tenant_id=test_tenant.id, name="Task customer")
    db_session.add(company)
    await db_session.commit()
    response = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={"title": "Follow up", "company_id": str(company.id)},
    )
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]
    completed = await client.patch(
        f"/api/v1/tasks/{task_id}", headers=auth_headers, json={"status": "completed"}
    )
    assert completed.status_code == 200 and completed.json()["completed_at"]
    reopened = await client.patch(
        f"/api/v1/tasks/{task_id}", headers=auth_headers, json={"status": "pending"}
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["completed_at"] is None


async def test_lead_owner_cannot_be_changed_without_assign_permission(
    client, db_session, test_tenant, test_user, auth_headers
):
    member = await db_session.scalar(
        select(Membership).where(
            Membership.tenant_id == test_tenant.id, Membership.user_id == test_user.id
        )
    )
    member.role = RoleEnum.MARKETING
    lead = Lead(tenant_id=test_tenant.id, title="Assignment protected", owner_id=test_user.id)
    db_session.add(lead)
    await db_session.commit()
    response = await client.patch(
        f"/api/v1/leads/{lead.id}", headers=auth_headers, json={"owner_id": None}
    )
    assert response.status_code == 403, response.text


async def test_customer360_cannot_bypass_assigned_lead_scope(
    client, db_session, test_tenant, test_user, auth_headers
):
    member = await db_session.scalar(
        select(Membership).where(
            Membership.tenant_id == test_tenant.id, Membership.user_id == test_user.id
        )
    )
    member.role = RoleEnum.SALES_EXECUTIVE
    lead = Lead(tenant_id=test_tenant.id, title="Unassigned confidential lead")
    db_session.add(lead)
    await db_session.commit()
    direct = await client.get(f"/api/v1/leads/{lead.id}", headers=auth_headers)
    assert direct.status_code == 404
    overview = await client.get(
        f"/api/v1/operations/customers/leads/{lead.id}", headers=auth_headers
    )
    assert overview.status_code == 404, overview.text


@pytest.mark.parametrize(
    "invalid", [None, "email", "nonce", "audience", "issuer", "expired", "subject", "inactive"]
)
async def test_google_signed_identity_and_browser_binding(
    client, db_session, test_user, monkeypatch, invalid
):
    """Use real OIDC signature/claim validation; only Google HTTP is replaced."""
    import time
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from joserfc import jwt
    from joserfc.jwk import RSAKey
    from app.services.auth.service import AuthService, settings
    from app.services.auth import google_state

    monkeypatch.setattr(settings.google_oauth, "client_id", "audit-google-client")
    monkeypatch.setattr(settings.google_oauth, "client_secret", "synthetic-google-secret")
    google = AuthService(db_session).oauth.google
    signing = RSAKey.generate_key(2048)
    metadata = {
        "issuer": "https://accounts.google.com",
        "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        "id_token_signing_alg_values_supported": ["RS256"],
    }
    monkeypatch.setattr(google, "load_server_metadata", AsyncMock(return_value=metadata))
    monkeypatch.setattr(
        google, "fetch_jwk_set", AsyncMock(return_value={"keys": [signing.as_dict(private=False)]})
    )
    monkeypatch.setattr(AuthService, "oauth", property(lambda self: SimpleNamespace(google=google)))
    state, binding, nonce, verifier = await google_state.begin()
    timestamp = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "audit-google-client",
        "sub": "audit-google-user",
        "iat": timestamp,
        "exp": timestamp + 120,
        "nonce": nonce,
        "email": test_user.email,
        "email_verified": True,
        "name": "Audit User",
    }
    if invalid == "email":
        claims["email_verified"] = False
    if invalid == "nonce":
        claims["nonce"] = "wrong-nonce"
    if invalid == "audience":
        claims["aud"] = "another-client"
    if invalid == "issuer":
        claims["iss"] = "https://attacker.example"
    if invalid == "expired":
        claims["exp"] = timestamp - 300
    if invalid == "subject":
        test_user.google_id = "different-google-user"
    if invalid == "inactive":
        test_user.is_active = False
    await db_session.commit()
    exchange = AsyncMock(return_value={"id_token": jwt.encode({"alg": "RS256"}, claims, signing)})
    monkeypatch.setattr(google, "fetch_access_token", exchange)
    client.cookies.set(google_state.COOKIE, binding)
    response = await client.post(
        "/api/v1/auth/google", json={"code": "synthetic-code", "state": state}
    )
    assert response.status_code == (400 if invalid else 200), response.text
    exchange.assert_awaited_once_with(
        redirect_uri=settings.google_oauth.redirect_uri,
        code="synthetic-code",
        code_verifier=verifier,
    )
    if not invalid:
        assert response.json()["access_token"]
        assert response.headers["cache-control"] == "no-store"
        assert test_user.google_id == "audit-google-user"
    # The same authorization transaction cannot be replayed, even with its cookie.
    client.cookies.set(google_state.COOKIE, binding)
    replay = await client.post(
        "/api/v1/auth/google", json={"code": "synthetic-code", "state": state}
    )
    assert replay.status_code == 400
    assert exchange.await_count == 1


async def test_google_state_requires_browser_secret():
    from app.services.auth.google_state import begin, consume

    state, binding, nonce, verifier = await begin()
    with pytest.raises(ValueError):
        await consume(state, "another-browser")
    stored = await consume(state, binding)
    assert stored["nonce"] == nonce and stored["verifier"] == verifier
    with pytest.raises(ValueError):
        await consume(state, binding)


async def test_google_start_uses_pkce_nonce_and_cookie(client, db_session, monkeypatch):
    from urllib.parse import urlsplit, parse_qs
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services.auth.service import AuthService, settings
    from app.services.auth.google_state import COOKIE

    monkeypatch.setattr(settings.google_oauth, "client_id", "audit-google-client")
    monkeypatch.setattr(settings.google_oauth, "client_secret", "synthetic-google-secret")
    google = AuthService(db_session).oauth.google
    monkeypatch.setattr(
        google,
        "load_server_metadata",
        AsyncMock(
            return_value={"authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth"}
        ),
    )
    monkeypatch.setattr(AuthService, "oauth", property(lambda self: SimpleNamespace(google=google)))
    response = await client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert response.status_code == 302, response.text
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["nonce"] and params["state"] and params["code_challenge"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert COOKIE in client.cookies


async def test_deal_pipeline_stage_and_reopening_invariants(client, db_session, crm):
    from app.models import Pipeline

    crm["stage2"].is_closed = True
    crm["stage2"].probability = 100
    second = Pipeline(tenant_id=crm["tenant"], name="Another pipeline")
    db_session.add(second)
    await db_session.commit()
    created = await post(
        client,
        crm,
        "/deals",
        {
            "title": "Audit deal",
            "value": 500,
            "pipeline_id": str(crm["pipeline"].id),
            "stage_id": str(crm["stage"].id),
        },
    )
    assert created.status_code == 201, created.text
    path = "/deals/" + created.json()["id"]
    invalid = await post(client, crm, path, {"pipeline_id": str(second.id)}, method="PATCH")
    assert invalid.status_code == 422, invalid.text
    closed = await post(client, crm, path, {"stage_id": str(crm["stage2"].id)}, method="PATCH")
    assert closed.status_code == 200, closed.text
    assert closed.json()["actual_close_date"] and closed.json()["weighted_value"] == 500
    reopened = await client.post(
        "/api/v1" + path + "/move?stage_id=" + str(crm["stage"].id), headers=crm["headers"]
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["actual_close_date"] is None


@pytest.mark.parametrize(
    "schema,field",
    [
        ("TaskUpdate", "status"),
        ("TaskUpdate", "title"),
        ("LeadUpdate", "status"),
        ("DealUpdate", "stage_id"),
        ("DealUpdate", "value"),
    ],
)
def test_required_patch_fields_cannot_be_cleared(schema, field):
    from pydantic import ValidationError
    from app import schemas

    with pytest.raises(ValidationError):
        getattr(schemas, schema).model_validate({field: None})


async def test_task_create_completed_and_relation_patch(client, crm):
    created = await post(
        client,
        crm,
        "/tasks",
        {"title": "Already done", "status": "completed", "company_id": str(crm["company"].id)},
    )
    assert created.status_code == 201 and created.json()["completed_at"], created.text
    path = "/tasks/" + created.json()["id"]
    invalid = await post(client, crm, path, {"lead_id": str(uuid4())}, method="PATCH")
    assert invalid.status_code == 404, invalid.text
    unlinked = await post(client, crm, path, {"company_id": None}, method="PATCH")
    assert unlinked.status_code == 422, unlinked.text


@pytest.mark.parametrize('revoked_role', [RoleEnum.VIEWER, RoleEnum.SALES_MANAGER])
async def test_membership_writer_reloads_a_revoked_actor(db_session, crm, revoked_role):
    from sqlalchemy import update
    from fastapi import HTTPException
    from app.models import User
    from app.api.v1.users.router import membership_writer

    member = await db_session.scalar(
        select(Membership).where(
            Membership.tenant_id == crm["tenant"], Membership.user_id == crm["user"]
        )
    )
    user = await db_session.get(User, crm["user"])
    await db_session.execute(
        update(Membership)
        .where(Membership.id == member.id)
        .values(role=revoked_role)
        .execution_options(synchronize_session=False)
    )
    assert member.role == RoleEnum.OWNER  # An earlier authentication dependency is stale.
    with pytest.raises(HTTPException) as error:
        await membership_writer(db_session, crm["tenant"], (user, member))
    assert error.value.status_code == 403


async def test_import_review_persists_company_contact_lead_and_is_idempotent(
    client, db_session, crm
):
    from app.models import PendingLead, Activity

    pending = PendingLead(
        tenant_id=crm["tenant"],
        source="firecrawl",
        source_id="https://example.com/audit",
        email="import.audit@example.com",
        first_name="Imported",
        last_name="Person",
        company_name="Imported Company",
        raw_data={"url": "https://example.com/audit"},
    )
    db_session.add(pending)
    await db_session.commit()
    body = {
        "source": pending.source,
        "source_id": pending.source_id,
        "action": "approve",
        "lead_data": {},
    }
    result = await post(client, crm, "/leads/firecrawl/approve", body)
    assert result.status_code == 200, result.text
    lead_id = UUID(result.json()["lead_id"])
    lead = await db_session.get(Lead, lead_id)
    assert lead.company_id and lead.contact_id and lead.source == "other"
    activity = await db_session.scalar(select(Activity).where(Activity.lead_id == lead_id))
    assert activity.metadata_["source"] == "firecrawl"
    repeat = await post(client, crm, "/leads/firecrawl/approve", body)
    assert repeat.status_code == 200 and repeat.json()["lead_id"] == str(lead_id)
    reject = await post(client, crm, "/leads/firecrawl/approve", {**body, "action": "reject"})
    assert reject.status_code == 409


async def test_bulk_review_isolates_invalid_rows(client, db_session, crm):
    from app.models import PendingLead

    rows = [
        PendingLead(
            tenant_id=crm["tenant"],
            source="firecrawl",
            source_id=str(uuid4()),
            email=email,
            raw_data={},
        )
        for email in ("not-an-email", "valid.import@example.com")
    ]
    db_session.add_all(rows)
    await db_session.commit()
    result = await post(
        client,
        crm,
        "/leads/firecrawl/bulk-approve",
        {"lead_ids": [str(row.id) for row in rows], "action": "approve"},
    )
    assert result.status_code == 200, result.text
    assert result.json()["failed"] == 1 and result.json()["approved"] == 1
    assert "SQL" not in str(result.json()["errors"])

async def test_workspace_deletion_preserves_retained_records(client, db_session, crm):
    from app.models import Tenant, Contact
    response = await client.delete(f"/api/v1/tenants/{crm['tenant']}", headers=crm['headers'])
    assert response.status_code == 409, response.text
    assert await db_session.get(Tenant, crm['tenant']) is not None
    assert await db_session.get(Contact, crm['contact'].id) is not None

@pytest.mark.parametrize('resource,field', [('companies','name'), ('contacts','first_name')])
async def test_required_customer_fields_reject_null_at_api(client, crm, resource, field):
    identity = crm['company' if resource == 'companies' else 'contact'].id
    response = await post(client, crm, f'/{resource}/{identity}', {field: None}, method='PATCH')
    assert response.status_code == 422, response.text
    persisted = await client.get(f'/api/v1/{resource}/{identity}', headers=crm['headers'])
    assert persisted.status_code == 200 and persisted.json()[field] is not None


def test_partial_updates_preserve_required_model_and_response_contracts():
    from typing import get_args
    from pydantic import ValidationError
    import app.models as models
    import app.schemas as schemas

    for name in dir(schemas):
        if not name.endswith('Update'):
            continue
        patch = getattr(schemas, name)
        model = getattr(models, name[:-6], None)
        base = getattr(schemas, name[:-6] + 'Base', None)
        assert patch().model_dump(exclude_unset=True) == {}
        for key in patch.model_fields:
            column = getattr(getattr(model, '__table__', None), 'c', {}).get(key)
            response_field = base.model_fields.get(key) if base else None
            required = (column is not None and not column.nullable) or (
                response_field is not None and type(None) not in get_args(response_field.annotation)
            )
            if required:
                with pytest.raises(ValidationError):
                    patch.model_validate({key: None})
    assert schemas.ContactUpdate(phone=None).model_dump(exclude_unset=True) == {'phone': None}
    assert schemas.LeadUpdate(owner_id=None).model_dump(exclude_unset=True) == {'owner_id': None}
