"use client";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import Sidebar from "@/components/Sidebar";
import { Dialog } from "@/components/Dialog";
import { ResourceState } from "@/components/ResourceState";
import { useResource } from "@/hooks/useResource";
import { useAction } from "@/hooks/useAction";
import { useSession } from "@/auth/SessionProvider";
import { api } from "@/api/client";
import { label, displayName, queryPath } from "@/services/crm";
import type { Customer360, CustomerRecord } from "@/types/crm";
import CrmForm from "@/app/leads/CrmForm";
import { Field, control, primary, button } from "@/app/leads/CrmFields";

export default function CustomerProfile({
  kind,
  id,
}: {
  kind: string;
  id: string;
}) {
  const valid = ["leads", "contacts", "companies"].includes(kind);
  const { can } = useSession();
  const [offset, setOffset] = useState(0);
  const [task, setTask] = useState(false);
  const [note, setNote] = useState("");
  const [subject, setSubject] = useState("");
  const action = useAction();
  const noteAction = useAction();
  const activityAction = useAction();
  const query = useResource<Customer360>(
    queryPath(`/operations/customers/${kind}/${id}`, { limit: 20, offset }),
    valid && can(`${kind}:read`),
  );
  const data = query.data;
  const relationKey =
    kind === "companies"
      ? "company_id"
      : kind === "contacts"
        ? "contact_id"
        : "lead_id";
  async function addNote(event: FormEvent) {
    event.preventDefault();
    await noteAction.run(async () => {
      await api.post("/notes", { content: note.trim(), [relationKey]: id });
      setNote("");
    });
  }
  async function addActivity(event: FormEvent) {
    event.preventDefault();
    await activityAction.run(async () => {
      await api.post("/operations/activities", {
        subject: subject.trim(),
        [relationKey]: id,
      });
      setSubject("");
    });
  }
  async function exportCustomer() {
    await action.run(async () => {
      const exported = await api.post<Customer360>(
        `/operations/customers/${kind}/${id}/export`,
      );
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(exported, null, 2)], {
          type: "application/json",
        }),
      );
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `customer-${id}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    });
  }
  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />
      <section className="min-w-0 flex-1 p-8">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs tracking-[3px] text-[var(--blue2)]">
              CUSTOMER 360
            </p>
            <h1 className="mt-2 break-words text-3xl font-semibold">
              {data ? displayName(data.customer) : "Customer profile"}
            </h1>
            <p className="mt-1 text-sm text-[var(--muted)]">
              Related records and the recorded customer timeline.
            </p>
          </div>
          <Link className={button} href={valid ? `/${kind}` : "/leads"}>
            Back to {valid ? kind : "leads"}
          </Link>
        </header>
        {!valid || !can(`${kind}:read`) ? (
          <p className="card p-8" role="status">
            This customer profile is not available to your role.
          </p>
        ) : (
          <ResourceState
            loading={query.isLoading}
            error={query.error}
            onRetry={() => void query.refetch()}
          >
            {data && (
              <>
                <div className="card mb-6 p-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-sm">
                      {data.customer.email ||
                        data.customer.description ||
                        "Profile details are available in the related records below."}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {can("tasks:write") && (
                        <button
                          className={button}
                          onClick={() => setTask(true)}
                        >
                          Create Task
                        </button>
                      )}
                      {can("conversations:write") && (
                        <Link
                          className={primary}
                          href={`/conversations?${relationKey}=${id}`}
                        >
                          Start Conversation
                        </Link>
                      )}
                      {can("leads:export") && (
                        <button
                          className={button}
                          disabled={action.pending}
                          onClick={() => void exportCustomer()}
                        >
                          Export profile
                        </button>
                      )}
                    </div>
                  </div>
                  {action.error && (
                    <p role="alert" className="mt-3 text-red-700">
                      {action.error}
                    </p>
                  )}
                </div>
                {data.restricted_sections.length > 0 && (
                  <p
                    role="status"
                    className="mb-5 rounded-xl border border-[var(--border)] p-4 text-sm"
                  >
                    Restricted by your role:{" "}
                    {data.restricted_sections.map(label).join(", ")}.
                  </p>
                )}
                <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(290px,.65fr)]">
                  <div className="min-w-0 space-y-5">
                    {Object.entries(data.sections).map(([section, records]) => (
                      <section className="card p-5" key={section}>
                        <h2 className="mb-4 text-lg font-semibold">
                          {label(section)}{" "}
                          <span className="text-sm font-normal text-[var(--muted)]">
                            ({records.length})
                          </span>
                        </h2>
                        {records.length ? (
                          <ul className="space-y-3">
                            {records.map((record, index) => (
                              <li
                                key={
                                  record.id ?? record.conversation_id ?? index
                                }
                                className="rounded-xl border border-[var(--border)] p-3"
                              >
                                <RecordItem section={section} record={record} />
                                {section === "tasks" &&
                                  can("tasks:write") &&
                                  record.status !== "completed" && (
                                    <button
                                      className={`${button} mt-3`}
                                      disabled={action.pending}
                                      onClick={() =>
                                        void action.run(() =>
                                          api.patch(`/tasks/${record.id}`, {
                                            status: "completed",
                                          }),
                                        )
                                      }
                                    >
                                      Mark complete
                                    </button>
                                  )}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-sm text-[var(--muted)]">
                            No related {label(section).toLowerCase()}.
                          </p>
                        )}
                      </section>
                    ))}
                  </div>
                  <aside className="min-w-0 space-y-5">
                    <section className="card p-5">
                      <h2 className="mb-4 text-lg font-semibold">Timeline</h2>
                      {data.timeline.length ? (
                        <ol className="space-y-4">
                          {data.timeline.map((event) => (
                            <li
                              key={event.id}
                              className="border-l-2 border-blue-200 pl-4"
                            >
                              <p className="font-medium">
                                {label(event.type.replaceAll(".", " "))}
                              </p>
                              <time
                                className="text-xs text-[var(--muted)]"
                                dateTime={event.occurred_at}
                              >
                                {new Date(event.occurred_at).toLocaleString()}
                              </time>
                              <p className="break-all text-xs text-[var(--muted)]">
                                Event {event.id}
                              </p>
                            </li>
                          ))}
                        </ol>
                      ) : (
                        <p className="text-sm text-[var(--muted)]">
                          No recorded events for this page.
                        </p>
                      )}
                      <div className="mt-4 flex justify-between gap-2">
                        <button
                          className={button}
                          disabled={offset === 0}
                          onClick={() => setOffset(Math.max(0, offset - 20))}
                        >
                          Newer events
                        </button>
                        <button
                          className={button}
                          disabled={!data.pagination.has_more}
                          onClick={() => setOffset(offset + 20)}
                        >
                          Older events
                        </button>
                      </div>
                      <p className="mt-3 text-xs text-[var(--muted)]">
                        Each section includes up to{" "}
                        {data.pagination.section_limit} linked records. The
                        timeline is drawn from those records.
                      </p>
                    </section>
                    {can("notes:write") && (
                      <form className="card grid gap-3 p-5" onSubmit={addNote}>
                        <h2 className="font-semibold">Add note</h2>
                        <Field title="Note">
                          <textarea
                            className={control}
                            rows={4}
                            required
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                          />
                        </Field>
                        {noteAction.error && (
                          <p role="alert" className="text-red-700">
                            {noteAction.error}
                          </p>
                        )}
                        {noteAction.success && <p role="status">Note saved.</p>}
                        <button
                          className={primary}
                          disabled={noteAction.pending || !note.trim()}
                        >
                          Save note
                        </button>
                      </form>
                    )}
                    {can("tasks:write") && (
                      <form
                        className="card grid gap-3 p-5"
                        onSubmit={addActivity}
                      >
                        <h2 className="font-semibold">Log meeting activity</h2>
                        <Field title="Meeting subject">
                          <input
                            className={control}
                            required
                            maxLength={255}
                            value={subject}
                            onChange={(e) => setSubject(e.target.value)}
                          />
                        </Field>
                        {activityAction.error && (
                          <p role="alert" className="text-red-700">
                            {activityAction.error}
                          </p>
                        )}
                        {activityAction.success && (
                          <p role="status">Activity saved.</p>
                        )}
                        <button
                          className={primary}
                          disabled={activityAction.pending || !subject.trim()}
                        >
                          Log activity
                        </button>
                      </form>
                    )}
                  </aside>
                </div>
              </>
            )}
          </ResourceState>
        )}
        <Dialog open={task} title="Create task" onClose={() => setTask(false)}>
          {task && (
            <CrmForm
              kind="tasks"
              relation={{ key: relationKey, id }}
              onSaved={() => setTask(false)}
            />
          )}
        </Dialog>
      </section>
    </main>
  );
}
function RecordItem({
  section,
  record,
}: {
  section: string;
  record: CustomerRecord;
}) {
  const href = ["contacts", "companies", "leads"].includes(section)
    ? `/customers/${section}/${record.id}`
    : section === "deals"
      ? `/pipeline?deal=${record.id}`
      : section === "conversations"
        ? `/conversations?conversation=${record.id}`
        : section === "campaigns"
          ? `/campaigns?campaign=${record.id}`
          : undefined;
  const title =
    record.name ||
    record.title ||
    record.subject ||
    [record.first_name, record.last_name].filter(Boolean).join(" ") ||
    record.capability ||
    label(section);
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {href ? (
          <Link className="font-medium text-[var(--blue)]" href={href}>
            {title}
          </Link>
        ) : (
          <p className="font-medium">{title}</p>
        )}
        {record.status && (
          <span className="rounded bg-blue-50 px-2 py-1 text-xs">
            {label(record.status)}
          </span>
        )}
      </div>
      {(record.content || record.body || record.description) && (
        <p className="mt-2 whitespace-pre-wrap break-words text-sm">
          {record.content || record.body || record.description}
        </p>
      )}
      {record.output && (
        <dl className="mt-2 grid gap-2 text-sm">
          {Object.entries(record.output).map(([key, value]) => (
            <div key={key}>
              <dt className="font-medium">{label(key)}</dt>
              <dd className="whitespace-pre-wrap break-words">
                {typeof value === "string" ? value : JSON.stringify(value)}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {record.due_date && (
        <p className="mt-2 text-xs">
          Due {new Date(record.due_date).toLocaleString()}
        </p>
      )}
      {record.created_at && (
        <time
          className="mt-2 block text-xs text-[var(--muted)]"
          dateTime={record.created_at}
        >
          {new Date(record.created_at).toLocaleString()}
        </time>
      )}
    </>
  );
}
