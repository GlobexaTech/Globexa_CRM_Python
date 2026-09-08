"use client";
import { useState, type FormEvent } from "react";
import Sidebar from "@/components/Sidebar";
import { Dialog } from "@/components/Dialog";
import { ResourceState } from "@/components/ResourceState";
import { useConfirm } from "@/components/ConfirmProvider";
import { useSession } from "@/auth/SessionProvider";
import { useResource } from "@/hooks/useResource";
import { useAction } from "@/hooks/useAction";
import {
  workspace,
  localTime,
  type User,
  type Tenant,
  type Page,
} from "@/services/workspace";
const roles = [
  "owner",
  "admin",
  "sales_manager",
  "sales_executive",
  "marketing",
  "viewer",
  "ai_agent",
];
type Audit = {
  action: string;
  resource_type: string;
  resource_id: string;
  success: boolean;
  created_at: string;
};
type Entitlement = { feature: string; enabled: boolean; limit: number | null };
function value(form: FormData, key: string) {
  return String(form.get(key) ?? "").trim();
}
export default function SettingsPage() {
  const { session, can, refreshSession } = useSession();
  const admin = session?.role === "owner" || session?.role === "admin";
  const [tab, setTab] = useState("profile");
  const [page, setPage] = useState(1);
  const [roleFilter, setRoleFilter] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const { confirm } = useConfirm();
  const action = useAction();
  const profile = useResource<User>("/auth/me");
  const tenant = useResource<Tenant>(
    "/tenants/me",
    tab === "workspace" || tab === "plan",
  );
  const users = useResource<Page<User>>(
    `/users?page=${page}&page_size=20${roleFilter ? `&role=${roleFilter}` : ""}`,
    can("users:read") && tab === "team",
  );
  const audit = useResource<Audit[]>(
    "/foundation/audit",
    admin && tab === "audit",
  );
  const entitlements = useResource<Entitlement[]>(
    "/foundation/entitlements",
    tab === "plan",
  );
  const tabs = [
    ["profile", "Profile", true],
    ["workspace", "Workspace", can("tenant:settings")],
    ["team", "Team", can("users:read")],
    ["plan", "Plan and entitlements", can("billing:read")],
    ["audit", "Audit log", admin],
  ] as const;
  const assignable = roles.filter(
    (role) => session?.role === "owner" || !["owner", "admin"].includes(role),
  );
  function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void action.run(async () => {
      await workspace.updateProfile({
        full_name: value(form, "full_name"),
        phone: value(form, "phone") || null,
        timezone: value(form, "timezone"),
        locale: value(form, "locale"),
      });
      await refreshSession();
    });
  }
  return (
    <main className="page-shell">
      <Sidebar />
      <section className="page-content">
        <p className="page-eyebrow">SYSTEM</p>
        <h1 className="page-title">Settings</h1>
        <p className="page-subtitle">
          Manage your profile and the workspace controls available to your role.
        </p>
        <div className="crm-actions my-6" aria-label="Settings sections">
          {tabs
            .filter(([, , allowed]) => allowed)
            .map(([id, label]) => (
              <button
                key={id}
                className={tab === id ? "crm-button" : "crm-secondary"}
                aria-pressed={tab === id}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
        </div>
        {action.error && (
          <p className="crm-error mb-4" role="alert">
            {action.error}
          </p>
        )}
        {action.success && (
          <p className="text-green-800 mb-4" role="status">
            Saved to the workspace.
          </p>
        )}
        {tab === "profile" && (
          <ResourceState
            loading={profile.isLoading}
            error={profile.error}
            onRetry={profile.refetch}
          >
            {profile.data && (
              <form
                className="card p-6 crm-form max-w-xl"
                key={profile.data.updated_at}
                onSubmit={saveProfile}
              >
                <h2 className="text-lg font-semibold">Your profile</h2>
                <p className="crm-muted">{profile.data.email}</p>
                <label className="crm-field">
                  Full name
                  <input
                    className="crm-input"
                    name="full_name"
                    defaultValue={profile.data.full_name}
                    required
                    maxLength={255}
                  />
                </label>
                <label className="crm-field">
                  Phone
                  <input
                    className="crm-input"
                    name="phone"
                    type="tel"
                    defaultValue={profile.data.phone ?? ""}
                  />
                </label>
                <label className="crm-field">
                  Timezone
                  <select
                    className="crm-input"
                    name="timezone"
                    defaultValue={profile.data.timezone}
                  >
                    <option>UTC</option>
                    <option>Asia/Calcutta</option>
                    <option>Asia/Kolkata</option>
                    <option>America/New_York</option>
                    <option>Europe/London</option>
                    {![
                      "UTC",
                      "Asia/Calcutta",
                      "Asia/Kolkata",
                      "America/New_York",
                      "Europe/London",
                    ].includes(profile.data.timezone ?? "") && (
                      <option>{profile.data.timezone}</option>
                    )}
                  </select>
                </label>
                <label className="crm-field">
                  Locale
                  <select
                    className="crm-input"
                    name="locale"
                    defaultValue={profile.data.locale}
                  >
                    <option value="en">English</option>
                    <option value="hi">Hindi</option>
                  </select>
                </label>
                <button className="crm-button" disabled={action.pending}>
                  Save profile
                </button>
              </form>
            )}
          </ResourceState>
        )}
        {tab === "workspace" && can("tenant:settings") && (
          <ResourceState
            loading={tenant.isLoading}
            error={tenant.error}
            onRetry={tenant.refetch}
          >
            {tenant.data && (
              <form
                className="card p-6 crm-form max-w-xl"
                key={tenant.data.updated_at}
                onSubmit={(event) => {
                  event.preventDefault();
                  const form = new FormData(event.currentTarget);
                  void action.run(async () => {
                    await workspace.updateTenant(session!.tenant_id, {
                      name: value(form, "name"),
                      domain: value(form, "domain") || null,
                    });
                    await refreshSession();
                  });
                }}
              >
                <h2 className="text-lg font-semibold">Workspace details</h2>
                <p className="crm-muted">{tenant.data.slug}</p>
                <label className="crm-field">
                  Workspace name
                  <input
                    className="crm-input"
                    name="name"
                    required
                    maxLength={255}
                    defaultValue={tenant.data.name}
                  />
                </label>
                <label className="crm-field">
                  Domain
                  <input
                    className="crm-input"
                    name="domain"
                    maxLength={255}
                    defaultValue={tenant.data.domain ?? ""}
                  />
                </label>
                <button className="crm-button" disabled={action.pending}>
                  Save workspace
                </button>
              </form>
            )}
          </ResourceState>
        )}
        {tab === "team" && can("users:read") && (
          <>
            <div className="crm-actions mb-5">
              <label className="crm-field">
                Filter team by role
                <select
                  className="crm-input"
                  value={roleFilter}
                  onChange={(event) => {
                    setRoleFilter(event.target.value);
                    setPage(1);
                  }}
                >
                  <option value="">All roles</option>
                  {roles.map((role) => (
                    <option key={role} value={role}>
                      {role.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </label>
              {can("users:write") && (
                <button
                  className="crm-button"
                  onClick={() => setCreating(true)}
                >
                  Add team member
                </button>
              )}
            </div>
            <ResourceState
              loading={users.isLoading}
              error={users.error}
              empty={users.data?.total === 0}
              onRetry={users.refetch}
            >
              <div
                className="crm-table-wrap"
                role="region"
                aria-label="Team members"
                tabIndex={0}
              >
                <table>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Email</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.data?.items.map((user) => (
                      <tr key={user.id}>
                        <td>{user.full_name}</td>
                        <td>{user.email}</td>
                        <td>{user.is_active ? "Active" : "Inactive"}</td>
                        <td>
                          <div className="crm-actions">
                            {admin && user.id !== session?.user.id && (
                              <button
                                className="crm-secondary"
                                onClick={() => setEditing(user)}
                              >
                                Change role
                              </button>
                            )}
                            {can("users:delete") &&
                              user.id !== session?.user.id && (
                                <button
                                  className="crm-danger"
                                  disabled={action.pending}
                                  onClick={() =>
                                    void action.run(async () => {
                                      if (
                                        await confirm({
                                          title: "Remove team member?",
                                          message: `Remove ${user.full_name} from this workspace? Their access to other workspaces is unchanged.`,
                                          tone: "danger",
                                          confirmText: "Remove member",
                                        })
                                      )
                                        await workspace.removeUser(user.id);
                                    })
                                  }
                                >
                                  Remove
                                </button>
                              )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="crm-actions mt-4">
                <button
                  className="crm-secondary"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  Previous team page
                </button>
                <span>
                  Page {page} of {users.data?.total_pages || 1}
                </span>
                <button
                  className="crm-secondary"
                  disabled={page >= (users.data?.total_pages ?? 1)}
                  onClick={() => setPage(page + 1)}
                >
                  Next team page
                </button>
              </div>
            </ResourceState>
            <p className="crm-muted mt-4">
              The server enforces role assignment rules and protects the last
              owner.
            </p>
          </>
        )}
        {tab === "plan" && can("billing:read") && (
          <>
            <ResourceState
              loading={tenant.isLoading}
              error={tenant.error}
              onRetry={tenant.refetch}
            >
              <div className="card p-6">
                <h2 className="text-lg font-semibold">Current plan</h2>
                <p className="mt-3">
                  {tenant.data?.subscription?.package ?? "No subscription"} ·{" "}
                  {tenant.data?.subscription?.status ?? "Unavailable"}
                </p>
                <p className="crm-muted mt-2">
                  Billing and plan details are read-only here.
                </p>
              </div>
            </ResourceState>
            <ResourceState
              loading={entitlements.isLoading}
              error={entitlements.error}
              onRetry={entitlements.refetch}
            >
              <div className="crm-table-wrap mt-5">
                <table>
                  <thead>
                    <tr>
                      <th>Feature</th>
                      <th>Enabled</th>
                      <th>Limit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entitlements.data?.map((item) => (
                      <tr key={item.feature}>
                        <td>{item.feature.replaceAll("_", " ")}</td>
                        <td>{item.enabled ? "Yes" : "No"}</td>
                        <td>
                          {item.limit == null ? "No fixed limit" : item.limit}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </ResourceState>
          </>
        )}
        {tab === "audit" && admin && (
          <ResourceState
            loading={audit.isLoading}
            error={audit.error}
            empty={audit.data?.length === 0}
            onRetry={audit.refetch}
          >
            <p className="crm-muted mb-4">
              Latest 100 events in this workspace.
            </p>
            <div
              className="crm-table-wrap"
              role="region"
              aria-label="Audit entries"
              tabIndex={0}
            >
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Action</th>
                    <th>Resource</th>
                    <th>Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.data?.map((entry, index) => (
                    <tr key={`${entry.created_at}:${index}`}>
                      <td>{localTime(entry.created_at)}</td>
                      <td>{entry.action}</td>
                      <td>{entry.resource_type}</td>
                      <td>{entry.success ? "Success" : "Failed"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </ResourceState>
        )}
        <Dialog
          open={creating}
          title="Add team member"
          onClose={() => setCreating(false)}
        >
          <form
            className="crm-form"
            onSubmit={(event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              void action.run(async () => {
                await workspace.createUser({
                  full_name: value(form, "full_name"),
                  email: value(form, "email"),
                  password: String(form.get("password")),
                  timezone: "UTC",
                  locale: "en",
                  role: value(form, "role"),
                });
                setCreating(false);
              });
            }}
          >
            <label className="crm-field">
              Full name
              <input
                className="crm-input"
                name="full_name"
                required
                maxLength={255}
              />
            </label>
            <label className="crm-field">
              Email
              <input
                className="crm-input"
                name="email"
                type="email"
                required
                autoComplete="off"
              />
            </label>
            <label className="crm-field">
              Initial password
              <input
                className="crm-input"
                name="password"
                type="password"
                required
                minLength={8}
                maxLength={72}
                autoComplete="new-password"
              />
            </label>
            <label className="crm-field">
              Role
              <select
                className="crm-input"
                name="role"
                defaultValue="sales_executive"
              >
                {assignable.map((role) => (
                  <option key={role} value={role}>
                    {role.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
            {action.error && (
              <p role="alert" className="crm-error">
                {action.error}
              </p>
            )}
            <button className="crm-button" disabled={action.pending}>
              Create team member
            </button>
          </form>
        </Dialog>
        <Dialog
          open={!!editing}
          title="Change membership role"
          onClose={() => setEditing(null)}
        >
          <form
            className="crm-form"
            onSubmit={(event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              void action.run(async () => {
                await workspace.role(editing!.id, value(form, "role"));
                setEditing(null);
              });
            }}
          >
            <p>
              {editing?.full_name} · {editing?.email}
            </p>
            <label className="crm-field">
              New role
              <select
                className="crm-input"
                name="role"
                required
                defaultValue=""
              >
                <option value="" disabled>
                  Choose a role
                </option>
                {assignable.map((role) => (
                  <option key={role} value={role}>
                    {role.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
            {action.error && (
              <p role="alert" className="crm-error">
                {action.error}
              </p>
            )}
            <button className="crm-button" disabled={action.pending}>
              Save role
            </button>
          </form>
        </Dialog>
      </section>
    </main>
  );
}
