"""Add missing enum labels

Revision ID: 006_add_missing_enum_labels
Revises: 005_ai_models
Create Date: 2024-08-17 00:00:00.000000
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '006_add_missing_enum_labels'
down_revision = '005_ai_models'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # integration_type_enum: add firecrawl
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE integration_type_enum ADD VALUE IF NOT EXISTS 'firecrawl';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # campaign_status_enum: add failed
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE campaign_status_enum ADD VALUE IF NOT EXISTS 'failed';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # activity_type_enum: add lead_created, email_delivered, email_complained, email_unsubscribed
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE activity_type_enum ADD VALUE IF NOT EXISTS 'lead_created';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            ALTER TYPE activity_type_enum ADD VALUE IF NOT EXISTS 'email_delivered';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            ALTER TYPE activity_type_enum ADD VALUE IF NOT EXISTS 'email_complained';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            ALTER TYPE activity_type_enum ADD VALUE IF NOT EXISTS 'email_unsubscribed';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)


def downgrade() -> None:
    # Note: PostgreSQL does not support removing enum values
    # These would need manual intervention if downgrading
    pass