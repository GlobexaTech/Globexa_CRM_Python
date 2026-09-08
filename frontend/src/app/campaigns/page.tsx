"use client";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Mail, Plus } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import { Dialog } from "@/components/Dialog";
import { ResourceState } from "@/components/ResourceState";
import { useConfirm } from "@/components/ConfirmProvider";
import { useSession } from "@/auth/SessionProvider";
import { useResource } from "@/hooks/useResource";
import { useAction } from "@/hooks/useAction";
import {
  operations,
  campaignStatus,
  choiceLabel,
  timestamp,
} from "@/services/operations";
import type {
  Campaign,
  CampaignPlan,
  CampaignStatistics,
  Choice,
  Integration,
  LegacyPage,
  Recipient,
} from "@/types/operations";

export default function CampaignsPage() {
  const { session, can } = useSession();
  return (
    <Suspense fallback={<p className="p-8">Loading campaigns…</p>}>
      <CampaignRoute
        key={`${session?.tenant_id}:${session?.version}`}
        can={can}
      />
    </Suspense>
  );
}
function CampaignRoute({ can }: { can: (permission: string) => boolean }) {
  const params = useSearchParams();
  return <CampaignWorkspace key={params.toString()} can={can} />;
}
function CampaignWorkspace({ can }: { can: (permission: string) => boolean }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState(searchParams.get("id") || "");
  const [create, setCreate] = useState(false);
  const list = useResource<LegacyPage<Campaign>>(
    `/campaigns?page=${page}&page_size=20${status ? `&status=${status}` : ""}`,
    can("campaigns:read"),
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
            <h1 className="mt-2 text-3xl font-semibold">Campaigns</h1>
            <p className="crm-muted">
              Audience, delivery plans and recipient outcomes
            </p>
          </div>
          {can("campaigns:write") && (
            <button className="crm-button" onClick={() => setCreate(true)}>
              <Plus size={16} />
              New campaign
            </button>
          )}
        </header>
        {!can("campaigns:read") ? (
          <p role="alert">Your role cannot read campaigns.</p>
        ) : (
          <>
            <div className="card mb-4 flex flex-wrap items-end gap-3 p-4">
              <label className="crm-field">
                Campaign status
                <select
                  className="crm-input"
                  value={status}
                  onChange={(e) => {
                    setStatus(e.target.value);
                    setPage(1);
                  }}
                >
                  <option value="">All statuses</option>
                  {[
                    "draft",
                    "scheduled",
                    "sending",
                    "paused",
                    "completed",
                    "cancelled",
                    "failed",
                  ].map((value) => (
                    <option key={value} value={value}>
                      {campaignStatus(value)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="crm-secondary"
                onClick={() => void list.refetch()}
              >
                Refresh campaigns
              </button>
            </div>
            <ResourceState
              loading={list.isLoading}
              error={list.error}
              empty={list.data?.items.length === 0}
              onRetry={() => void list.refetch()}
            >
              <div className="grid gap-4 xl:grid-cols-2">
                {list.data?.items.map((row) => (
                  <article className="card p-5" key={row.id}>
                    <div className="flex items-start gap-3">
                      <Mail className="mt-1 shrink-0 text-[var(--blue)]" />
                      <div className="min-w-0 flex-1">
                        <h2 className="break-words text-lg font-semibold">
                          {row.name}
                        </h2>
                        <p className="crm-muted">
                          {row.type} · {campaignStatus(row.status)}
                        </p>
                        {row.scheduled_at && (
                          <p className="mt-1 text-sm">
                            Scheduled: {timestamp(row.scheduled_at)}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-5 text-sm">
                      <span>
                        Recipients: {row.stats?.total ?? "Not enrolled"}
                      </span>
                      <span>Sent: {row.stats?.sent ?? "Not recorded"}</span>
                      <span>
                        Replies: {row.stats?.replied ?? "Not recorded"}
                      </span>
                    </div>
                    <button
                      className="crm-secondary mt-4"
                      onClick={() => setSelected(row.id)}
                    >
                      View campaign
                    </button>
                  </article>
                ))}
              </div>
            </ResourceState>
            <nav className="crm-actions mt-5" aria-label="Campaign pages">
              <button
                className="crm-secondary"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </button>
              <span>Page {page}</span>
              <button
                className="crm-secondary"
                disabled={!list.data || page >= list.data.total_pages}
                onClick={() => setPage(page + 1)}
              >
                Next
              </button>
            </nav>
          </>
        )}
        <Dialog
          open={create}
          title="Create campaign"
          onClose={() => setCreate(false)}
        >
          {create && (
            <CampaignCreateForm
              onSaved={(id) => {
                setCreate(false);
                setSelected(id);
              }}
            />
          )}
        </Dialog>
        <Dialog
          open={!!selected && can("campaigns:read")}
          title="Campaign details"
          onClose={() => {
            setSelected("");
            if (searchParams.has("id")) router.replace("/campaigns");
          }}
        >
          {selected && (
            <CampaignDetail
              key={selected}
              id={selected}
              can={can}
              onDeleted={() => setSelected("")}
            />
          )}
        </Dialog>
      </section>
    </main>
  );
}
function CampaignCreateForm({ onSaved }: { onSaved: (id: string) => void }) {
  const action = useAction();
  return (
    <form
      className="crm-form"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        void action.run(async () => {
          const result = await operations.createCampaign({
            name: String(data.get("name")).trim(),
            type: "broadcast",
            sender_name: String(data.get("sender_name")).trim(),
            sender_email: String(data.get("sender_email")),
            description: String(data.get("description")),
          });
          onSaved(result.id);
          return result;
        });
      }}
    >
      <label className="crm-field">
        Campaign name
        <input name="name" required maxLength={255} className="crm-input" />
      </label>
      <label className="crm-field">
        Sender name
        <input
          name="sender_name"
          required
          maxLength={255}
          className="crm-input"
        />
      </label>
      <label className="crm-field">
        Sender email
        <input
          name="sender_email"
          required
          type="email"
          className="crm-input"
        />
      </label>
      <label className="crm-field">
        Description
        <textarea name="description" maxLength={10000} className="crm-input" />
      </label>
      <p className="crm-muted">
        Create the draft, then choose its audience, integration and message
        sequence.
      </p>
      {action.error && (
        <p role="alert" className="crm-error">
          {action.error}
        </p>
      )}
      <button className="crm-button" disabled={action.pending}>
        {action.pending ? "Creating…" : "Create draft"}
      </button>
    </form>
  );
}
function CampaignDetail({
  id,
  can,
  onDeleted,
}: {
  id: string;
  can: (permission: string) => boolean;
  onDeleted: () => void;
}) {
  const detail = useResource<Campaign>(`/campaigns/${id}`);
  const [recipientPage, setRecipientPage] = useState(1);
  const [recipientStatus, setRecipientStatus] = useState("");
  const recipients = useResource<LegacyPage<Recipient>>(
    `/campaigns/${id}/recipients?page=${recipientPage}&page_size=20${recipientStatus ? `&status=${recipientStatus}` : ""}`,
  );
  const stats = useResource<CampaignStatistics>(
    `/operations/campaigns/${id}/statistics`,
    can("campaigns:analytics"),
  );
  const [plan, setPlan] = useState(false);
  const [edit, setEdit] = useState(false);
  const [notice, setNotice] = useState("");
  const action = useAction();
  const { confirm } = useConfirm();
  const row = detail.data;
  const state = campaignStatus(row?.status || "");
  async function transition(
    operation: "launch" | "pause" | "resume" | "cancel",
  ) {
    if (
      operation === "cancel" &&
      !(await confirm({
        title: "Cancel campaign?",
        message:
          "Pending recipients will stop. Messages already submitted to the provider cannot be recalled.",
        tone: "danger",
        confirmText: "Cancel campaign",
      }))
    )
      return;
    if (
      operation === "launch" &&
      !(await confirm({
        title: "Launch campaign?",
        message:
          "The backend will enroll eligible recipients and queue real email delivery through the selected integration.",
        confirmText: "Launch campaign",
        tone: "primary",
      }))
    )
      return;
    await action.run(async () => {
      const result = await operations.transitionCampaign(id, operation);
      setNotice(
        `Backend campaign state: ${result.status}. Recipient delivery is tracked separately.`,
      );
      return result;
    });
  }
  return (
    <div className="space-y-5">
      <ResourceState
        loading={detail.isLoading}
        error={detail.error}
        onRetry={() => void detail.refetch()}
      >
        {row && (
          <>
            <div>
              <h2 className="text-xl font-semibold">{row.name}</h2>
              <p>{row.description}</p>
              <p className="crm-muted">
                {row.type} · {state}
              </p>
              <p className="break-all text-sm">
                Sender: {row.sender_name} &lt;{row.sender_email}&gt;
              </p>
              {row.scheduled_at && (
                <p className="text-sm">
                  Scheduled: {timestamp(row.scheduled_at)}
                </p>
              )}
            </div>
            <div className="crm-actions">
              <button
                className="crm-secondary"
                onClick={() => {
                  void detail.refetch();
                  void recipients.refetch();
                  if (can("campaigns:analytics")) void stats.refetch();
                }}
              >
                Refresh status
              </button>
              {can("campaigns:write") && state === "draft" && (
                <>
                  <button
                    className="crm-secondary"
                    onClick={() => setEdit(!edit)}
                  >
                    Edit name and description
                  </button>
                  <button
                    className="crm-secondary"
                    onClick={() => setPlan(!plan)}
                  >
                    Configure audience and messages
                  </button>
                  <button
                    className="crm-danger"
                    disabled={action.pending}
                    onClick={() =>
                      void (async () => {
                        if (
                          await confirm({
                            title: "Delete draft campaign?",
                            message:
                              "This permanently removes the draft and its configuration.",
                            confirmText: "Delete draft",
                            tone: "danger",
                          })
                        )
                          await action.run(async () => {
                            await operations.deleteCampaign(id);
                            onDeleted();
                          });
                      })()
                    }
                  >
                    Delete draft
                  </button>
                </>
              )}
              {can("campaigns:send") && (
                <>
                  {["draft", "scheduled"].includes(state) && (
                    <button
                      className="crm-button"
                      disabled={action.pending || !row.templates?.length}
                      onClick={() => void transition("launch")}
                    >
                      Launch campaign
                    </button>
                  )}
                  {["running", "scheduled"].includes(state) && (
                    <button
                      className="crm-secondary"
                      disabled={action.pending}
                      onClick={() => void transition("pause")}
                    >
                      Pause campaign
                    </button>
                  )}
                  {state === "paused" && (
                    <button
                      className="crm-button"
                      disabled={action.pending}
                      onClick={() => void transition("resume")}
                    >
                      Resume campaign
                    </button>
                  )}
                  {["draft", "scheduled", "running", "paused"].includes(
                    state,
                  ) && (
                    <button
                      className="crm-danger"
                      disabled={action.pending}
                      onClick={() => void transition("cancel")}
                    >
                      Cancel campaign
                    </button>
                  )}
                </>
              )}
            </div>
            {edit && (
              <form
                className="crm-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  const data = new FormData(event.currentTarget);
                  void action.run(async () => {
                    const result = await operations.updateCampaign(id, {
                      name: String(data.get("name")).trim(),
                      description: String(data.get("description")),
                    });
                    setEdit(false);
                    return result;
                  });
                }}
              >
                <label className="crm-field">
                  Campaign name
                  <input
                    className="crm-input"
                    name="name"
                    required
                    maxLength={255}
                    defaultValue={row.name}
                  />
                </label>
                <label className="crm-field">
                  Description
                  <textarea
                    className="crm-input"
                    name="description"
                    defaultValue={row.description || ""}
                  />
                </label>
                <button className="crm-button" disabled={action.pending}>
                  Save campaign details
                </button>
              </form>
            )}
            {plan && (
              <CampaignPlanForm
                id={id}
                initialContacts={row.audience?.contact_ids || []}
                onSaved={() => {
                  setPlan(false);
                  setNotice("Audience and message plan saved by the backend.");
                }}
              />
            )}
            {can("campaigns:send") && state === "draft" && (
              <form
                className="crm-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  const date = new Date(
                    String(
                      new FormData(event.currentTarget).get("scheduled_at"),
                    ),
                  );
                  if (
                    !Number.isFinite(date.getTime()) ||
                    date.getTime() <= Date.now()
                  ) {
                    setNotice("Choose a future date and time.");
                    return;
                  }
                  void action.run(async () => {
                    const result = await operations.scheduleCampaign(
                      id,
                      date.toISOString(),
                    );
                    setNotice(`Backend campaign state: ${result.status}.`);
                    return result;
                  });
                }}
              >
                <label className="crm-field">
                  Schedule in your local timezone
                  <input
                    className="crm-input"
                    name="scheduled_at"
                    type="datetime-local"
                    required
                  />
                </label>
                <button
                  className="crm-secondary"
                  disabled={action.pending || !row.templates?.length}
                >
                  Schedule campaign
                </button>
              </form>
            )}
            <div>
              <h3 className="font-semibold">Saved delivery plan</h3>
              <p className="text-sm">
                Audience: {row.audience?.estimated_count ?? 0} contacts
              </p>
              {row.templates?.length ? (
                <ol className="mt-2 list-inside list-decimal space-y-1 text-sm">
                  {[...row.templates]
                    .sort((a, b) => a.step_order - b.step_order)
                    .map((template) => {
                      const sequence = row.sequences?.find(
                        (step) => step.step_order === template.step_order,
                      );
                      return (
                        <li key={template.id}>
                          {template.subject}
                          {sequence
                            ? ` · ${sequence.delay_days * 24 + sequence.delay_hours} hours from enrollment`
                            : ""}
                        </li>
                      );
                    })}
                </ol>
              ) : (
                <p className="crm-muted">No message plan configured.</p>
              )}
            </div>
          </>
        )}
      </ResourceState>
      {notice && (
        <p role="status" className="rounded-lg bg-[var(--panel2)] p-3 text-sm">
          {notice}
        </p>
      )}
      {action.error && (
        <p role="alert" className="crm-error">
          {action.error}
        </p>
      )}
      <div>
        <h3 className="font-semibold">Delivery statistics</h3>
        {can("campaigns:analytics") ? (
          <ResourceState
            loading={stats.isLoading}
            error={stats.error}
            onRetry={() => void stats.refetch()}
          >
            {(stats.data?.unknown ?? 0) > 0 && (
              <p role="status" className="crm-error">
                Delivery status pending verification for {stats.data?.unknown}{" "}
                operation(s). Do not resend while reconciliation is pending.
              </p>
            )}
            {stats.data && (
              <dl className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {(
                  [
                    "total_recipients",
                    "sent",
                    "queued",
                    "failed",
                    "suppressed",
                    "replied",
                  ] as const
                ).map((key) => (
                  <div className="rounded-lg bg-[var(--panel2)] p-3" key={key}>
                    <dt className="text-xs capitalize">
                      {key.replaceAll("_", " ")}
                    </dt>
                    <dd className="text-xl font-semibold">
                      {stats.data![key]}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </ResourceState>
        ) : (
          <p className="crm-muted">
            Campaign analytics permission is required.
          </p>
        )}
      </div>
      <div>
        <h3 className="font-semibold">Recipients and suppression</h3>
        <p className="crm-muted">
          Opt-outs and suppression are checked again before delivery. Campaign
          emails include the backend signed unsubscribe link. “Sent” records
          provider submission; it does not guarantee inbox delivery.
        </p>
        <label className="crm-field mt-3">
          Recipient status
          <select
            className="crm-input"
            value={recipientStatus}
            onChange={(e) => {
              setRecipientStatus(e.target.value);
              setRecipientPage(1);
            }}
          >
            <option value="">All outcomes</option>
            {[
              "queued",
              "scheduled",
              "sending",
              "sent",
              "delivered",
              "opened",
              "clicked",
              "replied",
              "bounced",
              "complained",
              "unsubscribed",
              "suppressed",
              "failed",
            ].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <ResourceState
          loading={recipients.isLoading}
          error={recipients.error}
          empty={recipients.data?.items.length === 0}
          onRetry={() => void recipients.refetch()}
        >
          <ul className="mt-3 space-y-2">
            {recipients.data?.items.map((recipient) => (
              <li
                className="rounded-lg border border-[var(--border)] p-3 text-sm"
                key={recipient.id}
              >
                <strong className="break-all">
                  {recipient.contact_name || recipient.email}
                </strong>
                <p className="break-all">{recipient.email}</p>
                <p>
                  {recipient.status === "unknown"
                    ? "Delivery status pending verification"
                    : recipient.status}{" "}
                  · {timestamp(recipient.sent_at)}
                </p>
              </li>
            ))}
          </ul>
        </ResourceState>
        <nav aria-label="Recipient pages" className="crm-actions mt-3">
          <button
            className="crm-secondary"
            disabled={recipientPage === 1}
            onClick={() => setRecipientPage(recipientPage - 1)}
          >
            Previous recipients
          </button>
          <button
            className="crm-secondary"
            disabled={
              !recipients.data || recipientPage >= recipients.data.total_pages
            }
            onClick={() => setRecipientPage(recipientPage + 1)}
          >
            Next recipients
          </button>
        </nav>
      </div>
    </div>
  );
}
function CampaignPlanForm({
  id,
  initialContacts,
  onSaved,
}: {
  id: string;
  initialContacts: string[];
  onSaved: () => void;
}) {
  const { can } = useSession();
  const [contactPage, setContactPage] = useState(1);
  const [search, setSearch] = useState("");
  const contacts = useResource<LegacyPage<Choice>>(
    `/contacts?page=${contactPage}&page_size=20&search=${encodeURIComponent(search)}`,
    can("contacts:read"),
  );
  const integrations = useResource<LegacyPage<Integration>>(
    "/integrations?page_size=100",
    can("integrations:read"),
  );
  const [selected, setSelected] = useState<string[]>(initialContacts);
  const [steps, setSteps] = useState<CampaignPlan["steps"]>([]);
  const [trigger, setTrigger] = useState("");
  const action = useAction();
  return (
    <form
      className="crm-form rounded-xl border border-[var(--border)] p-4"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        void action.run(async () => {
          const result = await operations.planCampaign(id, {
            integration_id: String(data.get("integration")),
            contact_ids: selected,
            subject: String(data.get("subject")).trim(),
            body: String(data.get("body")).trim(),
            steps,
            ...(trigger ? { trigger_event: trigger } : {}),
          });
          onSaved();
          return result;
        });
      }}
    >
      <h3 className="font-semibold">Replace draft delivery plan</h3>
      <p className="crm-muted">
        Saving replaces the current audience and templates. Select up to 1,000
        contacts. Provider credentials are managed in Integrations.
      </p>
      <label className="crm-field">
        Connected email integration
        <select className="crm-input" name="integration" required>
          <option value="">Choose integration</option>
          {integrations.data?.items
            .filter((item) => item.status === "connected")
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
        </select>
        {integrations.error && (
          <span role="alert">{integrations.error.message}</span>
        )}
      </label>
      <label className="crm-field">
        Find audience contacts
        <input
          className="crm-input"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setContactPage(1);
          }}
        />
      </label>
      <p className="text-sm">{selected.length} selected</p>
      <ResourceState
        loading={contacts.isLoading}
        error={contacts.error}
        empty={contacts.data?.items.length === 0}
        onRetry={() => void contacts.refetch()}
      >
        <div className="max-h-64 space-y-2 overflow-auto">
          {contacts.data?.items.map((contact) => (
            <label key={contact.id} className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={selected.includes(contact.id)}
                onChange={(e) =>
                  setSelected(
                    e.target.checked
                      ? [...selected, contact.id]
                      : selected.filter((value) => value !== contact.id),
                  )
                }
                disabled={
                  !selected.includes(contact.id) && selected.length >= 1000
                }
              />
              <span>
                {choiceLabel(contact)} · {contact.email || "No email"}
                {contact.email_opted_out || contact.do_not_contact
                  ? " · Suppressed / opted out"
                  : ""}
              </span>
            </label>
          ))}
        </div>
      </ResourceState>
      <div className="crm-actions">
        <button
          type="button"
          className="crm-secondary"
          disabled={contactPage === 1}
          onClick={() => setContactPage(contactPage - 1)}
        >
          Previous contacts
        </button>
        <button
          type="button"
          className="crm-secondary"
          disabled={!contacts.data || contactPage >= contacts.data.total_pages}
          onClick={() => setContactPage(contactPage + 1)}
        >
          Next contacts
        </button>
      </div>
      <label className="crm-field">
        First message subject
        <input className="crm-input" name="subject" required maxLength={500} />
      </label>
      <label className="crm-field">
        First message body
        <textarea
          className="crm-input"
          name="body"
          required
          maxLength={100000}
          rows={5}
        />
      </label>
      <label className="crm-field">
        Campaign trigger
        <select
          className="crm-input"
          value={trigger}
          disabled={steps.length > 0}
          onChange={(e) => setTrigger(e.target.value)}
        >
          <option value="">Manual or scheduled</option>
          {[
            "lead.created",
            "contact.created",
            "deal.stage_changed",
            "task.completed",
          ].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </label>
      {steps.map((step, index) => (
        <fieldset
          key={index}
          className="space-y-2 rounded-lg border border-[var(--border)] p-3"
        >
          <legend>Follow-up {index + 1}</legend>
          <label className="crm-field">
            Subject
            <input
              className="crm-input"
              required
              maxLength={500}
              value={step.subject}
              onChange={(e) =>
                setSteps(
                  steps.map((item, i) =>
                    i === index ? { ...item, subject: e.target.value } : item,
                  ),
                )
              }
            />
          </label>
          <label className="crm-field">
            Body
            <textarea
              className="crm-input"
              required
              maxLength={100000}
              value={step.body}
              onChange={(e) =>
                setSteps(
                  steps.map((item, i) =>
                    i === index ? { ...item, body: e.target.value } : item,
                  ),
                )
              }
            />
          </label>
          <label className="crm-field">
            Hours after previous step
            <input
              className="crm-input"
              type="number"
              min={0}
              max={720}
              step={1}
              required
              value={step.delay_hours}
              onChange={(e) =>
                setSteps(
                  steps.map((item, i) =>
                    i === index
                      ? { ...item, delay_hours: Number(e.target.value) }
                      : item,
                  ),
                )
              }
            />
          </label>
          <button
            type="button"
            className="crm-secondary"
            onClick={() => setSteps(steps.filter((_, i) => i !== index))}
          >
            Remove follow-up {index + 1}
          </button>
        </fieldset>
      ))}
      <button
        type="button"
        className="crm-secondary"
        disabled={steps.length >= 10 || !!trigger}
        onClick={() =>
          setSteps([...steps, { subject: "", body: "", delay_hours: 24 }])
        }
      >
        Add follow-up step
      </button>
      {action.error && (
        <p role="alert" className="crm-error">
          {action.error}
        </p>
      )}
      <button
        className="crm-button"
        disabled={action.pending || !selected.length}
      >
        {action.pending ? "Saving…" : "Save delivery plan"}
      </button>
    </form>
  );
}
