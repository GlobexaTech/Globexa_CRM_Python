"use client";
import { useRef, useState } from "react";
import { Plug, Plus } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import { Dialog } from "@/components/Dialog";
import { JobStatus } from "@/components/JobStatus";
import { ResourceState } from "@/components/ResourceState";
import { useConfirm } from "@/components/ConfirmProvider";
import { useSession } from "@/auth/SessionProvider";
import { useResource } from "@/hooks/useResource";
import { useAction } from "@/hooks/useAction";
import { operations, timestamp } from "@/services/operations";
import type {
  Integration,
  IntegrationStatus,
  LegacyPage,
  Provider,
  SyncLog,
} from "@/types/operations";

export default function IntegrationsPage() {
  const { session, can } = useSession();
  return (
    <IntegrationWorkspace
      key={`${session?.tenant_id}:${session?.version}`}
      can={can}
      tenantId={session?.tenant_id || ""}
    />
  );
}
function IntegrationWorkspace({
  can,
  tenantId,
}: {
  can: (permission: string) => boolean;
  tenantId: string;
}) {
  const providers = useResource<Provider[]>(
    "/operations/providers",
    can("integrations:read"),
  );
  const [page, setPage] = useState(1);
  const integrations = useResource<LegacyPage<Integration>>(
    `/integrations?page=${page}&page_size=20`,
    can("integrations:read"),
  );
  const [provider, setProvider] = useState("");
  const action = useAction();
  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />
      <section className="min-w-0 flex-1 p-4 sm:p-8">
        <header className="mb-6">
          <p className="text-xs tracking-[3px] text-[var(--blue)]">
            GLOBEXA CRM
          </p>
          <h1 className="mt-2 text-3xl font-semibold">Integrations</h1>
          <p className="crm-muted">
            Provider capabilities and connection status from your workspace
          </p>
        </header>
        {!can("integrations:read") ? (
          <p role="alert">Your role cannot read integrations.</p>
        ) : (
          <>
            <h2 className="mb-3 text-xl font-semibold">Available providers</h2>
            <ResourceState
              loading={providers.isLoading}
              error={providers.error}
              empty={providers.data?.length === 0}
              onRetry={() => void providers.refetch()}
            >
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {providers.data?.map((item) => (
                  <article className="card p-5" key={item.provider}>
                    <div className="flex items-center gap-3">
                      <Plug className="text-[var(--blue)]" />
                      <h3 className="text-lg font-semibold capitalize">
                        {item.provider.replaceAll("_", " ")}
                      </h3>
                    </div>
                    <p className="mt-3 text-sm">
                      {item.capabilities.length
                        ? `Capabilities: ${item.capabilities.join(", ").replaceAll("_", " ")}`
                        : "Not available in this release"}
                    </p>
                    {item.capabilities.length > 0 && (
                      <p className="crm-muted mt-2">
                        Application configuration and provider authorization are
                        required.{" "}
                        {item.live_verified
                          ? "Live verified by backend."
                          : "Live provider verification not recorded."}
                      </p>
                    )}
                    {item.capabilities.includes("connect") &&
                    can("integrations:write") ? (
                      <button
                        className="crm-secondary mt-4"
                        onClick={() => setProvider(item.provider)}
                      >
                        <Plus size={14} />
                        Add {item.provider} integration
                      </button>
                    ) : (
                      !item.capabilities.length && (
                        <span className="mt-4 inline-block rounded-lg bg-[var(--panel2)] px-3 py-2 text-sm">
                          Not available
                        </span>
                      )
                    )}
                  </article>
                ))}
              </div>
            </ResourceState>
            <div className="mb-3 mt-8 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-xl font-semibold">Workspace connections</h2>
              <button
                className="crm-secondary"
                onClick={() => void integrations.refetch()}
              >
                Refresh connections
              </button>
            </div>
            <ResourceState
              loading={integrations.isLoading}
              error={integrations.error}
              empty={integrations.data?.items.length === 0}
              onRetry={() => void integrations.refetch()}
            >
              <div className="grid gap-4 xl:grid-cols-2">
                {integrations.data?.items.map((item) => (
                  <IntegrationCard
                    key={item.id}
                    integration={item}
                    writable={can("integrations:write")}
                    tenantId={tenantId}
                  />
                ))}
              </div>
            </ResourceState>
            <nav className="crm-actions mt-4" aria-label="Integration pages">
              <button
                className="crm-secondary"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </button>
              <button
                className="crm-secondary"
                disabled={
                  !integrations.data || page >= integrations.data.total_pages
                }
                onClick={() => setPage(page + 1)}
              >
                Next
              </button>
            </nav>
          </>
        )}
        <Dialog
          open={!!provider}
          title={`Add ${provider} integration`}
          onClose={() => setProvider("")}
        >
          <form
            className="crm-form"
            onSubmit={(event) => {
              event.preventDefault();
              const name = String(
                new FormData(event.currentTarget).get("name"),
              ).trim();
              void action.run(async () => {
                const result = await operations.createIntegration(
                  provider,
                  name,
                );
                setProvider("");
                return result;
              });
            }}
          >
            <label className="crm-field">
              Connection name
              <input
                name="name"
                required
                maxLength={255}
                className="crm-input"
                placeholder="Team inbox"
              />
            </label>
            <p className="crm-muted">
              The integration is created pending authorization. Use Authorize on
              the connection to complete provider consent. Scheduled sync starts
              disabled.
            </p>
            {action.error && (
              <p role="alert" className="crm-error">
                {action.error}
              </p>
            )}
            <button className="crm-button" disabled={action.pending}>
              {action.pending ? "Creating…" : "Create integration"}
            </button>
          </form>
        </Dialog>
      </section>
    </main>
  );
}
function IntegrationCard({
  integration,
  writable,
  tenantId,
}: {
  integration: Integration;
  writable: boolean;
  tenantId: string;
}) {
  const status = useResource<IntegrationStatus>(
    `/operations/integrations/${integration.id}/status`,
  );
  const action = useAction();
  const [job, setJob] = useState("");
  const [logs, setLogs] = useState(false);
  const [notice, setNotice] = useState("");
  const [cursor, setCursor] = useState("");
  const key = useRef<{ cursor: string; value: string } | null>(null);
  const { confirm } = useConfirm();
  const current = status.data;
  async function authorize() {
    await action.run(async () => {
      const result = await operations.authorize(integration.id);
      const url = new URL(result.authorization_url);
      if (
        !(
          url.origin === window.location.origin &&
          url.pathname === "/integrations/callback"
        ) &&
        (url.protocol !== "https:" ||
          !["accounts.google.com", "login.microsoftonline.com"].includes(
            url.hostname,
          ))
      )
        throw new Error("Unexpected provider authorization destination.");
      sessionStorage.setItem(
        "globexa-oauth-correlation",
        JSON.stringify({
          integrationId: integration.id,
          tenantId,
          startedAt: Date.now(),
        }),
      );
      window.location.assign(url.toString());
      return result;
    });
  }
  async function sync() {
    if (key.current?.cursor !== cursor)
      key.current = { cursor, value: crypto.randomUUID() };
    const requestKey = key.current.value;
    await action.run(async () => {
      const result = await operations.sync(
        integration.id,
        requestKey,
        cursor || undefined,
      );
      setJob(result.id);
      key.current = null;
      return result;
    });
  }
  return (
    <article className="card space-y-3 p-5">
      <h3 className="text-lg font-semibold">{integration.name}</h3>
      <ResourceState
        loading={status.isLoading}
        error={status.error}
        onRetry={() => void status.refetch()}
      >
        {current && (
          <>
            <p className="text-sm">
              Status: <strong>{current.status}</strong>
              {current.status === "connected" && current.expired
                ? " · Credentials expired; refresh or reconnect"
                : ""}
            </p>
            <p className="crm-muted">
              Token expiry: {timestamp(current.expires_at)}
            </p>
            <p className="crm-muted">
              Supported operations:{" "}
              {current.capabilities.length
                ? current.capabilities.join(", ").replaceAll("_", " ")
                : "Not available"}
            </p>
          </>
        )}
      </ResourceState>
      <p className="text-sm">
        Last sync: {timestamp(integration.last_sync_at)} ·{" "}
        {integration.last_sync_status || "No sync recorded"}
      </p>
      <p className="crm-muted">
        {integration.sync_enabled
          ? `Scheduled sync every ${integration.sync_frequency_minutes} minutes`
          : "Scheduled sync disabled"}{" "}
        · {integration.records_synced} records synced
      </p>
      <div className="crm-actions">
        <button className="crm-secondary" onClick={() => void status.refetch()}>
          Check status
        </button>
        <button className="crm-secondary" onClick={() => setLogs(!logs)}>
          {logs ? "Hide sync history" : "Sync history"}
        </button>
        {writable && current?.capabilities.includes("connect") && (
          <button
            className="crm-button"
            disabled={action.pending}
            onClick={() => void authorize()}
          >
            {current.status === "connected" ? "Reconnect" : "Authorize"}
          </button>
        )}
        {writable && current?.status === "connected" && (
          <>
            <button
              className="crm-secondary"
              disabled={action.pending}
              onClick={() =>
                void action.run(async () => {
                  const result = await operations.refresh(integration.id);
                  setNotice("Backend confirmed credentials are valid.");
                  return result;
                })
              }
            >
              Refresh credentials
            </button>
            <button
              className="crm-danger"
              disabled={action.pending}
              onClick={() =>
                void (async () => {
                  if (
                    !(await confirm({
                      title: "Disconnect integration?",
                      message:
                        "Stored credentials will be removed and scheduled sync disabled. Pending deliveries may fail.",
                      confirmText: "Disconnect",
                      tone: "danger",
                    }))
                  )
                    return;
                  await action.run(async () => {
                    const result = await operations.disconnect(integration.id);
                    setNotice(
                      result.remote_revocation
                        ? "Disconnected. Provider revocation confirmed."
                        : "Disconnected locally. Provider account access may also need to be revoked in the provider settings.",
                    );
                    return result;
                  });
                })()
              }
            >
              Disconnect
            </button>
          </>
        )}
      </div>
      {writable &&
        current?.status === "connected" &&
        current.capabilities.includes("sync") && (
          <div className="crm-form">
            <label className="crm-field">
              Next-page cursor (optional)
              <input
                className="crm-input"
                value={cursor}
                maxLength={1000}
                onChange={(e) => setCursor(e.target.value)}
              />
            </label>
            <button
              className="crm-secondary"
              disabled={action.pending}
              onClick={() => void sync()}
            >
              Queue sync
            </button>
            <p className="crm-muted">
              Sync processes a bounded page. A continuation cursor is shown in
              the completed job result when more messages remain.
            </p>
          </div>
        )}
      {notice && (
        <p role="status" className="text-sm">
          {notice}
        </p>
      )}
      {action.error && (
        <p role="alert" className="crm-error">
          {action.error}
          {action.error.includes("unavailable")
            ? " Provider application configuration may be required."
            : ""}
        </p>
      )}
      {job && (
        <JobStatus jobId={job} onComplete={() => void status.refetch()} />
      )}
      {logs && <SyncHistory id={integration.id} />}
    </article>
  );
}
function SyncHistory({ id }: { id: string }) {
  const [page, setPage] = useState(1);
  const list = useResource<LegacyPage<SyncLog>>(
    `/integrations/${id}/sync-logs?page=${page}&page_size=10`,
  );
  return (
    <section>
      <h4 className="font-semibold">Sync history</h4>
      <ResourceState
        loading={list.isLoading}
        error={list.error}
        empty={list.data?.items.length === 0}
        onRetry={() => void list.refetch()}
      >
        <ul className="mt-2 space-y-2 text-sm">
          {list.data?.items.map((log) => (
            <li key={log.id} className="rounded-lg bg-[var(--panel2)] p-3">
              <strong>{log.status}</strong> · {timestamp(log.started_at)}
              <p>
                Processed: {log.records_processed ?? "Not supplied"} · Created:{" "}
                {log.records_created ?? "Not supplied"} · Updated:{" "}
                {log.records_updated ?? "Not supplied"}
              </p>
              {log.error_message && <p role="alert">{log.error_message}</p>}
            </li>
          ))}
        </ul>
      </ResourceState>
      <nav className="crm-actions mt-2" aria-label="Sync history pages">
        <button
          className="crm-secondary"
          disabled={page === 1}
          onClick={() => setPage(page - 1)}
        >
          Previous syncs
        </button>
        <button
          className="crm-secondary"
          disabled={!list.data || page >= list.data.total_pages}
          onClick={() => setPage(page + 1)}
        >
          Next syncs
        </button>
      </nav>
    </section>
  );
}
