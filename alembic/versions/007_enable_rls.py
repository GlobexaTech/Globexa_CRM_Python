"""Enable Row-Level Security (RLS) for multi-tenant isolation.

Revision ID: 007_enable_rls
Revises: 006_add_missing_enum_labels
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007_enable_rls'
down_revision = '006_add_missing_enum_labels'
branch_labels = None
depends_on = None


def _get_tenant_tables(connection) -> list:
    """Discover tables with tenant_id columns from the application metadata.
    
    Excludes global system tables that should not have RLS policies.
    """
    # Reflect the current schema to find all tables with tenant_id columns
    metadata = sa.MetaData()
    metadata.reflect(bind=connection, only=())
    
    tenant_tables = []
    for table_name, table in metadata.tables.items():
        # Skip global system tables
        if table_name in ('users', 'tenants', 'memberships'):
            continue
        # Check if table has a tenant_id column
        if any(c.name == 'tenant_id' for c in table.columns):
            tenant_tables.append(table_name)
    
    return sorted(tenant_tables)


def upgrade() -> None:
    # Discover tables with tenant_id columns
    connection = op.get_bind()
    tenant_tables = _get_tenant_tables(connection)
    
    # First, create a helper function to get the current tenant (for policies)
    op.execute("""CREATE OR REPLACE FUNCTION current_tenant_id()
    RETURNS uuid
    LANGUAGE plpgsql
    AS $$
    DECLARE
        tid uuid := '00000000-0000-0000-0000-000000000000'::uuid;
    BEGIN
        BEGIN
            tid := current_setting('app.current_tenant_id', true)::uuid;
        EXCEPTION WHEN others THEN
            tid := '00000000-0000-0000-0000-000000000000'::uuid;
        END;
        RETURN tid;
    END;
    $$""")
    
    # Enable RLS on each table and create policies
    for table in tenant_tables:
        # Enable RLS
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;')
        
        # Force RLS for table owners (so even table owners are subject to policies)
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY;')
        
        # Create USING policy (for SELECT, UPDATE, DELETE)
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (tenant_id = current_tenant_id())
        """)
        
        # Create WITH CHECK policy (for INSERT, UPDATE)
        op.execute(f"""
            CREATE POLICY {table}_tenant_insert ON {table}
            WITH CHECK (tenant_id = current_tenant_id())
        """)
    
    # Log the number of tables protected
    op.execute(f"""
        COMMENT ON FUNCTION current_tenant_id() IS 
        'Returns current tenant ID from session setting for RLS policies. '
        'Used for multi-tenant isolation in Globexa CRM. '
        ' {len(tenant_tables)} tables protected.'
    """)


def downgrade() -> None:
    # Discover tables with tenant_id columns
    connection = op.get_bind()
    tenant_tables = _get_tenant_tables(connection)
    
    # Drop policies and disable RLS
    for table in tenant_tables:
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};')
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_insert ON {table};')
        op.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;')
        op.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;')
    
    # Drop helper function
    op.execute('DROP FUNCTION IF EXISTS current_tenant_id();')