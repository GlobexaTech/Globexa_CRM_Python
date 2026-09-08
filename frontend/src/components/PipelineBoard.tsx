"use client";
import { useRef, useState, type FormEvent } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Columns3,
  List,
  Plus,
  Search,
  GripVertical,
  Trash2,
  ArrowLeft,
  ArrowRight,
  Pencil,
} from "lucide-react";
import { useSession } from "@/auth/SessionProvider";
import { useResource } from "@/hooks/useResource";
import { useAction } from "@/hooks/useAction";
import { api } from "@/api/client";
import { Dialog } from "./Dialog";
import { ResourceState } from "./ResourceState";
import { useConfirm } from "./ConfirmProvider";
import { JobStatus } from "./JobStatus";
import type {
  Deal,
  DealCreate,
  Paginated,
  Pipeline,
  PipelineStage,
  Job,
} from "@/types/crm";
import { crm, queryPath, formatMoney } from "@/services/crm";
import {
  control,
  button,
  primary,
  Field,
  EntityPicker,
  Pagination,
  useDebounced,
} from "@/app/leads/CrmFields";

export default function PipelineBoard() {
  const { can } = useSession();
  const { confirm } = useConfirm();
  const action = useAction();
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedDeal = searchParams.get("deal");
  const [pipelineId, setPipelineId] = useState("");
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [page, setPage] = useState(1);
  const [view, setView] = useState<"board" | "table">("board");
  const [selected, setSelected] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [edited, setEdited] = useState<Deal>();
  const [pipelineDialog, setPipelineDialog] = useState<
    "create" | "edit" | null
  >(null);
  const [stageDialog, setStageDialog] = useState<
    PipelineStage | "create" | null
  >(null);
  const [moves, setMoves] = useState<Record<string, string>>({});
  const [owner, setOwner] = useState("");
  const term = useDebounced(search);
  const pipelines = useResource<Pipeline[]>(
    "/deals/pipelines",
    can("deals:read"),
  );
  const linked = useResource<Deal>(
    `/deals/${requestedDeal}`,
    Boolean(requestedDeal) && can("deals:read"),
  );
  const chosenPipeline =
    pipelineId || linked.data?.pipeline_id || pipelines.data?.[0]?.id || "";
  const pipeline = pipelines.data?.find((v) => v.id === chosenPipeline);
  const stagesQuery = useResource<PipelineStage[]>(
    `/deals/pipelines/${chosenPipeline}/stages`,
    Boolean(chosenPipeline) && can("deals:read"),
  );
  const stages = stagesQuery.data ?? [];
  const query = useResource<Paginated<Deal>>(
    queryPath("/deals", {
      pipeline_id: chosenPipeline,
      stage_id: stageFilter,
      owner_id: owner,
      search: term,
      page,
      page_size: 20,
    }),
    Boolean(chosenPipeline) && can("deals:read"),
  );
  const rows = (query.data?.items ?? []).map((deal) =>
    moves[deal.id] ? { ...deal, stage_id: moves[deal.id] } : deal,
  );
  const visibleSelected = selected.filter((id) =>
    rows.some((row) => row.id === id),
  );
  const currentDeal = edited ?? linked.data;
  async function move(id: string, stage_id: string) {
    if (action.pending || !can("deals:write")) return;
    setMoves((old) => ({ ...old, [id]: stage_id }));
    await action.run(async () => {
      try {
        const saved = await crm.moveDeal(id, stage_id);
        if (edited?.id === id) setEdited(saved);
        await query.refetch();
        return saved;
      } finally {
        setMoves((old) => {
          const next = { ...old };
          delete next[id];
          return next;
        });
      }
    });
  }
  async function reorder(from: number, to: number) {
    if (to < 0 || to >= stages.length || from === to) return;
    const ids = stages.map((stage) => stage.id);
    ids.splice(to, 0, ids.splice(from, 1)[0]);
    await action.run(() =>
      api.put(`/deals/pipelines/${chosenPipeline}/stages/order`, {
        stage_ids: ids,
      }),
    );
  }
  async function bulkMove(stage_id: string) {
    if (!stage_id) return;
    if (
      !(await confirm({
        title: "Move selected deals?",
        message: `Move ${visibleSelected.length} deals on this page? Each move is saved individually.`,
        confirmText: "Move deals",
      }))
    )
      return;
    await action.run(async () => {
      try {
        for (const id of visibleSelected) {
          await crm.moveDeal(id, stage_id);
          setSelected((old) => old.filter((v) => v !== id));
        }
      } finally {
        await query.refetch();
      }
    });
  }
  async function deleteSelected() {
    if (
      !(await confirm({
        title: "Delete selected deals?",
        message: `Delete ${visibleSelected.length} deals? Deletions are individual and cannot be undone.`,
        tone: "danger",
        confirmText: "Delete",
      }))
    )
      return;
    await action.run(async () => {
      try {
        for (const id of visibleSelected) {
          await api.delete(`/deals/${id}`);
          setSelected((old) => old.filter((v) => v !== id));
        }
      } finally {
        await query.refetch();
      }
    });
  }
  async function removeStage(stage: PipelineStage) {
    if (
      !(await confirm({
        title: "Delete stage?",
        message: `Delete ${stage.name}? The backend rejects stages that still contain deals.`,
        tone: "danger",
        confirmText: "Delete stage",
      }))
    )
      return;
    await action.run(() => api.delete(`/deals/stages/${stage.id}`));
  }
  function closeDeal() {
    setOpen(false);
    setEdited(undefined);
    if (requestedDeal) router.replace("/pipeline");
  }
  function toggle(id: string) {
    setSelected((old) =>
      old.includes(id) ? old.filter((v) => v !== id) : [...old, id],
    );
  }
  return (
    <>
      <p className="text-xs tracking-[3px] text-[var(--blue2)]">
        CUSTOMER JOURNEY
      </p>
      <header className="mb-8 mt-2 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold">Deal Pipeline</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Move deals through the stages defined by your workspace.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className={button} href="/leads">
            View leads
          </Link>
          {can("deals:write") && (
            <button
              className={`${primary} flex items-center gap-2`}
              disabled={!stages.length}
              onClick={() => {
                setEdited(undefined);
                setOpen(true);
              }}
            >
              <Plus size={17} />
              New Deal
            </button>
          )}
        </div>
      </header>
      {!can("deals:read") ? (
        <p role="status" className="card p-8">
          Your role cannot view deals.
        </p>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <Field title="Pipeline">
              <select
                className={control}
                value={chosenPipeline}
                onChange={(e) => {
                  setPipelineId(e.target.value);
                  setPage(1);
                  setStageFilter("");
                  setSelected([]);
                }}
              >
                {!pipelines.data?.length && (
                  <option value="">No pipelines</option>
                )}
                {pipelines.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
            {can("deals:pipeline_manage") && (
              <>
                <button
                  className={button}
                  onClick={() => setPipelineDialog("create")}
                >
                  New pipeline
                </button>
                <button
                  className={button}
                  disabled={!pipeline}
                  onClick={() => setPipelineDialog("edit")}
                >
                  Manage pipeline
                </button>
                <button
                  className={button}
                  disabled={!pipeline}
                  onClick={() => setStageDialog("create")}
                >
                  Add stage
                </button>
              </>
            )}
            <div className="ml-auto flex gap-1 rounded-xl border border-[var(--border)] p-1">
              <button
                className={view === "board" ? primary : button}
                aria-label="Board view"
                aria-pressed={view === "board"}
                onClick={() => setView("board")}
              >
                <Columns3 size={17} />
              </button>
              <button
                className={view === "table" ? primary : button}
                aria-label="Table view"
                aria-pressed={view === "table"}
                onClick={() => setView("table")}
              >
                <List size={17} />
              </button>
            </div>
          </div>
          <div className="card mb-4 flex flex-wrap items-end gap-3 p-3">
            <label className="flex min-w-0 flex-1 items-center gap-2">
              <Search size={17} />
              <span className="sr-only">Search deals</span>
              <input
                className={control}
                placeholder="Search deals…"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                  setSelected([]);
                }}
              />
            </label>
            <Field title="Stage filter">
              <select
                className={control}
                value={stageFilter}
                onChange={(e) => {
                  setStageFilter(e.target.value);
                  setPage(1);
                  setSelected([]);
                }}
              >
                <option value="">All stages</option>
                {stages.map((stage) => (
                  <option key={stage.id} value={stage.id}>
                    {stage.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
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
          {can("deals:write") && rows.length > 0 && (
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <button
                className={button}
                onClick={() =>
                  setSelected(
                    visibleSelected.length === rows.length
                      ? []
                      : rows.map((row) => row.id),
                  )
                }
              >
                {visibleSelected.length === rows.length
                  ? "Deselect page"
                  : "Select this page"}
              </button>
              {visibleSelected.length > 0 && (
                <>
                  <span className="text-sm">
                    {visibleSelected.length} selected
                  </span>
                  <label className="text-sm">
                    Move selected
                    <select
                      aria-label="Move selected deals"
                      className={control}
                      value=""
                      disabled={action.pending}
                      onChange={(e) => void bulkMove(e.target.value)}
                    >
                      <option value="">Choose stage…</option>
                      {stages.map((stage) => (
                        <option value={stage.id} key={stage.id}>
                          {stage.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {can("deals:delete") && (
                    <button
                      className={`${button} flex gap-2`}
                      disabled={action.pending}
                      onClick={() => void deleteSelected()}
                    >
                      <Trash2 size={16} />
                      Delete selected
                    </button>
                  )}
                </>
              )}
            </div>
          )}
          {action.error && (
            <p
              className="mb-4 rounded-xl border border-red-200 p-4 text-red-700"
              role="alert"
            >
              {action.error} The board shows the last confirmed stage after an
              unsuccessful move.
            </p>
          )}
          {action.pending && (
            <p className="mb-3 text-sm" role="status">
              Saving pipeline changes…
            </p>
          )}
          <ResourceState
            loading={
              pipelines.isLoading || stagesQuery.isLoading || query.isLoading
            }
            error={pipelines.error || stagesQuery.error || query.error}
            onRetry={() => {
              void pipelines.refetch();
              if (chosenPipeline) {
                void stagesQuery.refetch();
                void query.refetch();
              }
            }}
          >
            {!pipeline ? (
              <p className="card p-8">
                No pipeline is configured. A workspace manager can create one
                above.
              </p>
            ) : !stages.length ? (
              <p className="card p-8">Add a stage before creating a deal.</p>
            ) : view === "board" ? (
              <div
                className="flex gap-3 overflow-x-auto pb-4"
                aria-label="Deal board"
              >
                {stages
                  .filter((stage) => !stageFilter || stageFilter === stage.id)
                  .map((stage) => {
                    const index = stages.findIndex((v) => v.id === stage.id);
                    const stageDeals = rows.filter(
                      (deal) => deal.stage_id === stage.id,
                    );
                    return (
                      <section
                        key={stage.id}
                        aria-label={`${stage.name} stage`}
                        onDragOver={(e) => {
                          if (can("deals:write")) e.preventDefault();
                        }}
                        onDrop={(e) => {
                          e.preventDefault();
                          const id = e.dataTransfer.getData(
                            "application/globexa-deal",
                          );
                          if (rows.some((row) => row.id === id))
                            void move(id, stage.id);
                        }}
                        className="card min-h-[420px] min-w-[260px] flex-1 p-3"
                      >
                        <header className="mb-4">
                          <div className="flex items-center justify-between gap-2">
                            <h2 className="flex items-center gap-2 font-semibold">
                              <GripVertical size={16} />
                              {stage.name}
                            </h2>
                            <span className="rounded-lg bg-[var(--panel2)] px-2 py-1 text-xs">
                              {stageDeals.length} on page
                            </span>
                          </div>
                          {can("deals:pipeline_manage") && (
                            <div className="mt-2 flex gap-1">
                              <button
                                className="rounded p-2"
                                disabled={index === 0 || action.pending}
                                aria-label={`Move ${stage.name} left`}
                                onClick={() => void reorder(index, index - 1)}
                              >
                                <ArrowLeft size={14} />
                              </button>
                              <button
                                className="rounded p-2"
                                disabled={
                                  index === stages.length - 1 || action.pending
                                }
                                aria-label={`Move ${stage.name} right`}
                                onClick={() => void reorder(index, index + 1)}
                              >
                                <ArrowRight size={14} />
                              </button>
                              <button
                                className="rounded p-2"
                                aria-label={`Edit ${stage.name} stage`}
                                onClick={() => setStageDialog(stage)}
                              >
                                <Pencil size={14} />
                              </button>
                              <button
                                className="rounded p-2"
                                disabled={action.pending}
                                aria-label={`Delete ${stage.name} stage`}
                                onClick={() => void removeStage(stage)}
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                          )}
                        </header>
                        <div className="space-y-3">
                          {stageDeals.map((deal) => (
                            <DealCard
                              key={deal.id}
                              deal={deal}
                              stages={stages}
                              canWrite={can("deals:write")}
                              selected={visibleSelected.includes(deal.id)}
                              pending={action.pending}
                              toggle={() => toggle(deal.id)}
                              open={() => {
                                setEdited(deal);
                                setOpen(true);
                              }}
                              move={(next) => void move(deal.id, next)}
                            />
                          ))}
                          {!stageDeals.length && (
                            <p className="py-6 text-center text-xs text-[var(--muted)]">
                              No deals on this page
                            </p>
                          )}
                        </div>
                      </section>
                    );
                  })}
              </div>
            ) : (
              <div className="card overflow-x-auto">
                <table className="w-full min-w-[760px] text-left text-sm">
                  <thead className="border-b border-[var(--border)] text-xs uppercase text-[var(--muted)]">
                    <tr>
                      <th className="p-4">Deal</th>
                      <th>Value</th>
                      <th>Owner</th>
                      <th>Stage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((deal) => (
                      <tr
                        key={deal.id}
                        className="border-b border-[var(--border)] last:border-0"
                      >
                        <td className="p-4">
                          <button
                            className="font-semibold text-[var(--blue)]"
                            onClick={() => {
                              setEdited(deal);
                              setOpen(true);
                            }}
                          >
                            {deal.title}
                          </button>
                        </td>
                        <td>
                          {formatMoney(deal.value ?? 0, deal.currency ?? "USD")}
                        </td>
                        <td>
                          {deal.owner?.full_name ||
                            deal.owner_id ||
                            "Unassigned"}
                        </td>
                        <td className="p-3">
                          <select
                            aria-label={`Stage for ${deal.title}`}
                            className={control}
                            disabled={!can("deals:write") || action.pending}
                            value={deal.stage_id}
                            onChange={(e) => void move(deal.id, e.target.value)}
                          >
                            {stages.map((stage) => (
                              <option key={stage.id} value={stage.id}>
                                {stage.name}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!rows.length && <p className="p-6">No matching deals.</p>}
              </div>
            )}
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
          <p className="mt-3 text-xs text-[var(--muted)]">
            Board counts cover this page. Values remain in each deal’s stored
            currency. Stage selectors provide a keyboard and touch alternative
            to dragging.
          </p>
        </>
      )}
      <Dialog
        open={open || Boolean(requestedDeal)}
        title={currentDeal ? "Deal details" : "New deal"}
        onClose={closeDeal}
      >
        {(open || requestedDeal) && (
          <ResourceState
            loading={Boolean(requestedDeal) && linked.isLoading}
            error={requestedDeal ? linked.error : null}
            onRetry={() => void linked.refetch()}
          >
            {can("deals:write") ? (
              <DealForm
                key={currentDeal?.id ?? chosenPipeline}
                deal={currentDeal}
                pipelineId={currentDeal?.pipeline_id ?? chosenPipeline}
                onSaved={closeDeal}
              />
            ) : (
              currentDeal && (
                <div className="space-y-3">
                  <h3 className="font-semibold">{currentDeal.title}</h3>
                  <p>{currentDeal.description || "No description"}</p>
                  <p>
                    {formatMoney(
                      currentDeal.value ?? 0,
                      currentDeal.currency ?? "USD",
                    )}
                  </p>
                </div>
              )
            )}
          </ResourceState>
        )}
      </Dialog>
      <Dialog
        open={Boolean(pipelineDialog)}
        title={pipelineDialog === "edit" ? "Manage pipeline" : "New pipeline"}
        onClose={() => setPipelineDialog(null)}
      >
        {pipelineDialog && (
          <PipelineForm
            pipeline={pipelineDialog === "edit" ? pipeline : undefined}
            onSaved={(id) => {
              setPipelineId(id ?? "");
              setPipelineDialog(null);
            }}
          />
        )}
      </Dialog>
      <Dialog
        open={Boolean(stageDialog)}
        title={stageDialog === "create" ? "New stage" : "Edit stage"}
        onClose={() => setStageDialog(null)}
      >
        {stageDialog && (
          <StageForm
            stage={stageDialog === "create" ? undefined : stageDialog}
            pipelineId={chosenPipeline}
            nextOrder={
              Math.max(-1, ...stages.map((stage) => stage.order ?? 0)) + 1
            }
            onSaved={() => setStageDialog(null)}
          />
        )}
      </Dialog>
    </>
  );
}
function DealCard({
  deal,
  stages,
  selected,
  toggle,
  open,
  move,
  canWrite,
  pending,
}: {
  deal: Deal;
  stages: PipelineStage[];
  selected: boolean;
  toggle: () => void;
  open: () => void;
  move: (id: string) => void;
  canWrite: boolean;
  pending: boolean;
}) {
  return (
    <article
      draggable={canWrite && !pending}
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("application/globexa-deal", deal.id);
      }}
      className={`rounded-xl border bg-[var(--panel2)] p-3 ${selected ? "border-[var(--blue)]" : "border-[var(--border)]"}`}
    >
      <div className="flex gap-2">
        {canWrite && (
          <input
            type="checkbox"
            aria-label={`Select ${deal.title}`}
            checked={selected}
            onChange={toggle}
          />
        )}
        <button className="min-w-0 flex-1 text-left" onClick={open}>
          <b className="break-words text-sm">{deal.title}</b>
          <p className="mt-2 text-sm text-[var(--blue)]">
            {formatMoney(deal.value ?? 0, deal.currency ?? "USD")}
          </p>
          <p className="mt-1 text-xs text-[var(--muted)]">
            {deal.company?.name ||
              deal.contact?.first_name ||
              (deal.company_id || deal.contact_id
                ? "Linked customer"
                : "No linked customer")}
          </p>
        </button>
      </div>
      <p className="mt-3 break-all text-xs text-[var(--muted)]">
        Owner:{" "}
        {deal.owner?.full_name ||
          deal.owner?.email ||
          deal.owner_id ||
          "Unassigned"}
      </p>
      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        {deal.lead_id && (
          <Link href={`/customers/leads/${deal.lead_id}`}>Lead</Link>
        )}
        {deal.contact_id && (
          <Link href={`/customers/contacts/${deal.contact_id}`}>Contact</Link>
        )}
        {deal.company_id && (
          <Link href={`/customers/companies/${deal.company_id}`}>Company</Link>
        )}
      </div>
      <p className="mt-3 text-xs text-[var(--muted)]">
        Probability {deal.probability ?? 0}%
      </p>
      <div className="mt-1 h-1 rounded bg-[var(--border)]">
        <div
          className="h-1 rounded bg-[var(--blue)]"
          style={{ width: `${deal.probability ?? 0}%` }}
        />
      </div>
      <label className="mt-3 grid gap-1 text-xs">
        Stage
        <select
          className={control}
          aria-label={`Stage for ${deal.title}`}
          value={deal.stage_id}
          disabled={!canWrite || pending}
          onChange={(e) => move(e.target.value)}
        >
          {stages.map((stage) => (
            <option key={stage.id} value={stage.id}>
              {stage.name}
            </option>
          ))}
        </select>
      </label>
    </article>
  );
}

function DealForm({
  deal,
  pipelineId,
  onSaved,
}: {
  deal?: Deal;
  pipelineId: string;
  onSaved: () => void;
}) {
  const { session, can } = useSession();
  const action = useAction();
  const aiAction = useAction();
  const stagesQuery = useResource<PipelineStage[]>(
    `/deals/pipelines/${pipelineId}/stages`,
    Boolean(pipelineId),
  );
  const stages = stagesQuery.data ?? [];
  const [title, setTitle] = useState(deal?.title ?? "");
  const [stage, setStage] = useState(deal?.stage_id ?? "");
  const [value, setValue] = useState(String(deal?.value ?? 0));
  const [currency, setCurrency] = useState(deal?.currency ?? "USD");
  const [description, setDescription] = useState(deal?.description ?? "");
  const [owner, setOwner] = useState(deal?.owner_id ?? session?.user.id ?? "");
  const [contact, setContact] = useState(deal?.contact_id ?? "");
  const [company, setCompany] = useState(deal?.company_id ?? "");
  const [lead, setLead] = useState(deal?.lead_id ?? "");
  const [job, setJob] = useState("");
  const [validation, setValidation] = useState("");
  const aiKey = useRef(crypto.randomUUID());
  async function submit(event: FormEvent) {
    event.preventDefault();
    setValidation("");
    if (
      !title.trim() ||
      !Number.isSafeInteger(Number(value)) ||
      Number(value) < 0
    ) {
      setValidation(
        "Enter a deal title and a non-negative whole-number value in minor units.",
      );
      return;
    }
    if (!Intl.supportedValuesOf("currency").includes(currency.toUpperCase())) {
      setValidation(
        "Choose a recognized three-letter currency code, such as USD, EUR or INR.",
      );
      return;
    }
    const body: DealCreate = {
      custom_fields: deal?.custom_fields ?? {},
      probability:
        deal?.probability ??
        stages.find((s) => s.id === (stage || stages[0]?.id))?.probability ??
        0,
      title: title.trim(),
      pipeline_id: pipelineId,
      stage_id: stage || stages[0]?.id,
      value: Number(value),
      currency: currency.toUpperCase(),
      description: description || null,
      owner_id: owner || null,
      contact_id: contact || null,
      company_id: company || null,
      lead_id: lead || null,
    };
    await action.run(async () => {
      if (deal) {
        const { stage_id, ...fields } = body;
        await crm.updateDeal(deal.id, fields);
        if (stage_id !== deal.stage_id) await crm.moveDeal(deal.id, stage_id);
      } else await crm.createDeal(body);
      onSaved();
    });
  }
  return (
    <>
      <form className="grid gap-4" onSubmit={submit}>
        {validation && (
          <p role="alert" className="text-red-700">
            {validation}
          </p>
        )}
        <Field title="Deal title">
          <input
            className={control}
            value={title}
            maxLength={255}
            required
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field title="Stage">
            <select
              className={control}
              required
              value={stage || stages[0]?.id || ""}
              onChange={(e) => setStage(e.target.value)}
            >
              <option value="" disabled>
                Choose stage
              </option>
              {stages.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
          <Field title="Currency (three-letter code)">
            <input
              className={control}
              required
              pattern="[A-Za-z]{3}"
              maxLength={3}
              value={currency}
              onChange={(e) => setCurrency(e.target.value.toUpperCase())}
            />
          </Field>
          <Field title="Value (minor units, e.g. 10000 = 100.00)">
            <input
              className={control}
              type="number"
              min={0}
              step={1}
              required
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </Field>
        </div>
        <Field title="Description">
          <textarea
            className={control}
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <EntityPicker
            entity="users"
            title="Owner"
            value={owner}
            onChange={setOwner}
          />
          <EntityPicker
            entity="contacts"
            title="Contact"
            value={contact}
            onChange={setContact}
          />
          <EntityPicker
            entity="companies"
            title="Company"
            value={company}
            onChange={setCompany}
          />
          <EntityPicker
            entity="leads"
            title="Lead"
            value={lead}
            onChange={setLead}
          />
        </div>
        {stagesQuery.error && <p role="alert">Stages could not load.</p>}
        {action.error && (
          <p role="alert" className="text-red-700">
            {action.error}
          </p>
        )}
        <button className={primary} disabled={action.pending || !stages.length}>
          {action.pending ? "Saving…" : deal ? "Save deal" : "Create deal"}
        </button>
      </form>
      {deal && (
        <div className="mt-5 space-y-3">
          {deal.lead_id && (
            <Link
              href={`/customers/leads/${deal.lead_id}`}
              className="text-[var(--blue)]"
            >
              View lead Customer 360
            </Link>
          )}
          <div className="flex flex-wrap gap-2">
            {can("ai:change_stage") && (
              <button
                className={button}
                disabled={aiAction.pending}
                onClick={() =>
                  void aiAction.run(async () => {
                    const result = await api.post<Job>(
                      "/operations/ai/requests",
                      { capability: "next_best_action", entity_id: deal.id },
                      { idempotencyKey: aiKey.current },
                    );
                    setJob(result.id);
                    aiKey.current = crypto.randomUUID();
                  })
                }
              >
                Request next best action
              </button>
            )}
            {can("ai:create_proposal") && (
              <button
                className={button}
                disabled={aiAction.pending}
                onClick={() =>
                  void aiAction.run(async () => {
                    const result = await api.post<Job>(
                      "/operations/ai/requests",
                      { capability: "proposal_draft", entity_id: deal.id },
                      { idempotencyKey: aiKey.current },
                    );
                    setJob(result.id);
                    aiKey.current = crypto.randomUUID();
                  })
                }
              >
                Draft proposal
              </button>
            )}
          </div>
          {aiAction.error && (
            <p role="alert" className="text-red-700">
              {aiAction.error}
            </p>
          )}
          {job && <JobStatus jobId={job} />}
        </div>
      )}
    </>
  );
}
function PipelineForm({
  pipeline,
  onSaved,
}: {
  pipeline?: Pipeline;
  onSaved: (id?: string) => void;
}) {
  const [name, setName] = useState(pipeline?.name ?? "");
  const action = useAction();
  const { confirm } = useConfirm();
  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        void action.run(async () => {
          const result = pipeline
            ? await api.patch<Pipeline>(`/deals/pipelines/${pipeline.id}`, {
                name: name.trim(),
              })
            : await crm.createPipeline(name.trim());
          onSaved(result.id);
        });
      }}
    >
      <Field title="Pipeline name">
        <input
          required
          maxLength={255}
          className={control}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      {action.error && (
        <p role="alert" className="text-red-700">
          {action.error}
        </p>
      )}
      <button className={primary} disabled={action.pending}>
        {pipeline ? "Save pipeline" : "Create pipeline"}
      </button>
      {pipeline && (
        <button
          type="button"
          className={button}
          disabled={action.pending}
          onClick={async () => {
            if (
              !(await confirm({
                title: "Delete pipeline?",
                message:
                  "Only an empty pipeline can be deleted. This cannot be undone.",
                tone: "danger",
              }))
            )
              return;
            void action.run(async () => {
              await api.delete(`/deals/pipelines/${pipeline.id}`);
              onSaved();
            });
          }}
        >
          Delete pipeline
        </button>
      )}
    </form>
  );
}
function StageForm({
  stage,
  pipelineId,
  nextOrder,
  onSaved,
}: {
  stage?: PipelineStage;
  pipelineId: string;
  nextOrder: number;
  onSaved: () => void;
}) {
  const action = useAction();
  const [name, setName] = useState(stage?.name ?? "");
  const [probability, setProbability] = useState(stage?.probability ?? 0);
  const [closed, setClosed] = useState(stage?.is_closed ?? false);
  const [won, setWon] = useState(stage?.is_won ?? false);
  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        void action.run(async () => {
          if (stage)
            await api.patch(`/deals/stages/${stage.id}`, {
              name: name.trim(),
              probability,
              is_closed: closed || won,
              is_won: won,
            });
          else
            await crm.createStage(
              pipelineId,
              name.trim(),
              nextOrder,
              probability,
              closed || won,
              won,
            );
          onSaved();
        });
      }}
    >
      <Field title="Stage name">
        <input
          className={control}
          required
          maxLength={100}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <Field title="Probability (%)">
        <input
          className={control}
          type="number"
          min={0}
          max={100}
          step={1}
          value={probability}
          onChange={(e) => setProbability(Number(e.target.value))}
        />
      </Field>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={closed || won}
          onChange={(e) => {
            setClosed(e.target.checked);
            if (!e.target.checked) setWon(false);
          }}
        />
        Closed stage
      </label>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={won}
          onChange={(e) => {
            setWon(e.target.checked);
            if (e.target.checked) setClosed(true);
          }}
        />
        Won stage
      </label>
      {action.error && (
        <p role="alert" className="text-red-700">
          {action.error}
        </p>
      )}
      <button className={primary} disabled={action.pending}>
        {stage ? "Save stage" : "Create stage"}
      </button>
    </form>
  );
}
