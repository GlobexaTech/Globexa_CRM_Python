"""Restrict shared identities and expose narrow authenticated-bootstrap lookups."""
from alembic import op

revision = "008_identity_boundaries"
down_revision = "007_checkpoint2_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION public.auth_lookup_user(email_input text)
    RETURNS SETOF public.users LANGUAGE sql SECURITY DEFINER
    SET search_path = pg_catalog, pg_temp SET row_security = off
    AS $$ SELECT * FROM public.users WHERE email = email_input LIMIT 1 $$""")
    op.execute("""CREATE FUNCTION public.tenant_slug_exists(slug_input text)
    RETURNS boolean LANGUAGE sql SECURITY DEFINER
    SET search_path = pg_catalog, pg_temp SET row_security = off
    AS $$ SELECT EXISTS(SELECT 1 FROM public.tenants WHERE slug = slug_input) $$""")
    op.execute("""CREATE FUNCTION public.lookup_webhook(endpoint_id uuid)
    RETURNS TABLE(tenant_id uuid, secret text, provider text)
    LANGUAGE sql SECURITY DEFINER
    SET search_path = pg_catalog, pg_temp SET row_security = off
    AS $$ SELECT w.tenant_id, w.secret, COALESCE(i.type::text, 'generic')
           FROM public.webhook_endpoints w LEFT JOIN public.integrations i ON i.id = w.integration_id
           WHERE w.id = endpoint_id AND w.is_active AND (i.id IS NULL OR i.tenant_id = w.tenant_id) $$""")
    op.execute("""CREATE FUNCTION public.active_tenant_ids()
    RETURNS SETOF uuid LANGUAGE sql SECURITY DEFINER
    SET search_path = pg_catalog, pg_temp SET row_security = off
    AS $$ SELECT id FROM public.tenants WHERE is_active $$""")
    for signature in ("auth_lookup_user(text)", "tenant_slug_exists(text)", "lookup_webhook(uuid)", "active_tenant_ids()"):
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
    for table in ("users", "tenants"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    actor = "NULLIF(current_setting('app.current_user_id', true),'')::uuid"
    tenant = "NULLIF(current_setting('app.current_tenant_id', true),'')::uuid"
    user_scope = f"id = {actor} OR EXISTS(SELECT 1 FROM public.memberships m WHERE m.user_id=users.id AND m.tenant_id={tenant})"
    op.execute(f"CREATE POLICY identity_read ON users FOR SELECT USING ({user_scope})")
    op.execute(f"""CREATE POLICY identity_insert ON users FOR INSERT WITH CHECK
        (NOT is_superuser AND (id={actor} OR EXISTS(SELECT 1 FROM public.memberships m
        WHERE m.user_id={actor} AND m.tenant_id={tenant} AND m.role IN ('owner','admin','sales_manager'))))""")
    op.execute(f"CREATE POLICY identity_update ON users FOR UPDATE USING (id={actor}) WITH CHECK (id={actor} AND NOT is_superuser)")
    tenant_scope = f"id={tenant} OR EXISTS(SELECT 1 FROM public.memberships m WHERE m.tenant_id=tenants.id AND m.user_id={actor})"
    op.execute(f"CREATE POLICY workspace_read ON tenants FOR SELECT USING ({tenant_scope})")
    op.execute(f"CREATE POLICY workspace_insert ON tenants FOR INSERT WITH CHECK (id={tenant})")
    op.execute(f"CREATE POLICY workspace_update ON tenants FOR UPDATE USING (id={tenant}) WITH CHECK (id={tenant})")


def downgrade():
    raise RuntimeError("Identity security downgrade requires a reviewed restore")
