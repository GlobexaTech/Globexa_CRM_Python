"use client";
import { useEffect, useState, type ReactNode } from "react";
import { useResource } from "@/hooks/useResource";
import { useSession } from "@/auth/SessionProvider";
import { queryPath, displayName, label } from "@/services/crm";
import type { Paginated } from "@/types/crm";

export const control =
  "w-full rounded-xl border border-[var(--border)] bg-[var(--panel)] px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-[var(--blue)]";
export const button =
  "rounded-xl border border-[var(--border)] px-4 py-2.5 text-sm disabled:opacity-50";
export const primary = `${button} crm-button`;
export function Field({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <label className="grid min-w-0 gap-1.5 text-sm font-medium">
      {title}
      {children}
    </label>
  );
}
export function useDebounced(value: string) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), 300);
    return () => clearTimeout(timer);
  }, [value]);
  return debounced;
}
type PickRecord = {
  id: string;
  title?: string;
  name?: string;
  first_name?: string;
  last_name?: string;
  full_name?: string;
  email?: string;
};
export function EntityPicker({
  entity,
  title,
  value,
  onChange,
  required = false,
}: {
  entity: "leads" | "contacts" | "companies" | "deals" | "users";
  title: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}) {
  const { can, session } = useSession();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const term = useDebounced(search);
  const allowed = can(`${entity}:read`);
  const query = useResource<Paginated<PickRecord>>(
    queryPath(`/${entity}`, { search: term, page, page_size: 20 }),
    allowed,
  );
  const self = entity === "users" && session?.user ? session.user : null;
  const items = query.data?.items ?? (self ? [self] : []);
  const selected = items.find((row) => row.id === value);
  return (
    <div className="grid min-w-0 gap-2 rounded-xl border border-[var(--border)] p-3">
      <Field title={title}>
        <select
          className={control}
          value={value}
          required={required}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">{required ? "Choose a record" : "None"}</option>
          {value && !selected && <option value={value}>{value}</option>}
          {items.map((row) => (
            <option key={row.id} value={row.id}>
              {displayName(row)}
            </option>
          ))}
        </select>
      </Field>
      {allowed && (
        <>
          <input
            aria-label={`Search ${title.toLowerCase()} options`}
            className={control}
            value={search}
            placeholder={`Find ${title.toLowerCase()}…`}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
          <div className="flex items-center justify-between text-xs">
            <button
              type="button"
              disabled={page === 1 || query.isLoading}
              onClick={() => setPage(page - 1)}
            >
              Previous options
            </button>
            <span>{query.isLoading ? "Loading…" : `Page ${page}`}</span>
            <button
              type="button"
              disabled={
                !query.data || page >= query.data.total_pages || query.isLoading
              }
              onClick={() => setPage(page + 1)}
            >
              Next options
            </button>
          </div>
        </>
      )}
      {query.error && (
        <p role="alert" className="text-xs text-red-700">
          Options could not load.{" "}
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </p>
      )}
      {!allowed && entity === "users" && (
        <p className="text-xs text-[var(--muted)]">
          Only your own assignment is available to your role.
        </p>
      )}
    </div>
  );
}
export function EnumField({
  title,
  value,
  options,
  onChange,
  blank,
}: {
  title: string;
  value: string;
  options: readonly string[];
  onChange: (v: string) => void;
  blank?: string;
}) {
  return (
    <Field title={title}>
      <select
        className={control}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {blank !== undefined && <option value="">{blank}</option>}
        {options.map((v) => (
          <option value={v} key={v}>
            {label(v)}
          </option>
        ))}
      </select>
    </Field>
  );
}
export function Pagination({
  page,
  totalPages,
  total,
  onPage,
}: {
  page: number;
  totalPages: number;
  total: number;
  onPage: (p: number) => void;
}) {
  return (
    <nav
      aria-label="Results pages"
      className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm"
    >
      <span>
        {total} records · Page {page} of {Math.max(1, totalPages)}
      </span>
      <div className="flex gap-2">
        <button
          className={button}
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          Previous
        </button>
        <button
          className={button}
          disabled={page >= totalPages}
          onClick={() => onPage(page + 1)}
        >
          Next
        </button>
      </div>
    </nav>
  );
}
