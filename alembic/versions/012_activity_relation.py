"""Repair the pre-existing Activity campaign relation missing from physical schema."""

from alembic import op
import sqlalchemy as sa

revision = "012_activity_relation"
down_revision = "011_crm_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("activities", sa.Column("campaign_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_cp3_activity_campaign",
        "activities",
        "campaigns",
        ["tenant_id", "campaign_id"],
        ["tenant_id", "id"],
    )


def downgrade():
    raise RuntimeError("Restore a reviewed backup to preserve timeline relationships")
