import { api } from "@/api/client";
import type {
  AgentExecution,
  Approval,
  WorkforceTask,
} from "@/types/workforce";

export const workforce = {
  execute: (body: WorkforceTask, idempotencyKey: string) =>
    api.post<AgentExecution>("/workforce/executions", body, { idempotencyKey }),
  cancel: (id: string) =>
    api.post<AgentExecution>(`/workforce/executions/${id}/cancel`),
  retry: (id: string, idempotencyKey: string) =>
    api.post<AgentExecution>(`/workforce/executions/${id}/retry`, undefined, {
      idempotencyKey,
    }),
  decide: (
    approval: Pick<Approval, "id" | "action_hash">,
    decision: "approved" | "rejected",
    reason?: string,
  ) =>
    api.post<Approval>(`/workforce/approvals/${approval.id}/decision`, {
      decision,
      action_hash: approval.action_hash,
      ...(reason ? { reason } : {}),
    }),
  remember: (
    body: {
      agent_name: string;
      key: string;
      value: Record<string, unknown>;
      retention_days: number;
    },
    idempotencyKey: string,
  ) => api.post<Approval>("/workforce/memory", body, { idempotencyKey }),
  forget: (id: string) => api.delete<void>(`/workforce/memory/${id}`),
};

export function executionActive(state: string) {
  return state === "queued" || state === "running";
}
export function approvalDecisionAllowed(
  approval: Approval,
  actorId: string,
  hasPermission: boolean,
) {
  return (
    hasPermission &&
    approval.status === "pending" &&
    approval.requesting_user_id !== actorId &&
    (!approval.expires_at || Date.parse(approval.expires_at) > Date.now())
  );
}
export function approvalExplanation(status: string) {
  const text: Record<string, string> = {
    pending: "Awaiting an independent reviewer.",
    approved: "Approved. Execution has not yet been confirmed.",
    executed:
      "The approved action was executed. Check the message provider state for delivery.",
    rejected: "Rejected. The proposed action will not execute.",
    expired: "Expired. A new request and approval are required.",
    failed:
      "Execution failed. Review the recorded outcome before requesting another action.",
  };
  return text[status] || "Review the backend outcome.";
}
