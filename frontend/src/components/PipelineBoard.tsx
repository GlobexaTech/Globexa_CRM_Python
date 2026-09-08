"use client";

import {
  useEffect,
  useRef,
  useState,
  type DragEvent,
} from "react";

import {
  Columns3,
  List,
  Mail,
  Search,
  Plus,
  Sparkles,
  GripVertical,
  CheckSquare,
  Trash2,
  X,
} from "lucide-react";

import LeadDrawer from "@/components/LeadDrawer";
import LeadFilters from "@/components/LeadFilters";

type Lead = {
  id: number;
  name: string;
  email: string;
  source: string;
  score: number;
  stage: string;
};

const LEADS_KEY = "globexa-pipeline";
const STAGES_KEY = "globexa-stages";

const defaultStages = [
  "New",
  "Contacted",
  "Qualified",
  "Proposal",
  "Won",
  "Lost",
];

const initialLeads: Lead[] = [
  {
    id: 1,
    name: "Aman Sharma",
    email: "aman@example.com",
    source: "Facebook",
    score: 92,
    stage: "New",
  },
  {
    id: 2,
    name: "Priya Singh",
    email: "priya@example.com",
    source: "Instagram",
    score: 95,
    stage: "New",
  },
  {
    id: 3,
    name: "Rahul Mehta",
    email: "rahul@example.com",
    source: "Referral",
    score: 79,
    stage: "Contacted",
  },
  {
    id: 4,
    name: "Sarah Khan",
    email: "sarah@example.com",
    source: "Website",
    score: 88,
    stage: "Qualified",
  },
];

export default function PipelineBoard() {
  const boardRef = useRef<HTMLDivElement>(null);

  const [leads, setLeads] = useState<Lead[]>([]);
  const [stages, setStages] = useState<string[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [selectedLead, setSelectedLead] =
    useState<Lead | null>(null);

  const [view, setView] =
    useState<"board" | "table">("board");

  const [search, setSearch] = useState("");
  const [newStage, setNewStage] = useState("");
  const [aiCommand, setAiCommand] = useState("");
  const [message, setMessage] = useState("");

  const [stageFilter, setStageFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [scoreFilter, setScoreFilter] = useState("");
  const [sort, setSort] = useState("default");

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const [dragStage, setDragStage] =
    useState<string | null>(null);

  const [emailOpen, setEmailOpen] = useState(false);
  const [subject, setSubject] = useState("");
  const [emailBody, setEmailBody] = useState("");

  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const savedLeads =
        localStorage.getItem(LEADS_KEY);

      const savedStages =
        localStorage.getItem(STAGES_KEY);

      const loadedLeads: Lead[] =
        savedLeads
          ? JSON.parse(savedLeads)
          : initialLeads;

      const normalized = loadedLeads.map(
        (lead) => ({
          ...lead,
          email:
            lead.email ||
            `${lead.name
              .replace(/\s+/g, ".")
              .toLowerCase()}@example.com`,
        })
      );

      setLeads(normalized);

      setStages(
        savedStages
          ? JSON.parse(savedStages)
          : defaultStages
      );
    } catch {
      setLeads(initialLeads);
      setStages(defaultStages);
    }

    setReady(true);
  }, []);

  function saveLeads(updated: Lead[]) {
    setLeads(updated);

    localStorage.setItem(
      LEADS_KEY,
      JSON.stringify(updated)
    );
  }

  function saveStages(updated: string[]) {
    setStages(updated);

    localStorage.setItem(
      STAGES_KEY,
      JSON.stringify(updated)
    );
  }

  function moveLead(
    id: number,
    stage: string
  ) {
    const updated = leads.map((lead) =>
      lead.id === id
        ? { ...lead, stage }
        : lead
    );

    saveLeads(updated);

    setSelectedLead((current) =>
      current?.id === id
        ? { ...current, stage }
        : current
    );

    setMessage(
      `Lead moved to ${stage}.`
    );
  }

  function bulkMove(stage: string) {
    if (!selected.length) return;

    const updated = leads.map((lead) =>
      selected.includes(lead.id)
        ? { ...lead, stage }
        : lead
    );

    saveLeads(updated);

    if (
      selectedLead &&
      selected.includes(selectedLead.id)
    ) {
      setSelectedLead({
        ...selectedLead,
        stage,
      });
    }

    setMessage(
      `${selected.length} lead(s) moved to ${stage}.`
    );
  }

  function deleteSelected() {
    if (!selected.length) return;

    const approved = window.confirm(
      `Delete ${selected.length} selected lead(s)?`
    );

    if (!approved) return;

    saveLeads(
      leads.filter(
        (lead) =>
          !selected.includes(lead.id)
      )
    );

    if (
      selectedLead &&
      selected.includes(selectedLead.id)
    ) {
      setSelectedLead(null);
    }

    setSelected([]);

    setMessage(
      "Selected leads deleted."
    );
  }

  function moveStage(
    from: string,
    to: string
  ) {
    if (!from || from === to) return;

    const updated = [...stages];

    const fromIndex =
      updated.indexOf(from);

    const toIndex =
      updated.indexOf(to);

    if (
      fromIndex === -1 ||
      toIndex === -1
    ) {
      return;
    }

    updated.splice(fromIndex, 1);
    updated.splice(toIndex, 0, from);

    saveStages(updated);
  }

  function addStage(name: string) {
    const stage = name.trim();

    if (!stage) return false;

    const exists = stages.some(
      (item) =>
        item.toLowerCase() ===
        stage.toLowerCase()
    );

    if (exists) {
      setMessage(
        `Stage "${stage}" already exists.`
      );

      return false;
    }

    saveStages([
      ...stages,
      stage,
    ]);

    setMessage(
      `Stage "${stage}" created.`
    );

    return true;
  }

  function addManualStage() {
    if (addStage(newStage)) {
      setNewStage("");
    }
  }

  function runAICommand() {
    const command =
      aiCommand.trim();

    const match =
      command.match(
        /(?:add|create|make).*(?:stage)(?: called| named)?\s+["']?(.+?)["']?$/i
      ) ||
      command.match(
        /(?:add|create|make)\s+["']?(.+?)["']?\s+stage$/i
      );

    if (!match) {
      setMessage(
        'Try: "Add a stage called Follow Up"'
      );

      return;
    }

    if (addStage(match[1])) {
      setAiCommand("");
    }
  }

  function toggleLead(id: number) {
    setSelected((old) =>
      old.includes(id)
        ? old.filter(
            (item) => item !== id
          )
        : [...old, id]
    );
  }

  const sources = [
    ...new Set(
      leads.map(
        (lead) => lead.source
      )
    ),
  ];

  let filtered = leads.filter(
    (lead) => {
      const haystack =
        `${lead.name} ${lead.email} ${lead.source} ${lead.stage}`
          .toLowerCase();

      const matchesSearch =
        haystack.includes(
          search.toLowerCase()
        );

      const matchesStage =
        !stageFilter ||
        lead.stage === stageFilter;

      const matchesSource =
        !sourceFilter ||
        lead.source === sourceFilter;

      const matchesScore =
        !scoreFilter ||
        (scoreFilter === "low"
          ? lead.score < 70
          : lead.score >=
            Number(scoreFilter));

      return (
        matchesSearch &&
        matchesStage &&
        matchesSource &&
        matchesScore
      );
    }
  );

  if (sort === "score-high") {
    filtered = [...filtered].sort(
      (a, b) =>
        b.score - a.score
    );
  }

  if (sort === "score-low") {
    filtered = [...filtered].sort(
      (a, b) =>
        a.score - b.score
    );
  }

  if (sort === "name") {
    filtered = [...filtered].sort(
      (a, b) =>
        a.name.localeCompare(
          b.name
        )
    );
  }

  if (sort === "stage") {
    filtered = [...filtered].sort(
      (a, b) =>
        stages.indexOf(a.stage) -
        stages.indexOf(b.stage)
    );
  }

  const totalPages = Math.max(
    1,
    Math.ceil(
      filtered.length / pageSize
    )
  );

  const tableLeads =
    filtered.slice(
      (page - 1) * pageSize,
      page * pageSize
    );

  useEffect(() => {
    setPage(1);
  }, [
    search,
    stageFilter,
    sourceFilter,
    scoreFilter,
    sort,
    pageSize,
  ]);

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const visibleIds =
    filtered.map(
      (lead) => lead.id
    );

  const allSelected =
    visibleIds.length > 0 &&
    visibleIds.every(
      (id) =>
        selected.includes(id)
    );

  function toggleAll() {
    if (allSelected) {
      setSelected((old) =>
        old.filter(
          (id) =>
            !visibleIds.includes(id)
        )
      );

      return;
    }

    setSelected((old) => [
      ...new Set([
        ...old,
        ...visibleIds,
      ]),
    ]);
  }

  function autoScroll(
    e: DragEvent<HTMLDivElement>
  ) {
    const board =
      boardRef.current;

    if (!board) return;

    const rect =
      board.getBoundingClientRect();

    const edge = 130;
    const speed = 32;

    if (
      e.clientX <
      rect.left + edge
    ) {
      board.scrollLeft -= speed;
    }

    if (
      e.clientX >
      rect.right - edge
    ) {
      board.scrollLeft += speed;
    }
  }

  if (!ready) {
    return (
      <div className="card flex min-h-96 items-center justify-center text-sm text-[var(--muted)]">
        Loading pipeline...
      </div>
    );
  }

  return (
    <>
      {/* TOP TOOLBAR */}

      <div className="mb-4 flex flex-wrap gap-3">
        <div className="card flex min-w-[250px] flex-1 items-center gap-2 px-4">
          <Search
            size={17}
            className="text-[var(--muted)]"
          />

          <input
            value={search}
            onChange={(e) =>
              setSearch(
                e.target.value
              )
            }
            placeholder="Search leads..."
            className="w-full bg-transparent py-3 text-sm outline-none"
          />
        </div>

        <div className="card flex items-center p-1">
          <button
            onClick={() =>
              setView("board")
            }
            className={`rounded-lg p-2 ${
              view === "board"
                ? "bg-[var(--blue)]"
                : ""
            }`}
            title="Board view"
          >
            <Columns3 size={17} />
          </button>

          <button
            onClick={() =>
              setView("table")
            }
            className={`rounded-lg p-2 ${
              view === "table"
                ? "bg-[var(--blue)]"
                : ""
            }`}
            title="Table view"
          >
            <List size={17} />
          </button>
        </div>

        <div className="card flex min-w-[220px] items-center p-1">
          <input
            value={newStage}
            onChange={(e) =>
              setNewStage(
                e.target.value
              )
            }
            onKeyDown={(e) => {
              if (
                e.key === "Enter"
              ) {
                addManualStage();
              }
            }}
            placeholder="New stage..."
            className="min-w-0 flex-1 bg-transparent px-3 text-sm outline-none"
          />

          <button
            onClick={
              addManualStage
            }
            className="rounded-lg bg-[var(--blue)] p-2"
          >
            <Plus size={17} />
          </button>
        </div>

        <div className="card flex min-w-[280px] items-center p-1">
          <Sparkles
            size={17}
            className="ml-3 text-[var(--cyan)]"
          />

          <input
            value={aiCommand}
            onChange={(e) =>
              setAiCommand(
                e.target.value
              )
            }
            onKeyDown={(e) => {
              if (
                e.key === "Enter"
              ) {
                runAICommand();
              }
            }}
            placeholder='Ask AI: "Add Follow Up stage"'
            className="min-w-0 flex-1 bg-transparent px-3 text-sm outline-none"
          />

          <button
            onClick={
              runAICommand
            }
            className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
          >
            Run
          </button>
        </div>
      </div>

      {/* FILTERS */}

      <LeadFilters
        stage={stageFilter}
        source={sourceFilter}
        score={scoreFilter}
        sort={sort}
        stages={stages}
        sources={sources}
        setStage={setStageFilter}
        setSource={setSourceFilter}
        setScore={setScoreFilter}
        setSort={setSort}
        reset={() => {
          setStageFilter("");
          setSourceFilter("");
          setScoreFilter("");
          setSort("default");
          setSearch("");
        }}
      />

      {/* BULK ACTIONS */}

      <div className="mb-4 flex min-h-10 flex-wrap items-center gap-3">
        <button
          onClick={toggleAll}
          className="flex items-center gap-2 text-sm text-[var(--muted)]"
        >
          <CheckSquare size={17} />

          {allSelected
            ? "Deselect all"
            : `Select all (${filtered.length})`}
        </button>

        {selected.length > 0 && (
          <>
            <span className="text-sm text-[var(--cyan)]">
              {selected.length} selected
            </span>

            <select
              defaultValue=""
              onChange={(e) => {
                if (
                  e.target.value
                ) {
                  bulkMove(
                    e.target.value
                  );

                  e.target.value =
                    "";
                }
              }}
              className="rounded-lg border border-[var(--border)] bg-[var(--panel)] px-3 py-2 text-sm"
            >
              <option
                value=""
                disabled
              >
                Move to...
              </option>

              {stages.map(
                (stage) => (
                  <option
                    key={stage}
                    value={stage}
                  >
                    {stage}
                  </option>
                )
              )}
            </select>

            <button
              onClick={() =>
                setEmailOpen(true)
              }
              className="flex items-center gap-2 rounded-lg bg-[var(--blue)] px-3 py-2 text-sm"
            >
              <Mail size={16} />
              Bulk Email
            </button>

            <button
              onClick={
                deleteSelected
              }
              className="flex items-center gap-2 rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
            >
              <Trash2 size={16} />
              Delete
            </button>

            <button
              onClick={() =>
                setSelected([])
              }
              className="rounded-lg border border-[var(--border)] p-2"
            >
              <X size={16} />
            </button>
          </>
        )}
      </div>

      {message && (
        <p className="mb-4 text-xs text-[var(--cyan)]">
          ✦ {message}
        </p>
      )}

      {/* BOARD */}

      {view === "board" && (
        <div
          ref={boardRef}
          onDragOver={(e) => {
            e.preventDefault();
            autoScroll(e);
          }}
          className="hide-scrollbar flex gap-3 overflow-x-auto"
        >
          {stages.map(
            (stage) => {
              const items =
                filtered.filter(
                  (lead) =>
                    lead.stage ===
                    stage
                );

              return (
                <div
                  key={stage}
                  onDragOver={(e) =>
                    e.preventDefault()
                  }
                  onDrop={(e) => {
                    e.preventDefault();

                    const type =
                      e.dataTransfer.getData(
                        "dragType"
                      );

                    if (
                      type ===
                      "stage"
                    ) {
                      moveStage(
                        e.dataTransfer.getData(
                          "stageName"
                        ),
                        stage
                      );

                      setDragStage(
                        null
                      );

                      return;
                    }

                    const id =
                      Number(
                        e.dataTransfer.getData(
                          "leadId"
                        )
                      );

                    if (id) {
                      moveLead(
                        id,
                        stage
                      );
                    }
                  }}
                  className={`card min-h-[420px] min-w-[210px] flex-1 p-3 transition ${
                    dragStage ===
                    stage
                      ? "opacity-50"
                      : ""
                  }`}
                >
                  <div
                    draggable
                    onDragStart={(
                      e
                    ) => {
                      e.dataTransfer.effectAllowed =
                        "move";

                      e.dataTransfer.setData(
                        "dragType",
                        "stage"
                      );

                      e.dataTransfer.setData(
                        "stageName",
                        stage
                      );

                      setDragStage(
                        stage
                      );
                    }}
                    onDragEnd={() =>
                      setDragStage(
                        null
                      )
                    }
                    className="mb-4 flex cursor-grab items-center justify-between active:cursor-grabbing"
                  >
                    <div className="flex items-center gap-2">
                      <GripVertical
                        size={15}
                        className="text-[var(--muted)]"
                      />

                      <b className="text-sm">
                        {stage}
                      </b>
                    </div>

                    <span className="text-xs text-[var(--muted)]">
                      {items.length}
                    </span>
                  </div>

                  <div className="space-y-2">
                    {items.map(
                      (lead) => (
                        <LeadCard
                          key={
                            lead.id
                          }
                          lead={
                            lead
                          }
                          selected={selected.includes(
                            lead.id
                          )}
                          toggle={() =>
                            toggleLead(
                              lead.id
                            )
                          }
                          open={() =>
                            setSelectedLead(
                              lead
                            )
                          }
                        />
                      )
                    )}

                    {!items.length && (
                      <p className="py-6 text-center text-xs text-[var(--muted)]">
                        Drop leads here
                      </p>
                    )}
                  </div>
                </div>
              );
            }
          )}
        </div>
      )}

      {/* TABLE */}

      {view === "table" && (
        <div className="card overflow-hidden">
          <div className="grid grid-cols-[40px_1.4fr_1.8fr_1fr_1fr_70px] border-b border-[var(--border)] px-4 py-2 text-[10px] uppercase tracking-wider text-[var(--muted)]">
            <span />
            <span>Lead</span>
            <span>Email</span>
            <span>Source</span>
            <span>Stage</span>
            <span>Score</span>
          </div>

          {tableLeads.map(
            (lead) => (
              <div
                key={lead.id}
                className="grid grid-cols-[40px_1.4fr_1.8fr_1fr_1fr_70px] items-center border-b border-[var(--border)] px-4 py-2 text-sm transition last:border-0 hover:bg-[var(--panel2)]"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(
                    lead.id
                  )}
                  onChange={() =>
                    toggleLead(
                      lead.id
                    )
                  }
                />

                <button
                  onClick={() =>
                    setSelectedLead(
                      lead
                    )
                  }
                  className="truncate text-left font-medium hover:text-[var(--cyan)]"
                >
                  {lead.name}
                </button>

                <span className="truncate text-[var(--muted)]">
                  {lead.email}
                </span>

                <span className="truncate">
                  {lead.source}
                </span>

                <span>
                  <span className="rounded-md bg-[var(--panel2)] px-2 py-1 text-xs">
                    {lead.stage}
                  </span>
                </span>

                <span className="font-medium text-[var(--cyan)]">
                  {lead.score}
                </span>
              </div>
            )
          )}

          {!tableLeads.length && (
            <p className="p-8 text-center text-sm text-[var(--muted)]">
              No leads found.
            </p>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border)] px-4 py-3">
            <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
              <span>Show</span>

              <select
                value={pageSize}
                onChange={(e) =>
                  setPageSize(
                    Number(
                      e.target.value
                    )
                  )
                }
                className="rounded border border-[var(--border)] bg-[var(--panel)] px-2 py-1"
              >
                <option value={25}>
                  25
                </option>

                <option value={50}>
                  50
                </option>

                <option value={100}>
                  100
                </option>
              </select>

              <span>
                leads ·{" "}
                {filtered.length}{" "}
                total
              </span>
            </div>

            <div className="flex items-center gap-3 text-sm">
              <button
                disabled={
                  page === 1
                }
                onClick={() =>
                  setPage(
                    (old) =>
                      Math.max(
                        1,
                        old - 1
                      )
                  )
                }
                className="rounded-lg border border-[var(--border)] px-3 py-1.5 disabled:opacity-30"
              >
                Previous
              </button>

              <span className="text-xs text-[var(--muted)]">
                Page {page} of{" "}
                {totalPages}
              </span>

              <button
                disabled={
                  page ===
                  totalPages
                }
                onClick={() =>
                  setPage(
                    (old) =>
                      Math.min(
                        totalPages,
                        old + 1
                      )
                  )
                }
                className="rounded-lg border border-[var(--border)] px-3 py-1.5 disabled:opacity-30"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}

      {/* DRAWER — FIXED VERSION */}

      {selectedLead && (
        <>
          <div
            onClick={() =>
              setSelectedLead(null)
            }
            className="fixed inset-0 z-40 bg-black/50"
          />

          <LeadDrawer
            lead={selectedLead}
            stages={stages}
            onStageChange={(
              stage
            ) =>
              moveLead(
                selectedLead.id,
                stage
              )
            }
            onClose={() =>
              setSelectedLead(null)
            }
          />
        </>
      )}

      {/* BULK EMAIL */}

      {emailOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="card w-full max-w-[620px] p-6">
            <div className="mb-5 flex items-start justify-between">
              <div>
                <p className="text-xs tracking-[2px] text-[var(--blue2)]">
                  BULK EMAIL
                </p>

                <h2 className="mt-1 text-xl font-semibold">
                  Email{" "}
                  {selected.length}{" "}
                  Leads
                </h2>
              </div>

              <button
                onClick={() =>
                  setEmailOpen(
                    false
                  )
                }
              >
                <X size={20} />
              </button>
            </div>

            <div className="mb-4 max-h-20 overflow-y-auto rounded-lg bg-[var(--panel2)] p-3 text-xs text-[var(--muted)]">
              {leads
                .filter((lead) =>
                  selected.includes(
                    lead.id
                  )
                )
                .map(
                  (lead) =>
                    lead.email
                )
                .join(", ")}
            </div>

            <input
              value={subject}
              onChange={(e) =>
                setSubject(
                  e.target.value
                )
              }
              placeholder="Email subject"
              className="card mb-3 w-full px-4 py-3 text-sm outline-none"
            />

            <textarea
              value={emailBody}
              onChange={(e) =>
                setEmailBody(
                  e.target.value
                )
              }
              placeholder="Write your email..."
              rows={8}
              className="card w-full resize-none px-4 py-3 text-sm outline-none"
            />

            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() =>
                  setEmailOpen(
                    false
                  )
                }
                className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm"
              >
                Cancel
              </button>

              <button
                onClick={() => {
                  setMessage(
                    `${selected.length} email(s) prepared for sending.`
                  );

                  setEmailOpen(
                    false
                  );
                }}
                className="rounded-lg bg-[var(--blue)] px-4 py-2 text-sm"
              >
                Send Email
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function LeadCard({
  lead,
  selected,
  toggle,
  open,
}: {
  lead: Lead;
  selected: boolean;
  toggle: () => void;
  open: () => void;
}) {
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.stopPropagation();

        e.dataTransfer.effectAllowed =
          "move";

        e.dataTransfer.setData(
          "dragType",
          "lead"
        );

        e.dataTransfer.setData(
          "leadId",
          String(lead.id)
        );
      }}
      className={`rounded-xl border bg-[var(--panel2)] p-3 transition ${
        selected
          ? "border-[var(--blue)]"
          : "border-[var(--border)] hover:border-[var(--blue2)]"
      }`}
    >
      <div className="flex gap-2">
        <input
          type="checkbox"
          checked={selected}
          onChange={toggle}
          onClick={(e) =>
            e.stopPropagation()
          }
        />

        <button
          onClick={open}
          className="min-w-0 flex-1 text-left"
        >
          <div className="flex justify-between gap-2">
            <b className="truncate text-sm">
              {lead.name}
            </b>

            <span className="text-xs text-[var(--cyan)]">
              {lead.score}
            </span>
          </div>

          <p className="mt-2 truncate text-xs text-[var(--muted)]">
            {lead.source}
          </p>
        </button>
      </div>

      <div className="mt-3 h-1 rounded bg-[var(--border)]">
        <div
          className="h-1 rounded bg-[var(--blue)]"
          style={{
            width: `${lead.score}%`,
          }}
        />
      </div>
    </div>
  );
}