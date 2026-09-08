"use client";

import { useEffect, useState } from "react";
import {
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";

import Sidebar from "@/components/Sidebar";

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

const defaultLeads: Lead[] = [
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

export default function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [stages, setStages] = useState(defaultStages);

  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [selected, setSelected] = useState<number[]>([]);

  const [addOpen, setAddOpen] = useState(false);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [source, setSource] = useState("Website");
  const [score, setScore] = useState(80);
  const [stage, setStage] = useState("New");

  useEffect(() => {
    try {
      const savedLeads = localStorage.getItem(LEADS_KEY);
      const savedStages = localStorage.getItem(STAGES_KEY);

      const loaded: Lead[] = savedLeads
        ? JSON.parse(savedLeads)
        : defaultLeads;

      setLeads(
        loaded.map((lead) => ({
          ...lead,
          email:
            lead.email ||
            `${lead.name
              .replace(/\s+/g, ".")
              .toLowerCase()}@example.com`,
        }))
      );

      if (savedStages) {
        setStages(JSON.parse(savedStages));
      }
    } catch {
      setLeads(defaultLeads);
    }
  }, []);

  function save(updated: Lead[]) {
    setLeads(updated);
    localStorage.setItem(
      LEADS_KEY,
      JSON.stringify(updated)
    );
  }

  function addLead() {
    if (!name.trim()) return;

    const newLead: Lead = {
      id: Date.now(),
      name: name.trim(),
      email: email.trim() || "lead@example.com",
      source,
      score: Math.min(100, Math.max(0, score)),
      stage,
    };

    save([newLead, ...leads]);

    setName("");
    setEmail("");
    setSource("Website");
    setScore(80);
    setStage(stages[0] || "New");
    setAddOpen(false);
  }

  function changeStage(id: number, nextStage: string) {
    save(
      leads.map((lead) =>
        lead.id === id
          ? { ...lead, stage: nextStage }
          : lead
      )
    );
  }

  function toggle(id: number) {
    setSelected((old) =>
      old.includes(id)
        ? old.filter((item) => item !== id)
        : [...old, id]
    );
  }

  function deleteSelected() {
    if (!selected.length) return;

    if (
      !window.confirm(
        `Delete ${selected.length} selected lead(s)?`
      )
    ) {
      return;
    }

    save(
      leads.filter(
        (lead) => !selected.includes(lead.id)
      )
    );

    setSelected([]);
  }

  const filtered = leads.filter((lead) => {
    const query = search.toLowerCase();

    const matchesSearch =
      `${lead.name} ${lead.email} ${lead.source}`
        .toLowerCase()
        .includes(query);

    const matchesStage =
      !stageFilter || lead.stage === stageFilter;

    return matchesSearch && matchesStage;
  });

  const filteredIds = filtered.map((lead) => lead.id);

  const allSelected =
    filteredIds.length > 0 &&
    filteredIds.every((id) =>
      selected.includes(id)
    );

  function toggleAll() {
    if (allSelected) {
      setSelected((old) =>
        old.filter(
          (id) => !filteredIds.includes(id)
        )
      );
    } else {
      setSelected((old) => [
        ...new Set([...old, ...filteredIds]),
      ]);
    }
  }

  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />

      <section className="min-w-0 flex-1 p-8">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <p className="text-xs tracking-[3px] text-[var(--blue2)]">
              CUSTOMER DATABASE
            </p>

            <h1 className="mt-2 text-3xl font-semibold">
              Leads
            </h1>

            <p className="mt-1 text-sm text-[var(--muted)]">
              Manage, qualify and organize every opportunity.
            </p>
          </div>

          <button
            onClick={() => setAddOpen(true)}
            className="flex items-center gap-2 rounded-xl bg-[var(--blue)] px-4 py-2.5 text-sm"
          >
            <Plus size={17} />
            New Lead
          </button>
        </header>

        <div className="card mb-4 flex flex-wrap gap-3 p-3">
          <div className="flex min-w-[260px] flex-1 items-center gap-2">
            <Search
              size={17}
              className="text-[var(--muted)]"
            />

            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, email or source..."
              className="w-full bg-transparent text-sm outline-none"
            />
          </div>

          <select
            value={stageFilter}
            onChange={(e) =>
              setStageFilter(e.target.value)
            }
            className="rounded-lg border border-[var(--border)] bg-[var(--panel)] px-3 py-2 text-sm"
          >
            <option value="">All Stages</option>

            {stages.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>

        <div className="mb-3 flex items-center gap-3">
          <button
            onClick={toggleAll}
            className="text-sm text-[var(--muted)]"
          >
            {allSelected
              ? "Deselect all"
              : `Select all (${filtered.length})`}
          </button>

          {selected.length > 0 && (
            <>
              <span className="text-sm text-[var(--cyan)]">
                {selected.length} selected
              </span>

              <button
                onClick={deleteSelected}
                className="flex items-center gap-2 rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
              >
                <Trash2 size={15} />
                Delete
              </button>
            </>
          )}
        </div>

        <div className="card overflow-hidden">
          <div className="grid grid-cols-[42px_1.4fr_1.8fr_1fr_1fr_70px] border-b border-[var(--border)] px-4 py-2 text-[10px] uppercase tracking-wider text-[var(--muted)]">
            <span />
            <span>Lead</span>
            <span>Email</span>
            <span>Source</span>
            <span>Stage</span>
            <span>Score</span>
          </div>

          {filtered.map((lead) => (
            <div
              key={lead.id}
              className="grid grid-cols-[42px_1.4fr_1.8fr_1fr_1fr_70px] items-center border-b border-[var(--border)] px-4 py-2.5 text-sm last:border-0 hover:bg-[var(--panel2)]"
            >
              <input
                type="checkbox"
                checked={selected.includes(lead.id)}
                onChange={() => toggle(lead.id)}
              />

              <b className="truncate">
                {lead.name}
              </b>

              <span className="truncate text-[var(--muted)]">
                {lead.email}
              </span>

              <span>{lead.source}</span>

              <select
                value={lead.stage}
                onChange={(e) =>
                  changeStage(
                    lead.id,
                    e.target.value
                  )
                }
                className="w-fit rounded-md border border-[var(--border)] bg-[var(--panel)] px-2 py-1 text-xs"
              >
                {stages.map((item) => (
                  <option key={item}>
                    {item}
                  </option>
                ))}
              </select>

              <span className="text-[var(--cyan)]">
                {lead.score}
              </span>
            </div>
          ))}

          {!filtered.length && (
            <p className="p-10 text-center text-sm text-[var(--muted)]">
              No leads found.
            </p>
          )}
        </div>
      </section>

      {addOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="card w-full max-w-lg p-6">
            <div className="mb-5 flex justify-between">
              <div>
                <p className="text-xs tracking-[2px] text-[var(--blue2)]">
                  NEW LEAD
                </p>

                <h2 className="mt-1 text-xl font-semibold">
                  Add Lead
                </h2>
              </div>

              <button
                onClick={() => setAddOpen(false)}
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-3">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Full name"
                className="card w-full px-4 py-3 text-sm outline-none"
              />

              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email"
                className="card w-full px-4 py-3 text-sm outline-none"
              />

              <input
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder="Lead source"
                className="card w-full px-4 py-3 text-sm outline-none"
              />

              <select
                value={stage}
                onChange={(e) => setStage(e.target.value)}
                className="card w-full px-4 py-3 text-sm outline-none"
              >
                {stages.map((item) => (
                  <option key={item}>
                    {item}
                  </option>
                ))}
              </select>

              <input
                type="number"
                min={0}
                max={100}
                value={score}
                onChange={(e) =>
                  setScore(Number(e.target.value))
                }
                placeholder="AI Score"
                className="card w-full px-4 py-3 text-sm outline-none"
              />
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setAddOpen(false)}
                className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm"
              >
                Cancel
              </button>

              <button
                onClick={addLead}
                className="rounded-lg bg-[var(--blue)] px-4 py-2 text-sm"
              >
                Add Lead
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}