"""Phase 5: AI models - ICP Profile

Revision ID: 005_ai_models
Revises: 004_integration_models
Create Date: 2024-08-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005_ai_models'
down_revision = '004_integration_models'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # icp_profiles table
    op.create_table(
        'icp_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('criteria', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('min_score_threshold', sa.Integer(), nullable=False, server_default='85'),
        sa.Column('prospects_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('prospects_qualified', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('prospects_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_icp_profiles_tenant_active', 'icp_profiles', ['tenant_id', 'is_active'])
    op.create_index('ix_icp_profiles_tenant_id', 'icp_profiles', ['tenant_id'])


def downgrade() -> None:
    op.drop_table('icp_profiles')