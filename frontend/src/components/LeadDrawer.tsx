"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Mail, Phone, UserRound, X, Sparkles } from "lucide-react";
import { useResource } from "@/hooks/useResource";
import { useSession } from "@/auth/SessionProvider";
import { useAction } from "@/hooks/useAction";
import { ResourceState } from "./ResourceState";
import { Dialog } from "./Dialog";
import { JobStatus } from "./JobStatus";
import { crm, label } from "@/services/crm";
import type { Lead } from "@/types/crm";
import { LEAD_STATUSES } from "@/types/crm";
import CrmForm from "@/app/leads/CrmForm";
import { button, primary, control } from "@/app/leads/CrmFields";
export default function LeadDrawer({
  lead,
  onClose,
}: {
  lead: Lead;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const { can } = useSession();
  const action = useAction();
  const query = useResource<Lead>(`/leads/${lead.id}`, can("leads:read"));
  const current = query.data ?? lead;
  const [edit, setEdit] = useState(false);
  const [task, setTask] = useState(false);
  const [jobId, setJobId] = useState("");
  const scoreKey = useRef(crypto.randomUUID());
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (!returnFocus.current && document.activeElement instanceof HTMLElement) {
      returnFocus.current = document.activeElement;
    }
    dialog.showModal();
    return () => {
      dialog.close();
      requestAnimationFrame(() => {
        if (!dialog.isConnected && returnFocus.current?.isConnected)
          returnFocus.current.focus();
      });
    };
  }, []);
  return (
    <>
      <dialog
        ref={ref}
        className="m-0 ml-auto h-dvh max-h-dvh w-full max-w-[480px] overflow-y-auto border-0 border-l border-[var(--border)] bg-[var(--panel)] p-0 shadow-[-20px_0_60px_rgba(29,78,135,0.12)] backdrop:bg-black/40"
        aria-labelledby="lead-profile-title"
        onCancel={onClose}
        onKeyDown={(event) => {
          if (event.key !== "Tab") return;
          const controls = Array.from(
            event.currentTarget.querySelectorAll<HTMLElement>(
              'button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]',
            ),
          ).filter((node) => node.getClientRects().length > 0);
          const first = controls[0];
          const last = controls[controls.length - 1];
          if (event.shiftKey && document.activeElement === first && last) {
            event.preventDefault();
            last.focus();
          }
          if (!event.shiftKey && document.activeElement === last && first) {
            event.preventDefault();
            first.focus();
          }
        }}
        onClick={(e) => {
          if (e.target === e.currentTarget) {
            const rect = e.currentTarget.getBoundingClientRect();
            if (e.clientX < rect.left || e.clientX > rect.right) onClose();
          }
        }}
      >
        <div className="h-1 w-full bg-gradient-to-r from-blue-600 via-blue-500 to-sky-400" />
        <div className="p-6">
          <header className="mb-7 flex items-start justify-between gap-4">
            <div>
              <p className="text-[11px] font-semibold tracking-[3px] text-[var(--blue)]">
                LEAD PROFILE
              </p>
              <h2
                id="lead-profile-title"
                className="mt-2 break-words text-2xl font-bold"
              >
                {current.title}
              </h2>
              <p className="mt-1 text-sm text-[var(--muted)]">
                {current.source
                  ? label(current.source)
                  : "Source not specified"}
              </p>
            </div>
            <button
              className={button}
              aria-label="Close lead profile"
              onClick={onClose}
            >
              <X size={18} />
            </button>
          </header>
          <ResourceState
            loading={query.isLoading}
            error={query.error}
            onRetry={() => void query.refetch()}
          >
            <div className="card mb-5 p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[var(--muted)]">AI score</p>
                  <p className="mt-1 text-xs text-[var(--muted2)]">
                    Verified backend assessment
                  </p>
                </div>
                <span className="rounded-xl bg-blue-50 p-3 text-lg font-bold text-[var(--blue)]">
                  {current.ai_score ?? "Not scored"}
                </span>
              </div>
              {current.ai_score_reason && (
                <p className="mt-3 text-sm">{current.ai_score_reason}</p>
              )}
              {can("ai:score_leads") && (
                <button
                  className={`${button} mt-4 flex items-center gap-2`}
                  disabled={action.pending}
                  onClick={() =>
                    void action.run(async () => {
                      const job = await crm.scoreLead(
                        current.id,
                        scoreKey.current,
                      );
                      setJobId(job.id);
                      scoreKey.current = crypto.randomUUID();
                    })
                  }
                >
                  <Sparkles size={16} />
                  {action.pending ? "Requesting…" : "Request AI score"}
                </button>
              )}
              <div className="my-5 h-px bg-[var(--border)]" />
              <label className="grid gap-2 text-sm">
                Lead status
                <select
                  className={control}
                  disabled={!can("leads:write") || action.pending}
                  value={current.status}
                  onChange={(e) =>
                    void action.run(() =>
                      crm.updateLead(current.id, {
                        status: e.target.value as Lead["status"],
                      }),
                    )
                  }
                >
                  {LEAD_STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {label(status)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {jobId && (
              <JobStatus
                jobId={jobId}
                onComplete={() => void query.refetch()}
              />
            )}
            {action.error && (
              <p role="alert" className="mb-4 text-red-700">
                {action.error}
              </p>
            )}
            <h3 className="mb-2 text-xs font-semibold tracking-[2px] text-[var(--muted)]">
              CONTACT INFORMATION
            </h3>
            <div className="mb-6 space-y-3">
              {current.contact?.phone ? (
                <a
                  className="card flex items-center gap-3 p-4"
                  href={`tel:${current.contact.phone}`}
                >
                  <Phone size={17} />
                  {current.contact.phone}
                </a>
              ) : (
                <p className="card p-4 text-sm text-[var(--muted)]">
                  No linked phone number
                </p>
              )}
              {current.contact?.email ? (
                <a
                  className="card flex items-center gap-3 break-all p-4"
                  href={`mailto:${current.contact.email}`}
                >
                  <Mail size={17} />
                  {current.contact.email}
                </a>
              ) : (
                <p className="card p-4 text-sm text-[var(--muted)]">
                  No linked email address
                </p>
              )}
            </div>
            <h3 className="mb-2 text-xs font-semibold tracking-[2px] text-[var(--muted)]">
              ASSIGNED TO
            </h3>
            <div className="card mb-6 flex items-center gap-3 p-4">
              <UserRound size={18} />
              <span>
                {current.owner?.full_name ||
                  current.owner?.email ||
                  current.owner_id ||
                  "Unassigned"}
              </span>
            </div>
            <h3 className="mb-2 text-xs font-semibold tracking-[2px] text-[var(--muted)]">
              DESCRIPTION
            </h3>
            <p className="card whitespace-pre-wrap p-4 text-sm">
              {current.description || "No description yet."}
            </p>
            {current.ai_summary && (
              <div className="card mt-4 p-4">
                <h3 className="font-semibold">AI summary</h3>
                <p className="mt-2 text-sm">{current.ai_summary}</p>
              </div>
            )}
            <div className="mt-6 grid grid-cols-2 gap-3">
              {can("leads:write") && (
                <button className={button} onClick={() => setEdit(true)}>
                  Edit lead
                </button>
              )}
              {can("tasks:write") && (
                <button className={button} onClick={() => setTask(true)}>
                  Create Task
                </button>
              )}
              {can("conversations:write") && (
                <Link
                  className={primary}
                  href={`/conversations?lead_id=${current.id}`}
                >
                  Start Conversation
                </Link>
              )}
              <Link className={button} href={`/customers/leads/${current.id}`}>
                Customer 360 & timeline
              </Link>
            </div>
          </ResourceState>
        </div>
      </dialog>
      <Dialog open={edit} title="Edit lead" onClose={() => setEdit(false)}>
        {edit && (
          <CrmForm
            kind="leads"
            record={current}
            onSaved={() => setEdit(false)}
          />
        )}
      </Dialog>
      <Dialog open={task} title="Create task" onClose={() => setTask(false)}>
        {task && (
          <CrmForm
            kind="tasks"
            relation={{ key: "lead_id", id: current.id }}
            onSaved={() => setTask(false)}
          />
        )}
      </Dialog>
    </>
  );
}
