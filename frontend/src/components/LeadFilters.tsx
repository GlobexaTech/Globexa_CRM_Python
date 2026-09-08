"use client";
import { Filter, RotateCcw } from "lucide-react";
import { LEAD_STATUSES, LEAD_SOURCES } from "@/types/crm";
import { label } from "@/services/crm";
import { control } from "@/app/leads/CrmFields";
export default function LeadFilters({
  status,
  source,
  onStatus,
  onSource,
  onReset,
}: {
  status: string;
  source: string;
  onStatus: (v: string) => void;
  onSource: (v: string) => void;
  onReset: () => void;
}) {
  return (
    <div className="card mb-4 flex flex-wrap items-center gap-3 p-3">
      <span className="flex items-center gap-2 text-sm">
        <Filter size={16} />
        Filters
      </span>
      <label className="grid gap-1 text-xs">
        Lead status
        <select
          className={control}
          value={status}
          onChange={(e) => onStatus(e.target.value)}
        >
          <option value="">All statuses</option>
          {LEAD_STATUSES.map((v) => (
            <option key={v} value={v}>
              {label(v)}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-xs">
        Lead source
        <select
          className={control}
          value={source}
          onChange={(e) => onSource(e.target.value)}
        >
          <option value="">All sources</option>
          {LEAD_SOURCES.map((v) => (
            <option key={v} value={v}>
              {label(v)}
            </option>
          ))}
        </select>
      </label>
      <button
        className="ml-auto flex items-center gap-2 rounded-lg px-3 py-2 text-sm"
        onClick={onReset}
      >
        <RotateCcw size={15} />
        Reset
      </button>
    </div>
  );
}
