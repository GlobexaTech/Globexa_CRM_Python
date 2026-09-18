"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { useResource } from "@/hooks/useResource";
import { useAction } from "@/hooks/useAction";
import { workforce } from "@/services/workforce";
import { timestamp } from "@/services/operations";
import type { AgentMemory, WorkforceAgent } from "@/types/workforce";
import type { Page } from "@/types/operations";
import { Dialog } from "./Dialog";
import { ResourceState } from "./ResourceState";
import { useConfirm } from "./ConfirmProvider";

export function WorkforceMemory({ agents }: { agents: WorkforceAgent[] }) {
  const [offset, setOffset] = useState(0);
  const [create, setCreate] = useState(false);
  const [notice, setNotice] = useState("");
  const list = useResource<Page<AgentMemory>>(
    `/workforce/memory?limit=20&offset=${offset}`,
  );
  const action = useAction();
  const { confirm } = useConfirm();
  const request = useRef<{ signature: string; key: string } | null>(null);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {
      agent_name: String(form.get("agent")),
      key: String(form.get("key")).trim(),
      value: { text: String(form.get("value")).trim() },
      retention_days: Number(form.get("retention")),
    };
    const signature = JSON.stringify(body);
    if (request.current?.signature !== signature)
      request.current = { signature, key: crypto.randomUUID() };
    const key = request.current.key;
    await action.run(async () => {
      const result = await workforce.remember(body, key);
      request.current = null;
      setCreate(false);
      setNotice(
        `Memory approval requested (${result.status}). An independent reviewer must approve it before long-term storage.`,
      );
      return result;
    });
  }
  return (
    <section className="card mt-6 p-5">
      <div className="mb-3 flex flex-wrap justify-between gap-3">
        <h2 className="text-xl font-semibold">Agent memory</h2>
        <button className="crm-secondary" disabled={!agents.length} onClick={() => setCreate(true)}>
          Propose memory
        </button>
      </div>
      <p className="crm-muted mb-4">
        Working context expires. Long-term memory is explicitly proposed,
        independently approved and retained for a bounded period.
      </p>
      {notice && (
        <p role="status" className="mb-3 text-sm">
          {notice}{" "}
          <Link href="/approvals" className="underline">
            Open Approval Center
          </Link>
        </p>
      )}
      <ResourceState
        loading={list.isLoading}
        error={list.error}
        empty={list.data?.items.length === 0}
        onRetry={list.refetch}
      >
        <ul className="divide-y divide-[var(--border)]">
          {list.data?.items.map((memory) => (
            <li key={memory.id} className="space-y-2 py-4">
              <div className="flex flex-wrap justify-between gap-3">
                <strong className="min-w-0 [overflow-wrap:anywhere]">{memory.key}</strong>
                <span className="text-sm">
                  {memory.memory_type} ·{" "}
                  {memory.approved_by ? "approved" : "not approved"}
                </span>
              </div>
              <p className="crm-muted">
                {memory.agent_name} · Expires {timestamp(memory.expires_at)}
              </p>
              <pre className="whitespace-pre-wrap break-words text-sm [overflow-wrap:anywhere]">
                {JSON.stringify(memory.value, null, 2)}
              </pre>
              <button
                className="crm-danger"
                disabled={action.pending}
                onClick={() =>
                  void (async () => {
                    if (
                      await confirm({
                        title: "Delete agent memory?",
                        message:
                          "This memory will no longer be available to the agent.",
                        confirmText: "Delete memory",
                        tone: "danger",
                      })
                    )
                      await action.run(() => workforce.forget(memory.id));
                  })()
                }
              >
                Delete memory
              </button>
            </li>
          ))}
        </ul>
      </ResourceState>
      <nav className="crm-actions mt-4" aria-label="Memory pages">
        <button
          className="crm-secondary"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 20))}
        >
          Previous memories
        </button>
        <button
          className="crm-secondary"
          disabled={!list.data || offset + 20 >= list.data.total}
          onClick={() => setOffset(offset + 20)}
        >
          Next memories
        </button>
      </nav>
      {!create && action.error && (
        <p role="alert" className="crm-error">
          {action.error}
        </p>
      )}
      <Dialog
        open={create}
        title="Propose long-term memory"
        onClose={() => setCreate(false)}
      >
        <form className="crm-form" onSubmit={submit}>
          <label className="crm-field">
            Memory agent
            <select className="crm-input" name="agent" required>
              {agents.map((agent) => (
                <option key={agent.name} value={agent.name}>
                  {agent.label}
                </option>
              ))}
            </select>
          </label>
          <label className="crm-field">
            Memory key
            <input
              name="key"
              className="crm-input"
              required
              maxLength={100}
              pattern="[a-zA-Z0-9_. \-]+"
            />
          </label>
          <label className="crm-field">
            Approved context to retain
            <textarea
              name="value"
              className="crm-input"
              required
              maxLength={10000}
              rows={4}
            />
          </label>
          <label className="crm-field">
            Retention days
            <input
              name="retention"
              className="crm-input"
              type="number"
              required
              min={1}
              max={90}
              defaultValue={30}
            />
          </label>
          <p className="crm-muted">
            This submits a proposal. It does not approve or activate memory.
          </p>
          {action.error && (
            <p role="alert" className="crm-error">
              {action.error}
            </p>
          )}
          <button className="crm-button" disabled={action.pending}>
            {action.pending ? "Submitting…" : "Request memory approval"}
          </button>
        </form>
      </Dialog>
    </section>
  );
}
