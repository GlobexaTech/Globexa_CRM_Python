"use client";
import { useState } from "react";
import Link from "next/link";
import Sidebar from "@/components/Sidebar";
import { ResourceState } from "@/components/ResourceState";
import { AutomationBuilder } from "@/components/AutomationBuilder";
import { useSession } from "@/auth/SessionProvider";
import { useResource } from "@/hooks/useResource";
import { useAction } from "@/hooks/useAction";
import { api } from "@/api/client";
import type { Page } from "@/types/operations";
import type { Automation, Catalog, Execution } from "@/types/automation";

export default function AdvancedPage() {
  const { session } = useSession();
  return <Workspace key={`${session?.tenant_id}:${session?.version}`} />;
}
function Workspace() {
  const { can } = useSession();
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<Automation | null>(null);
  const [creating, setCreating] = useState(false);
  const list = useResource<Page<Automation>>(
    `/automation/workflows?limit=20&offset=${offset}${status ? `&status=${status}` : ""}`,
    can("automation:read"),
  );
  const catalog = useResource<Catalog>(
    "/automation/catalog",
    can("automation:read"),
  );
  const analytics = useResource<Record<string, unknown>>(
    "/automation/analytics",
    can("automation:read") && can("analytics:read"),
  );
  const action = useAction();
  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />
      <section className="min-w-0 flex-1 space-y-5 p-4 sm:p-8">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Link href="/automations" className="text-sm text-[var(--blue)]">
              Automations
            </Link>
            <h1 className="mt-2 text-3xl font-semibold">Advanced workflows</h1>
            <p className="crm-muted">
              Versioned workflows, independent approvals and recorded outcomes.
            </p>
          </div>
          {can("automation:write") && (
            <button
              className="crm-button"
              onClick={() => {
                setCreating(true);
                setSelected(null);
              }}
            >
              New advanced workflow
            </button>
          )}
        </header>
        {!can("automation:read") ? (
          <p role="alert">Your role cannot read workflows.</p>
        ) : (
          <>
            {analytics.data && (
              <div className="grid gap-3 sm:grid-cols-4">
                {[
                  "executions",
                  "success_rate",
                  "ai_calls",
                  "provider_actions",
                ].map((key) => (
                  <div key={key} className="card p-4">
                    <p className="crm-muted capitalize">
                      {key.replaceAll("_", " ")}
                    </p>
                    <strong className="text-2xl">
                      {analytics.data[key] == null
                        ? "Not available"
                        : key.endsWith("rate")
                          ? `${Math.round(Number(analytics.data[key]) * 100)}%`
                          : String(analytics.data[key])}
                    </strong>
                  </div>
                ))}
              </div>
            )}
            {analytics.error && <p role="alert">{analytics.error.message}</p>}
            <div className="crm-actions">
              <label className="crm-field">
                Workflow status
                <select
                  className="crm-input"
                  value={status}
                  onChange={(e) => {
                    setStatus(e.target.value);
                    setOffset(0);
                  }}
                >
                  <option value="">All statuses</option>
                  {["DRAFT", "ACTIVE", "PAUSED", "DISABLED", "ARCHIVED"].map(
                    (value) => (
                      <option key={value}>{value}</option>
                    ),
                  )}
                </select>
              </label>
              <button
                className="crm-secondary"
                onClick={() => {
                  void list.refetch();
                  void analytics.refetch();
                }}
              >
                Refresh workflows
              </button>
            </div>
            <ResourceState
              loading={list.isLoading || catalog.isLoading}
              error={list.error || catalog.error}
              empty={list.data?.items.length === 0}
              onRetry={() => {
                void list.refetch();
                void catalog.refetch();
              }}
            >
              <div className="grid gap-3 lg:grid-cols-2">
                {list.data?.items.map((row) => (
                  <article className="card p-4" key={row.id}>
                    <h2 className="text-lg font-semibold">{row.name}</h2>
                    <p className="crm-muted">
                      {row.status} · Published version {row.version} ·{" "}
                      {row.draft.trigger}
                    </p>
                    <button
                      className="crm-secondary mt-3"
                      onClick={() => {
                        setSelected(row);
                        setCreating(false);
                      }}
                    >
                      Open {row.name}
                    </button>
                  </article>
                ))}
              </div>
            </ResourceState>
            <nav className="crm-actions" aria-label="Advanced workflow pages">
              <button
                className="crm-secondary"
                disabled={!offset}
                onClick={() => setOffset(offset - 20)}
              >
                Previous
              </button>
              <button
                className="crm-secondary"
                disabled={!list.data || offset + 20 >= list.data.total}
                onClick={() => setOffset(offset + 20)}
              >
                Next
              </button>
            </nav>
            {creating && catalog.data && (
              <section className="card p-5">
                <h2 className="mb-4 text-xl font-semibold">
                  New workflow draft
                </h2>
                <AutomationBuilder
                  catalog={catalog.data}
                  disabled={action.pending}
                  onSave={async (value) => {
                    const row = await action.run(() =>
                      api.post<Automation>("/automation/workflows", value),
                    );
                    if (row) {
                      setCreating(false);
                      setSelected(row);
                    }
                  }}
                />
                {action.error && <p role="alert">{action.error}</p>}
              </section>
            )}
            {selected && catalog.data && (
              <WorkflowDetail
                key={selected.id}
                initial={selected}
                catalog={catalog.data}
                editable={can("automation:write")}
              />
            )}
            <details className="card p-4">
              <summary className="cursor-pointer">Usage and outcomes</summary>
              <pre className="mt-3 overflow-auto whitespace-pre-wrap text-sm">
                {JSON.stringify(
                  analytics.data ?? { status: "No analytics available" },
                  null,
                  2,
                )}
              </pre>
              <p className="crm-muted">
                Unknown usage and conversion attribution remain unavailable
                until measured.
              </p>
            </details>
          </>
        )}
      </section>
    </main>
  );
}

function WorkflowDetail({
  initial,
  catalog,
  editable,
}: {
  initial: Automation;
  catalog: Catalog;
  editable: boolean;
}) {
  const detail = useResource<Automation>(`/automation/workflows/${initial.id}`);
  const row = detail.data ?? initial;
  const action = useAction();
  const [editing, setEditing] = useState(false);
  const [simulation, setSimulation] = useState("");
  const [context, setContext] = useState("{}");
  const [useModel, setUseModel] = useState(false);
  const [entityType, setEntityType] = useState("lead");
  const [entityId, setEntityId] = useState("");
  const [executionId, setExecutionId] = useState("");
  const [offset, setOffset] = useState(0);
  const [runKey, setRunKey] = useState<string | null>(null);
  const executions = useResource<Page<Execution>>(
    `/automation/executions?automation_id=${row.id}&limit=20&offset=${offset}`,
  );
  const versions = useResource<
    Page<{ id: string; number: number; digest: string; definition: unknown }>
  >(`/automation/workflows/${row.id}/versions?limit=20`);
  async function transition(name: string) {
    await action.run(() => api.post(`/automation/workflows/${row.id}/${name}`));
  }
  const transitions =
    row.status === "ACTIVE"
      ? ["pause", "disable", "archive"]
      : row.status === "PAUSED"
        ? ["resume", "disable", "archive"]
        : row.status === "DISABLED"
          ? ["resume", "archive"]
          : row.status === "DRAFT"
            ? ["disable", "archive"]
            : [];
  return (
    <section className="card space-y-4 p-5" aria-label="Selected workflow">
      <h2 className="text-2xl font-semibold">{row.name}</h2>
      <p>
        {row.status} · Version {row.version}
      </p>
      <ResourceState
        loading={detail.isLoading}
        error={detail.error}
        onRetry={() => void detail.refetch()}
      />
      {editable && (
        <div className="crm-actions">
          {row.status !== "ARCHIVED" && (
            <>
              <button
                className="crm-secondary"
                disabled={action.pending}
                onClick={() => setEditing(!editing)}
              >
                Edit draft
              </button>
              <button
                className="crm-secondary"
                disabled={action.pending}
                onClick={() => void transition("validate")}
              >
                Validate draft
              </button>
              <button
                className="crm-button"
                disabled={action.pending}
                onClick={() => void transition("publish")}
              >
                Publish version
              </button>
            </>
          )}
          {transitions.map((name) => (
            <button
              className="crm-secondary capitalize"
              disabled={action.pending}
              key={name}
              onClick={() => void transition(name)}
            >
              {name}
            </button>
          ))}
          <button
            className="crm-secondary"
            disabled={action.pending}
            onClick={() => void transition("clone")}
          >
            Clone
          </button>
        </div>
      )}
      {action.error && <p role="alert">{action.error}</p>}
      {action.success && (
        <p role="status">Saved. The latest state is shown below.</p>
      )}
      {editing && (
        <AutomationBuilder
          key={JSON.stringify(row.draft)}
          workflow={row}
          catalog={catalog}
          disabled={action.pending}
          onSave={async (value) => {
            const saved = await action.run(() =>
              api.put(`/automation/workflows/${row.id}`, value),
            );
            if (saved) setEditing(false);
          }}
        />
      )}
      <details>
        <summary className="cursor-pointer">Published versions</summary>
        {versions.error && <p role="alert">{versions.error.message}</p>}
        {versions.data?.items.map((version) => (
          <details key={version.id} className="my-2">
            <summary>Version {version.number}</summary>
            <pre className="overflow-auto whitespace-pre-wrap text-sm">
              {JSON.stringify(version.definition, null, 2)}
            </pre>
          </details>
        ))}
      </details>
      {editable && (
        <div className="grid gap-4 xl:grid-cols-2">
          <form
            className="space-y-3"
            onSubmit={async (e) => {
              e.preventDefault();
              const result = await action.run(() =>
                api.post(`/automation/workflows/${row.id}/simulate`, {
                  context: JSON.parse(context),
                  use_model: useModel,
                }),
              );
              if (result) setSimulation(JSON.stringify(result, null, 2));
            }}
          >
            <h3 className="font-semibold">Test without performing actions</h3>
            <label className="crm-field">
              Sample customer context
              <textarea
                className="crm-input font-mono"
                rows={5}
                value={context}
                onChange={(e) => setContext(e.target.value)}
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={useModel}
                onChange={(e) => setUseModel(e.target.checked)}
              />
              Use configured model for AI decisions (consumes model usage)
            </label>
            <button className="crm-secondary" disabled={action.pending}>
              Run dry test
            </button>
            <p className="crm-muted">
              The test shows conditions and approval requirements. CRM actions
              and external sends remain disabled.
            </p>
            <pre
              className="overflow-auto whitespace-pre-wrap text-sm"
              aria-live="polite"
            >
              {simulation}
            </pre>
          </form>
          <form
            className="space-y-3"
            onSubmit={async (e) => {
              e.preventDefault();
              const key = runKey ?? crypto.randomUUID();
              setRunKey(key);
              const result = await action.run(() =>
                api.post<Execution>(
                  `/automation/workflows/${row.id}/execute`,
                  entityId
                    ? { entity_type: entityType, entity_id: entityId }
                    : {},
                  { idempotencyKey: key },
                ),
              );
              if (result) {
                setExecutionId(result.id);
                setRunKey(null);
              }
            }}
          >
            <h3 className="font-semibold">Run published version</h3>
            <label className="crm-field">
              Customer type
              <select
                className="crm-input"
                value={entityType}
                onChange={(e) => setEntityType(e.target.value)}
              >
                {["lead", "contact", "deal", "task", "message", "campaign"].map(
                  (type) => (
                    <option key={type}>{type}</option>
                  ),
                )}
              </select>
            </label>
            <label className="crm-field">
              Customer record ID (optional)
              <input
                className="crm-input"
                value={entityId}
                onChange={(e) => setEntityId(e.target.value)}
              />
            </label>
            <button
              className="crm-button"
              disabled={action.pending || row.status !== "ACTIVE"}
            >
              Start execution
            </button>
            <p className="crm-muted">
              This performs real CRM actions. External sends require independent
              approval.
            </p>
          </form>
        </div>
      )}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Execution history</h3>
        <button
          className="crm-secondary"
          onClick={() => void executions.refetch()}
        >
          Refresh history
        </button>
      </div>
      <ResourceState
        loading={executions.isLoading}
        error={executions.error}
        empty={executions.data?.items.length === 0}
        onRetry={() => void executions.refetch()}
      >
        <ol className="space-y-2">
          {executions.data?.items.map((execution) => (
            <li
              key={execution.id}
              className="flex flex-wrap justify-between gap-2 rounded border border-[var(--border)] p-3"
            >
              <span>
                {execution.state} ·{" "}
                {new Date(execution.created_at).toLocaleString()} ·{" "}
                {execution.step_count} steps
                {execution.error_code ? ` · ${execution.error_code}` : ""}
              </span>
              <button
                className="crm-secondary"
                onClick={() => setExecutionId(execution.id)}
              >
                Timeline {execution.id.slice(0, 8)}
              </button>
            </li>
          ))}
        </ol>
      </ResourceState>
      <nav className="crm-actions" aria-label="Execution pages">
        <button
          className="crm-secondary"
          disabled={!offset}
          onClick={() => setOffset(offset - 20)}
        >
          Earlier page
        </button>
        <button
          className="crm-secondary"
          disabled={!executions.data || offset + 20 >= executions.data.total}
          onClick={() => setOffset(offset + 20)}
        >
          More executions
        </button>
      </nav>
      {executionId && (
        <Timeline key={executionId} id={executionId} editable={editable} />
      )}
    </section>
  );
}

function Timeline({ id, editable }: { id: string; editable: boolean }) {
  const resource = useResource<Execution>(`/automation/executions/${id}`);
  const action = useAction();
  const execution = resource.data;
  const controls =
    execution?.state === "FAILED"
      ? ["retry"]
      : execution?.state === "PAUSED"
        ? ["resume", "cancel"]
        : ["QUEUED", "RUNNING", "WAITING"].includes(execution?.state ?? "")
          ? ["pause", "cancel"]
          : [];
  return (
    <section className="space-y-3 rounded border border-[var(--border)] p-4">
      <h3 className="text-lg font-semibold">Execution timeline</h3>
      <button className="crm-secondary" onClick={() => void resource.refetch()}>
        Refresh timeline
      </button>
      <ResourceState
        loading={resource.isLoading}
        error={resource.error}
        onRetry={() => void resource.refetch()}
      >
        {execution && (
          <>
            <p>
              {execution.state} · Correlation {execution.correlation_id}
            </p>
            <p className="crm-muted">
              Version {execution.version_id}
              {execution.resume_at
                ? ` · Resume ${new Date(execution.resume_at).toLocaleString()}`
                : ""}
            </p>
            {editable && (
              <div className="crm-actions">
                {controls.map((control) => (
                  <button
                    key={control}
                    disabled={action.pending}
                    className="crm-secondary capitalize"
                    onClick={() =>
                      void action.run(() =>
                        api.post(`/automation/executions/${id}/${control}`),
                      )
                    }
                  >
                    {control} execution
                  </button>
                ))}
              </div>
            )}
            {action.error && <p role="alert">{action.error}</p>}
            <ol className="space-y-3">
              {execution.steps?.map((step) => (
                <li
                  className="rounded border-l-4 border-[var(--blue)] p-3"
                  key={step.id}
                >
                  <strong>
                    {step.node_key} · {step.state}
                  </strong>
                  <p>
                    Attempts {step.attempts} · Retries {step.retry_count}
                    {step.error_code ? ` · ${step.error_code}` : ""}
                  </p>
                  {step.approval_id && (
                    <Link className="text-[var(--blue)]" href="/approvals">
                      Review approval {step.approval_id.slice(0, 8)}
                    </Link>
                  )}
                  <details>
                    <summary>Inputs and recorded output</summary>
                    <pre className="overflow-auto whitespace-pre-wrap text-sm">
                      {JSON.stringify(
                        { input: step.input, output: step.result },
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                </li>
              ))}
            </ol>
          </>
        )}
      </ResourceState>
    </section>
  );
}
