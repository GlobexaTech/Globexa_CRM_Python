"""Seed isolated E2E data. Never run this script against production data.

Run as the migration administrator with APP_ENVIRONMENT=testing and a database
named globexa_cp4*. --bootstrap creates the database (only if missing), applies
real migrations and provisions the restricted runtime role. Every run seeds new
tenant IDs; no customer data is deleted. Credentials live only in ignored evidence.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def require_test_database():
    if os.environ.get("APP_ENVIRONMENT") != "testing":
        raise RuntimeError("E2E fixtures require APP_ENVIRONMENT=testing")
    name = os.environ.get("DATABASE_NAME", "")
    if not name.startswith("globexa_cp4") or not name.replace("_", "").isalnum():
        raise RuntimeError("E2E fixtures require a dedicated globexa_cp4 database")


async def seed():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.config import get_settings
    from app.core.security import hash_password
    from app.models import (
        Tenant, User, Membership, RoleEnum, Subscription, FeatureEntitlement,
        Company, Contact, Lead, Pipeline, Stage, Deal, Task, Note, Activity,
        Integration, OAuthToken, Conversation, Message, Participant, Campaign,
    )

    run = uuid4().hex[:10]
    engine = create_async_engine(get_settings().database.url)
    fixture = {
        "run": run,
        "origin": os.environ.get("APP_ORIGIN", "http://127.0.0.1:3254"),
        "backend": os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8004"),
        "users": {}, "records": {},
    }
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        tenant_a = Tenant(name="Globexa Alpha E2E", slug="cp4-alpha-" + run)
        tenant_b = Tenant(name="Globexa Beta E2E", slug="cp4-beta-" + run)
        db.add_all([tenant_a, tenant_b])
        users = {}
        for role in RoleEnum:
            password = secrets.token_urlsafe(24)
            user = User(email=f"{role.value}.{run}@example.com", full_name=f"E2E {role.value.replace('_', ' ').title()}", hashed_password=hash_password(password), is_active=True, email_verified=True)
            db.add(user)
            users[role.value] = user
            fixture["users"][role.value] = {"email": user.email, "password": password}
        await db.flush()
        fixture["tenantA"], fixture["tenantB"] = str(tenant_a.id), str(tenant_b.id)
        for role, user in users.items():
            fixture["users"][role]["id"] = str(user.id)
            db.add(Membership(tenant_id=tenant_a.id, user_id=user.id, role=role, is_default=True))
        owner = users["owner"]
        db.add(Membership(tenant_id=tenant_b.id, user_id=owner.id, role="owner", is_default=False))
        await db.flush()
        for key, tenant, label in [("tenantA", tenant_a, "Alpha"), ("tenantB", tenant_b, "Beta")]:
            db.add(Subscription(tenant_id=tenant.id, package="enterprise", status="active"))
            for feature in ["automation", "ai_credits", "messages", "campaigns", "integrations", "users", "storage"]:
                db.add(FeatureEntitlement(tenant_id=tenant.id, feature_key=feature, enabled=True, limit_value=10000))
            company = Company(tenant_id=tenant.id, name=f"{label} Customer {run}", industry="Software", website="https://example.test")
            pipeline = Pipeline(tenant_id=tenant.id, name=f"{label} Sales", is_default=True)
            integration = Integration(tenant_id=tenant.id, name=f"{label} Gmail test adapter", type="email_inbox", status="connected", created_by_id=owner.id, config={"provider": "gmail"}, sync_enabled=False)
            db.add_all([company, pipeline, integration])
            await db.flush()
            contact = Contact(tenant_id=tenant.id, company_id=company.id, first_name=label, last_name="Customer", email=f"{label.lower()}.{run}@example.com", created_by_id=owner.id)
            stages = [Stage(tenant_id=tenant.id, pipeline_id=pipeline.id, name=name, order=index) for index, name in enumerate(["New", "Qualified", "Proposal", "Won"])]
            db.add_all([contact, *stages])
            await db.flush()
            lead = Lead(tenant_id=tenant.id, title=f"{label} verified lead {run}", contact_id=contact.id, company_id=company.id, owner_id=owner.id, created_by_id=owner.id, status="new", source="manual")
            db.add(lead)
            await db.flush()
            deal = Deal(tenant_id=tenant.id, title=f"{label} discovery deal", lead_id=lead.id, contact_id=contact.id, company_id=company.id, pipeline_id=pipeline.id, stage_id=stages[0].id, value=2500, currency="USD", owner_id=owner.id, created_by_id=owner.id)
            task = Task(tenant_id=tenant.id, title=f"{label} follow-up", lead_id=lead.id, contact_id=contact.id, company_id=company.id, owner_id=owner.id, created_by_id=owner.id, due_date=datetime.now(timezone.utc) + timedelta(days=1))
            note = Note(tenant_id=tenant.id, content=f"{label} verified customer requirements", lead_id=lead.id, contact_id=contact.id, company_id=company.id, author_id=owner.id)
            activity = Activity(tenant_id=tenant.id, subject=f"{label} discovery call", type="call", lead_id=lead.id, contact_id=contact.id, user_id=owner.id)
            conversation = Conversation(tenant_id=tenant.id, subject=f"{label} customer conversation", contact_id=contact.id, company_id=company.id, lead_id=lead.id, integration_id=integration.id, channel="email", last_message_at=datetime.now(timezone.utc), unread_count=1)
            campaign = Campaign(tenant_id=tenant.id, name=f"{label} draft campaign", type="broadcast", sender_name="Globexa E2E", sender_email="sender@example.com", created_by_id=owner.id)
            token = OAuthToken(tenant_id=tenant.id, integration_id=integration.id, access_token=secrets.token_urlsafe(30), refresh_token=secrets.token_urlsafe(30), expires_at=datetime.now(timezone.utc) + timedelta(hours=3))
            db.add_all([deal, task, note, activity, conversation, campaign, token])
            await db.flush()
            message = Message(tenant_id=tenant.id, conversation_id=conversation.id, body=f"{label} asks for a discovery meeting.", direction="inbound", status="received", sender=contact.email, recipient="sender@example.com", provider_message_id="seed-" + run + label, idempotency_key="seed-" + run + label)
            db.add_all([message, Participant(tenant_id=tenant.id, conversation_id=conversation.id, address=contact.email, name=f"{label} Customer")])
            await db.flush()
            fixture["records"][key] = {name: str(entity.id) for name, entity in {"company": company, "contact": contact, "lead": lead, "pipeline": pipeline, "stage": stages[0], "stage2": stages[1], "stage3": stages[2], "stage4": stages[3], "deal": deal, "task": task, "note": note, "activity": activity, "conversation": conversation, "message": message, "campaign": campaign, "integration": integration}.items()}
            fixture["records"][key]["leadTitle"] = lead.title
            fixture["records"][key]["contactEmail"] = contact.email
        await db.commit()
    await engine.dispose()
    return fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args()
    require_test_database()
    os.chdir(ROOT)
    previous_file = ROOT / "evidence" / "runtime.env.json"
    if previous_file.exists():
        previous = json.loads(previous_file.read_text(encoding="utf-8"))
        if previous.get("DATABASE_NAME") == os.environ["DATABASE_NAME"]:
            # Re-seeding this isolated database keeps existing encrypted records
            # and running browser/server sessions readable. Explicit env wins.
            for key in ("SECURITY_SECRET_KEY", "SECURITY_CREDENTIAL_ENCRYPTION_KEY", "SESSION_ENCRYPTION_KEY"):
                os.environ.setdefault(key, previous[key])
            os.environ.setdefault("RUNTIME_DATABASE_PASSWORD", previous["DATABASE_PASSWORD"])
            os.environ.setdefault("RUNTIME_DATABASE_ROLE", previous["DATABASE_USERNAME"])
    from cryptography.fernet import Fernet
    os.environ.setdefault("SECURITY_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    os.environ.setdefault("SECURITY_SECRET_KEY", secrets.token_hex(32))
    os.environ.setdefault("RUNTIME_DATABASE_PASSWORD", secrets.token_urlsafe(32))
    os.environ.setdefault("RUNTIME_DATABASE_ROLE", "globexa_cp4_runtime")
    os.environ.setdefault("SESSION_ENCRYPTION_KEY", secrets.token_hex(32))
    from app.core.config import get_settings
    settings = get_settings()
    if args.bootstrap:
        import psycopg2
        from psycopg2 import sql
        conn = psycopg2.connect(host=settings.database.host, port=settings.database.port, user=settings.database.username, password=settings.database.password, dbname="postgres")
        try:
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_database WHERE datname=%s", (settings.database.name,))
                if cursor.fetchone() is None:
                    cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.database.name)))
        finally:
            conn.close()
        from alembic import command
        from alembic.config import Config
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        from scripts.provision_runtime import provision
        provision()
    fixture = asyncio.run(seed())
    directory = ROOT / "evidence"
    directory.mkdir(exist_ok=True)
    (directory / "fixture.json").write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    runtime = {
        "APP_ENVIRONMENT": "testing", "APP_DEBUG": "false", "DATABASE_HOST": settings.database.host,
        "DATABASE_PORT": str(settings.database.port), "DATABASE_NAME": settings.database.name,
        "DATABASE_USERNAME": os.environ["RUNTIME_DATABASE_ROLE"], "DATABASE_PASSWORD": os.environ["RUNTIME_DATABASE_PASSWORD"],
        "REDIS_HOST": os.environ.get("REDIS_HOST", "127.0.0.1"), "REDIS_PORT": os.environ.get("REDIS_PORT", "6379"),
        "REDIS_DB": "10", "CELERY_BROKER_URL": os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/11"),
        "CELERY_RESULT_BACKEND": os.environ.get("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/12"),
        "SECURITY_SECRET_KEY": os.environ["SECURITY_SECRET_KEY"], "SECURITY_CREDENTIAL_ENCRYPTION_KEY": os.environ["SECURITY_CREDENTIAL_ENCRYPTION_KEY"],
        "SECURITY_ACCESS_TOKEN_EXPIRE_MINUTES": str(30), "SESSION_ENCRYPTION_KEY": os.environ["SESSION_ENCRYPTION_KEY"],
        "FRONTEND_REDIS_URL": os.environ.get("FRONTEND_REDIS_URL", "redis://127.0.0.1:6379/13"),
        "APP_ORIGIN": fixture["origin"], "BACKEND_API_URL": fixture["backend"], "FRONTEND_ENV": "testing",
        "CRM_PUBLIC_BASE_URL": "https://crm.example.test", "CRM_GMAIL_CLIENT_ID": "cp4-test-adapter",
        "CRM_GMAIL_CLIENT_SECRET": secrets.token_urlsafe(24), "CRM_GMAIL_REDIRECT_URI": fixture["origin"] + "/integrations/callback",
    }
    (directory / "runtime.env.json").write_text(json.dumps(runtime, indent=2), encoding="utf-8")
    for name in ("fixture.json", "runtime.env.json"):
        (directory / name).chmod(0o600)
    print("Checkpoint 4 fixture seeded: two tenants, seven roles, relational CRM, encrypted provider credentials.")
    print("Private test settings written to ignored evidence/fixture.json and evidence/runtime.env.json.")


if __name__ == "__main__":
    main()
