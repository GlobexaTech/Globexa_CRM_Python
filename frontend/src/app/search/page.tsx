"use client";
import { useState } from "react";
import Link from "next/link";
import Sidebar from "@/components/Sidebar";
import { ResourceState } from "@/components/ResourceState";
import { Dialog } from "@/components/Dialog";
import { useResource } from "@/hooks/useResource";
import { useSession } from "@/auth/SessionProvider";
type Result = {
  id: string;
  entity: string;
  title: string;
  snippet: string;
  rank: number;
  conversation_id?: string | null;
  contact_id?: string | null;
  company_id?: string | null;
  lead_id?: string | null;
  deal_id?: string | null;
};
type Results = {
  items: Result[];
  total: number;
  limit: number;
  offset: number;
};
const entities = [
  ["leads", "leads:read"],
  ["contacts", "contacts:read"],
  ["companies", "companies:read"],
  ["deals", "deals:read"],
  ["tasks", "tasks:read"],
  ["notes", "notes:read"],
  ["messages", "conversations:read"],
  ["conversations", "conversations:read"],
  ["campaigns", "campaigns:read"],
  ["agents", "ai:chat"],
];
function href(row: Result) {
  if (["leads", "contacts", "companies"].includes(row.entity))
    return `/customers/${row.entity}/${row.id}`;
  if (row.entity === "deals") return `/pipeline?deal=${row.id}`;
  if (row.entity === "tasks") return `/tasks?id=${row.id}`;
  if (row.entity === "conversations") return `/conversations?id=${row.id}`;
  if (row.entity === "messages" && row.conversation_id)
    return `/conversations?id=${row.conversation_id}`;
  if (row.entity === "campaigns") return `/campaigns?id=${row.id}`;
  if (row.contact_id) return `/customers/contacts/${row.contact_id}`;
  if (row.lead_id) return `/customers/leads/${row.lead_id}`;
  if (row.company_id) return `/customers/companies/${row.company_id}`;
  if (row.deal_id) return `/pipeline?deal=${row.deal_id}`;
  return null;
}
export default function SearchPage() {
  const { can } = useSession();
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [entity, setEntity] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Result | null>(null);
  const query = new URLSearchParams({
    q: submitted,
    limit: "20",
    offset: String(offset),
  });
  if (entity) query.set("entity", entity);
  const result = useResource<Results>(
    `/operations/search?${query}`,
    !!submitted,
  );
  return (
    <main className="page-shell">
      <Sidebar />
      <section className="page-content">
        <p className="page-eyebrow">WORKSPACE</p>
        <h1 className="page-title">Global search</h1>
        <p className="page-subtitle">
          Search ten CRM record types within your workspace and permissions.
        </p>
        <form
          className="crm-actions my-6"
          onSubmit={(event) => {
            event.preventDefault();
            setSubmitted(q.trim());
            setOffset(0);
          }}
        >
          <label className="crm-field flex-1">
            Search CRM
            <input
              className="crm-input"
              type="search"
              required
              maxLength={500}
              value={q}
              onChange={(event) => setQ(event.target.value)}
            />
          </label>
          <label className="crm-field">
            Record type
            <select
              className="crm-input"
              value={entity}
              onChange={(event) => {
                setEntity(event.target.value);
                setOffset(0);
              }}
            >
              <option value="">All permitted records</option>
              {entities
                .filter(([, permission]) => can(permission))
                .map(([name]) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
            </select>
          </label>
          <button className="crm-button">Search</button>
        </form>
        {!submitted ? (
          <p className="crm-muted">
            Enter a customer name, email, task or message text to begin.
          </p>
        ) : (
          <ResourceState
            loading={result.isLoading}
            error={result.error}
            empty={result.data?.total === 0}
            onRetry={result.refetch}
          >
            <p className="crm-muted mb-3">
              {result.data?.total ?? 0} matches (up to 100 per entity)
            </p>
            <ul className="space-y-3">
              {result.data?.items.map((row) => (
                <li className="card p-5" key={`${row.entity}:${row.id}`}>
                  <span className="badge-soft">{row.entity}</span>
                  <h2 className="font-semibold mt-2">
                    <button
                      className="text-left text-blue-800"
                      onClick={() => setSelected(row)}
                    >
                      {row.title || "Untitled record"}
                    </button>
                  </h2>
                  <p className="crm-muted break-words mt-1">{row.snippet}</p>
                  {href(row) && (
                    <Link className="crm-secondary mt-3" href={href(row)!}>
                      Open record
                    </Link>
                  )}
                </li>
              ))}
            </ul>
            <div className="crm-actions mt-5">
              <button
                className="crm-secondary"
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 20))}
              >
                Previous results
              </button>
              <button
                className="crm-secondary"
                disabled={offset + 20 >= (result.data?.total ?? 0)}
                onClick={() => setOffset(offset + 20)}
              >
                Next results
              </button>
            </div>
          </ResourceState>
        )}
        <Dialog
          open={!!selected}
          title={selected?.title || "Search result"}
          onClose={() => setSelected(null)}
        >
          <p className="crm-muted mb-3">
            {selected?.entity} · {selected?.id}
          </p>
          <p className="whitespace-pre-wrap break-words">{selected?.snippet}</p>
          {selected?.entity === "agents" && (
            <p className="crm-muted mt-4">
              Agent definitions are searchable reference records. Controlled AI
              capabilities are available in the AI workspace.
            </p>
          )}
          {selected && href(selected) && (
            <Link className="crm-button mt-5" href={href(selected)!}>
              Open related record
            </Link>
          )}
        </Dialog>
      </section>
    </main>
  );
}
