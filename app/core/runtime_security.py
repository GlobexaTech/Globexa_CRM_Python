"""Fail production startup/worker access closed when the database can bypass isolation."""
from sqlalchemy import text


async def verify_runtime_security(connection):
    from app.models import Base
    unsafe = await connection.scalar(text(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user"))
    if unsafe:
        raise RuntimeError("Runtime role must not be SUPERUSER or BYPASSRLS")
    expected = {table.name for table in Base.metadata.tables.values() if "tenant_id" in table.c}
    expected.update({"users", "tenants"})
    rows = await connection.execute(text(
        "SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace "
        "AND relkind='r' AND relrowsecurity AND relforcerowsecurity"))
    if not expected.issubset({row[0] for row in rows}):
        raise RuntimeError("Tenant security migrations are incomplete")
