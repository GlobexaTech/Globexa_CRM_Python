"""
RLS Tenant Isolation Migration

Enable Row-Level Security on all tenant-owned tables and create policies
using app.current_tenant_id session-local configuration.
"""

from alembic import op
import sqlalchemy as sa

revision = '007_rls_tenant_isolation'
down_revision = '006_add_missing_enum_labels'
branch_labels = None
depends_on = None


# All tenant-owned tables (tables with tenant_id column)
TENANT_TABLES = [
    # Core tables
    'memberships',
    'subscriptions',
    'feature_entitlements',
    'usage_records',
    'audit_logs',
    'ai_usage_logs',
    # CRM tables
    'contacts',
    'companies',
    'leads',
    'deals',
    'pipelines',
    'stages',
    'tasks',
    'notes',
    'activities',
    'proposals',
    'proposal_templates',
    'products',
    # Campaign tables
    'campaigns',
    'campaign_audiences',
    'campaign_templates',
    'campaign_recipients',
    'campaign_sequences',
    'campaign_triggers',
    'campaign_stats',
    'email_events',
    'suppression_lists',
    'sending_domains',
    'email_provider_configs',
    # Integration tables
    'integrations',
    'integration_credentials',
    'webhook_endpoints',
    'integration_sync_logs',
    'lead_source_configs',
    # Attribution tables
    'touchpoints',
    'attribution_rules',
    'revenue_attributions',
    # AI tables
    'icp_profiles',
    'pending_leads',
]


def upgrade() -> None:
    # Enable RLS on all tenant tables
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;')
    
    # FORCE RLS on tables that should never be accessed without tenant context
    # (superuser bypass is not granted to application role)
    force_rls_tables = [
        'memberships',
        'subscriptions', 
        'feature_entitlements',
        'usage_records',
        'audit_logs',
        'ai_usage_logs',
        'contacts',
        'companies',
        'leads',
        'deals',
        'pipelines',
        'stages',
        'tasks',
        'notes',
        'activities',
        'proposals',
        'proposal_templates',
        'products',
        'campaigns',
        'campaign_audiences',
        'campaign_templates',
        'campaign_recipients',
        'campaign_sequences',
        'campaign_triggers',
        'campaign_stats',
        'email_events',
        'suppression_lists',
        'sending_domains',
        'email_provider_configs',
        'integrations',
        'integration_credentials',
        'webhook_endpoints',
        'integration_sync_logs',
        'lead_source_configs',
        'touchpoints',
        'attribution_rules',
        'revenue_attributions',
        'icp_profiles',
        'pending_leads',
    ]
    for table in force_rls_tables:
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY;')

    # Create tenant isolation policies for each table
    # Policy pattern: USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
    # WITH CHECK ensures INSERT/UPDATE also respect tenant isolation
    
    for table in TENANT_TABLES:
        policy_name = f'{table}_tenant_isolation'
        
        # USING policy - for SELECT, UPDATE, DELETE
        op.execute(f"""
            CREATE POLICY {policy_name}_using ON {table}
            USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
        """)
        
        # WITH CHECK policy - for INSERT, UPDATE
        op.execute(f"""
            CREATE POLICY {policy_name}_check ON {table}
            WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
        """)

    # Create the app.current_tenant_id GUC if it doesn't exist
    # This is a session-local configuration parameter
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_settings WHERE name = 'app.current_tenant_id'
            ) THEN
                -- Create the GUC by setting a custom class
                -- Note: In PostgreSQL, we don't need to explicitly create GUCs,
                -- current_setting() with a non-existent name returns empty string
                -- We just need to ensure it's set before queries
                NULL;
            END IF;
        END $$;
    """)

    # Create a helper function to set tenant context safely
    op.execute("""
        CREATE OR REPLACE FUNCTION set_tenant_context(tenant_id uuid)
        RETURNS void
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT set_config('app.current_tenant_id', tenant_id::text, true);
        $$;
    """)

    # Create a helper function to get current tenant context
    op.execute("""
        CREATE OR REPLACE FUNCTION get_tenant_context()
        RETURNS uuid
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid;
        $$;
    """)

    # Grant execute on helper functions to application role
    op.execute("GRANT EXECUTE ON FUNCTION set_tenant_context(uuid) TO PUBLIC;")
    op.execute("GRANT EXECUTE ON FUNCTION get_tenant_context() TO PUBLIC;")


def downgrade() -> None:
    # Drop policies in reverse order
    for table in reversed(TENANT_TABLES):
        policy_name = f'{table}_tenant_isolation'
        op.execute(f'DROP POLICY IF EXISTS {policy_name}_using ON {table};')
        op.execute(f'DROP POLICY IF EXISTS {policy_name}_check ON {table};')
    
    # Drop helper functions
    op.execute('DROP FUNCTION IF EXISTS set_tenant_context(uuid);')
    op.execute('DROP FUNCTION IF EXISTS get_tenant_context();')
    
    # Disable RLS
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;')