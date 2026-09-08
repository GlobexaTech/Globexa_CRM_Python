"use client";

import { useEffect, useState } from "react";

type Lead = { stage: string };

const defaultStages = [
  "New",
  "Contacted",
  "Qualified",
  "Proposal",
  "Won",
  "Lost",
];

export default function StageOverview() {
  const [stages, setStages] = useState<string[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);

  useEffect(() => {
    setStages(
      JSON.parse(localStorage.getItem("globexa-stages") || "null") ||
        defaultStages
    );

    setLeads(
      JSON.parse(localStorage.getItem("globexa-pipeline") || "[]")
    );
  }, []);

  return (
    <div className="card mb-8 p-5">
      <div className="mb-4">
        <p className="text-xs tracking-[2px] text-[var(--blue2)]">
          PIPELINE OVERVIEW
        </p>
        <h2 className="mt-1 font-semibold">Lead Stages</h2>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {stages.map((stage) => (
          <div
            key={stage}
            className="rounded-xl border border-[var(--border)] bg-[var(--panel2)] p-4"
          >
            <p className="truncate text-xs text-[var(--muted)]">
              {stage}
            </p>

            <p className="mt-2 text-2xl font-semibold">
              {leads.filter((lead) => lead.stage === stage).length}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}