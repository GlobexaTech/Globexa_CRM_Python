"""Checkpoint 2 frozen schema and metadata-discovered RLS/security constraints.

No application model imports: this migration remains reproducible as models evolve.
"""
import os
from alembic import op
import sqlalchemy as sa
from cryptography.fernet import Fernet

revision = "007_checkpoint2_foundation"
down_revision = "006_add_missing_enum_labels"
branch_labels = None
depends_on = None

SCHEMA_DDL = [
    """
CREATE TABLE features (
	id UUID NOT NULL,
	key VARCHAR(100) NOT NULL,
	unit VARCHAR(50) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (key)
)

""",
    """
CREATE TABLE plans (
	id UUID NOT NULL,
	key VARCHAR(100) NOT NULL,
	name VARCHAR(255) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (key)
)

""",
    """
CREATE TABLE agent_definitions (
	name VARCHAR(255) NOT NULL,
	approved_tools JSONB NOT NULL,
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

""",
    """CREATE INDEX ix_agent_definitions_tenant_id ON agent_definitions (tenant_id)""",
    """
CREATE TABLE conversations (
	subject VARCHAR(255) NOT NULL,
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

""",
    """CREATE INDEX ix_conversations_tenant_id ON conversations (tenant_id)""",
    """
CREATE TABLE domain_events (
	event_type VARCHAR(100) NOT NULL,
	version INTEGER NOT NULL,
	aggregate_id VARCHAR(100) NOT NULL,
	actor_id UUID,
	payload JSONB NOT NULL,
	idempotency_key VARCHAR(255) NOT NULL,
	published_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, idempotency_key),
	FOREIGN KEY(actor_id) REFERENCES users (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

""",
    """CREATE INDEX ix_domain_events_tenant_id ON domain_events (tenant_id)""",
    """
CREATE TABLE plan_features (
	plan_id UUID NOT NULL,
	feature_id UUID NOT NULL,
	limit_value INTEGER,
	enabled BOOLEAN NOT NULL,
	PRIMARY KEY (plan_id, feature_id),
	FOREIGN KEY(plan_id) REFERENCES plans (id),
	FOREIGN KEY(feature_id) REFERENCES features (id)
)

""",
    """
CREATE TABLE workflows (
	name VARCHAR(255) NOT NULL,
	enabled BOOLEAN NOT NULL,
	version INTEGER NOT NULL,
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

""",
    """CREATE INDEX ix_workflows_tenant_id ON workflows (tenant_id)""",
    """
CREATE TABLE event_deliveries (
	event_id UUID NOT NULL,
	subscriber VARCHAR(100) NOT NULL,
	completed_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, event_id, subscriber),
	FOREIGN KEY(event_id) REFERENCES domain_events (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

""",
    """CREATE INDEX ix_event_deliveries_tenant_id ON event_deliveries (tenant_id)""",
    """
CREATE TABLE messages (
	conversation_id UUID NOT NULL,
	body TEXT NOT NULL,
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

""",
    """CREATE INDEX ix_messages_tenant_id ON messages (tenant_id)""",
    """
CREATE TABLE oauth_tokens (
	integration_id UUID NOT NULL,
	access_token TEXT NOT NULL,
	refresh_token TEXT,
	expires_at TIMESTAMP WITH TIME ZONE,
	scopes JSONB NOT NULL,
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(integration_id) REFERENCES integrations (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

""",
    """CREATE INDEX ix_oauth_tokens_tenant_id ON oauth_tokens (tenant_id)""",
    """
CREATE TABLE workflow_actions (
	workflow_id UUID NOT NULL,
	tool VARCHAR(100) NOT NULL,
	arguments JSONB NOT NULL,
	position INTEGER NOT NULL,
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workflow_id) REFERENCES workflows (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

""",
    """CREATE INDEX ix_workflow_actions_tenant_id ON workflow_actions (tenant_id)""",
    """
CREATE TABLE workflow_conditions (
	workflow_id UUID NOT NULL,
	expression JSONB NOT NULL,
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workflow_id) REFERENCES workflows (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

""",
    """CREATE INDEX ix_workflow_conditions_tenant_id ON workflow_conditions (tenant_id)""",
    """
CREATE TABLE workflow_execution_logs (
	workflow_id UUID NOT NULL,
	event_id UUID NOT NULL,
	status VARCHAR(30) NOT NULL,
	error_code VARCHAR(100),
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, workflow_id, event_id),
	FOREIGN KEY(workflow_id) REFERENCES workflows (id),
	FOREIGN KEY(event_id) REFERENCES domain_events (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

""",
    """CREATE INDEX ix_workflow_execution_logs_tenant_id ON workflow_execution_logs (tenant_id)""",
    """
CREATE TABLE workflow_triggers (
	workflow_id UUID NOT NULL,
	event_type VARCHAR(100) NOT NULL,
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workflow_id) REFERENCES workflows (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

""",
    """CREATE INDEX ix_workflow_triggers_tenant_id ON workflow_triggers (tenant_id)""",
    """
CREATE TABLE webhook_receipts (
	webhook_id UUID NOT NULL,
	digest VARCHAR(64) NOT NULL,
	event_id UUID NOT NULL,
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, webhook_id, digest),
	FOREIGN KEY(webhook_id) REFERENCES webhook_endpoints (id),
	FOREIGN KEY(event_id) REFERENCES domain_events (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

""",
    """CREATE INDEX ix_webhook_receipts_tenant_id ON webhook_receipts (tenant_id)""",
]

def tenant_tables(bind):
    inspector = sa.inspect(bind)
    return sorted(name for name in inspector.get_table_names(schema="public")
                  if any(c["name"] == "tenant_id" for c in inspector.get_columns(name, schema="public")))


def upgrade():
    bind = op.get_bind()
    for statement in SCHEMA_DDL:
        op.execute(statement)
    op.execute("ALTER TYPE role_enum ADD VALUE IF NOT EXISTS 'ai_agent'")
    op.execute("ALTER TYPE ai_provider_enum ADD VALUE IF NOT EXISTS 'deepseek'")
    # Upgrade existing data in one transaction; abort if credentials cannot be encrypted.
    secret_columns = {
        "integration_credentials": ["credentials_encrypted", "access_token", "refresh_token"],
        "email_provider_configs": ["credentials_encrypted"],
        "webhook_endpoints": ["secret"],
        "sending_domains": ["provider_config"],
    }
    op.execute("ALTER TABLE webhook_endpoints ALTER COLUMN secret TYPE text")
    op.execute("ALTER TABLE sending_domains ALTER COLUMN provider_config DROP DEFAULT")
    op.execute("ALTER TABLE sending_domains ALTER COLUMN provider_config TYPE text USING provider_config::text")
    cipher = None
    for table, columns in secret_columns.items():
        for column in columns:
            for row in bind.execute(sa.text(f'SELECT id, "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL')).all():
                value = row[1]
                if value.startswith("enc:v1:"):
                    continue
                if cipher is None:
                    key = os.environ.get("SECURITY_CREDENTIAL_ENCRYPTION_KEY")
                    if not key:
                        raise RuntimeError("Existing credentials require SECURITY_CREDENTIAL_ENCRYPTION_KEY")
                    cipher = Fernet(key.encode())
                encrypted = "enc:v1:" + cipher.encrypt(value.encode()).decode()
                bind.execute(sa.text(f'UPDATE "{table}" SET "{column}"=:value WHERE id=:id'), {"value": encrypted, "id": row[0]})
            op.create_check_constraint(f"ck_{table}_{column}_encrypted", table,
                                       f"\"{column}\" IS NULL OR \"{column}\" LIKE 'enc:v1:%'")
    inspector = sa.inspect(bind)
    tables = tenant_tables(bind)
    quote = bind.dialect.identifier_preparer.quote
    for table in tables:
        q = quote(table)
        op.execute(f'ALTER TABLE {q} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {q} FORCE ROW LEVEL SECURITY')
        predicate = "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
        # Own memberships may be discovered only after identity verification, before tenant selection.
        if table == "memberships":
            op.execute(f"CREATE POLICY tenant_read ON {q} FOR SELECT USING ({predicate} OR user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)")
            for command in ("INSERT", "UPDATE", "DELETE"):
                clause = f"WITH CHECK ({predicate})" if command == "INSERT" else f"USING ({predicate})"
                if command == "UPDATE":
                    clause += f" WITH CHECK ({predicate})"
                op.execute(f"CREATE POLICY tenant_{command.lower()} ON {q} FOR {command} {clause}")
        elif table == "audit_logs":
            op.execute(f"CREATE POLICY tenant_read ON {q} FOR SELECT USING ({predicate})")
            op.execute(f"CREATE POLICY tenant_insert ON {q} FOR INSERT WITH CHECK ({predicate})")
        else:
            op.execute(f"CREATE POLICY tenant_isolation ON {q} USING ({predicate}) WITH CHECK ({predicate})")
        op.create_unique_constraint(f"uq_{table}_tenant_id_id", table, ["tenant_id", "id"])
    # RLS alone cannot stop A rows from referencing B IDs. Add composite tenant foreign keys.
    for table in tables:
        for fk in inspector.get_foreign_keys(table):
            target = fk["referred_table"]
            columns = fk["constrained_columns"]
            if target in tables and fk["referred_columns"] == ["id"] and len(columns) == 1:
                name = f"fk_cp2_{table}_{columns[0]}"[:63]
                # NO ACTION avoids SET NULL clearing the owning tenant_id.
                op.create_foreign_key(name, table, target, ["tenant_id", columns[0]], ["tenant_id", "id"])
    # Stable indexed PostgreSQL FTS; other backends can implement the same service interface.
    for table, expression in {
        "leads": "coalesce(title,'')", "contacts": "coalesce(first_name,'') || ' ' || coalesce(last_name,'') || ' ' || coalesce(email,'')",
        "messages": "body", "tasks": "title", "campaigns": "name", "agent_definitions": "name"
    }.items():
        op.execute(f"CREATE INDEX ix_{table}_fts ON {quote(table)} USING gin(to_tsvector('simple', {expression}))")


def downgrade():
    raise RuntimeError("Security downgrade would expose tenant data and credentials; restore a reviewed backup instead")
