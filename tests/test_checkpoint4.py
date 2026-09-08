"""UI integration gaps exercised against migrated PostgreSQL and tenant/RBAC guards."""
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from app.models import Membership, RoleEnum, OperationJob, Campaign, CampaignStatusEnum, CampaignTypeEnum
from app.core.rbac import get_role_permissions
from app.services.crm.common import public_job
from test_checkpoint3 import crm as crm, post, dispatch_all


@pytest.mark.parametrize("role", list(RoleEnum))
async def test_effective_permissions_match_live_membership(client, crm, db_session, role):
    member = await db_session.scalar(select(Membership).where(Membership.tenant_id == crm["tenant"], Membership.user_id == crm["user"]))
    member.role = role
    await db_session.flush()
    response = await client.get("/api/v1/auth/permissions", headers=crm["headers"])
    assert response.status_code == 200
    assert response.json() == {"permissions": sorted(get_role_permissions(role))}


async def test_pipeline_crud_and_atomic_stage_order(client, crm):
    response = await post(client, crm, "/deals/pipelines", {"name": "UI pipeline"})
    assert response.status_code == 201, response.text
    pipeline = response.json()["id"]
    assert response.json()["stages"] == []
    ids = []
    for index in range(3):
        response = await post(client, crm, f"/deals/pipelines/{pipeline}/stages", {"pipeline_id":pipeline,"name":f"Step {index}","order":index})
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    response = await post(client, crm, f"/deals/pipelines/{pipeline}/stages/order", {"stage_ids":ids[::-1]}, method="PUT")
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()] == ids[::-1]
    assert [row["order"] for row in response.json()] == [0,1,2]
    duplicate = await post(client, crm, f"/deals/pipelines/{pipeline}/stages/order", {"stage_ids":[ids[0]]*3}, method="PUT")
    assert duplicate.status_code == 422
    invalid = await post(client, crm, f"/deals/pipelines/{pipeline}/stages/order", {"stage_ids":[str(uuid4()),*ids[1:]]}, method="PUT")
    assert invalid.status_code == 422
    read = await client.get(f"/api/v1/deals/pipelines/{pipeline}", headers=crm["headers"])
    assert sorted(read.json()["stages"], key=lambda row:row["order"])[0]["id"] == ids[-1]
    updated = await post(client, crm, f"/deals/pipelines/{pipeline}", {"name":"Renamed pipeline"}, method="PATCH")
    assert updated.status_code == 200 and len(updated.json()["stages"]) == 3


async def test_pipeline_stage_url_binding_and_management_permission(client, crm, db_session):
    response = await post(client, crm, f'/deals/pipelines/{crm["pipeline"].id}/stages', {"pipeline_id":str(uuid4()),"name":"Wrong pipeline","order":8})
    assert response.status_code == 422
    member = await db_session.scalar(select(Membership).where(Membership.user_id == crm["user"], Membership.tenant_id == crm["tenant"]))
    member.role = RoleEnum.SALES_EXECUTIVE
    await db_session.flush()
    response = await post(client, crm, "/deals/pipelines", {"name":"Forbidden"})
    assert response.status_code == 403
    response = await post(client, crm, f'/deals/pipelines/{crm["pipeline"].id}/stages/order', {"stage_ids":[str(crm["stage"].id),str(crm["stage2"].id)]}, method="PUT")
    assert response.status_code == 403


async def test_related_entity_writes_and_deal_move_serialize_without_lazy_io(client, crm):
    contact = await post(client, crm, "/contacts", {"first_name":"Linked","last_name":"Contact","company_id":str(crm["company"].id),"email":"linked@example.com"})
    assert contact.status_code == 201, contact.text
    lead = await post(client, crm, "/leads", {"title":"Linked lead","contact_id":contact.json()["id"],"company_id":str(crm["company"].id),"owner_id":str(crm["user"])})
    assert lead.status_code == 201, lead.text
    update = await post(client, crm, "/leads/"+lead.json()["id"], {"status":"qualified"}, method="PATCH")
    assert update.status_code == 200 and update.json()["status"] == "qualified"
    deal = await post(client, crm, "/deals", {"title":"Linked deal","pipeline_id":str(crm["pipeline"].id),"stage_id":str(crm["stage"].id),"contact_id":contact.json()["id"],"lead_id":lead.json()["id"],"owner_id":str(crm["user"]),"value":10000})
    assert deal.status_code == 201, deal.text
    moved = await post(client, crm, f'/deals/{deal.json()["id"]}/move?stage_id={crm["stage2"].id}')
    assert moved.status_code == 200, moved.text
    assert moved.json()["stage_id"] == str(crm["stage2"].id)


async def test_sync_history_paginates_real_query(client, crm):
    response = await client.get(f'/api/v1/integrations/{crm["integration"].id}/sync-logs?page=1&page_size=5', headers=crm["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [] and response.json()["total"] == 0


async def test_workflow_execution_exposes_its_job_without_payload(client, crm, db_session):
    workflow = await post(client, crm, "/operations/workflows", {"name":"Linked execution","trigger":"lead.created","actions":[{"tool":"create_task","arguments":{"title":"Follow up","lead_id":"$event.id"}}]})
    assert workflow.status_code == 201, workflow.text
    enabled = await post(client, crm, f'/operations/workflows/{workflow.json()["id"]}/enabled', {"enabled":True}, method="PATCH")
    assert enabled.status_code == 200, enabled.text
    lead = await post(client, crm, "/leads", {"title":"Trigger execution"})
    assert lead.status_code == 201
    await dispatch_all(db_session, crm["tenant"])
    logs = await client.get(f'/api/v1/operations/workflows/{workflow.json()["id"]}/executions', headers=crm["headers"])
    assert logs.status_code == 200, logs.text
    assert logs.json()["total"] >= 1
    for item in logs.json()["items"]:
        assert item["job_id"]
        job = await db_session.get(OperationJob, UUID(item["job_id"]))
        assert job.tenant_id == crm["tenant"] and job.payload["execution_id"] == item["id"]
        assert "payload" not in item


def test_hook_review_exposes_only_safe_target_fields():
    job = OperationJob(id=uuid4(),kind="ai_hook",status="awaiting_approval",attempts=0,result={},payload={"capability":"lead_score","entity_type":"leads","entity_id":str(uuid4()),"private":"sensitive"})
    result = public_job(job)
    assert set(result["result"]["suggestion"]) == {"capability","entity_type","entity_id"}
    assert "private" not in str(result)


async def test_search_relations_navigate_to_tenant_customer(client, crm):
    response = await client.get("/api/v1/operations/search?q=Alice&entity=contacts", headers=crm["headers"])
    assert response.status_code == 200
    assert response.json()["items"][0]["company_id"] == str(crm["company"].id)


async def test_unknown_campaign_deliveries_remain_explicit(client, crm, db_session):
    campaign = Campaign(tenant_id=crm["tenant"],name="Ambiguous delivery",type=CampaignTypeEnum.BROADCAST,status=CampaignStatusEnum.SENDING,sender_name="CRM",sender_email="crm@example.com",created_by_id=crm["user"])
    db_session.add(campaign)
    await db_session.flush()
    db_session.add(OperationJob(tenant_id=crm["tenant"],actor_id=crm["user"],kind="campaign_send",status="unknown",idempotency_key="cp4-unknown-delivery",payload={"campaign_id":str(campaign.id)}))
    await db_session.flush()
    response = await client.get(f"/api/v1/operations/campaigns/{campaign.id}/statistics",headers=crm["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["unknown"] == 1
    assert response.json()["status"] == "running"


async def test_response_validation_does_not_expose_model_inputs(client, crm, db_session, test_user, caplog):
    test_user.email = "private-invalid-email-input"
    await db_session.flush()
    response = await client.get("/api/v1/auth/me", headers=crm["headers"])
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "private-invalid-email-input" not in caplog.text


async def test_team_role_edit_returns_complete_membership(client, crm):
    created = await post(client, crm, "/users", {"full_name":"Team Member","email":"new-member@example.com","password":uuid4().hex,"role":"viewer"})
    assert created.status_code == 201, created.text
    response = await post(client, crm, f'/users/{created.json()["id"]}/memberships', {"role":"marketing"}, method="PATCH")
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "marketing"
    assert response.json()["user"]["id"] == created.json()["id"]
    assert response.json()["tenant_id"] == str(crm["tenant"])


async def test_note_written_by_other_member_can_be_reviewed_by_admin(client, crm):
    from app.core.security import create_access_token
    created = await post(client, crm, "/users", {"full_name":"Note Author","email":"note-author@example.com","password":uuid4().hex,"role":"admin"})
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    token = create_access_token({"sub":user_id,"tenant_id":str(crm["tenant"]),"role":"admin","email":"note-author@example.com"})
    note = await client.post("/api/v1/notes",headers={"Authorization":"Bearer "+token,"X-Tenant-ID":str(crm["tenant"])},json={"content":"Review this note","contact_id":str(crm["contact"].id)})
    assert note.status_code == 201, note.text
    response = await post(client, crm, f'/notes/{note.json()["id"]}', {"content":"Reviewed by owner"}, method="PATCH")
    assert response.status_code == 200, response.text
    assert response.json()["content"] == "Reviewed by owner"
    assert response.json()["author"]["id"] == user_id


async def test_workspace_plan_serializes_entitlement_metadata(client, crm):
    response = await client.get("/api/v1/tenants/me", headers=crm["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["subscription"]["package"] == "starter"
    assert len(response.json()["feature_entitlements"]) == 7
    assert all(isinstance(row["metadata"], dict) for row in response.json()["feature_entitlements"])
