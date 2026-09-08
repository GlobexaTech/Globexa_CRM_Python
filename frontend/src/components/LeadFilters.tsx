"use client";

import { Filter, RotateCcw } from "lucide-react";

type Props = {
  stage: string;
  source: string;
  score: string;
  sort: string;

  stages: string[];
  sources: string[];

  setStage: (value: string) => void;
  setSource: (value: string) => void;
  setScore: (value: string) => void;
  setSort: (value: string) => void;

  reset: () => void;
};

export default function LeadFilters({
  stage,
  source,
  score,
  sort,
  stages,
  sources,
  setStage,
  setSource,
  setScore,
  setSort,
  reset,
}: Props) {
  const input =
    "rounded-lg border border-[var(--border)] bg-[var(--panel)] px-3 py-2 text-sm outline-none";

  return (
    <div className="card mb-4 flex flex-wrap items-center gap-2 p-2">

      <div className="flex items-center gap-2 px-2 text-sm text-[var(--muted)]">
        <Filter size={16} />
        Filters
      </div>

      <select
        value={stage}
        onChange={(e) => setStage(e.target.value)}
        className={input}
      >
        <option value="">All Stages</option>

        {stages.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>

      <select
        value={source}
        onChange={(e) => setSource(e.target.value)}
        className={input}
      >
        <option value="">All Sources</option>

        {sources.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>

      <select
        value={score}
        onChange={(e) => setScore(e.target.value)}
        className={input}
      >
        <option value="">All Scores</option>
        <option value="90">90+ High Intent</option>
        <option value="80">80+</option>
        <option value="70">70+</option>
        <option value="low">Below 70</option>
      </select>

      <select
        value={sort}
        onChange={(e) => setSort(e.target.value)}
        className={input}
      >
        <option value="default">Default Order</option>
        <option value="score-high">Score: High → Low</option>
        <option value="score-low">Score: Low → High</option>
        <option value="name">Name: A → Z</option>
        <option value="stage">Stage</option>
      </select>

      <button
        onClick={reset}
        className="ml-auto flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-[var(--muted)] hover:bg-[var(--panel2)] hover:text-white"
      >
        <RotateCcw size={15} />
        Reset
      </button>

    </div>
  );
}