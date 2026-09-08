"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Plus,
  Search,
  Trash2,
  CheckCircle2,
  Mail,
  Phone,
  Pencil,
} from "lucide-react";
import Sidebar from "@/components/Sidebar";
import { Dialog } from "@/components/Dialog";
import { ResourceState } from "@/components/ResourceState";
import { useConfirm } from "@/components/ConfirmProvider";
import { useSession } from "@/auth/SessionProvider";
import { useResource } from "@/hooks/useResource";
import { useAction } from "@/hooks/useAction";
import { api } from "@/api/client";
import { queryPath, displayName, label } from "@/services/crm";
import type { Contact, Company, Task, Paginated } from "@/types/crm";
import { TASK_STATUSES } from "@/types/crm";
import CrmForm from "./CrmForm";
import {
  control,
  primary,
  button,
  useDebounced,
  Pagination,
  EntityPicker,
} from "./CrmFields";

type Kind = "contacts" | "companies" | "tasks";
type Row = Contact | Company | Task;
export default function CrmEntityPage({ kind }: { kind: Kind }) {
  const router = useRouter();
  const params = useSearchParams();
  const requestedId = kind === "tasks" ? params.get("id") : null;
  const detail = useResource<Task>(
    "/tasks/" + requestedId,
    Boolean(requestedId),
  );
  const { can, session } = useSession();
  const { confirm } = useConfirm();
  const action = useAction();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [owner, setOwner] = useState("");
  const [overdue, setOverdue] = useState(false);
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState<Row>();
  const term = useDebounced(search);
  const path = queryPath(`/${kind}`, {
    page,
    page_size: 20,
    search: kind === "tasks" ? undefined : term,
    status: kind === "tasks" ? filter : undefined,
    industry: kind === "companies" ? filter : undefined,
    email_opted_out: kind === "contacts" ? filter : undefined,
    owner_id: kind === "tasks" ? owner : undefined,
    overdue: kind === "tasks" && overdue ? true : undefined,
  });
  const query = useResource<Paginated<Row>>(path, can(`${kind}:read`));
  async function remove(row: Row) {
    if (
      !(await confirm({
        title: `Delete ${kind.slice(0, -1)}?`,
        message: `Delete ${displayName(row)}? This cannot be undone.`,
        tone: "danger",
        confirmText: "Delete",
      }))
    )
      return;
    await action.run(async () => {
      await api.delete(`/${kind}/${row.id}`);
    });
  }
  const title = label(kind);
  const rows = query.data?.items ?? [];
  const currentEdit = edit ?? detail.data;
  function close() {
    setOpen(false);
    setEdit(undefined);
    if (requestedId) router.replace(`/tasks`);
  }
  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />
      <section className="min-w-0 flex-1 p-8">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs tracking-[3px] text-[var(--blue2)]">
              {kind === "tasks"
                ? "WORKSPACE PRODUCTIVITY"
                : "CUSTOMER DATABASE"}
            </p>
            <h1 className="mt-2 text-3xl font-semibold">{title}</h1>
            <p className="mt-1 text-sm text-[var(--muted)]">
              {kind === "tasks"
                ? "Track real follow-ups, ownership and completion."
                : kind === "contacts"
                  ? "Manage people and their contact preferences."
                  : "Organize accounts and customer relationships."}
            </p>
          </div>
          {can(`${kind}:write`) && (
            <button
              className={`${primary} flex items-center gap-2`}
              onClick={() => {
                setEdit(undefined);
                setOpen(true);
              }}
            >
              <Plus size={17} />
              New {kind === "companies" ? "Company" : label(kind.slice(0, -1))}
            </button>
          )}
        </header>
        {!can(`${kind}:read`) ? (
          <p role="status" className="card p-8">
            Your role cannot view {kind}.
          </p>
        ) : (
          <>
            <div className="card mb-4 flex flex-wrap items-end gap-3 p-3">
              {kind !== "tasks" && (
                <label className="flex min-w-0 flex-1 items-center gap-2">
                  <Search size={17} />
                  <span className="sr-only">Search {kind}</span>
                  <input
                    className={control}
                    placeholder={`Search ${kind}…`}
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setPage(1);
                    }}
                  />
                </label>
              )}
              {kind === "companies" ? (
                <label className="grid gap-1 text-sm">
                  Industry
                  <input
                    className={control}
                    value={filter}
                    placeholder="All industries"
                    onChange={(e) => {
                      setFilter(e.target.value);
                      setPage(1);
                    }}
                  />
                </label>
              ) : (
                <label className="grid gap-1 text-sm">
                  {kind === "tasks" ? "Status" : "Email preference"}
                  <select
                    className={control}
                    value={filter}
                    onChange={(e) => {
                      setFilter(e.target.value);
                      setPage(1);
                    }}
                  >
                    <option value="">
                      All {kind === "tasks" ? "statuses" : "contacts"}
                    </option>
                    {kind === "tasks" ? (
                      TASK_STATUSES.map((status) => (
                        <option key={status} value={status}>
                          {label(status)}
                        </option>
                      ))
                    ) : (
                      <>
                        <option value="false">Not opted out</option>
                        <option value="true">Opted out</option>
                      </>
                    )}
                  </select>
                </label>
              )}
              {kind === "tasks" && (
                <>
                  <label className="flex items-center gap-2 py-3">
                    <input
                      type="checkbox"
                      checked={overdue}
                      onChange={(e) => {
                        setOverdue(e.target.checked);
                        setPage(1);
                      }}
                    />
                    Overdue
                  </label>
                  <button
                    className={button}
                    onClick={() => {
                      setOwner(owner ? "" : (session?.user?.id ?? ""));
                      setPage(1);
                    }}
                    aria-pressed={Boolean(owner)}
                  >
                    {owner ? "Show all tasks" : "My tasks"}
                  </button>
                </>
              )}
            </div>
            {kind === "tasks" && can("users:read") && (
              <details className="mb-4">
                <summary className="cursor-pointer text-sm">
                  Filter by owner
                </summary>
                <EntityPicker
                  entity="users"
                  title="Filter owner"
                  value={owner}
                  onChange={(v) => {
                    setOwner(v);
                    setPage(1);
                  }}
                />
              </details>
            )}
            {action.error && (
              <p role="alert" className="mb-4 text-red-700">
                {action.error}
              </p>
            )}
            <ResourceState
              loading={query.isLoading}
              error={query.error}
              empty={!rows.length}
              onRetry={() => void query.refetch()}
            >
              <div className="card overflow-x-auto">
                <table className="w-full min-w-[680px] text-left text-sm">
                  <thead className="border-b border-[var(--border)] text-xs uppercase text-[var(--muted)]">
                    <tr>
                      <th className="p-4">
                        {kind === "tasks"
                          ? "Task"
                          : kind === "contacts"
                            ? "Contact"
                            : "Company"}
                      </th>
                      <th>
                        {kind === "tasks"
                          ? "Status"
                          : kind === "contacts"
                            ? "Email / phone"
                            : "Industry / domain"}
                      </th>
                      <th>
                        {kind === "tasks"
                          ? "Due / priority"
                          : kind === "contacts"
                            ? "Contact policy"
                            : "Website"}
                      </th>
                      <th className="p-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr
                        key={row.id}
                        className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--panel2)]"
                      >
                        <td className="p-4">
                          {kind !== "tasks" ? (
                            <Link
                              className="font-semibold text-[var(--blue)]"
                              href={`/customers/${kind}/${row.id}`}
                            >
                              {displayName(row)}
                            </Link>
                          ) : (
                            <>
                              <button
                                className="text-left font-semibold text-[var(--blue)]"
                                onClick={() => {
                                  setEdit(row);
                                  setOpen(true);
                                }}
                              >
                                {displayName(row)}
                              </button>
                              <TaskRelation task={row as Task} />
                            </>
                          )}
                        </td>
                        <td className="py-3">
                          {kind === "contacts" ? (
                            <div className="space-y-1">
                              {(row as Contact).email ? (
                                <a
                                  className="flex items-center gap-1"
                                  href={`mailto:${(row as Contact).email}`}
                                >
                                  <Mail size={14} />
                                  {(row as Contact).email}
                                </a>
                              ) : (
                                <span>No email</span>
                              )}
                              {(row as Contact).phone && (
                                <a
                                  className="flex items-center gap-1"
                                  href={`tel:${(row as Contact).phone}`}
                                >
                                  <Phone size={14} />
                                  {(row as Contact).phone}
                                </a>
                              )}
                            </div>
                          ) : kind === "companies" ? (
                            <>
                              <p>
                                {(row as Company).industry || "Not specified"}
                              </p>
                              <p className="text-xs text-[var(--muted)]">
                                {(row as Company).domain}
                              </p>
                            </>
                          ) : (
                            <span className="rounded-lg bg-blue-50 px-2 py-1">
                              {label((row as Task).status ?? "pending")}
                            </span>
                          )}
                        </td>
                        <td>
                          {kind === "tasks" ? (
                            <>
                              <p>
                                {(row as Task).due_date
                                  ? new Date(
                                      (row as Task).due_date!,
                                    ).toLocaleString()
                                  : "No due date"}
                              </p>
                              <p className="text-xs">
                                {label((row as Task).priority ?? "medium")}
                              </p>
                            </>
                          ) : kind === "contacts" ? (
                            <span>
                              {(row as Contact).do_not_contact
                                ? "Do not contact"
                                : (row as Contact).email_opted_out
                                  ? "Email opted out"
                                  : "Contactable, subject to suppression"}
                            </span>
                          ) : (row as Company).website &&
                            /^https?:\/\//i.test((row as Company).website!) ? (
                            <a
                              className="text-[var(--blue)]"
                              href={(row as Company).website!}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Visit website
                            </a>
                          ) : (
                            "Not specified"
                          )}
                        </td>
                        <td className="p-4">
                          <div className="flex justify-end gap-2">
                            {kind === "tasks" &&
                              can("tasks:write") &&
                              (row as Task).status !== "completed" && (
                                <button
                                  title="Complete task"
                                  aria-label={`Complete ${displayName(row)}`}
                                  className={button}
                                  disabled={action.pending}
                                  onClick={() =>
                                    void action.run(() =>
                                      api.patch(`/tasks/${row.id}`, {
                                        status: "completed",
                                      }),
                                    )
                                  }
                                >
                                  <CheckCircle2 size={16} />
                                </button>
                              )}
                            {can(`${kind}:write`) && (
                              <button
                                aria-label={`Edit ${displayName(row)}`}
                                className={button}
                                onClick={() => {
                                  setEdit(row);
                                  setOpen(true);
                                }}
                              >
                                <Pencil size={16} />
                              </button>
                            )}
                            {can(`${kind}:delete`) && (
                              <button
                                aria-label={`Delete ${displayName(row)}`}
                                className={button}
                                disabled={action.pending}
                                onClick={() => void remove(row)}
                              >
                                <Trash2 size={16} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </ResourceState>
            {query.data && (
              <Pagination
                page={page}
                totalPages={query.data.total_pages}
                total={query.data.total}
                onPage={setPage}
              />
            )}
          </>
        )}
        <Dialog
          open={open || Boolean(requestedId)}
          title={`${currentEdit ? "Edit" : "New"} ${kind === "companies" ? "company" : kind.slice(0, -1)}`}
          onClose={close}
        >
          {(open || requestedId) && (
            <ResourceState
              loading={Boolean(requestedId) && detail.isLoading}
              error={requestedId ? detail.error : null}
              onRetry={() => void detail.refetch()}
            >
              {can(`${kind}:write`) ? (
                <CrmForm
                  key={currentEdit?.id ?? "new"}
                  kind={kind}
                  record={currentEdit}
                  onSaved={close}
                />
              ) : (
                currentEdit && (
                  <div className="space-y-3">
                    <h3>{displayName(currentEdit)}</h3>
                    <p>
                      {(currentEdit as Task).description || "No description"}
                    </p>
                    <TaskRelation task={currentEdit as Task} />
                  </div>
                )
              )}
            </ResourceState>
          )}
        </Dialog>
      </section>
    </main>
  );
}
function TaskRelation({ task }: { task: Task }) {
  return (
    <div className="mt-2 flex flex-wrap gap-2 text-xs">
      {task.lead_id && (
        <Link href={`/customers/leads/${task.lead_id}`}>Lead profile</Link>
      )}
      {task.contact_id && (
        <Link href={`/customers/contacts/${task.contact_id}`}>
          Contact profile
        </Link>
      )}
      {task.company_id && (
        <Link href={`/customers/companies/${task.company_id}`}>
          Company profile
        </Link>
      )}
      {task.deal_id && (
        <Link href={`/pipeline?deal=${task.deal_id}`}>Deal</Link>
      )}
    </div>
  );
}
