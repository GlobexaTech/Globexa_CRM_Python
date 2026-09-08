"""Run as migration administrator after upgrade; reads the runtime password from env."""
import os
from sqlalchemy import create_engine, text
from app.core.config import get_settings


def provision():
    engine = create_engine(get_settings().database.sync_url)
    role = os.environ.get("RUNTIME_DATABASE_ROLE", "globexa_runtime")
    password = os.environ["RUNTIME_DATABASE_PASSWORD"]
    if not role.replace("_", "").isalnum() or role == "postgres":
        raise ValueError("Invalid runtime role")
    with engine.begin() as db:
        quote = db.dialect.identifier_preparer.quote(role)
        if not db.scalar(text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}):
            db.exec_driver_sql(f"CREATE ROLE {quote} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT")
        # psycopg2 supplies correct SQL literal quoting; never put credentials in logs.
        from psycopg2.extensions import adapt
        literal = adapt(password).getquoted().decode()
        db.exec_driver_sql(f"ALTER ROLE {quote} PASSWORD {literal}")
        db.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {quote}")
        db.exec_driver_sql(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {quote}")
        db.exec_driver_sql(f"REVOKE ALL ON alembic_version FROM {quote}")
        db.exec_driver_sql(f"REVOKE SELECT, UPDATE, DELETE ON security_events FROM {quote}")
        db.exec_driver_sql(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {quote}")
        db.exec_driver_sql(f"REVOKE INSERT, UPDATE, DELETE ON plans, features, plan_features FROM {quote}")
        db.exec_driver_sql(f"REVOKE UPDATE, DELETE ON audit_logs FROM {quote}")
        for signature in ("auth_lookup_user(text)", "tenant_slug_exists(text)", "lookup_webhook(uuid)", "active_tenant_ids()"):
            db.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION public.{signature} TO {quote}")
    engine.dispose()
    print("Restricted runtime role provisioned")


if __name__ == "__main__":
    provision()
