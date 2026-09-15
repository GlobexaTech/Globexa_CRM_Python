"""Enable Row-Level Security (RLS) for multi-tenant isolation.

Revision ID: 007_enable_rls
Revises: 006_add_missing_enum_labels
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa

revision = "007_enable_rls"
down_revision = "006_add_missing_enum_labels"
branch_labels = None
depends_on = None

_GLOBAL_TABLES = {"users", "tenants", "memberships"}


def _get_tenant_tables(connection) -> list[str]:
    """Discover existing application tables that contain tenant_id."""
    metadata = sa.MetaData()
    # Reflect the actual current schema. ``only=()`` reflects nothing and
    # therefore silently produced an empty RLS migration on fresh installs.
    metadata.reflect(bind=connection)
    return sorted(
        table.name
        for table in metadata.tables.values()
        if table.name not in _GLOBAL_TABLES
        and any(column.name == "tenant_id" for column in table.columns)
    )


def _quote_identifier(connection, identifier: str) -> str:
    return connection.dialect.identifier_preparer.quote(identifier)


def upgrade() -> None:
    connection = op.get_bind()
    tenant_tables = _get_tenant_tables(connection)

    op.execute("""
        CREATE OR REPLACE FUNCTION current_tenant_id()
        RETURNS uuid
        LANGUAGE plpgsql
        STABLE
        SET search_path = pg_catalog
        AS $$
        DECLARE
            raw_tid text;
        BEGIN
            raw_tid := current_setting('app.current_tenant_id', true);
            IF raw_tid IS NULL OR raw_tid = '' THEN
                RETURN NULL;
            END IF;
            BEGIN
                RETURN raw_tid::uuid;
            EXCEPTION WHEN invalid_text_representation THEN
                RETURN NULL;
            END;
        END;
        $$
    """)

    for table in tenant_tables:
        qtable = _quote_identifier(connection, table)
        isolation_policy = _quote_identifier(connection, f"{table}_tenant_isolation")
        insert_policy = _quote_identifier(connection, f"{table}_tenant_insert")

        op.execute(f"ALTER TABLE {qtable} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {qtable} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {isolation_policy} ON {qtable}")
        op.execute(f"DROP POLICY IF EXISTS {insert_policy} ON {qtable}")
        op.execute(f"""
            CREATE POLICY {isolation_policy} ON {qtable}
            AS RESTRICTIVE FOR ALL TO PUBLIC
            USING (tenant_id = current_tenant_id())
            WITH CHECK (tenant_id = current_tenant_id())
        """)

    op.execute(f"""
        COMMENT ON FUNCTION current_tenant_id() IS
        'Returns the transaction-local current tenant UUID for Globexa CRM RLS. {len(tenant_tables)} tables protected by migration 007.'
    """)


def downgrade() -> None:
    # Security migration is intentionally not reversible: silently disabling
    # RLS during a downgrade could expose tenant data.
    pass
