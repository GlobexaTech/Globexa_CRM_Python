"use client";
import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useSession } from "@/auth/SessionProvider";
import { useAction } from "@/hooks/useAction";
import {
  workforce,
  approvalDecisionAllowed,
  approvalExplanation,
} from "@/services/workforce";
import { timestamp } from "@/services/operations";
import type { Approval } from "@/types/workforce";
import type { Page } from "@/types/operations";
import Sidebar from "@/components/Sidebar";
import { Dialog } from "@/components/Dialog";
import { ResourceState } from "@/components/ResourceState";
import { JobStatus } from "@/components/JobStatus";
import { SafeResult } from "@/components/WorkforceWorkspace";
import { useConfirm } from "@/components/ConfirmProvider";

export default function ApprovalsPage() {
  const { session } = useSession();
  return <Approvals key={`${session?.tenant_id}:${session?.version}`} />;
}
function Approvals() {
  const { session, can } = useSession();
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [status, setStatus] = useState("");
  const path = `/workforce/approvals?limit=20&offset=${offset}${status ? `&status=${status}` : ""}`;
  const list = useQuery({
    queryKey: [session?.tenant_id, session?.version, path],
    queryFn: ({ signal }) => api.get<Page<Approval>>(path, { signal }),
    enabled: Boolean(session) && can("ai:chat"),
    retry: false,
    refetchInterval: (query) => (query.state.error ? false : 3000),
  });
  const item = list.data?.items.find((approval) => approval.id === selected);
  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />
      <section className="min-w-0 flex-1 p-4 sm:p-8">
        <header className="mb-6">
          <p className="text-xs tracking-[3px] text-[var(--blue)]">
            GLOBEXA CRM
          </p>
          <h1 className="mt-2 text-3xl font-semibold">Approval Center</h1>
          <p className="crm-muted">
            Review the exact recipient, content, target and provider before
            deciding
          </p>
        </header>
        {!can("ai:chat") ? (
          <p role="alert">Your role cannot view AI approvals.</p>
        ) : (
          <>
            <div className="crm-actions mb-5">
              <Link href="/ai-workforce" className="crm-secondary">
                AI Workforce
              </Link>
              <label className="crm-field">
                Approval status
                <select
                  className="crm-input"
                  value={status}
                  onChange={(event) => {
                    setStatus(event.target.value);
                    setOffset(0);
                    setSelected("");
                  }}
                >
                  <option value="">All statuses</option>
                  {[
                    "pending",
                    "approved",
                    "rejected",
                    "expired",
                    "executed",
                    "failed",
                  ].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
              <button
                className="crm-secondary"
                onClick={() => void list.refetch()}
              >
                Refresh approvals
              </button>
            </div>
            <ResourceState
              loading={list.isLoading}
              error={list.error}
              empty={list.data?.items.length === 0}
              onRetry={list.refetch}
            >
              <div className="grid gap-4 lg:grid-cols-2">
                {list.data?.items.map((approval) => (
                  <article className="card space-y-3 p-5" key={approval.id}>
                    <div className="flex flex-wrap justify-between gap-2">
                      <h2 className="font-semibold">
                        {approval.action_type.replaceAll("_", " ")}
                      </h2>
                      <strong className="text-sm">{approval.status}</strong>
                    </div>
                    <p className="text-sm">
                      {approvalExplanation(approval.status)}
                    </p>
                    <p className="crm-muted">
                      {approval.agent_name} · {timestamp(approval.created_at)}
                    </p>
                    <button
                      className="crm-secondary"
                      onClick={() => setSelected(approval.id)}
                    >
                      Review action
                    </button>
                  </article>
                ))}
              </div>
            </ResourceState>
            <nav className="crm-actions mt-5" aria-label="Approval pages">
              <button
                className="crm-secondary"
                disabled={offset === 0}
                onClick={() => {
                  setSelected("");
                  setOffset(Math.max(0, offset - 20));
                }}
              >
                Previous approvals
              </button>
              <button
                className="crm-secondary"
                disabled={!list.data || offset + 20 >= list.data.total}
                onClick={() => {
                  setSelected("");
                  setOffset(offset + 20);
                }}
              >
                Next approvals
              </button>
            </nav>
          </>
        )}
        <Dialog
          open={Boolean(item)}
          title="Review exact action"
          onClose={() => setSelected("")}
        >
          {item && (
            <ApprovalDetail
              key={item.id}
              approval={item}
              actorId={session?.user.id || ""}
              canDecide={can("ai:approve")}
            />
          )}
        </Dialog>
      </section>
    </main>
  );
}
function ApprovalDetail({
  approval,
  actorId,
  canDecide,
}: {
  approval: Approval;
  actorId: string;
  canDecide: boolean;
}) {
  const action = useAction();
  const { can } = useSession();
  const { confirm } = useConfirm();
  const [reason, setReason] = useState("");
  const allowed = approvalDecisionAllowed(approval, actorId, canDecide);
  const jobId =
    typeof approval.execution_result?.job_id === "string" &&
    /^[a-f\d-]{36}$/i.test(approval.execution_result.job_id)
      ? approval.execution_result.job_id
      : null;
  const argumentsValue = approval.proposed_action.arguments;
  const conversationId =
    argumentsValue &&
    typeof argumentsValue === "object" &&
    "conversation_id" in argumentsValue &&
    typeof argumentsValue.conversation_id === "string" &&
    /^[a-f\d-]{36}$/i.test(argumentsValue.conversation_id)
      ? argumentsValue.conversation_id
      : null;
  async function decide(decision: "approved" | "rejected") {
    if (
      !(await confirm({
        title:
          decision === "approved"
            ? "Approve this exact action?"
            : "Reject this action?",
        message:
          decision === "approved"
            ? "Only the stored action shown above will be authorized. Approval queues execution; provider delivery is tracked separately."
            : "This request will be rejected without executing the action.",
        confirmText:
          decision === "approved" ? "Approve exact action" : "Reject action",
        tone: decision === "approved" ? "primary" : "danger",
      }))
    )
      return;
    await action.run(() =>
      workforce.decide(approval, decision, reason.trim() || undefined),
    );
  }
  return (
    <div className="space-y-4">
      <p role="status">
        Approval: <strong>{approval.status}</strong>
      </p>
      <p className="text-sm">{approvalExplanation(approval.status)}</p>
      <p className="crm-muted">Expires {timestamp(approval.expires_at)}</p>
      <section>
        <h3 className="mb-2 font-semibold">Action and content</h3>
        <SafeResult value={approval.proposed_action} />
      </section>
      <section>
        <h3 className="mb-2 font-semibold">Target</h3>
        <SafeResult value={approval.target} />
      </section>
      <p className="break-all text-xs text-[var(--muted)]">
        Action fingerprint: {approval.action_hash}
      </p>
      {approval.execution_result && (
        <section>
          <h3 className="mb-2 font-semibold">Execution outcome</h3>
          <SafeResult value={approval.execution_result} />
        </section>
      )}
      {jobId && can("conversations:read") && <JobStatus jobId={jobId} />}
      {conversationId && can("conversations:read") && (
        <Link
          className="crm-secondary"
          href={`/conversations?conversation=${conversationId}`}
        >
          Open conversation and delivery status
        </Link>
      )}
      {approval.rejection_reason && (
        <p className="text-sm">Reason: {approval.rejection_reason}</p>
      )}
      {allowed ? (
        <>
          <label className="crm-field">
            Decision note (optional)
            <textarea
              className="crm-input"
              value={reason}
              maxLength={1000}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <div className="crm-actions">
            <button
              className="crm-button"
              disabled={action.pending}
              onClick={() => void decide("approved")}
            >
              Approve exact action
            </button>
            <button
              className="crm-danger"
              disabled={action.pending}
              onClick={() => void decide("rejected")}
            >
              Reject action
            </button>
          </div>
        </>
      ) : approval.status === "pending" ? (
        <p className="crm-muted">
          {approval.requesting_user_id === actorId
            ? "Another authorized reviewer must decide this request. You cannot approve your own action."
            : !canDecide
              ? "Your role cannot decide approvals."
              : "This request has expired; refresh to see its current state."}
        </p>
      ) : null}
      {action.error && (
        <p role="alert" className="crm-error">
          {action.error}
        </p>
      )}
    </div>
  );
}
