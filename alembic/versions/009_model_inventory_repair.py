"""Create baseline model tables missing from historical migrations; protect them."""
from alembic import op
import sqlalchemy as sa
revision = "009_model_inventory_repair"
down_revision = "008_identity_boundaries"
branch_labels = None
depends_on = None

DDL = [
    """
CREATE TABLE proposal_templates (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	name VARCHAR(255) NOT NULL,
	description TEXT,
	content JSONB NOT NULL,
	is_default BOOLEAN NOT NULL,
	created_by_id UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_proposal_template_tenant_name UNIQUE (tenant_id, name),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
)

""",
    """CREATE INDEX ix_proposal_templates_tenant_id ON proposal_templates (tenant_id)""",
    """
CREATE TABLE products (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	name VARCHAR(255) NOT NULL,
	description TEXT,
	sku VARCHAR(100),
	price_cents BIGINT NOT NULL,
	currency VARCHAR(3) NOT NULL,
	billing_type VARCHAR(50) NOT NULL,
	billing_period VARCHAR(20),
	is_active BOOLEAN NOT NULL,
	custom_fields JSONB NOT NULL,
	created_by_id UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
)

""",
    """CREATE INDEX ix_products_tenant_id ON products (tenant_id)""",
    """CREATE INDEX ix_products_sku ON products (sku)""",
    """CREATE INDEX ix_products_tenant_sku ON products (tenant_id, sku)""",
    """CREATE INDEX ix_products_tenant_name ON products (tenant_id, name)""",
    """
CREATE TABLE pending_leads (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	source VARCHAR(100) NOT NULL,
	source_id VARCHAR(255) NOT NULL,
	email VARCHAR(255) NOT NULL,
	first_name VARCHAR(100),
	last_name VARCHAR(100),
	title VARCHAR(255),
	company_name VARCHAR(255),
	phone VARCHAR(50),
	raw_data JSONB NOT NULL,
	status pending_lead_status_enum NOT NULL,
	assigned_reviewer_id UUID,
	reviewed_by_id UUID,
	reviewed_at TIMESTAMP WITH TIME ZONE,
	review_notes TEXT,
	created_lead_id UUID,
	created_contact_id UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
	FOREIGN KEY(assigned_reviewer_id) REFERENCES users (id) ON DELETE SET NULL,
	FOREIGN KEY(reviewed_by_id) REFERENCES users (id) ON DELETE SET NULL,
	FOREIGN KEY(created_lead_id) REFERENCES leads (id) ON DELETE SET NULL,
	FOREIGN KEY(created_contact_id) REFERENCES contacts (id) ON DELETE SET NULL
)

""",
    """CREATE INDEX ix_pending_leads_email ON pending_leads (email)""",
    """CREATE INDEX ix_pending_leads_source_id ON pending_leads (source_id)""",
    """CREATE INDEX ix_pending_leads_tenant_status ON pending_leads (tenant_id, status)""",
    """CREATE INDEX ix_pending_leads_tenant_email ON pending_leads (tenant_id, email)""",
    """CREATE INDEX ix_pending_leads_source ON pending_leads (source)""",
    """CREATE INDEX ix_pending_leads_tenant_source ON pending_leads (tenant_id, source)""",
    """CREATE INDEX ix_pending_leads_status ON pending_leads (status)""",
    """CREATE INDEX ix_pending_leads_tenant_id ON pending_leads (tenant_id)""",
]

def upgrade():
    op.execute("CREATE TYPE pending_lead_status_enum AS ENUM ('pending', 'approved', 'rejected', 'needs_review')")
    for statement in DDL:
        op.execute(statement)
    for table in ("proposal_templates", "products", "pending_leads"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        predicate = "tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid"
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({predicate}) WITH CHECK ({predicate})")
        op.create_unique_constraint(f"uq_{table}_tenant_id_id", table, ["tenant_id", "id"])
    for column, target in (("created_lead_id", "leads"), ("created_contact_id", "contacts")):
        op.create_foreign_key(f"fk_cp2_pending_leads_{column}", "pending_leads", target,
                              ["tenant_id", column], ["tenant_id", "id"])



def downgrade():
    raise RuntimeError("Security downgrade requires a reviewed restore")
