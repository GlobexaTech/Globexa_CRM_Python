"""Persist execution attribution added by the provider/workforce models."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "015_execution_attribution"
down_revision = "014_provider_workforce"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("audit_logs", "activities"):
        op.add_column(
            table, sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True)
        )
        op.create_index(f"ix_{table}_execution_id", table, ["execution_id"])
        op.create_foreign_key(
            f"fk_{table}_execution",
            table,
            "agent_executions",
            ["tenant_id", "execution_id"],
            ["tenant_id", "id"],
        )


def downgrade():
    for table in ("audit_logs", "activities"):
        op.drop_constraint(f"fk_{table}_execution", table, type_="foreignkey")
        op.drop_column(table, "execution_id")
