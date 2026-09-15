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


def upgrade() -> None:
    # Only tables with tenant_id column should have RLS policies
    # EXCLUDED: users (global), tenants (global), memberships (join table with dual FK)
    tenant_tables = [
        'subscriptions',
        'feature_entitlements',
        'usage_records',
        'audit_logs',
        'ai_usage_logs',
        'companies',
        'contacts',
        'leads',
        'pipelines',
        'stages',
        'deals',
        'tasks',
        'notes',
        'activities',
        'proposals',
        'campaigns',
        'campaign_recipients',
        'email_templates',
        'integrations',
        'integration_field_mappings',
        'webhooks',
        'sync_logs',
    ]

    # First, create a helper function to get the current tenant (for policies)
    op.execute("""
        CREATE OR REPLACE FUNCTION current_tenant_id()
        RETURNS uuid AS $$
        BEGIN
            RETURN current_setting('app.current_tenant_id')::uuid;
        EXCEPTION WHEN others THEN
            RETURN '00000000-0000-0000-0000-000000000000'::uuid;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)

    # Enable RLS on each table and create policies
    for table in tenant_tables:
        # Enable RLS
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;')
        
        # Force RLS for table owners (so even table owners are subject to policies)
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY;')

        # Create USING policy (for SELECT, UPDATE, DELETE)
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (tenant_id = current_tenant_id());
        """)

        # Create WITH CHECK policy (for INSERT, UPDATE)
        op.execute(f"""
            CREATE POLICY {table}_tenant_insert ON {table}
            WITH CHECK (tenant_id = current_tenant_id());
        """)


def downgrade() -> None:
    # Drop policies and disable RLS
    tenant_tables = [
        'subscriptions',
        'feature_entitlements',
        'usage_records',
        'audit_logs',
        'ai_usage_logs',
        'companies',
        'contacts',
        'leads',
        'pipelines',
        'stages',
        'deals',
        'tasks',
        'notes',
        'activities',
        'proposals',
        'campaigns',
        'campaign_recipients',
        'email_templates',
        'integrations',
        'integration_field_mappings',
        'webhooks',
        'sync_logs',
    ]

    for table in tenant_tables:
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};')
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_insert ON {table};')
        op.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;')
        op.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;')

    # Drop helper function
    op.execute('DROP FUNCTION IF EXISTS current_tenant_id();')