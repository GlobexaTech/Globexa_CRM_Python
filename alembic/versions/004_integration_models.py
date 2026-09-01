"""Phase 4: Integration Framework models

Revision ID: 004_integration_models
Revises: 003_campaign_models
Create Date: 2024-08-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_integration_models'
down_revision = '003_campaign_models'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types using raw SQL with IF NOT EXISTS to avoid duplicate errors
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE integration_type_enum AS ENUM (
                'meta', 'google_ads', 'linkedin', 'apollo', 'whatsapp', 'csv', 'webhook',
                'email_inbox', 'website_form', 'website_chatbot', 'ai_lead_miner',
                'appointments', 'referral', 'partner', 'api', 'other'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE integration_status_enum AS ENUM (
                'pending', 'connected', 'error', 'disconnected', 'expired'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE sync_status_enum AS ENUM (
                'pending', 'running', 'completed', 'failed', 'partial'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE field_mapping_type_enum AS ENUM (
                'direct', 'transform', 'static', 'computed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE attribution_model_enum AS ENUM (
                'first_touch', 'last_touch', 'linear', 'time_decay', 'u_shaped', 'w_shaped', 'custom'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # integrations table
    op.create_table(
        'integrations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', postgresql.ENUM(name='integration_type_enum', create_type=False), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', postgresql.ENUM(name='integration_status_enum', create_type=False), nullable=False, server_default='pending'),
        sa.Column('config', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('sync_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sync_frequency_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_status', postgresql.ENUM(name='sync_status_enum', create_type=False), nullable=True),
        sa.Column('last_sync_error', sa.Text(), nullable=True),
        sa.Column('records_synced', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('field_mappings', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'type', 'name', name='uq_integration_tenant_type_name'),
    )
    op.create_index('ix_integrations_tenant_type', 'integrations', ['tenant_id', 'type'])
    op.create_index('ix_integrations_tenant_status', 'integrations', ['tenant_id', 'status'])
    op.create_index('ix_integrations_tenant_id', 'integrations', ['tenant_id'])

    # integration_credentials table
    op.create_table(
        'integration_credentials',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('integration_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('credentials_encrypted', sa.Text(), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('token_type', sa.String(50), nullable=True),
        sa.Column('scopes', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('validation_error', sa.Text(), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('integration_id', 'name', name='uq_credential_integration_name'),
    )
    op.create_index('ix_credentials_tenant_integration', 'integration_credentials', ['tenant_id', 'integration_id'])
    op.create_index('ix_credentials_tenant_id', 'integration_credentials', ['tenant_id'])

    # webhook_endpoints table
    op.create_table(
        'webhook_endpoints',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('integration_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('url_path', sa.String(500), nullable=False),
        sa.Column('secret', sa.String(255), nullable=False),
        sa.Column('events', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('retry_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('rate_limit_per_minute', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('response_template', sa.Text(), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'url_path', name='uq_webhook_tenant_path'),
    )
    op.create_index('ix_webhooks_tenant_active', 'webhook_endpoints', ['tenant_id', 'is_active'])
    op.create_index('ix_webhooks_tenant_id', 'webhook_endpoints', ['tenant_id'])
    op.create_index('ix_webhooks_integration_id', 'webhook_endpoints', ['integration_id'])

    # integration_sync_logs table
    op.create_table(
        'integration_sync_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('integration_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sync_type', sa.String(50), nullable=False),
        sa.Column('status', postgresql.ENUM(name='sync_status_enum', create_type=False), nullable=False, server_default='pending'),
        sa.Column('records_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_updated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_skipped', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_details', postgresql.JSONB(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('triggered_by', sa.String(50), nullable=True),
        sa.Column('triggered_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['triggered_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sync_logs_integration_started', 'integration_sync_logs', ['integration_id', 'started_at'])
    op.create_index('ix_sync_logs_tenant_status', 'integration_sync_logs', ['tenant_id', 'status'])
    op.create_index('ix_sync_logs_tenant_id', 'integration_sync_logs', ['tenant_id'])

    # lead_source_configs table
    op.create_table(
        'lead_source_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_key', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source_type', postgresql.ENUM(name='integration_type_enum', create_type=False), nullable=False),
        sa.Column('default_utm_source', sa.String(100), nullable=True),
        sa.Column('default_utm_medium', sa.String(100), nullable=True),
        sa.Column('default_utm_campaign', sa.String(100), nullable=True),
        sa.Column('auto_create_contact', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('auto_create_company', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('default_lead_status', sa.String(50), nullable=False, server_default='new'),
        sa.Column('default_owner_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('deduplication_fields', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('icon', sa.String(100), nullable=True),
        sa.Column('color', sa.String(7), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['default_owner_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'source_key', name='uq_lead_source_tenant_key'),
    )
    op.create_index('ix_lead_sources_tenant_active', 'lead_source_configs', ['tenant_id', 'is_active'])
    op.create_index('ix_lead_sources_tenant_id', 'lead_source_configs', ['tenant_id'])

    # touchpoints table
    op.create_table(
        'touchpoints',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('lead_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('deal_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source', sa.String(100), nullable=False),
        sa.Column('medium', sa.String(100), nullable=False),
        sa.Column('campaign', sa.String(255), nullable=True),
        sa.Column('ad_group', sa.String(255), nullable=True),
        sa.Column('ad_creative', sa.String(255), nullable=True),
        sa.Column('landing_page', sa.String(500), nullable=True),
        sa.Column('utm_source', sa.String(100), nullable=True),
        sa.Column('utm_medium', sa.String(100), nullable=True),
        sa.Column('utm_campaign', sa.String(100), nullable=True),
        sa.Column('utm_content', sa.String(100), nullable=True),
        sa.Column('utm_term', sa.String(100), nullable=True),
        sa.Column('referrer_url', sa.String(500), nullable=True),
        sa.Column('interaction_type', sa.String(50), nullable=False),
        sa.Column('interaction_value', sa.Float(), nullable=True),
        sa.Column('cost', sa.BigInteger(), nullable=True),
        sa.Column('is_first_touch', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_last_touch', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('attribution_weight', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('integration_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('external_id', sa.String(255), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_touchpoints_tenant_contact_occurred', 'touchpoints', ['tenant_id', 'contact_id', 'occurred_at'])
    op.create_index('ix_touchpoints_tenant_lead_occurred', 'touchpoints', ['tenant_id', 'lead_id', 'occurred_at'])
    op.create_index('ix_touchpoints_tenant_deal_occurred', 'touchpoints', ['tenant_id', 'deal_id', 'occurred_at'])
    op.create_index('ix_touchpoints_tenant_source_occurred', 'touchpoints', ['tenant_id', 'source', 'occurred_at'])
    op.create_index('ix_touchpoints_tenant_campaign', 'touchpoints', ['tenant_id', 'campaign'])
    op.create_index('ix_touchpoints_tenant_id', 'touchpoints', ['tenant_id'])

    # attribution_rules table
    op.create_table(
        'attribution_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('model', postgresql.ENUM(name='attribution_model_enum', create_type=False), nullable=False, server_default='last_touch'),
        sa.Column('lookback_days', sa.Integer(), nullable=False, server_default='90'),
        sa.Column('included_sources', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('excluded_sources', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('included_mediums', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('excluded_mediums', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('first_touch_weight', sa.Float(), nullable=False, server_default='0.4'),
        sa.Column('last_touch_weight', sa.Float(), nullable=False, server_default='0.4'),
        sa.Column('middle_touch_weight', sa.Float(), nullable=False, server_default='0.2'),
        sa.Column('half_life_days', sa.Integer(), nullable=False, server_default='7'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_attribution_rule_tenant_name'),
    )
    op.create_index('ix_attribution_rules_tenant_active', 'attribution_rules', ['tenant_id', 'is_active'])
    op.create_index('ix_attribution_rules_tenant_id', 'attribution_rules', ['tenant_id'])

    # revenue_attributions table
    op.create_table(
        'revenue_attributions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deal_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('attribution_rule_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('attributed_revenue', sa.BigInteger(), nullable=False),
        sa.Column('touchpoint_attributions', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('by_source', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('by_medium', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('by_campaign', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['attribution_rule_id'], ['attribution_rules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('deal_id', 'attribution_rule_id', name='uq_revenue_attribution_deal_rule'),
    )
    op.create_index('ix_revenue_attributions_tenant_deal', 'revenue_attributions', ['tenant_id', 'deal_id'])
    op.create_index('ix_revenue_attributions_tenant_id', 'revenue_attributions', ['tenant_id'])


def downgrade() -> None:
    op.drop_table('revenue_attributions')
    op.drop_table('attribution_rules')
    op.drop_table('touchpoints')
    op.drop_table('lead_source_configs')
    op.drop_table('integration_sync_logs')
    op.drop_table('webhook_endpoints')
    op.drop_table('integration_credentials')
    op.drop_table('integrations')

    op.execute("DROP TYPE IF EXISTS attribution_model_enum")
    op.execute("DROP TYPE IF EXISTS field_mapping_type_enum")
    op.execute("DROP TYPE IF EXISTS sync_status_enum")
    op.execute("DROP TYPE IF EXISTS integration_status_enum")
    op.execute("DROP TYPE IF EXISTS integration_type_enum")