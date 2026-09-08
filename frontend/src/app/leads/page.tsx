"use client";
import { useState } from "react";
import { Plus, Search, Trash2 } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import LeadTable from "@/components/LeadTable";
import LeadFilters from "@/components/LeadFilters";
import LeadDrawer from "@/components/LeadDrawer";
import { Dialog } from "@/components/Dialog";
import { ResourceState } from "@/components/ResourceState";
import { useConfirm } from "@/components/ConfirmProvider";
import { useSession } from "@/auth/SessionProvider";
import { useResource } from "@/hooks/useResource";
import { useAction } from "@/hooks/useAction";
import { crm, queryPath } from "@/services/crm";
import type { Lead, Paginated } from "@/types/crm";
import CrmForm from "./CrmForm";
import {
  control,
  primary,
  button,
  useDebounced,
  Pagination,
  EntityPicker,
} from "./CrmFields";
export default function LeadsPage() {
  const { can } = useSession();
  const { confirm } = useConfirm();
  const action = useAction();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [source, setSource] = useState("");
  const [owner, setOwner] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState<Lead | null>(null);
  const term = useDebounced(search);
  const query = useResource<Paginated<Lead>>(
    queryPath("/leads", {
      page,
      page_size: 20,
      search: term,
      status,
      source,
      owner_id: owner,
    }),
    can("leads:read"),
  );
  const rows = query.data?.items ?? [];
  const visibleSelected = selected.filter((id) =>
    rows.some((row) => row.id === id),
  );
  function toggle(id: string) {
    setSelected((old) =>
      old.includes(id) ? old.filter((v) => v !== id) : [...old, id],
    );
  }
  async function removeSelected() {
    if (
      !(await confirm({
        title: "Delete selected leads?",
        message: `Delete ${visibleSelected.length} leads on this page? Deletions are individual and cannot be undone.`,
        tone: "danger",
        confirmText: "Delete",
      }))
    )
      return;
    await action.run(async () => {
      try {
        for (const id of visibleSelected) {
          await crm.deleteLead(id);
          setSelected((old) => old.filter((v) => v !== id));
        }
      } finally {
        await query.refetch();
      }
    });
  }
  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />
      <section className="min-w-0 flex-1 p-8">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs tracking-[3px] text-[var(--blue2)]">
              CUSTOMER DATABASE
            </p>
            <h1 className="mt-2 text-3xl font-semibold">Leads</h1>
            <p className="mt-1 text-sm text-[var(--muted)]">
              Manage, qualify and organize every opportunity.
            </p>
          </div>
          {can("leads:write") && (
            <button
              className={`${primary} flex items-center gap-2`}
              onClick={() => setOpen(true)}
            >
              <Plus size={17} />
              New Lead
            </button>
          )}
        </header>
        {!can("leads:read") ? (
          <p className="card p-8" role="status">
            Your role cannot view leads.
          </p>
        ) : (
          <>
            <label className="card mb-4 flex items-center gap-2 p-3">
              <Search size={17} />
              <span className="sr-only">Search leads</span>
              <input
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                  setSelected([]);
                }}
                placeholder="Search lead titles and descriptions…"
                className={control}
              />
            </label>
            <LeadFilters
              status={status}
              source={source}
              onStatus={(v) => {
                setStatus(v);
                setPage(1);
                setSelected([]);
              }}
              onSource={(v) => {
                setSource(v);
                setPage(1);
                setSelected([]);
              }}
              onReset={() => {
                setStatus("");
                setSource("");
                setSearch("");
                setOwner("");
                setPage(1);
                setSelected([]);
              }}
            />
            {can("users:read") && (
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
                    setSelected([]);
                  }}
                />
              </details>
            )}
            {can("leads:delete") && (
              <div className="mb-3 flex flex-wrap items-center gap-3">
                <button
                  className={button}
                  onClick={() =>
                    setSelected(
                      visibleSelected.length === rows.length
                        ? []
                        : rows.map((v) => v.id),
                    )
                  }
                >
                  {visibleSelected.length === rows.length && rows.length
                    ? "Deselect page"
                    : "Select this page"}
                </button>
                {visibleSelected.length > 0 && (
                  <button
                    className={`${button} flex items-center gap-2`}
                    disabled={action.pending}
                    onClick={() => void removeSelected()}
                  >
                    <Trash2 size={15} />
                    Delete {visibleSelected.length} selected
                  </button>
                )}
              </div>
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
              <LeadTable
                leads={rows}
                selected={visibleSelected}
                toggle={toggle}
                open={setActive}
                selectable={can("leads:delete")}
              />
            </ResourceState>
            {query.data && (
              <Pagination
                page={page}
                total={query.data.total}
                totalPages={query.data.total_pages}
                onPage={(v) => {
                  setPage(v);
                  setSelected([]);
                }}
              />
            )}
          </>
        )}
        <Dialog open={open} title="New lead" onClose={() => setOpen(false)}>
          {open && <CrmForm kind="leads" onSaved={() => setOpen(false)} />}
        </Dialog>
        {active && (
          <LeadDrawer
            key={active.id}
            lead={active}
            onClose={() => setActive(null)}
          />
        )}
      </section>
    </main>
  );
}
