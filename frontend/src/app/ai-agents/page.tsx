"use client";
import { useRef, useState } from "react";
import { Bot, Sparkles } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import { JobStatus } from "@/components/JobStatus";
import { ResourceState } from "@/components/ResourceState";
import { useSession } from "@/auth/SessionProvider";
import { useResource } from "@/hooks/useResource";
import { useAction } from "@/hooks/useAction";
import { operations, choiceLabel, timestamp } from "@/services/operations";
import { aiCapabilities } from "@/types/operations";
import type {
  AICapability,
  Choice,
  Conversation,
  Job,
  LegacyPage,
  Message,
  Page,
} from "@/types/operations";

export default function AIAgentsPage() {
  const { session, can } = useSession();
  return (
    <AIWorkspace key={`${session?.tenant_id}:${session?.version}`} can={can} />
  );
}
function AIWorkspace({ can }: { can: (permission: string) => boolean }) {
  const available = aiCapabilities.filter((item) => can(item.permission));
  const [capability, setCapability] = useState<AICapability>(
    available[0]?.value || "lead_score",
  );
  const [jobId, setJobId] = useState("");
  const [offset, setOffset] = useState(0);
  const [showHooks, setShowHooks] = useState(false);
  const jobs = useResource<Page<Job>>(
    `/operations/jobs?kind=ai&limit=10&offset=${offset}`,
    available.length > 0,
  );
  const entitlements = useResource<
    { feature: string; enabled: boolean; limit: number | null }[]
  >("/foundation/entitlements");
  const quota = entitlements.data?.find(
    (item) => item.feature === "ai_credits",
  );
  const selected = aiCapabilities.find((item) => item.value === capability)!;
  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />
      <section className="min-w-0 flex-1 p-4 sm:p-8">
        <header className="mb-6">
          <p className="text-xs tracking-[3px] text-[var(--blue)]">
            GLOBEXA CRM
          </p>
          <h1 className="mt-2 text-3xl font-semibold">Controlled AI</h1>
          <p className="crm-muted">
            Generate insights and drafts from authorized CRM records
          </p>
        </header>
        <div className="card mb-6 flex items-start gap-3 p-5">
          <Bot className="shrink-0 text-[var(--blue)]" />
          <div>
            <h2 className="font-semibold">Reviewable CRM assistance</h2>
            <p className="mt-1 text-sm">
              Six controlled capabilities run through the backend AI Gateway.
              Suggestions and drafts do not send email or move deals. Autonomous
              workforce management is not available in this release.
            </p>
          </div>
        </div>
        {available.length === 0 ? (
          <p role="alert">
            Your role has no controlled AI capability permission.
          </p>
        ) : (
          <div className="grid items-start gap-6 xl:grid-cols-2">
            <section className="card space-y-4 p-5">
              <h2 className="text-xl font-semibold">Request AI assistance</h2>
              <label className="crm-field">
                Capability
                <select
                  className="crm-input"
                  value={capability}
                  onChange={(e) =>
                    setCapability(e.target.value as AICapability)
                  }
                >
                  {available.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <ResourceState
                loading={entitlements.isLoading}
                error={entitlements.error}
                onRetry={() => void entitlements.refetch()}
              >
                <p className="crm-muted">
                  AI entitlement:{" "}
                  {quota
                    ? quota.enabled
                      ? `enabled · configured limit ${quota.limit !== null && quota.limit >= 0 ? quota.limit : "unlimited"}`
                      : "disabled"
                    : "not configured"}
                  . The backend checks remaining quota for every request.
                </p>
              </ResourceState>
              <AIRequestForm
                key={capability}
                capability={capability}
                entity={selected.entity}
                allowed={quota?.enabled === true}
                onQueued={setJobId}
              />
              {jobId && (
                <div>
                  <h3 className="mb-2 font-semibold">Latest request</h3>
                  <JobStatus
                    jobId={jobId}
                    onComplete={() => void jobs.refetch()}
                  />
                </div>
              )}
            </section>
            <section className="card space-y-3 p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-xl font-semibold">Request history</h2>
                <button
                  className="crm-secondary"
                  onClick={() => void jobs.refetch()}
                >
                  Refresh AI history
                </button>
              </div>
              <ResourceState
                loading={jobs.isLoading}
                error={jobs.error}
                empty={jobs.data?.items.length === 0}
                onRetry={() => void jobs.refetch()}
              >
                <div className="space-y-4">
                  {jobs.data?.items.map((job) => (
                    <AIHistoryItem key={job.id} job={job} />
                  ))}
                </div>
              </ResourceState>
              <nav className="crm-actions" aria-label="AI request pages">
                <button
                  className="crm-secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - 10))}
                >
                  Previous
                </button>
                <button
                  className="crm-secondary"
                  disabled={!jobs.data || offset + 10 >= jobs.data.total}
                  onClick={() => setOffset(offset + 10)}
                >
                  Next
                </button>
              </nav>
              {can("ai:chat") && (
                <>
                  <button
                    className="crm-secondary"
                    onClick={() => setShowHooks(!showHooks)}
                  >
                    {showHooks
                      ? "Hide event suggestions"
                      : "Review event suggestions"}
                  </button>
                  {showHooks && <AIHooks />}
                </>
              )}
            </section>
          </div>
        )}
      </section>
    </main>
  );
}
function AIRequestForm({
  capability,
  entity,
  allowed,
  onQueued,
}: {
  capability: AICapability;
  entity: string;
  allowed: boolean;
  onQueued: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState("");
  const [conversationId, setConversationId] = useState("");
  const records = useResource<LegacyPage<Choice>>(
    `/${entity === "messages" ? "leads" : entity}?page=${page}&page_size=20${entity === "campaigns" ? "" : `&search=${encodeURIComponent(query)}`}`,
    entity !== "messages",
  );
  const conversations = useResource<Page<Conversation>>(
    "/operations/conversations?limit=100&offset=0",
    entity === "messages",
  );
  const messages = useResource<Page<Message>>(
    `/operations/conversations/${conversationId}/messages?limit=100&offset=0&direction=inbound`,
    entity === "messages" && !!conversationId,
  );
  const action = useAction();
  const request = useRef<{ entityId: string; key: string } | null>(null);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    if (request.current?.entityId !== selected)
      request.current = { entityId: selected, key: crypto.randomUUID() };
    const key = request.current.key;
    await action.run(async () => {
      const result = await operations.ai(capability, selected, key);
      onQueued(result.id);
      request.current = null;
      return result;
    });
  }
  return (
    <form className="crm-form" onSubmit={submit}>
      {entity === "messages" ? (
        <>
          <label className="crm-field">
            Conversation
            <select
              className="crm-input"
              required
              value={conversationId}
              onChange={(e) => {
                setConversationId(e.target.value);
                setSelected("");
              }}
            >
              <option value="">Choose conversation</option>
              {conversations.data?.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.subject}
                </option>
              ))}
            </select>
            {conversations.error && (
              <span role="alert">{conversations.error.message}</span>
            )}
          </label>
          <label className="crm-field">
            Inbound message
            <select
              className="crm-input"
              required
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">Choose message</option>
              {messages.data?.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {timestamp(item.occurred_at)} · {item.body.slice(0, 100)}
                </option>
              ))}
            </select>
            {messages.error && (
              <span role="alert">{messages.error.message}</span>
            )}
          </label>
          <p className="crm-muted">
            Pickers show the first 100 conversations and inbound messages.
          </p>
        </>
      ) : (
        <>
          {entity !== "campaigns" && (
            <label className="crm-field">
              Search {entity}
              <input
                className="crm-input"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPage(1);
                  setSelected("");
                }}
              />
            </label>
          )}
          <ResourceState
            loading={records.isLoading}
            error={records.error}
            empty={records.data?.items.length === 0}
            onRetry={() => void records.refetch()}
          >
            <label className="crm-field">
              {entity === "leads"
                ? "Lead"
                : entity === "deals"
                  ? "Deal"
                  : "Campaign"}
              <select
                className="crm-input"
                required
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
              >
                <option value="">Choose a record</option>
                {records.data?.items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {choiceLabel(item)}
                  </option>
                ))}
              </select>
            </label>
          </ResourceState>
          <nav className="crm-actions" aria-label="AI record pages">
            <button
              type="button"
              className="crm-secondary"
              disabled={page === 1}
              onClick={() => {
                setPage(page - 1);
                setSelected("");
              }}
            >
              Previous records
            </button>
            <button
              type="button"
              className="crm-secondary"
              disabled={!records.data || page >= records.data.total_pages}
              onClick={() => {
                setPage(page + 1);
                setSelected("");
              }}
            >
              Next records
            </button>
          </nav>
        </>
      )}
      {action.error && (
        <p role="alert" className="crm-error">
          {action.error}
        </p>
      )}
      <button
        className="crm-button"
        disabled={action.pending || !selected || !allowed}
      >
        <Sparkles size={16} />
        {action.pending ? "Submitting…" : "Queue AI request"}
      </button>
      <p className="crm-muted">
        A configured AI provider is required. Provider failures and quota
        denials remain visible; no sample output is substituted.
      </p>
    </form>
  );
}
function AIHistoryItem({ job }: { job: Job }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <article className="rounded-xl border border-[var(--border)] p-3">
      <p className="text-sm">
        <strong>{job.status}</strong> · {timestamp(job.created_at)}
      </p>
      <p className="break-all text-xs text-[var(--muted)]">
        Provenance: backend AI operation {job.id}
      </p>
      <button
        className="crm-secondary mt-2"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? "Hide result" : "View result and status"}
      </button>
      {expanded && (
        <>
          <JobStatus jobId={job.id} />
          {typeof job.result.proposal_id === "string" && (
            <Proposal id={job.result.proposal_id} />
          )}
        </>
      )}
    </article>
  );
}
function Proposal({ id }: { id: string }) {
  const result = useResource<{
    id: string;
    title: string;
    status: string;
    body: string;
    version: number;
    is_ai_generated: boolean;
  }>(`/operations/proposals/${id}`);
  return (
    <ResourceState
      loading={result.isLoading}
      error={result.error}
      onRetry={() => void result.refetch()}
    >
      {result.data && (
        <div className="mt-3 rounded-xl bg-[var(--panel2)] p-3">
          <h3 className="font-semibold">{result.data.title}</h3>
          <p className="text-xs">
            {result.data.status} · Version {result.data.version} ·{" "}
            {result.data.is_ai_generated
              ? "AI generated draft"
              : "CRM proposal"}
          </p>
          <p className="mt-3 whitespace-pre-wrap break-words text-sm">
            {result.data.body}
          </p>
        </div>
      )}
    </ResourceState>
  );
}
function AIHooks() {
  const [approved, setApproved] = useState<string[]>([]);
  const hooks = useResource<Page<Job>>(
    "/operations/jobs?kind=ai_hook&state=awaiting_approval&limit=10&offset=0",
  );
  return (
    <div>
      <h3 className="font-semibold">Event suggestions awaiting review</h3>
      <ResourceState
        loading={hooks.isLoading}
        error={hooks.error}
        empty={hooks.data?.items.length === 0}
        onRetry={() => void hooks.refetch()}
      >
        {hooks.data?.items.map((job) => (
          <JobStatus
            key={job.id}
            jobId={job.id}
            onComplete={() => void hooks.refetch()}
            onApproved={(id) =>
              setApproved((current) =>
                current.includes(id) ? current : [...current, id],
              )
            }
          />
        ))}
      </ResourceState>
      {approved.length > 0 && (
        <section aria-label="Approved AI requests" className="mt-4 space-y-3">
          <h3 className="font-semibold">Approved AI requests</h3>
          <p className="crm-muted">
            Approval queued these requests. Each result is also retained in AI
            request history.
          </p>
          {approved.map((id) => (
            <JobStatus key={id} jobId={id} />
          ))}
        </section>
      )}
    </div>
  );
}
