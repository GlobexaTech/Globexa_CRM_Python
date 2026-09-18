"""Repair and enforce RLS for every tenant-owned table.

Revision ID: 008_reinforce_rls_coverage
Revises: 007_enable_rls
"""
from alembic import op

revision = "008_reinforce_rls_coverage"
down_revision = "007_enable_rls"
branch_labels = None
depends_on = None


_RLS_SQL = r"""
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
$$;

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT c.table_schema, c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema
         AND t.table_name = c.table_name
        WHERE c.column_name = 'tenant_id'
          AND t.table_type = 'BASE TABLE'
          AND c.table_schema = current_schema()
          AND c.table_name NOT IN ('users', 'tenants', 'memberships')
    LOOP
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', r.table_schema, r.table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', r.table_schema, r.table_name);

        EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I',
                       r.table_name || '_tenant_isolation', r.table_schema, r.table_name);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I',
                       r.table_name || '_tenant_insert', r.table_schema, r.table_name);

        EXECUTE format(
            'CREATE POLICY %I ON %I.%I AS RESTRICTIVE FOR ALL TO PUBLIC USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id())',
            r.table_name || '_tenant_isolation', r.table_schema, r.table_name
        );
    END LOOP;
END;
$$;
"""


def upgrade() -> None:
    # asyncpg prepares one SQL statement at a time. Keep PL/pgSQL bodies intact
    # while executing the function and the policy block separately.
    function_sql, policy_sql = _RLS_SQL.split("\nDO $$", 1)
    op.execute(function_sql)
    op.execute("DO $$" + policy_sql)


def downgrade() -> None:
    # Keep RLS enabled on tenant tables. A downgrade must never silently
    # remove tenant isolation. The migration is therefore intentionally
    # irreversible from a security perspective.
    pass
