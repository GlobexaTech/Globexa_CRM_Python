"use client";

import { Suspense, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Mail, Plus, RefreshCw, Send } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import { Dialog } from "@/components/Dialog";
import { JobStatus } from "@/components/JobStatus";
import { ResourceState } from "@/components/ResourceState";
import { useSession } from "@/auth/SessionProvider";
import { useResource } from "@/hooks/useResource";
import { useAction } from "@/hooks/useAction";
import { operations, choiceLabel, timestamp } from "@/services/operations";
import type {
  Choice,
  Conversation,
  ConversationDetail,
  Integration,
  LegacyPage,
  Message,
  Page,
} from "@/types/operations";

export default function ConversationsPage() {
  const { session, can } = useSession();
  return (
    <Suspense fallback={<p className="p-8">Loading conversations…</p>}>
      <ConversationRoute
        key={`${session?.tenant_id}:${session?.version}`}
        can={can}
      />
    </Suspense>
  );
}
function ConversationRoute({ can }: { can: (permission: string) => boolean }) {
  const params = useSearchParams();
  return <ConversationWorkspace key={params.toString()} can={can} />;
}
function ConversationWorkspace({
  can,
}: {
  can: (permission: string) => boolean;
}) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialRelation = Object.fromEntries(
    ["lead_id", "contact_id", "company_id"].flatMap((field) => {
      const value = searchParams.get(field);
      return value && /^[0-9a-f-]{36}$/i.test(value) ? [[field, value]] : [];
    }),
  );
  const [selected, setSelected] = useState(
    searchParams.get("conversation") || searchParams.get("id") || "",
  );
  const [query, setQuery] = useState("");
  const [channel, setChannel] = useState("");
  const [unread, setUnread] = useState(false);
  const [offset, setOffset] = useState(0);
  const [create, setCreate] = useState(
    can("conversations:write") && Object.keys(initialRelation).length > 0,
  );
  const list = useResource<Page<Conversation>>(
    `/operations/conversations?limit=20&offset=${offset}&q=${encodeURIComponent(query)}${channel ? `&channel=${channel}` : ""}${unread ? "&unread=true" : ""}`,
    can("conversations:read"),
  );
  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />
      <section className="min-w-0 flex-1 p-4 sm:p-8">
        <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs tracking-[3px] text-[var(--blue)]">
              GLOBEXA CRM
            </p>
            <h1 className="mt-2 text-3xl font-semibold">Conversations</h1>
            <p className="crm-muted">Customer messages and delivery status</p>
          </div>
          {can("conversations:write") && (
            <button className="crm-button" onClick={() => setCreate(true)}>
              <Plus size={16} />
              New conversation
            </button>
          )}
        </header>
        {!can("conversations:read") ? (
          <p role="alert">Your role cannot read conversations.</p>
        ) : (
          <div className="flex min-h-[560px] min-w-0 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--panel)]">
            <aside
              className={`${selected ? "hidden md:block" : "block"} w-full shrink-0 border-r border-[var(--border)] md:w-72 lg:w-80`}
            >
              <div className="space-y-3 border-b border-[var(--border)] p-4">
                <label className="crm-field">
                  Search conversations
                  <input
                    className="crm-input"
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      setOffset(0);
                    }}
                  />
                </label>
                <label className="crm-field">
                  Channel
                  <select
                    className="crm-input"
                    value={channel}
                    onChange={(e) => {
                      setChannel(e.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="">All channels</option>
                    <option value="email">Email</option>
                    <option value="whatsapp">WhatsApp</option>
                    <option value="social">Social</option>
                  </select>
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={unread}
                    onChange={(e) => {
                      setUnread(e.target.checked);
                      setOffset(0);
                    }}
                  />
                  Unread only
                </label>
                <button
                  className="crm-secondary"
                  onClick={() => void list.refetch()}
                >
                  <RefreshCw size={14} />
                  Refresh
                </button>
              </div>
              <ResourceState
                loading={list.isLoading}
                error={list.error}
                empty={list.data?.items.length === 0}
                onRetry={() => void list.refetch()}
              >
                {list.data?.items.map((item) => (
                  <button
                    key={item.id}
                    className={`w-full border-b border-[var(--border)] p-4 text-left hover:bg-[var(--panel2)] ${selected === item.id ? "bg-[var(--panel2)]" : ""}`}
                    onClick={() => setSelected(item.id)}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <strong className="break-words">{item.subject}</strong>
                      {item.unread_count > 0 && (
                        <span
                          className="rounded-full bg-[var(--blue)] px-2 py-1 text-xs text-white"
                          aria-label={`${item.unread_count} unread messages`}
                        >
                          {item.unread_count}
                        </span>
                      )}
                    </span>
                    <span className="mt-2 block text-xs text-[var(--muted)]">
                      {item.channel} ·{" "}
                      {timestamp(item.last_message_at || item.created_at)}
                    </span>
                  </button>
                ))}
              </ResourceState>
              <nav
                aria-label="Conversation pages"
                className="flex items-center justify-between gap-2 p-4"
              >
                <button
                  className="crm-secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - 20))}
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
            </aside>
            <section
              className={`${selected ? "flex" : "hidden md:flex"} min-w-0 flex-1 flex-col`}
            >
              {selected ? (
                <ConversationView
                  key={selected}
                  id={selected}
                  canSend={can("conversations:send")}
                  onBack={() => {
                    setSelected("");
                    if (
                      searchParams.has("conversation") ||
                      searchParams.has("id")
                    )
                      router.replace("/conversations");
                  }}
                />
              ) : (
                <div className="m-auto p-8 text-center text-[var(--muted)]">
                  <Mail className="mx-auto mb-3" />
                  <p>Select a conversation to see its messages.</p>
                </div>
              )}
            </section>
          </div>
        )}
        <Dialog
          open={create}
          title="New conversation"
          onClose={() => setCreate(false)}
        >
          {create && (
            <ConversationForm
              initialRelation={initialRelation}
              onSaved={(id) => {
                setCreate(false);
                setSelected(id);
              }}
            />
          )}
        </Dialog>
      </section>
    </main>
  );
}
function ConversationView({
  id,
  canSend,
  onBack,
}: {
  id: string;
  canSend: boolean;
  onBack: () => void;
}) {
  const detail = useResource<ConversationDetail>(
    `/operations/conversations/${id}`,
  );
  const [offset, setOffset] = useState(0);
  const messages = useResource<Page<Message>>(
    `/operations/conversations/${id}/messages?limit=30&offset=${offset}`,
  );
  const action = useAction();
  const [body, setBody] = useState("");
  const [recipient, setRecipient] = useState("");
  const [jobId, setJobId] = useState("");
  const request = useRef<{ signature: string; key: string } | null>(null);
  async function send(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const signature = JSON.stringify({ id, body, recipient });
    if (request.current?.signature !== signature)
      request.current = { signature, key: crypto.randomUUID() };
    const key = request.current.key;
    await action.run(async () => {
      const result = await operations.sendMessage(id, { recipient, body }, key);
      setJobId(result.id);
      setBody("");
      request.current = null;
      return result;
    });
  }
  return (
    <>
      <header className="border-b border-[var(--border)] p-4 sm:p-6">
        <button className="crm-secondary mb-3 md:hidden" onClick={onBack}>
          <ArrowLeft size={16} />
          Conversation list
        </button>
        <ResourceState
          loading={detail.isLoading}
          error={detail.error}
          onRetry={() => void detail.refetch()}
        >
          {detail.data && (
            <>
              <h2 className="break-words text-xl font-semibold">
                {detail.data.conversation.subject}
              </h2>
              <p className="crm-muted">
                {detail.data.conversation.channel} ·{" "}
                {detail.data.conversation.unread_count} unread for this
                workspace
              </p>
              <ul aria-label="Participants" className="mt-2 text-sm">
                {detail.data.participants.map((p) => (
                  <li className="break-all" key={p.address}>
                    {p.name ? `${p.name} · ` : ""}
                    {p.address}
                  </li>
                ))}
              </ul>
              <div className="crm-actions mt-3">
                <button
                  className="crm-secondary"
                  disabled={
                    action.pending ||
                    detail.data.conversation.unread_count === 0
                  }
                  onClick={() =>
                    void action.run(() => operations.readConversation(id))
                  }
                >
                  Mark as read
                </button>
                <button
                  className="crm-secondary"
                  onClick={() => {
                    void messages.refetch();
                    void detail.refetch();
                  }}
                >
                  Refresh messages
                </button>
              </div>
            </>
          )}
        </ResourceState>
      </header>
      <div className="flex-1 space-y-4 p-4 sm:p-6">
        <ResourceState
          loading={messages.isLoading}
          error={messages.error}
          empty={messages.data?.items.length === 0}
          onRetry={() => void messages.refetch()}
        >
          {messages.data?.items.map((message) => (
            <article
              key={message.id}
              className={`max-w-full rounded-2xl border border-[var(--border)] p-4 md:max-w-[90%] ${message.direction === "outbound" ? "ml-auto bg-[var(--panel2)]" : "bg-white"}`}
            >
              <p className="mb-2 break-all text-xs text-[var(--muted)]">
                {message.direction} · {message.sender || "Sender not supplied"}{" "}
                → {message.recipient || "Recipient not supplied"}
              </p>
              <p className="whitespace-pre-wrap break-words text-sm">
                {message.body}
              </p>
              <p className="mt-3 text-xs">
                {message.status === "unknown"
                  ? "Delivery status pending verification"
                  : message.status}{" "}
                · {timestamp(message.occurred_at)}
              </p>
              <p className="mt-1 break-all text-xs text-[var(--muted)]">
                Provider message ID:{" "}
                {message.provider_message_id || "Not supplied by provider"}
              </p>
              {message.attachments.length > 0 && (
                <ul aria-label="Attachment metadata" className="mt-2 text-xs">
                  {message.attachments.map((file, index) => (
                    <li key={`${file.name}:${index}`}>
                      {file.name}
                      {file.size !== undefined ? ` (${file.size} bytes)` : ""} —
                      metadata only
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </ResourceState>
        <nav aria-label="Message pages" className="crm-actions">
          <button
            className="crm-secondary"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 30))}
          >
            Previous messages
          </button>
          <button
            className="crm-secondary"
            disabled={!messages.data || offset + 30 >= messages.data.total}
            onClick={() => setOffset(offset + 30)}
          >
            Next messages
          </button>
        </nav>
      </div>
      <div className="border-t border-[var(--border)] p-4">
        {jobId && (
          <JobStatus
            jobId={jobId}
            onComplete={() => {
              void messages.refetch();
              void detail.refetch();
            }}
          />
        )}
        {action.error && (
          <p role="alert" className="crm-error">
            {action.error}
          </p>
        )}
        {canSend &&
        detail.data?.conversation.channel === "email" &&
        detail.data.conversation.integration_id ? (
          <form onSubmit={send} className="crm-form">
            <label className="crm-field">
              Recipient email
              <input
                className="crm-input"
                type="email"
                required
                value={recipient}
                onChange={(e) => setRecipient(e.target.value)}
                list="conversation-participants"
              />
            </label>
            <datalist id="conversation-participants">
              {detail.data.participants.map((p) => (
                <option key={p.address} value={p.address} />
              ))}
            </datalist>
            <label className="crm-field">
              Message
              <textarea
                className="crm-input"
                required
                maxLength={100000}
                rows={3}
                value={body}
                onChange={(e) => setBody(e.target.value)}
              />
            </label>
            <button
              className="crm-button"
              disabled={action.pending || !body.trim()}
            >
              <Send size={16} />
              {action.pending ? "Submitting…" : "Queue message"}
            </button>
            <p className="crm-muted">
              Delivery is confirmed by the background job. Attachments cannot be
              sent in this release.
            </p>
          </form>
        ) : (
          <p className="crm-muted">
            {!canSend
              ? "Your role cannot send messages."
              : "Sending requires an email conversation linked to a supported integration."}
          </p>
        )}
      </div>
    </>
  );
}
function ConversationForm({
  onSaved,
  initialRelation,
}: {
  onSaved: (id: string) => void;
  initialRelation: Record<string, string>;
}) {
  const { can } = useSession();
  const contacts = useResource<LegacyPage<Choice>>(
    "/contacts?page_size=100",
    can("contacts:read"),
  );
  const leads = useResource<LegacyPage<Choice>>(
    "/leads?page_size=100",
    can("leads:read"),
  );
  const companies = useResource<LegacyPage<Choice>>(
    "/companies?page_size=100",
    can("companies:read"),
  );
  const integrations = useResource<LegacyPage<Integration>>(
    "/integrations?page_size=100",
    can("integrations:read"),
  );
  const action = useAction();
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const optional = (name: string) =>
      String(data.get(name) || "") || undefined;
    await action.run(async () => {
      const row = await operations.createConversation({
        subject: String(data.get("subject")).trim(),
        channel: "email",
        contact_id: optional("contact_id"),
        company_id: optional("company_id"),
        lead_id: optional("lead_id"),
        integration_id: optional("integration_id"),
        participants: [
          { address: String(data.get("email")), name: optional("name") },
        ],
      });
      onSaved(row.id);
      return row;
    });
  }
  return (
    <form className="crm-form" onSubmit={submit}>
      <label className="crm-field">
        Subject
        <input name="subject" className="crm-input" required maxLength={255} />
      </label>
      <label className="crm-field">
        Participant email
        <input name="email" className="crm-input" type="email" required />
      </label>
      <label className="crm-field">
        Participant name
        <input name="name" className="crm-input" maxLength={255} />
      </label>
      {[
        { name: "contact_id", label: "Contact", query: contacts },
        { name: "company_id", label: "Company", query: companies },
        { name: "lead_id", label: "Lead", query: leads },
      ].map((field) => (
        <label key={field.name} className="crm-field">
          {field.label}
          <select
            className="crm-input"
            name={field.name}
            defaultValue={initialRelation[field.name] || ""}
          >
            <option value="">No linked {field.label.toLowerCase()}</option>
            {initialRelation[field.name] &&
              !field.query.data?.items.some(
                (row) => row.id === initialRelation[field.name],
              ) && (
                <option value={initialRelation[field.name]}>
                  Selected {field.label.toLowerCase()} (
                  {initialRelation[field.name]})
                </option>
              )}
            {field.query.data?.items.map((row) => (
              <option key={row.id} value={row.id}>
                {choiceLabel(row)}
              </option>
            ))}
          </select>
          {field.query.error && (
            <span role="alert">{field.query.error.message}</span>
          )}
        </label>
      ))}
      <label className="crm-field">
        Email integration
        <select name="integration_id" className="crm-input">
          <option value="">No integration (read-only conversation)</option>
          {integrations.data?.items
            .filter((row) => row.status === "connected")
            .map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
        </select>
        {integrations.error && (
          <span role="alert">{integrations.error.message}</span>
        )}
      </label>
      <p className="crm-muted">
        Only email sending is currently available. Related record pickers show
        the first 100 accessible records.
      </p>
      {action.error && (
        <p role="alert" className="crm-error">
          {action.error}
        </p>
      )}
      <button className="crm-button" disabled={action.pending}>
        {action.pending ? "Creating…" : "Create conversation"}
      </button>
    </form>
  );
}
