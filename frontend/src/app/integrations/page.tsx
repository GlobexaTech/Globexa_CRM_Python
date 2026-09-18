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
                    {item.provider_state && (
                      <p className="mt-2 text-sm">
                        Provider configuration:{" "}
                        <strong>{item.provider_state}</strong>
                      </p>
                    )}
                    {item.capabilities.length > 0 && (
                      <p className="crm-muted mt-2">
                        Application configuration and provider authorization are
                        required.{" "}
                        {item.live_verified
                          ? "Live verified by backend."
                          : "Live provider verification not recorded."}
                      </p>
                    )}
                    {(item.capabilities.includes("connect") ||
                      ["whatsapp", "apollo"].includes(item.provider)) &&
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
              const form = new FormData(event.currentTarget);
              const config = Object.fromEntries(
                [
                  "phone_number_id",
                  "page_id",
                  "form_id",
                  "customer_id",
                ].flatMap((field) => {
                  const value = String(form.get(field) || "").trim();
                  return value ? [[field, value]] : [];
                }),
              );
              void action.run(async () => {
                const result = await operations.createIntegration(
                  provider,
                  name,
                  config,
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
            {(
              {
                whatsapp: ["phone_number_id"],
                meta: ["page_id", "form_id"],
                instagram: ["page_id"],
                google_ads: ["customer_id", "form_id"],
              } as Record<string, string[]>
            )[provider]?.map((field) => (
              <label className="crm-field" key={field}>
                {field.replaceAll("_", " ")}
                <input
                  name={field}
                  className="crm-input"
                  required
                  maxLength={255}
                />
              </label>
            ))}
            <p className="crm-muted">
              The integration is created pending authorization. OAuth providers
              require consent; API providers require encrypted credentials and a
              successful health check. Scheduled sync starts disabled.
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
  const [configure, setConfigure] = useState(false);
  const key = useRef<string | null>(null);
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
          ![
            "accounts.google.com",
            "login.microsoftonline.com",
            "www.facebook.com",
            "www.linkedin.com",
          ].includes(url.hostname))
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
    key.current ??= crypto.randomUUID();
    const requestKey = key.current;
    await action.run(async () => {
      const result = await operations.sync(integration.id, requestKey);
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
            {integration.provider_state && (
              <p className="text-sm">
                Provider state: <strong>{integration.provider_state}</strong>
              </p>
            )}
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
        {writable &&
          ["whatsapp", "apollo"].includes(integration.provider || "") && (
            <button
              className="crm-secondary"
              onClick={() => setConfigure(true)}
            >
              Configure API credentials
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
            <button
              className="crm-secondary"
              disabled={action.pending}
              onClick={() => void sync()}
            >
              Queue sync
            </button>
            <p className="crm-muted">
              Sync resumes from the last successfully stored provider
              checkpoint. The server owns pagination and continuation cursors.
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
      {logs && <ProviderHistory id={integration.id} writable={writable} />}
      <Dialog
        open={configure}
        title="Configure provider credentials"
        onClose={() => setConfigure(false)}
      >
        {configure && (
          <CredentialForm
            integration={integration}
            onSaved={() => {
              setConfigure(false);
              setNotice(
                "Provider health check completed. Connection state was refreshed from the backend.",
              );
            }}
          />
        )}
      </Dialog>
    </article>
  );
}
function CredentialForm({
  integration,
  onSaved,
}: {
  integration: Integration;
  onSaved: () => void;
}) {
  const action = useAction();
  const credentialName = useRef<string | null>(null);
  const [credentialId, setCredentialId] = useState("");
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    await action.run(async () => {
      let id = credentialId;
      if (!id) {
        const value = String(new FormData(form).get("credential") || "");
        credentialName.current ??= `provider-access-${crypto.randomUUID()}`;
        const credential = await operations.storeCredential(
          integration.id,
          {
            [integration.provider === "apollo" ? "api_key" : "access_token"]:
              value,
          },
          credentialName.current,
        );
        id = credential.id;
        setCredentialId(id);
        form.reset();
      }
      const result = await operations.configure(integration.id, id);
      onSaved();
      return result;
    });
  }
  return (
    <form className="crm-form" onSubmit={submit}>
      {!credentialId && (
        <label className="crm-field">
          {integration.provider === "apollo" ? "API key" : "Access token"}
          <input
            name="credential"
            className="crm-input"
            type="password"
            autoComplete="off"
            required
            maxLength={10000}
          />
        </label>
      )}
      <p className="crm-muted">
        Credentials are encrypted on the server. The provider must pass a health
        check before this connection becomes connected.
      </p>
      {credentialId && (
        <p role="status">
          Credentials stored. Retry the health check after correcting provider
          configuration.
        </p>
      )}
      {action.error && (
        <p role="alert" className="crm-error">
          {action.error}
        </p>
      )}
      <button className="crm-button" disabled={action.pending}>
        {action.pending
          ? "Checking…"
          : credentialId
            ? "Retry health check"
            : "Save and verify credentials"}
      </button>
    </form>
  );
}
type ProviderSync = {
  id: string;
  sync_type: string;
  status: string;
  records_processed: number;
  records_created: number;
  records_updated: number;
  records_failed: number;
  error_code: string | null;
  started_at: string | null;
  finished_at: string | null;
};
type WebhookReceipt = {
  id: string;
  state: string;
  attempts: number;
  error_code: string | null;
  created_at: string;
  processed_at: string | null;
};
function ProviderHistory({ id, writable }: { id: string; writable: boolean }) {
  const syncs = useResource<ProviderSync[]>(`/integrations/${id}/sync-jobs`);
  const receipts = useResource<WebhookReceipt[]>(
    `/integrations/${id}/webhook-receipts`,
  );
  const action = useAction();
  return (
    <div className="space-y-4 border-t border-[var(--border)] pt-4">
      <section>
        <h4 className="mb-3 font-semibold">Resumable sync jobs</h4>
        <ResourceState
          loading={syncs.isLoading}
          error={syncs.error}
          empty={syncs.data?.length === 0}
          onRetry={syncs.refetch}
        >
          <ul className="space-y-3">
            {syncs.data?.map((sync) => (
              <li
                key={sync.id}
                className="rounded-xl bg-[var(--panel2)] p-3 text-sm"
              >
                <p>
                  {sync.sync_type} · <strong>{sync.status}</strong>
                </p>
                <p>
                  Processed {sync.records_processed} · Created{" "}
                  {sync.records_created} · Updated {sync.records_updated} ·
                  Failed {sync.records_failed}
                </p>
                <p className="crm-muted">
                  {timestamp(sync.started_at)} — {timestamp(sync.finished_at)}
                </p>
                {sync.error_code && (
                  <p className="crm-error">
                    {sync.error_code.replaceAll("_", " ")}
                  </p>
                )}
                {writable &&
                  ["pending", "running", "partial"].includes(sync.status) && (
                    <button
                      className="crm-danger mt-2"
                      disabled={action.pending}
                      onClick={() =>
                        void action.run(() => operations.cancelSync(sync.id))
                      }
                    >
                      Cancel sync
                    </button>
                  )}
              </li>
            ))}
          </ul>
        </ResourceState>
      </section>
      <section>
        <h4 className="mb-3 font-semibold">Inbound webhook receipts</h4>
        <ResourceState
          loading={receipts.isLoading}
          error={receipts.error}
          empty={receipts.data?.length === 0}
          onRetry={receipts.refetch}
        >
          <ul className="space-y-2 text-sm">
            {receipts.data?.map((receipt) => (
              <li
                key={receipt.id}
                className="rounded-xl bg-[var(--panel2)] p-3"
              >
                <p>
                  <strong>{receipt.state}</strong> · Attempt {receipt.attempts}
                </p>
                <p className="crm-muted">{timestamp(receipt.created_at)}</p>
                {receipt.error_code && (
                  <p className="crm-error">
                    {receipt.error_code.replaceAll("_", " ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </ResourceState>
      </section>
      {action.error && (
        <p role="alert" className="crm-error">
          {action.error}
        </p>
      )}
    </div>
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
