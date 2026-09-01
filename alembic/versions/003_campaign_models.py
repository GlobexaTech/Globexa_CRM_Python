"""Phase 3: Campaign & Email models

Revision ID: 003_campaign_models
Revises: 002_crm_models
Create Date: 2024-08-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_campaign_models'
down_revision = '002_crm_models'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types using raw SQL with IF NOT EXISTS to avoid duplicate errors
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE campaign_type_enum AS ENUM (
                'broadcast', 'sequence', 'triggered'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE campaign_status_enum AS ENUM (
                'draft', 'scheduled', 'sending', 'sent', 'paused', 'completed', 'cancelled'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE campaign_recipient_status_enum AS ENUM (
                'queued', 'scheduled', 'sending', 'sent', 'delivered', 'opened', 'clicked',
                'replied', 'bounced', 'complained', 'unsubscribed', 'suppressed', 'failed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE audience_type_enum AS ENUM (
                'static', 'dynamic'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE trigger_type_enum AS ENUM (
                'email_opened', 'email_clicked', 'email_replied', 'link_clicked',
                'form_submitted', 'stage_changed', 'deal_created', 'task_completed',
                'custom_event', 'date_based'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE email_provider_type_enum AS ENUM (
                'resend', 'gmail', 'microsoft', 'smtp'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # sending_domains table (must be created before campaigns which references it)
    op.create_table(
        'sending_domains',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('domain', sa.String(255), nullable=False),
        sa.Column('subdomain', sa.String(100), nullable=True),
        sa.Column('from_name', sa.String(255), nullable=False),
        sa.Column('from_email', sa.String(255), nullable=False),
        sa.Column('reply_to_email', sa.String(255), nullable=True),
        sa.Column('provider', postgresql.ENUM(name='email_provider_type_enum', create_type=False), nullable=False),
        sa.Column('provider_config', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('dkim_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('spf_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('dmarc_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('warmup_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('warmup_stage', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('daily_limit', sa.Integer(), nullable=False, server_default='500'),
        sa.Column('current_daily_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_sent_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('bounce_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('complaint_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('reply_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('health_score', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pause_reason', sa.Text(), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'domain', 'subdomain', name='uq_sending_domain_tenant_domain_sub'),
    )
    op.create_index('ix_sending_domains_tenant_active', 'sending_domains', ['tenant_id', 'is_active'])
    op.create_index('ix_sending_domains_tenant_id', 'sending_domains', ['tenant_id'])

    # email_provider_configs table
    op.create_table(
        'email_provider_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', postgresql.ENUM(name='email_provider_type_enum', create_type=False), nullable=False),
        sa.Column('credentials_encrypted', sa.Text(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'provider', 'name', name='uq_email_config_tenant_provider_name'),
    )
    op.create_index('ix_email_configs_tenant_default', 'email_provider_configs', ['tenant_id', 'is_default'])
    op.create_index('ix_email_configs_tenant_id', 'email_provider_configs', ['tenant_id'])

    # campaigns table
    op.create_table(
        'campaigns',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('type', postgresql.ENUM(name='campaign_type_enum', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM(name='campaign_status_enum', create_type=False), nullable=False, server_default='draft'),
        sa.Column('sending_domain_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('sender_name', sa.String(255), nullable=False),
        sa.Column('sender_email', sa.String(255), nullable=False),
        sa.Column('reply_to_email', sa.String(255), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ai_personalization_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('ai_personalization_prompt', sa.Text(), nullable=True),
        sa.Column('track_opens', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('track_clicks', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('unsubscribe_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('tags', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sending_domain_id'], ['sending_domains.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_campaigns_tenant_status', 'campaigns', ['tenant_id', 'status'])
    op.create_index('ix_campaigns_tenant_type', 'campaigns', ['tenant_id', 'type'])
    op.create_index('ix_campaigns_tenant_scheduled', 'campaigns', ['tenant_id', 'scheduled_at'])
    op.create_index('ix_campaigns_tenant_id', 'campaigns', ['tenant_id'])

    # campaign_audiences table
    op.create_table(
        'campaign_audiences',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', postgresql.ENUM(name='audience_type_enum', create_type=False), nullable=False, server_default='static'),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('contact_ids', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('filters', postgresql.JSONB(), nullable=True),
        sa.Column('exclude_contact_ids', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('exclude_suppressed', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('exclude_unsubscribed', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('exclude_bounced', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('estimated_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_computed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', name='uq_audience_campaign'),
    )
    op.create_index('ix_campaign_audiences_tenant_id', 'campaign_audiences', ['tenant_id'])

    # campaign_templates table
    op.create_table(
        'campaign_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('preheader', sa.String(500), nullable=True),
        sa.Column('html_content', sa.Text(), nullable=False),
        sa.Column('text_content', sa.Text(), nullable=True),
        sa.Column('ai_personalization_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('ai_personalization_prompt', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_active_version', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'step_order', name='uq_template_campaign_step'),
    )
    op.create_index('ix_campaign_templates_tenant_id', 'campaign_templates', ['tenant_id'])
    op.create_index('ix_campaign_templates_campaign_id', 'campaign_templates', ['campaign_id'])

    # campaign_recipients table
    op.create_table(
        'campaign_recipients',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('status', postgresql.ENUM(name='campaign_recipient_status_enum', create_type=False), nullable=False, server_default='queued'),
        sa.Column('provider_message_id', sa.String(255), nullable=True),
        sa.Column('provider_type', postgresql.ENUM(name='email_provider_type_enum', create_type=False), nullable=True),
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_opened_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_opened_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_clicked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_clicked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('replied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('bounced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('complained_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('unsubscribed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('open_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('click_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bounce_type', sa.String(50), nullable=True),
        sa.Column('bounce_reason', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(255), nullable=True),
        sa.Column('ai_personalized', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('ai_personalization_data', postgresql.JSONB(), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_id'], ['campaign_templates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_campaign_recipients_campaign_status', 'campaign_recipients', ['campaign_id', 'status'])
    op.create_index('ix_campaign_recipients_tenant_contact', 'campaign_recipients', ['tenant_id', 'contact_id'])
    op.create_index('ix_campaign_recipients_provider_msg', 'campaign_recipients', ['provider_message_id'])
    op.create_index('ix_campaign_recipients_idempotency', 'campaign_recipients', ['idempotency_key'])
    op.create_index('ix_campaign_recipients_tenant_id', 'campaign_recipients', ['tenant_id'])

    # campaign_sequences table
    op.create_table(
        'campaign_sequences',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('delay_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('delay_hours', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('send_time', sa.String(5), nullable=True),
        sa.Column('send_timezone', sa.String(50), nullable=False, server_default='UTC'),
        sa.Column('send_on_weekends', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('stop_on_reply', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('stop_on_unsubscribe', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('stop_on_bounce', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_id'], ['campaign_templates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'step_order', name='uq_sequence_campaign_step'),
    )
    op.create_index('ix_campaign_sequences_tenant_id', 'campaign_sequences', ['tenant_id'])
    op.create_index('ix_campaign_sequences_campaign_id', 'campaign_sequences', ['campaign_id'])

    # campaign_triggers table
    op.create_table(
        'campaign_triggers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trigger_type', postgresql.ENUM(name='trigger_type_enum', create_type=False), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('conditions', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('delay_minutes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_triggers_per_contact', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('cooldown_hours', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_id'], ['campaign_templates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_campaign_triggers_tenant_id', 'campaign_triggers', ['tenant_id'])
    op.create_index('ix_campaign_triggers_campaign_id', 'campaign_triggers', ['campaign_id'])

    # campaign_stats table
    op.create_table(
        'campaign_stats',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('total_recipients', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('queued', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('delivered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bounced', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('suppressed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('opened', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('clicked', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('replied', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unsubscribed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('complained', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('interested', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('qualified_leads', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('appointments', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proposals', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('conversions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('revenue', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('ai_personalized_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ai_cost_usd', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('ai_reply_classifications', postgresql.JSONB(), nullable=True),
        sa.Column('delivery_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('open_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('click_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('reply_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('bounce_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('unsubscribe_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('conversion_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('attribution_data', postgresql.JSONB(), nullable=True),
        sa.Column('last_calculated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', name='uq_stats_campaign'),
    )
    op.create_index('ix_campaign_stats_tenant_id', 'campaign_stats', ['tenant_id'])

    # email_events table
    op.create_table(
        'email_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', postgresql.ENUM(name='email_provider_type_enum', create_type=False), nullable=False),
        sa.Column('provider_event_id', sa.String(255), nullable=False),
        sa.Column('provider_event_type', sa.String(100), nullable=False),
        sa.Column('recipient_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('provider_message_id', sa.String(255), nullable=True),
        sa.Column('event_data', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('event_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('processed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['recipient_id'], ['campaign_recipients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'provider_event_id', name='uq_email_event_provider_event'),
    )
    op.create_index('ix_email_events_tenant_recipient', 'email_events', ['tenant_id', 'recipient_id'])
    op.create_index('ix_email_events_tenant_timestamp', 'email_events', ['tenant_id', 'event_timestamp'])
    op.create_index('ix_email_events_tenant_id', 'email_events', ['tenant_id'])

    # suppression_lists table
    op.create_table(
        'suppression_lists',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sending_domain_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reason', sa.String(100), nullable=False),
        sa.Column('reason_detail', sa.Text(), nullable=True),
        sa.Column('provider', postgresql.ENUM(name='email_provider_type_enum', create_type=False), nullable=True),
        sa.Column('provider_event_id', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sending_domain_id'], ['sending_domains.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'email', 'sending_domain_id', name='uq_suppression_tenant_email_domain'),
    )
    op.create_index('ix_suppression_lists_tenant_active', 'suppression_lists', ['tenant_id', 'is_active'])
    op.create_index('ix_suppression_lists_tenant_id', 'suppression_lists', ['tenant_id'])


def downgrade() -> None:
    op.drop_table('email_provider_configs')
    op.drop_table('sending_domains')
    op.drop_table('suppression_lists')
    op.drop_table('email_events')
    op.drop_table('campaign_stats')
    op.drop_table('campaign_triggers')
    op.drop_table('campaign_sequences')
    op.drop_table('campaign_recipients')
    op.drop_table('campaign_templates')
    op.drop_table('campaign_audiences')
    op.drop_table('campaigns')

    op.execute("DROP TYPE IF EXISTS email_provider_type_enum")
    op.execute("DROP TYPE IF EXISTS trigger_type_enum")
    op.execute("DROP TYPE IF EXISTS audience_type_enum")
    op.execute("DROP TYPE IF EXISTS campaign_recipient_status_enum")
    op.execute("DROP TYPE IF EXISTS campaign_status_enum")
    op.execute("DROP TYPE IF EXISTS campaign_type_enum")