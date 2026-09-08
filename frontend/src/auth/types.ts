export interface Workspace {
  id: string;
  name: string;
  slug: string;
  role: string;
  is_default: boolean;
}

/** Deliberately excludes backend tokens and provider credentials. */
export interface Session {
  user: { id: string; email: string; full_name: string; first_name: string; last_name: string };
  tenants: Workspace[];
  tenant_id: string;
  role: string;
  permissions: string[];
  version: string;
}
