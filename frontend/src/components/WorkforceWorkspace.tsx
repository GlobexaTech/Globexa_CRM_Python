"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, ShieldCheck, Workflow } from "lucide-react";
import { api } from "@/api/client";
import { useSession } from "@/auth/SessionProvider";
import { useAction } from "@/hooks/useAction";
import { useResource } from "@/hooks/useResource";
import { workforce, executionActive } from "@/services/workforce";
import { choiceLabel, timestamp } from "@/services/operations";
import type {
  AgentExecution,
  WorkforceAgent,
  WorkforceContext,
  WorkforceTask,
} from "@/types/workforce";
import type { Choice, LegacyPage, Page } from "@/types/operations";
import Sidebar from "./Sidebar";
import { Dialog } from "./Dialog";
import { ResourceState } from "./ResourceState";
import { useConfirm } from "./ConfirmProvider";
import { WorkforceMemory } from "./WorkforceMemory";

export function WorkforceWorkspace({
  supervisor = false,
  initialContext = {},
}: {
  supervisor?: boolean;
  initialContext?: WorkforceContext;
}) {
  const { session } = useSession();
  return (
    <Workspace
      key={`${session?.tenant_id}:${session?.version}`}
      supervisor={supervisor}
      initialContext={initialContext}
    />
  );
}
function Workspace({
  supervisor,
  initialContext,
}: {
  supervisor: boolean;
  initialContext: WorkforceContext;
}) {
  const { session, can } = useSession();
  const permitted = can("ai:chat");
  const agents = useResource<{ items: WorkforceAgent[] }>(
    "/workforce/agents",
    permitted,
  );
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [create, setCreate] = useState(Boolean(initialContext.entity_id));
  const path = `/workforce/executions?limit=20&offset=${offset}${supervisor ? "&agent_name=supervisor" : ""}`;
  const executions = useQuery({
    queryKey: [session?.tenant_id, session?.version, path],
    queryFn: ({ signal }) => api.get<Page<AgentExecution>>(path, { signal }),
    enabled: Boolean(session) && permitted,
    retry: false,
    refetchInterval: (query) => (query.state.error ? false : 3000),
  });
  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />
      <section className="min-w-0 flex-1 p-4 sm:p-8">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs tracking-[3px] text-[var(--blue)]">
              GLOBEXA CRM
            </p>
            <h1 className="mt-2 text-3xl font-semibold">
              {supervisor ? "Supervisor" : "AI Workforce"}
            </h1>
            <p className="crm-muted">
              {supervisor
                ? "Assign an objective and review the coordinated results"
                : "Bounded agents, authorized tools and reviewable outcomes"}
            </p>
          </div>
          {permitted && (
            <button className="crm-button" disabled={!agents.data?.items.length} onClick={() => setCreate(true)}>
              {supervisor ? "New objective" : "New agent task"}
            </button>
          )}
        </header>
        {!permitted ? (
          <p role="alert">Your role cannot access the AI workforce.</p>
        ) : (
          <>
            <div className="crm-actions mb-6">
              <Link
                className="crm-secondary"
                href={supervisor ? "/ai-workforce" : "/supervisor"}
              >
                <Workflow size={16} />
                {supervisor ? "AI Workforce" : "Supervisor"}
              </Link>
              <Link className="crm-secondary" href="/approvals">
                <ShieldCheck size={16} />
                Approval Center
              </Link>
              <Link className="crm-secondary" href="/ai-agents">
                Controlled AI
              </Link>
            </div>
            {!supervisor && (
              <ResourceState
                loading={agents.isLoading}
                error={agents.error}
                onRetry={agents.refetch}
              >
                <div className="mb-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {agents.data?.items
                    .filter((agent) => agent.name !== "supervisor")
                    .map((agent) => (
                      <article className="card p-5" key={agent.name}>
                        <Bot className="mb-3 text-[var(--blue)]" />
                        <h2 className="font-semibold">{agent.label}</h2>
                        <p className="crm-muted mt-2 break-words">
                          Available tools:{" "}
                          {agent.tools.join(", ").replaceAll("_", " ") ||
                            "None"}
                        </p>
                      </article>
                    ))}
                </div>
              </ResourceState>
            )}
            <section className="card p-5">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-xl font-semibold">Execution history</h2>
                <button
                  className="crm-secondary"
                  onClick={() => void executions.refetch()}
                >
                  Refresh executions
                </button>
              </div>
              <ResourceState
                loading={executions.isLoading}
                error={executions.error}
                empty={executions.data?.items.length === 0}
                onRetry={executions.refetch}
              >
                <ul className="divide-y divide-[var(--border)]">
                  {executions.data?.items.map((execution) => (
                    <li key={execution.id} className="py-4">
                      <button
                        className="w-full space-y-2 text-left"
                        onClick={() => setSelected(execution.id)}
                      >
                        <span className="flex flex-wrap justify-between gap-2">
                        <strong className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                            {execution.task.objective}
                          </strong>
                          <span className="rounded-lg bg-[var(--panel2)] px-2 py-1 text-sm">
                            {execution.state}
                          </span>
                        </span>
                        <span className="crm-muted block">
                          {execution.agent_name.replaceAll("_", " ")} ·{" "}
                          {timestamp(execution.created_at)}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </ResourceState>
              <nav className="crm-actions mt-4" aria-label="Execution pages">
                <button
                  className="crm-secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - 20))}
                >
                  Previous executions
                </button>
                <button
                  className="crm-secondary"
                  disabled={
                    !executions.data || offset + 20 >= executions.data.total
                  }
                  onClick={() => setOffset(offset + 20)}
                >
                  Next executions
                </button>
              </nav>
            </section>
            {!supervisor && (
              <WorkforceMemory agents={agents.data?.items || []} />
            )}
          </>
        )}
        <Dialog
          open={create}
          title={supervisor ? "New objective" : "New agent task"}
          onClose={() => setCreate(false)}
        >
        {create && agents.data?.items.length ? (
            <TaskForm
              agents={agents.data?.items || []}
              supervisor={supervisor}
              initialContext={initialContext}
              onCreated={(id) => {
                setCreate(false);
                setSelected(id);
              }}
            />
        ) : create ? <ResourceState loading={agents.isLoading} error={agents.error} onRetry={agents.refetch} /> : null}
        </Dialog>
        <Dialog
          open={Boolean(selected)}
          title="Execution details"
          onClose={() => setSelected("")}
        >
          {selected && (
            <ExecutionDetail
              key={selected}
              id={selected}
              onRetryCreated={setSelected}
            />
          )}
        </Dialog>
      </section>
    </main>
  );
}
function TaskForm({
  agents,
  supervisor,
  initialContext,
  onCreated,
}: {
  agents: WorkforceAgent[];
  supervisor: boolean;
  initialContext: WorkforceContext;
  onCreated: (id: string) => void;
}) {
  const { can } = useSession();
  const [agent, setAgent] = useState(
    supervisor
      ? "supervisor"
      : agents.find((item) => item.name !== "supervisor")?.name || "research",
  );
  const [kind, setKind] = useState<
    NonNullable<WorkforceContext["entity_type"]>
  >(initialContext.entity_type || "lead");
  const [entity, setEntity] = useState(initialContext.entity_id || "");
  const [tools, setTools] = useState<string[]>([]);
  const collection = {
    lead: "leads",
    contact: "contacts",
    deal: "deals",
    campaign: "campaigns",
    conversation: "operations/conversations",
  }[kind];
  const permission = {
    lead: "leads:read",
    contact: "contacts:read",
    deal: "deals:read",
    campaign: "campaigns:read",
    conversation: "conversations:read",
  }[kind];
  const choices = useResource<LegacyPage<Choice> | Page<Choice>>(
    `/${collection}?${kind === "conversation" ? "limit=100" : "page_size=100"}`,
    can(permission),
  );
  const action = useAction();
  const request = useRef<{ signature: string; key: string } | null>(null);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const external = String(form.get("external") || "").trim();
    const body: WorkforceTask = {
      agent_name: agent,
      objective: String(form.get("objective") || "").trim(),
      tools,
      context: {
        ...(entity ? { entity_type: kind, entity_id: entity } : {}),
        ...(external ? { untrusted_text: external } : {}),
        ...(form.get("research_urls")
          ? {
              research_urls: String(form.get("research_urls"))
                .split(/\r?\n/)
                .map((url) => url.trim())
                .filter(Boolean),
            }
          : {}),
      },
    };
    const signature = JSON.stringify(body);
    if (request.current?.signature !== signature)
      request.current = { signature, key: crypto.randomUUID() };
    const key = request.current.key;
    await action.run(async () => {
      const result = await workforce.execute(body, key);
      request.current = null;
      onCreated(result.id);
      return result;
    });
  }
  return (
    <form className="crm-form" onSubmit={submit}>
      {!supervisor && (
        <label className="crm-field">
          Agent
          <select
            className="crm-input"
            value={agent}
            onChange={(event) => {
              setAgent(event.target.value);
              setTools([]);
            }}
          >
            {agents
              .filter((item) => item.name !== "supervisor")
              .map((item) => (
                <option key={item.name} value={item.name}>
                  {item.label}
                </option>
              ))}
          </select>
        </label>
      )}
      <label className="crm-field">
        Objective
        <textarea
          name="objective"
          className="crm-input"
          required
          minLength={3}
          maxLength={4000}
          rows={4}
          placeholder="Describe the specific outcome to prepare for review"
        />
      </label>
      <label className="crm-field">
        Customer context type
        <select
          className="crm-input"
          value={kind}
          onChange={(event) => {
            setKind(event.target.value as typeof kind);
            setEntity("");
          }}
        >
          {["lead", "contact", "deal", "conversation", "campaign"].map(
            (value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ),
          )}
        </select>
      </label>
      <ResourceState
        loading={choices.isLoading}
        error={choices.error}
        onRetry={choices.refetch}
      >
        <label className="crm-field">
          Related record
          <select
            aria-label="Related record"
            className="crm-input"
            value={entity}
            onChange={(event) => setEntity(event.target.value)}
          >
            <option value="">No related record</option>
            {entity &&
              !choices.data?.items.some((item) => item.id === entity) && (
                <option value={entity}>
                  Selected {kind} ({entity})
                </option>
              )}
            {choices.data?.items.map((item) => (
              <option key={item.id} value={item.id}>
                {choiceLabel(item)}
              </option>
            ))}
          </select>
        </label>
      </ResourceState>
      <fieldset className="rounded-xl border border-[var(--border)] p-4">
        <legend className="px-1 font-medium">Requested tools</legend>
        <p className="crm-muted mb-3">
          The server applies your current permissions. External actions require
          independent approval.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {agents
            .find((item) => item.name === agent)
            ?.tools.map((tool) => (
              <label key={tool} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={tools.includes(tool)}
                  onChange={(event) =>
                    setTools(
                      event.target.checked
                        ? [...tools, tool]
                        : tools.filter((value) => value !== tool),
                    )
                  }
                />
                {tool.replaceAll("_", " ")}
              </label>
            ))}
        </div>
      </fieldset>
      {tools.includes("research_web") && (
        <label className="crm-field">
          Research URLs
          <textarea
            name="research_urls"
            className="crm-input"
            maxLength={10000}
            rows={3}
            placeholder="One public HTTPS URL per line (at most five)"
          />
          <span className="crm-muted">
            Research is restricted to these explicit destinations. Internal
            addresses and unsafe redirects are rejected.
          </span>
        </label>
      )}
      <label className="crm-field">
        External material (optional)
        <textarea
          name="external"
          className="crm-input"
          maxLength={12000}
          rows={3}
        />
        <span className="crm-muted">
          Included as untrusted reference material; it cannot change permissions
          or approvals.
        </span>
      </label>
      {action.error && (
        <p role="alert" className="crm-error">
          {action.error}
        </p>
      )}
      <button className="crm-button" disabled={action.pending}>
        {action.pending
          ? "Submitting…"
          : supervisor
            ? "Queue objective"
            : "Queue agent task"}
      </button>
    </form>
  );
}
export function ExecutionDetail({
  id,
  onRetryCreated,
}: {
  id: string;
  onRetryCreated?: (id: string) => void;
}) {
  const { session } = useSession();
  const action = useAction();
  const { confirm } = useConfirm();
  const retryKey = useRef<string | null>(null);
  const path = `/workforce/executions/${id}`;
  const execution = useQuery({
    queryKey: [session?.tenant_id, session?.version, path],
    queryFn: ({ signal }) => api.get<AgentExecution>(path, { signal }),
    enabled: Boolean(session),
    retry: false,
    refetchInterval: (query) =>
      query.state.error ||
      (query.state.data && !executionActive(query.state.data.state))
        ? false
        : 1500,
  });
  const item = execution.data;
  return (
    <ResourceState
      loading={execution.isLoading}
      error={execution.error}
      onRetry={execution.refetch}
    >
      {item && (
        <div className="space-y-4">
          <p className="font-medium whitespace-pre-wrap break-words">
            {item.task.objective}
          </p>
          <p role="status">
            Execution: <strong>{item.state}</strong>
            {item.cancel_requested && executionActive(item.state)
              ? " · Cancellation requested"
              : ""}
          </p>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="crm-muted">Agent</dt>
              <dd>{item.agent_name.replaceAll("_", " ")}</dd>
            </div>
            <div>
              <dt className="crm-muted">Provider / model</dt>
              <dd>
                {item.provider || "Not recorded"} /{" "}
                {item.model || "Not recorded"}
              </dd>
            </div>
            <div>
              <dt className="crm-muted">Started</dt>
              <dd>{timestamp(item.started_at)}</dd>
            </div>
            <div>
              <dt className="crm-muted">Finished</dt>
              <dd>{timestamp(item.completed_at || item.failed_at)}</dd>
            </div>
            <div>
              <dt className="crm-muted">Tools used</dt>
              <dd>
                {item.tools_used.join(", ").replaceAll("_", " ") ||
                  "None recorded"}
              </dd>
            </div>
            <div>
              <dt className="crm-muted">Attempt</dt>
              <dd>{item.attempts}</dd>
            </div>
          </dl>
          {item.error_message && (
            <p role="alert" className="crm-error">
              {item.error_message}
            </p>
          )}
          {item.result && (
            <section>
              <h3 className="mb-2 font-semibold">Recorded result</h3>
              <SafeResult value={item.result} />
            </section>
          )}
          {Boolean(item.children?.length) && (
            <section>
              <h3 className="mb-3 font-semibold">Assigned work</h3>
              {item.children?.map((child) => (
                <details
                  key={child.id}
                  className="mb-2 rounded-lg border border-[var(--border)] p-3"
                >
                  <summary className="cursor-pointer break-words">
                    {child.agent_name}: {child.state}
                  </summary>
                  <p className="my-2 text-sm">{child.task.objective}</p>
                  {child.result && <SafeResult value={child.result} />}
                  {child.error_message && (
                    <p role="alert" className="crm-error">
                      {child.error_message}
                    </p>
                  )}
                </details>
              ))}
            </section>
          )}
          <div className="crm-actions">
            <button
              className="crm-secondary"
              onClick={() => void execution.refetch()}
            >
              Refresh execution
            </button>
            {executionActive(item.state) && !item.cancel_requested && (
              <button
                className="crm-danger"
                disabled={action.pending}
                onClick={() =>
                  void (async () => {
                    if (
                      await confirm({
                        title: "Cancel agent execution?",
                        message:
                          "Cancellation stops further work. Already completed actions remain in the audit history.",
                        confirmText: "Cancel execution",
                        tone: "danger",
                      })
                    )
                      await action.run(() => workforce.cancel(item.id));
                  })()
                }
              >
                Cancel execution
              </button>
            )}
            {item.state === "failed" &&
              item.tools_used.length === 0 &&
              item.attempts < 2 &&
              ["model_unavailable", "provider_unavailable"].includes(
                item.error_message || "",
              ) &&
              onRetryCreated && (
                <button
                  className="crm-secondary"
                  disabled={action.pending}
                  onClick={() =>
                    void action.run(async () => {
                      retryKey.current ??= crypto.randomUUID();
                      const result = await workforce.retry(
                        item.id,
                        retryKey.current,
                      );
                      retryKey.current = null;
                      onRetryCreated(result.id);
                      return result;
                    })
                  }
                >
                  Retry safe work
                </button>
              )}
            <Link href="/approvals" className="crm-secondary">
              Review approvals
            </Link>
          </div>
          {action.error && (
            <p role="alert" className="crm-error">
              {action.error}
            </p>
          )}
        </div>
      )}
    </ResourceState>
  );
}
export function SafeResult({ value }: { value: unknown }) {
  return (
    <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-[var(--panel2)] p-4 text-xs [overflow-wrap:anywhere]">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
