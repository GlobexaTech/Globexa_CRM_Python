"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useSession } from "@/auth/SessionProvider";
import { useAction } from "@/hooks/useAction";
import { aiCapabilities, type Job } from "@/types/operations";
import { useConfirm } from "./ConfirmProvider";
import { ResourceState } from "./ResourceState";
import { notifyWorkspace } from "./WorkspaceSync";

const terminal = new Set(["completed", "failed", "cancelled", "unknown"]);
function suggestionOf(value: unknown) {
  if (!value || typeof value !== "object") return null;
  const suggestion = value as Record<string, unknown>;
  const capability = aiCapabilities.find(
    (item) => item.value === suggestion.capability,
  );
  if (!capability || typeof suggestion.entity_id !== "string") return null;
  return { capability, entityId: suggestion.entity_id };
}
export function JobStatus({
  jobId,
  onComplete,
  onApproved,
}: {
  jobId: string;
  onComplete?: () => void;
  onApproved?: (childJobId: string) => void;
}) {
  const { session, can } = useSession();
  const cache = useQueryClient();
  const action = useAction();
  const { confirm } = useConfirm();
  const [approvedId, setApprovedId] = useState("");
  const notified = useRef("");
  const callback = useRef(onComplete);
  useEffect(() => {
    callback.current = onComplete;
  }, [onComplete]);
  const path = "/operations/jobs/" + jobId;
  const job = useQuery({
    queryKey: [session?.tenant_id, session?.version, path],
    queryFn: ({ signal }) => api.get<Job>(path, { signal }),
    enabled: Boolean(jobId && session),
    retry: false,
    refetchInterval: (query) =>
      query.state.error ||
      terminal.has(query.state.data?.status ?? "") ||
      query.state.data?.status === "awaiting_approval"
        ? false
        : 1500,
  });
  useEffect(() => {
    const value = job.data;
    if (!value || !terminal.has(value.status)) return;
    const revision = `${jobId}:${value.status}:${value.attempts}`;
    if (notified.current === revision) return;
    notified.current = revision;
    void cache.invalidateQueries({
      predicate: (query) =>
        query.queryKey[0] === session?.tenant_id && query.queryKey[2] !== path,
    });
    // A hook is complete when it is approved. Its child AI job owns execution completion.
    if (value.kind !== "ai_hook") callback.current?.();
    notifyWorkspace(session?.tenant_id);
  }, [job.data, jobId, cache, session?.tenant_id, path]);
  const suggestion = suggestionOf(job.data?.result.suggestion);
  const linkedChild =
    job.data?.kind === "ai_hook" && typeof job.data.result.job_id === "string"
      ? job.data.result.job_id
      : approvedId;
  const childJobId =
    linkedChild !== jobId && /^[0-9a-f-]{36}$/i.test(linkedChild)
      ? linkedChild
      : "";
  const hook = job.data?.kind === "ai_hook";
  async function approve() {
    if (!suggestion || !can(suggestion.capability.permission)) return;
    if (
      !(await confirm({
        title: "Approve AI request",
        message: `Run ${suggestion.capability.label.toLowerCase()} for CRM record ${suggestion.entityId}? This uses available AI credits. The resulting AI job is tracked separately from this suggestion.`,
        confirmText: "Approve AI request",
        tone: "primary",
      }))
    )
      return;
    await action.run(async () => {
      const child = await api.post<Job>(path + "/approve");
      cache.setQueryData(
        [session?.tenant_id, session?.version, "/operations/jobs/" + child.id],
        child,
      );
      setApprovedId(child.id);
      onApproved?.(child.id);
      return child;
    });
  }
  return (
    <ResourceState
      loading={job.isLoading}
      error={job.error}
      onRetry={job.refetch}
    >
      {job.data && (
        <div className="card p-4 space-y-3" aria-live="polite">
          <p>
            <strong>
              {hook
                ? `Suggestion: ${job.data.status === "completed" ? "approved" : job.data.status.replaceAll("_", " ")}`
                : `Operation: ${job.data.status.replaceAll("_", " ")}`}
            </strong>{" "}
            · {job.data.kind} · Attempt {job.data.attempts}
          </p>
          {job.data.error_code && (
            <p className="crm-error">
              {job.data.error_code.replaceAll("_", " ")}
            </p>
          )}
          {job.data.status === "unknown" && (
            <p className="crm-error">
              Delivery status pending verification. Check the provider and
              conversation history before taking another action. This operation
              cannot be resent here.
            </p>
          )}
          {job.data.status === "failed" &&
            ["sync", "automation"].includes(job.data.kind) &&
            job.data.attempts < 3 && (
              <button
                className="crm-secondary"
                disabled={action.pending}
                onClick={() =>
                  void action.run(async () => {
                    await api.post(path + "/retry");
                  })
                }
              >
                Retry operation
              </button>
            )}
          {Object.keys(job.data.result ?? {}).length > 0 && (
            <dl className="crm-result">
              {Object.entries(job.data.result).map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd>
                    {typeof value === "string"
                      ? value
                      : JSON.stringify(value, null, 2)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          {hook &&
            job.data.status === "awaiting_approval" &&
            (suggestion && can(suggestion.capability.permission) ? (
              <button
                className="crm-button"
                disabled={action.pending}
                onClick={() => void approve()}
              >
                Review and approve
              </button>
            ) : (
              <p className="crm-muted">
                {suggestion
                  ? "Your role cannot approve this capability."
                  : "Suggestion details are unavailable; refresh before approving."}
              </p>
            ))}
          {hook && job.data.status === "completed" && (
            <p className="crm-muted">
              Approval recorded. The linked AI request has its own processing
              status and result.
            </p>
          )}
          {childJobId && !onApproved && (
            <section aria-label="Approved AI request">
              <h3 className="font-semibold">Approved AI request</h3>
              <JobStatus
                key={childJobId}
                jobId={childJobId}
                onComplete={onComplete}
              />
            </section>
          )}
          {action.error && (
            <p className="crm-error" role="alert">
              {action.error}
            </p>
          )}
        </div>
      )}
    </ResourceState>
  );
}
