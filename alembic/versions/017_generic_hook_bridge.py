"""Keep generic signed notification bridges separate from provider-native hooks."""

from alembic import op

revision = "017_generic_hook_bridge"
down_revision = "016_webhook_provider_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE OR REPLACE FUNCTION public.lookup_webhook(endpoint_id uuid)
    RETURNS TABLE(tenant_id uuid, secret text, provider text)
    LANGUAGE sql SECURITY DEFINER
    SET search_path = pg_catalog, pg_temp SET row_security = off
    AS $$ SELECT w.tenant_id, w.secret,
           CASE WHEN i.type::text = 'webhook' THEN 'webhook'
                ELSE COALESCE(i.config->>'provider', i.type::text, 'generic') END
           FROM public.webhook_endpoints w LEFT JOIN public.integrations i ON i.id = w.integration_id
           WHERE w.id = endpoint_id AND w.is_active AND (i.id IS NULL OR i.tenant_id = w.tenant_id) $$""")


def downgrade():
    raise RuntimeError("Provider identity rollback requires disabling affected webhooks first")
