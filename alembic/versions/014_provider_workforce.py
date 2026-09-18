"""Durable provider and workforce schema; frozen DDL with tenant ownership guards."""

from alembic import op
import sqlalchemy as sa

revision = "014_provider_workforce"
down_revision = "013_merge_rls_heads"
branch_labels = None
depends_on = None

SCHEMA_DDL = [
    "CREATE TABLE dead_letter_events (\n\tprovider VARCHAR(100) NOT NULL, \n\tevent_type VARCHAR(100) NOT NULL, \n\tprovider_event_id VARCHAR(255), \n\tpayload JSONB NOT NULL, \n\treceived_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tprocessed_at TIMESTAMP WITH TIME ZONE, \n\terror_message TEXT, \n\tretry_count INTEGER NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)",
    "CREATE INDEX ix_dead_letter_events_tenant_id ON dead_letter_events (tenant_id)",
    "CREATE TABLE agent_executions (\n\tactor_id UUID NOT NULL, \n\tagent_name VARCHAR(100) NOT NULL, \n\ttask_type VARCHAR(100) NOT NULL, \n\ttask JSONB NOT NULL, \n\tstate VARCHAR(30) NOT NULL, \n\tidempotency_key VARCHAR(255) NOT NULL, \n\tparent_id UUID, \n\tjob_id UUID, \n\tattempts INTEGER NOT NULL, \n\tcancel_requested BOOLEAN NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\tfailed_at TIMESTAMP WITH TIME ZONE, \n\tmodel VARCHAR(100), \n\tprovider VARCHAR(100), \n\ttools_used JSONB NOT NULL, \n\tresult JSONB, \n\terror_message TEXT, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, idempotency_key), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tFOREIGN KEY(parent_id) REFERENCES agent_executions (id), \n\tFOREIGN KEY(job_id) REFERENCES operation_jobs (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)",
    "CREATE INDEX ix_agent_executions_tenant_id ON agent_executions (tenant_id)",
    "CREATE TABLE sync_cursors (\n\tintegration_id UUID NOT NULL, \n\tcursor_type VARCHAR(50) NOT NULL, \n\tcursor_value TEXT NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, integration_id, cursor_type), \n\tFOREIGN KEY(integration_id) REFERENCES integrations (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)",
    "CREATE INDEX ix_sync_cursors_tenant_id ON sync_cursors (tenant_id)",
    "CREATE TABLE sync_jobs (\n\tintegration_id UUID NOT NULL, \n\tsync_type VARCHAR(20) NOT NULL, \n\tcursor TEXT, \n\tstatus VARCHAR(20) NOT NULL, \n\terror_message TEXT, \n\trecords_processed INTEGER NOT NULL, \n\trecords_created INTEGER NOT NULL, \n\trecords_updated INTEGER NOT NULL, \n\trecords_failed INTEGER NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(integration_id) REFERENCES integrations (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)",
    "CREATE INDEX ix_sync_jobs_tenant_id ON sync_jobs (tenant_id)",
    "CREATE TABLE agent_memory (\n\tactor_id UUID NOT NULL, \n\tapproved_by UUID, \n\texecution_id UUID, \n\tagent_name VARCHAR(100) NOT NULL, \n\tmemory_type VARCHAR(20) NOT NULL, \n\tkey VARCHAR(255) NOT NULL, \n\tvalue JSONB NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, agent_name, memory_type, key), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tFOREIGN KEY(approved_by) REFERENCES users (id), \n\tFOREIGN KEY(execution_id) REFERENCES agent_executions (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)",
    "CREATE INDEX ix_agent_memory_tenant_id ON agent_memory (tenant_id)",
    "CREATE TABLE approval_requests (\n\tagent_name VARCHAR(100) NOT NULL, \n\trequesting_user_id UUID NOT NULL, \n\texecution_id UUID, \n\taction_type VARCHAR(100) NOT NULL, \n\ttarget VARCHAR(255), \n\tproposed_action JSONB NOT NULL, \n\taction_hash VARCHAR(64) NOT NULL, \n\tidempotency_key VARCHAR(255) NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE, \n\tdecided_at TIMESTAMP WITH TIME ZONE, \n\tdecided_by UUID, \n\trejection_reason TEXT, \n\texecution_result JSONB, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, idempotency_key), \n\tFOREIGN KEY(requesting_user_id) REFERENCES users (id), \n\tFOREIGN KEY(execution_id) REFERENCES agent_executions (id), \n\tFOREIGN KEY(decided_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)",
    "CREATE INDEX ix_approval_requests_tenant_id ON approval_requests (tenant_id)",
]
NEW_TABLES = [
    "dead_letter_events",
    "agent_executions",
    "sync_cursors",
    "sync_jobs",
    "agent_memory",
    "approval_requests",
]


def upgrade():
    for statement in SCHEMA_DDL:
        op.execute(statement)
    op.add_column(
        "webhook_receipts",
        sa.Column("state", sa.String(30), nullable=False, server_default="pending"),
    )
    op.add_column(
        "webhook_receipts", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "webhook_receipts",
        sa.Column(
            "payload",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("webhook_receipts", sa.Column("error_code", sa.String(100)))
    op.add_column("webhook_receipts", sa.Column("processed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "ai_usage_logs", sa.Column("execution_id", sa.dialects.postgresql.UUID(as_uuid=True))
    )
    op.create_index("ix_ai_usage_logs_execution_id", "ai_usage_logs", ["execution_id"])
    for column in ("input_tokens", "output_tokens", "total_tokens"):
        op.alter_column(
            "ai_usage_logs", column, existing_type=sa.Integer(), nullable=True, server_default=None
        )
    inspector = sa.inspect(op.get_bind())
    quote = op.get_bind().dialect.identifier_preparer.quote
    predicate = "tenant_id = current_tenant_id()"
    for name in NEW_TABLES:
        q = quote(name)
        op.execute(f"ALTER TABLE {q} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {q} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {q} FOR ALL USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.create_unique_constraint(f"uq_{name}_tenant_id_id", name, ["tenant_id", "id"])
    for name in NEW_TABLES:
        for fk in inspector.get_foreign_keys(name):
            target = fk["referred_table"]
            columns = fk["constrained_columns"]
            if (
                len(columns) == 1
                and fk["referred_columns"] == ["id"]
                and any(c["name"] == "tenant_id" for c in inspector.get_columns(target))
            ):
                op.create_foreign_key(
                    f"fk_cp56_{name}_{columns[0]}"[:63],
                    name,
                    target,
                    ["tenant_id", columns[0]],
                    ["tenant_id", "id"],
                )
    op.create_foreign_key(
        "fk_cp56_ai_usage_execution",
        "ai_usage_logs",
        "agent_executions",
        ["tenant_id", "execution_id"],
        ["tenant_id", "id"],
    )
    # A permissive policy cannot weaken this mandatory tenant equality guard.
    for name in inspector.get_table_names(schema="public"):
        if name in {"memberships", "users", "tenants"}:
            continue  # Existing identity-discovery policies remain independently enforced.
        if not any(c["name"] == "tenant_id" for c in inspector.get_columns(name, schema="public")):
            continue
        q = quote(name)
        policy = quote(name + "_tenant_isolation")
        op.execute(f"ALTER TABLE {q} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {q} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {q}")
        op.execute(
            f"CREATE POLICY {policy} ON {q} AS RESTRICTIVE FOR ALL USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade():
    raise RuntimeError("Checkpoint 5/6 downgrade requires an explicit data retention plan")
