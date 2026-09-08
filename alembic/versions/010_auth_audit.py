"""Global pre-tenant authentication audit, append-only for the runtime role."""
from alembic import op
import sqlalchemy as sa

revision = "010_auth_audit"
down_revision = "009_model_inventory_repair"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("security_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("principal_digest", sa.String(64), nullable=False),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    raise RuntimeError("Authentication audit cannot be silently discarded")
