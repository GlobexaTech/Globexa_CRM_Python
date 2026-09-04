"""PostgreSQL Row-Level Security for tenant isolation

Revision ID: 007_rls_tenant_isolation
Revises: 006_add_missing_enum_labels
Create Date: 2024-08-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007_rls_tenant_isolation'
down_revision = '006_add_missing_enum_labels'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create function to get current tenant context
    op.execute("""
        CREATE OR REPLACE FUNCTION get_current_tenant_id()
        RETURNS uuid LANGUAGE sql STABLE AS $$
            SELECT current_setting('app.current_tenant_id', true)::uuid
        $$;
    """)

    # Create function to set tenant context
    op.execute("""
        CREATE OR REPLACE FUNCTION set_current_tenant_id(tenant_id uuid)
        RETURNS void LANGUAGE sql AS $$
            SELECT set_config('app.current_tenant_id', tenant_id::text, true);
        $$;
    """)

    # Create function to clear tenant context
    op.execute("""
        CREATE OR REPLACE FUNCTION clear_current_tenant_id()
        RETURNS void LANGUAGE sql AS $$
            SELECT set_config('app.current_tenant_id', '', true);
        $$;
    """)

    # Enable RLS and create policies for all tenant-scoped tables
    
    # Core CRM tables
    for table in ['companies', 'contacts', 'leads', 'pipelines', 'stages', 'deals', 
                  'tasks', 'notes', 'activities', 'proposals', 'proposal_templates', 'products']:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            
            CREATE POLICY {table}_tenant_isolation ON {table}
                USING (tenant_id = get_current_tenant_id())
                WITH CHECK (tenant_id = get_current_tenant_id());
        """)

    # Campaign tables
    for table in ['campaigns', 'campaign_audiences', 'campaign_templates', 'campaign_recipients',
                  'campaign_sequences', 'campaign_triggers', 'campaign_stats', 'email_events',
                  'suppression_lists', 'sending_domains', 'email_provider_configs']:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            
            CREATE POLICY {table}_tenant_isolation ON {table}
                USING (tenant_id = get_current_tenant_id())
                WITH CHECK (tenant_id = get_current_tenant_id());
        """)

    # Integration tables
    for table in ['integrations', 'integration_credentials', 'webhook_endpoints', 
                  'integration_sync_logs', 'lead_source_configs']:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            
            CREATE POLICY {table}_tenant_isolation ON {table}
                USING (tenant_id = get_current_tenant_id())
                WITH CHECK (tenant_id = get_current_tenant_id());
        """)

    # Attribution tables
    for table in ['touchpoints', 'attribution_rules', 'revenue_attributions']:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            
            CREATE POLICY {table}_tenant_isolation ON {table}
                USING (tenant_id = get_current_tenant_id())
                WITH CHECK (tenant_id = get_current_tenant_id());
        """)

    # AI/Lead Miner tables
    for table in ['icp_profiles', 'pending_leads']:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            
            CREATE POLICY {table}_tenant_isolation ON {table}
                USING (tenant_id = get_current_tenant_id())
                WITH CHECK (tenant_id = get_current_tenant_id());
        """)

    # Revenue attribution
    op.execute("""
        ALTER TABLE revenue_attributions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE revenue_attributions FORCE ROW LEVEL SECURITY;
        
        CREATE POLICY revenue_attributions_tenant_isolation ON revenue_attributions
            USING (tenant_id = get_current_tenant_id())
            WITH CHECK (tenant_id = get_current_tenant_id());
    """)

    # Email events
    op.execute("""
        ALTER TABLE email_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE email_events FORCE ROW LEVEL SECURITY;
        
        CREATE POLICY email_events_tenant_isolation ON email_events
            USING (tenant_id = get_current_tenant_id())
            WITH CHECK (tenant_id = get_current_tenant_id());
    """)

    # Suppression lists
    op.execute("""
        ALTER TABLE suppression_lists ENABLE ROW LEVEL SECURITY;
        ALTER TABLE suppression_lists FORCE ROW LEVEL SECURITY;
        
        CREATE POLICY suppression_lists_tenant_isolation ON suppression_lists
            USING (tenant_id = get_current_tenant_id())
            WITH CHECK (tenant_id = get_current_tenant_id());
    """)

    # Sending domains
    op.execute("""
        ALTER TABLE sending_domains ENABLE ROW LEVEL SECURITY;
        ALTER TABLE sending_domains FORCE ROW LEVEL SECURITY;
        
        CREATE POLICY sending_domains_tenant_isolation ON sending_domains
            USING (tenant_id = get_current_tenant_id())
            WITH CHECK (tenant_id = get_current_tenant_id());
    """)

    # Email provider configs
    op.execute("""
        ALTER TABLE email_provider_configs ENABLE ROW LEVEL SECURITY;
        ALTER TABLE email_provider_configs FORCE ROW LEVEL SECURITY;
        
        CREATE POLICY email_provider_configs_tenant_isolation ON email_provider_configs
            USING (tenant_id = get_current_tenant_id())
            WITH CHECK (tenant_id = get_current_tenant_id());
    """)

    # Email events - already covered above

    # User/Membership tables - special handling
    # Users are global, but membership is tenant-scoped
    op.execute("""
        ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
        ALTER TABLE memberships FORCE ROW LEVEL SECURITY;
        
        CREATE POLICY memberships_tenant_isolation ON memberships
            USING (tenant_id = get_current_tenant_id())
            WITH CHECK (tenant_id = get_current_tenant_id());
    """)

    # Users are global - no RLS needed (they belong to multiple tenants via memberships)
    # Tenants table is global - no RLS needed (root of hierarchy)

    # Create index on tenant_id for performance where not already present
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_memberships_tenant_user ON memberships (tenant_id, user_id);
    """)


def downgrade() -> None:
    # Drop policies and disable RLS
    tables = [
        'companies', 'contacts', 'leads', 'pipelines', 'stages', 'deals', 
        'tasks', 'notes', 'activities', 'proposals', 'proposal_templates', 'products',
        'campaigns', 'campaign_audiences', 'campaign_templates', 'campaign_recipients',
        'campaign_sequences', 'campaign_triggers', 'campaign_stats', 'email_events',
        'suppression_lists', 'sending_domains', 'email_provider_configs',
        'integrations', 'integration_credentials', 'webhook_endpoints', 
        'integration_sync_logs', 'lead_source_configs',
        'touchpoints', 'attribution_rules', 'revenue_attributions',
        'icp_profiles', 'pending_leads', 'revenue_attributions',
        'email_events', 'suppression_lists', 'sending_domains', 
        'email_provider_configs', 'memberships'
    ]
    
    for table in tables:
        op.execute(f"""
            DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};
            ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
        """)

    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS get_current_tenant_id();")
    op.execute("DROP FUNCTION IF EXISTS set_current_tenant_id(uuid);")
    op.execute("DROP FUNCTION IF EXISTS clear_current_tenant_id();")