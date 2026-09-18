"use client";
import Link from "next/link";
import { useState } from "react";
import { useResource } from "@/hooks/useResource";
import { timestamp } from "@/services/operations";
import type { Page } from "@/types/operations";
import type { AgentExecution } from "@/types/workforce";
import { ResourceState } from "./ResourceState";
import { Dialog } from "./Dialog";
import { ExecutionDetail } from "./WorkforceWorkspace";

export function CustomerWorkforce({
  kind,
  id,
}: {
  kind: "lead" | "contact";
  id: string;
}) {
  const [selected, setSelected] = useState("");
  const [offset, setOffset] = useState(0);
  const executions = useResource<Page<AgentExecution>>(
    `/workforce/executions?entity_type=${kind}&entity_id=${id}&limit=10&offset=${offset}`,
  );
  return (
    <section className="card mb-6 p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Customer AI activity</h2>
        <Link
          className="crm-secondary"
          href={`/ai-workforce?entity_type=${kind}&entity_id=${id}`}
        >
          Create agent task
        </Link>
      </div>
      <ResourceState
        loading={executions.isLoading}
        error={executions.error}
        empty={executions.data?.items.length === 0}
        onRetry={executions.refetch}
      >
        <ul className="space-y-3">
          {executions.data?.items.map((execution) => (
            <li key={execution.id}>
              <button
                className="w-full rounded-xl border border-[var(--border)] p-3 text-left"
                onClick={() => setSelected(execution.id)}
              >
                <span className="flex flex-wrap justify-between gap-2">
                  <strong className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                    {execution.task.objective}
                  </strong>
                  <span>{execution.state}</span>
                </span>
                <span className="crm-muted mt-2 block">
                  {execution.agent_name} · {timestamp(execution.created_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </ResourceState>
      <nav className="crm-actions mt-3" aria-label="Customer AI pages">
        <button
          className="crm-secondary"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 10))}
        >
          Previous AI activity
        </button>
        <button
          className="crm-secondary"
          disabled={!executions.data || offset + 10 >= executions.data.total}
          onClick={() => setOffset(offset + 10)}
        >
          Next AI activity
        </button>
        <button
          className="crm-secondary"
          onClick={() => void executions.refetch()}
        >
          Refresh AI activity
        </button>
      </nav>
      <Dialog
        open={Boolean(selected)}
        title="Execution details"
        onClose={() => setSelected("")}
      >
        {selected && (
          <ExecutionDetail
            key={selected}
            id={selected}
            onRetryCreated={setSelected}
          />
        )}
      </Dialog>
    </section>
  );
}
