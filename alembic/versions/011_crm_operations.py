"""Functional CRM operations; frozen DDL, preserving migrations 001-010."""

from alembic import op
import sqlalchemy as sa

revision = "011_crm_operations"
down_revision = "010_auth_audit"
branch_labels = None
depends_on = None

SCHEMA_DDL = [
    "ALTER TABLE workflows ADD COLUMN owner_id UUID",
    "ALTER TABLE workflows ADD CONSTRAINT fk_cp3_workflows_owner_id FOREIGN KEY (owner_id) REFERENCES users (id)",
    "ALTER TABLE workflow_execution_logs ADD COLUMN workflow_version INTEGER DEFAULT 1 NOT NULL",
    "ALTER TABLE workflow_execution_logs ADD COLUMN attempts INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE workflow_execution_logs ADD COLUMN snapshot JSONB DEFAULT '{}'::jsonb NOT NULL",
    "ALTER TABLE conversations ADD COLUMN channel VARCHAR(30) DEFAULT 'email' NOT NULL",
    "ALTER TABLE conversations ADD COLUMN contact_id UUID",
    "ALTER TABLE conversations ADD CONSTRAINT fk_cp3_conversations_contact_id FOREIGN KEY (tenant_id, contact_id) REFERENCES contacts (tenant_id, id)",
    "ALTER TABLE conversations ADD COLUMN company_id UUID",
    "ALTER TABLE conversations ADD CONSTRAINT fk_cp3_conversations_company_id FOREIGN KEY (tenant_id, company_id) REFERENCES companies (tenant_id, id)",
    "ALTER TABLE conversations ADD COLUMN lead_id UUID",
    "ALTER TABLE conversations ADD CONSTRAINT fk_cp3_conversations_lead_id FOREIGN KEY (tenant_id, lead_id) REFERENCES leads (tenant_id, id)",
    "ALTER TABLE conversations ADD COLUMN integration_id UUID",
    "ALTER TABLE conversations ADD CONSTRAINT fk_cp3_conversations_integration_id FOREIGN KEY (tenant_id, integration_id) REFERENCES integrations (tenant_id, id)",
    "ALTER TABLE conversations ADD COLUMN provider_thread_id VARCHAR(255)",
    "ALTER TABLE conversations ADD COLUMN last_message_at TIMESTAMP WITH TIME ZONE",
    "ALTER TABLE conversations ADD COLUMN unread_count INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE messages ADD COLUMN direction VARCHAR(20) DEFAULT 'inbound' NOT NULL",
    "ALTER TABLE messages ADD COLUMN status VARCHAR(30) DEFAULT 'received' NOT NULL",
    "ALTER TABLE messages ADD COLUMN sender VARCHAR(255)",
    "ALTER TABLE messages ADD COLUMN recipient VARCHAR(255)",
    "ALTER TABLE messages ADD COLUMN provider_message_id VARCHAR(255)",
    "ALTER TABLE messages ADD COLUMN attachments JSONB DEFAULT '[]'::jsonb NOT NULL",
    "ALTER TABLE messages ADD COLUMN occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL",
    "ALTER TABLE messages ADD COLUMN idempotency_key VARCHAR(255)",
    "CREATE TABLE operation_jobs (\n\tkind VARCHAR(40) NOT NULL, \n\tactor_id UUID, \n\tstatus VARCHAR(30) NOT NULL, \n\tidempotency_key VARCHAR(255) NOT NULL, \n\tpayload JSONB NOT NULL, \n\tresult JSONB NOT NULL, \n\tattempts INTEGER NOT NULL, \n\terror_code VARCHAR(100), \n\tavailable_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tclaimed_at TIMESTAMP WITH TIME ZONE, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, idempotency_key), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)",
    "CREATE INDEX ix_operation_jobs_tenant_id ON operation_jobs (tenant_id)",
    "CREATE TABLE ai_insights (\n\tjob_id UUID NOT NULL, \n\tcapability VARCHAR(50) NOT NULL, \n\tentity_type VARCHAR(30) NOT NULL, \n\tentity_id UUID, \n\toutput JSONB NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, job_id), \n\tFOREIGN KEY(job_id) REFERENCES operation_jobs (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)",
    "CREATE INDEX ix_ai_insights_tenant_id ON ai_insights (tenant_id)",
    "CREATE TABLE analytics_events (\n\tevent_id UUID, \n\tevent_type VARCHAR(100) NOT NULL, \n\tentity_id VARCHAR(100) NOT NULL, \n\tvalue FLOAT, \n\tdimensions JSONB NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, event_id), \n\tFOREIGN KEY(event_id) REFERENCES domain_events (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)",
    "CREATE INDEX ix_analytics_events_tenant_id ON analytics_events (tenant_id)",
    "CREATE TABLE oauth_sessions (\n\tintegration_id UUID NOT NULL, \n\tactor_id UUID NOT NULL, \n\tstate_hash VARCHAR(64) NOT NULL, \n\tverifier TEXT NOT NULL, \n\tredirect_uri TEXT NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tconsumed_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(integration_id) REFERENCES integrations (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tUNIQUE (state_hash), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)",
    "CREATE INDEX ix_oauth_sessions_tenant_id ON oauth_sessions (tenant_id)",
    "CREATE TABLE workflow_revisions (\n\tworkflow_id UUID NOT NULL, \n\tversion INTEGER NOT NULL, \n\tdefinition JSONB NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, workflow_id, version), \n\tFOREIGN KEY(workflow_id) REFERENCES workflows (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)",
    "CREATE INDEX ix_workflow_revisions_tenant_id ON workflow_revisions (tenant_id)",
    "CREATE TABLE conversation_participants (\n\tconversation_id UUID NOT NULL, \n\taddress VARCHAR(255) NOT NULL, \n\tname VARCHAR(255), \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, conversation_id, address), \n\tFOREIGN KEY(conversation_id) REFERENCES conversations (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)",
    "CREATE INDEX ix_conversation_participants_tenant_id ON conversation_participants (tenant_id)",
    "ALTER TABLE messages ADD CONSTRAINT uq_messages_tenant_id_idempotency_key UNIQUE (tenant_id,idempotency_key)",
    "ALTER TABLE oauth_sessions ADD CONSTRAINT ck_oauth_verifier_encrypted CHECK (verifier LIKE 'enc:v1:%')",
    "ALTER TABLE messages ADD CONSTRAINT ck_message_direction CHECK (direction IN ('inbound','outbound'))",
    "ALTER TABLE messages ADD CONSTRAINT ck_message_status CHECK (status IN ('received','queued','sending','sent','delivered','failed','unknown','draft','suppressed'))",
    "ALTER TABLE conversations ADD CONSTRAINT ck_conversation_channel CHECK (channel IN ('email','whatsapp','social'))",
    "ALTER TABLE conversations ADD CONSTRAINT ck_unread_count CHECK (unread_count >= 0)",
    "CREATE INDEX ix_operation_jobs_pending ON operation_jobs (tenant_id, status, available_at)",
    "CREATE INDEX ix_analytics_events_time ON analytics_events (tenant_id,event_type,created_at)",
    "CREATE INDEX ix_companies_fts ON companies USING gin(to_tsvector('simple', name))",
    "CREATE INDEX ix_deals_fts ON deals USING gin(to_tsvector('simple', title))",
    "CREATE INDEX ix_notes_fts ON notes USING gin(to_tsvector('simple', content))",
    "CREATE INDEX ix_conversations_fts ON conversations USING gin(to_tsvector('simple', subject))",
]

NEW_TABLES = [
    "ai_insights",
    "analytics_events",
    "conversation_participants",
    "oauth_sessions",
    "operation_jobs",
    "workflow_revisions",
]


def upgrade():
    for statement in SCHEMA_DDL:
        op.execute(statement)
    predicate = (
        "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    )
    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.create_unique_constraint(
            f"uq_{table}_tenant_id_id", table, ["tenant_id", "id"]
        )
    inspector = sa.inspect(op.get_bind())
    for table in NEW_TABLES:
        for fk in inspector.get_foreign_keys(table):
            target = fk["referred_table"]
            cols = fk["constrained_columns"]
            if (
                len(cols) == 1
                and fk["referred_columns"] == ["id"]
                and any(c["name"] == "tenant_id" for c in inspector.get_columns(target))
            ):
                op.create_foreign_key(
                    f"fk_cp3_{table}_{cols[0]}"[:63],
                    table,
                    target,
                    ["tenant_id", cols[0]],
                    ["tenant_id", "id"],
                )


def downgrade():
    raise RuntimeError(
        "Reviewed backup restore required: operational/audit data must not be silently discarded"
    )
