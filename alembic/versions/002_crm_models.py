"""Phase 2: CRM models - contacts, companies, leads, deals, pipelines, stages, tasks, notes, activities, proposals

Revision ID: 002_crm_models
Revises: 001_initial_schema
Create Date: 2024-08-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_crm_models'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types using raw SQL with IF NOT EXISTS to avoid duplicate errors
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE lead_source_enum AS ENUM (
                'website', 'meta_lead_ads', 'facebook', 'instagram', 'linkedin', 'google_ads',
                'csv_import', 'whatsapp', 'email_inbox', 'apollo', 'website_chatbot',
                'ai_lead_miner', 'referral', 'manual', 'api', 'webhook', 'appointments',
                'partner_integration', 'other'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE lead_status_enum AS ENUM (
                'new', 'contacted', 'qualified', 'unqualified', 'nurturing', 'converted', 'lost'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE deal_stage_enum AS ENUM (
                'prospecting', 'qualification', 'proposal', 'negotiation', 'closed_won', 'closed_lost'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE task_status_enum AS ENUM (
                'pending', 'in_progress', 'completed', 'cancelled'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE task_priority_enum AS ENUM (
                'low', 'medium', 'high', 'urgent'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE activity_type_enum AS ENUM (
                'note', 'call', 'email', 'meeting', 'task',
                'email_opened', 'email_clicked', 'email_replied', 'email_bounced',
                'stage_changed', 'assignment', 'ai_action', 'campaign_sent',
                'whatsapp_sent', 'whatsapp_received'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # =========================================================================
    # CREATE TABLES IN DEPENDENCY ORDER (no circular FKs initially)
    # =========================================================================
    
    # 1. companies table (no dependencies)
    op.create_table(
        'companies',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('domain', sa.String(255), nullable=True),
        sa.Column('industry', sa.String(100), nullable=True),
        sa.Column('size', sa.String(50), nullable=True),
        sa.Column('annual_revenue', sa.BigInteger(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('website', sa.String(500), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('state', sa.String(100), nullable=True),
        sa.Column('country', sa.String(100), nullable=True),
        sa.Column('postal_code', sa.String(20), nullable=True),
        sa.Column('linkedin_url', sa.String(500), nullable=True),
        sa.Column('facebook_url', sa.String(500), nullable=True),
        sa.Column('twitter_url', sa.String(500), nullable=True),
        sa.Column('source', postgresql.ENUM(name='lead_source_enum', create_type=False), nullable=True),
        sa.Column('utm_source', sa.String(100), nullable=True),
        sa.Column('utm_medium', sa.String(100), nullable=True),
        sa.Column('utm_campaign', sa.String(100), nullable=True),
        sa.Column('utm_content', sa.String(100), nullable=True),
        sa.Column('utm_term', sa.String(100), nullable=True),
        sa.Column('ai_summary', sa.Text(), nullable=True),
        sa.Column('ai_icp_score', sa.Integer(), nullable=True),
        sa.Column('ai_icp_reason', sa.Text(), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_companies_tenant_name', 'companies', ['tenant_id', 'name'])
    op.create_index('ix_companies_tenant_domain', 'companies', ['tenant_id', 'domain'])
    op.create_index('ix_companies_tenant_source', 'companies', ['tenant_id', 'source'])
    op.create_index('ix_companies_tenant_id', 'companies', ['tenant_id'])

    # 2. contacts table (depends on companies)
    op.create_table(
        'contacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('mobile', sa.String(50), nullable=True),
        sa.Column('title', sa.String(100), nullable=True),
        sa.Column('department', sa.String(100), nullable=True),
        sa.Column('linkedin_url', sa.String(500), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('state', sa.String(100), nullable=True),
        sa.Column('country', sa.String(100), nullable=True),
        sa.Column('postal_code', sa.String(20), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('do_not_contact', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('email_opted_out', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sms_opted_out', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('source', postgresql.ENUM(name='lead_source_enum', create_type=False), nullable=True),
        sa.Column('utm_source', sa.String(100), nullable=True),
        sa.Column('utm_medium', sa.String(100), nullable=True),
        sa.Column('utm_campaign', sa.String(100), nullable=True),
        sa.Column('utm_content', sa.String(100), nullable=True),
        sa.Column('utm_term', sa.String(100), nullable=True),
        sa.Column('ai_summary', sa.Text(), nullable=True),
        sa.Column('ai_lead_score', sa.Integer(), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contacts_tenant_email', 'contacts', ['tenant_id', 'email'])
    op.create_index('ix_contacts_tenant_company', 'contacts', ['tenant_id', 'company_id'])
    op.create_index('ix_contacts_tenant_name', 'contacts', ['tenant_id', 'last_name', 'first_name'])
    op.create_index('ix_contacts_tenant_id', 'contacts', ['tenant_id'])

    # 3. pipelines table (no CRM dependencies)
    op.create_table(
        'pipelines',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_pipeline_tenant_name'),
    )
    op.create_index('ix_pipelines_tenant_id', 'pipelines', ['tenant_id'])

    # 4. stages table (depends on pipelines)
    op.create_table(
        'stages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pipeline_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('probability', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_closed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_won', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('color', sa.String(7), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['pipeline_id'], ['pipelines.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pipeline_id', 'order', name='uq_stage_pipeline_order'),
        sa.UniqueConstraint('pipeline_id', 'name', name='uq_stage_pipeline_name'),
    )
    op.create_index('ix_stages_tenant_id', 'stages', ['tenant_id'])
    op.create_index('ix_stages_pipeline_id', 'stages', ['pipeline_id'])

    # 5. leads table (depends on contacts, companies - NO deals FK yet)
    op.create_table(
        'leads',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', postgresql.ENUM(name='lead_status_enum', create_type=False), nullable=False, server_default='new'),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('assigned_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source', postgresql.ENUM(name='lead_source_enum', create_type=False), nullable=True),
        sa.Column('source_id', sa.String(255), nullable=True),
        sa.Column('utm_source', sa.String(100), nullable=True),
        sa.Column('utm_medium', sa.String(100), nullable=True),
        sa.Column('utm_campaign', sa.String(100), nullable=True),
        sa.Column('utm_content', sa.String(100), nullable=True),
        sa.Column('utm_term', sa.String(100), nullable=True),
        sa.Column('referrer_url', sa.String(500), nullable=True),
        sa.Column('landing_page', sa.String(500), nullable=True),
        sa.Column('ai_score', sa.Integer(), nullable=True),
        sa.Column('ai_score_reason', sa.Text(), nullable=True),
        sa.Column('ai_next_action', sa.Text(), nullable=True),
        sa.Column('ai_next_action_confidence', sa.Float(), nullable=True),
        sa.Column('ai_summary', sa.Text(), nullable=True),
        sa.Column('is_qualified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('qualified_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('qualified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('qualification_notes', sa.Text(), nullable=True),
        sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
        # converted_deal_id FK added later after deals table exists
        sa.Column('converted_deal_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['assigned_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['qualified_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_leads_tenant_status', 'leads', ['tenant_id', 'status'])
    op.create_index('ix_leads_tenant_owner', 'leads', ['tenant_id', 'owner_id'])
    op.create_index('ix_leads_tenant_source', 'leads', ['tenant_id', 'source'])
    op.create_index('ix_leads_tenant_ai_score', 'leads', ['tenant_id', 'ai_score'])
    op.create_index('ix_leads_tenant_created', 'leads', ['tenant_id', 'created_at'])
    op.create_index('ix_leads_tenant_id', 'leads', ['tenant_id'])

    # 6. deals table (depends on pipelines, stages, contacts, companies, leads)
    # lead_id FK added later after leads table exists
    op.create_table(
        'deals',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pipeline_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('stage_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True),
        # lead_id FK added later after leads table exists
        sa.Column('lead_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('value', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('expected_close_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_close_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('probability', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('weighted_value', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('source', postgresql.ENUM(name='lead_source_enum', create_type=False), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['pipeline_id'], ['pipelines.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['stage_id'], ['stages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_deals_tenant_stage', 'deals', ['tenant_id', 'stage_id'])
    op.create_index('ix_deals_tenant_owner', 'deals', ['tenant_id', 'owner_id'])
    op.create_index('ix_deals_tenant_pipeline', 'deals', ['tenant_id', 'pipeline_id'])
    op.create_index('ix_deals_tenant_expected_close', 'deals', ['tenant_id', 'expected_close_date'])
    op.create_index('ix_deals_tenant_id', 'deals', ['tenant_id'])

    # 7. NOW add the circular FKs after both tables exist
    op.create_foreign_key(
        'fk_leads_converted_deal_id', 'leads', 'deals',
        ['converted_deal_id'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_deals_lead_id', 'deals', 'leads',
        ['lead_id'], ['id'], ondelete='SET NULL'
    )

    # 8. tasks table (depends on contacts, companies, deals, leads)
    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lead_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('deal_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', postgresql.ENUM(name='task_status_enum', create_type=False), nullable=False, server_default='pending'),
        sa.Column('priority', postgresql.ENUM(name='task_priority_enum', create_type=False), nullable=False, server_default='medium'),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reminder_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reminder_sent', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_recurring', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('recurrence_rule', sa.Text(), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tasks_tenant_owner_status', 'tasks', ['tenant_id', 'owner_id', 'status'])
    op.create_index('ix_tasks_tenant_due_date', 'tasks', ['tenant_id', 'due_date'])
    op.create_index('ix_tasks_tenant_lead', 'tasks', ['tenant_id', 'lead_id'])
    op.create_index('ix_tasks_tenant_deal', 'tasks', ['tenant_id', 'deal_id'])
    op.create_index('ix_tasks_tenant_id', 'tasks', ['tenant_id'])

    # 9. notes table (depends on contacts, companies, deals, leads)
    op.create_table(
        'notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lead_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('deal_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notes_tenant_lead', 'notes', ['tenant_id', 'lead_id'])
    op.create_index('ix_notes_tenant_deal', 'notes', ['tenant_id', 'deal_id'])
    op.create_index('ix_notes_tenant_contact', 'notes', ['tenant_id', 'contact_id'])
    op.create_index('ix_notes_tenant_company', 'notes', ['tenant_id', 'company_id'])
    op.create_index('ix_notes_tenant_id', 'notes', ['tenant_id'])

    # 10. activities table (depends on contacts, companies, deals, leads)
    op.create_table(
        'activities',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lead_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('deal_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('type', postgresql.ENUM(name='activity_type_enum', create_type=False), nullable=False),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('is_ai_generated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('ai_provider', sa.String(50), nullable=True),
        sa.Column('ai_model', sa.String(100), nullable=True),
        sa.Column('correlation_id', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_activities_tenant_lead_created', 'activities', ['tenant_id', 'lead_id', 'created_at'])
    op.create_index('ix_activities_tenant_deal_created', 'activities', ['tenant_id', 'deal_id', 'created_at'])
    op.create_index('ix_activities_tenant_type_created', 'activities', ['tenant_id', 'type', 'created_at'])
    op.create_index('ix_activities_tenant_user_created', 'activities', ['tenant_id', 'user_id', 'created_at'])
    op.create_index('ix_activities_tenant_id', 'activities', ['tenant_id'])
    op.create_index('ix_activities_correlation_id', 'activities', ['correlation_id'])

    # 11. proposals table (depends on deals)
    op.create_table(
        'proposals',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deal_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
        sa.Column('executive_summary', sa.Text(), nullable=True),
        sa.Column('solution_overview', sa.Text(), nullable=True),
        sa.Column('pricing_details', postgresql.JSONB(), nullable=True),
        sa.Column('terms', sa.Text(), nullable=True),
        sa.Column('pdf_url', sa.String(500), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('viewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_ai_generated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('ai_provider', sa.String(50), nullable=True),
        sa.Column('ai_model', sa.String(100), nullable=True),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_proposals_tenant_deal', 'proposals', ['tenant_id', 'deal_id'])
    op.create_index('ix_proposals_tenant_status', 'proposals', ['tenant_id', 'status'])
    op.create_index('ix_proposals_tenant_id', 'proposals', ['tenant_id'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('proposals')
    op.drop_table('activities')
    op.drop_table('notes')
    op.drop_table('tasks')
    op.drop_table('leads')
    op.drop_table('deals')
    op.drop_table('stages')
    op.drop_table('pipelines')
    op.drop_table('contacts')
    op.drop_table('companies')

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS activity_type_enum")
    op.execute("DROP TYPE IF EXISTS task_priority_enum")
    op.execute("DROP TYPE IF EXISTS task_status_enum")
    op.execute("DROP TYPE IF EXISTS deal_stage_enum")
    op.execute("DROP TYPE IF EXISTS lead_status_enum")
    op.execute("DROP TYPE IF EXISTS lead_source_enum")