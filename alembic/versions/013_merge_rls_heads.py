"""Join the reviewed RLS repair history with the Checkpoint 4 schema history."""

revision = "013_merge_rls_heads"
down_revision = ("012_activity_relation", "008_reinforce_rls_coverage")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
