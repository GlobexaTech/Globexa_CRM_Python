"use client";

import {
  CalendarClock,
  ChevronDown,
  Mail,
  Phone,
  UserRound,
  X,
} from "lucide-react";

type Lead = {
  id: number;
  name: string;
  email?: string;
  source: string;
  score: number;
  stage: string;
};

type Props = {
  lead: Lead;
  stages: string[];
  onStageChange: (stage: string) => void;
  onClose: () => void;
};

export default function LeadDrawer({
  lead,
  stages,
  onStageChange,
  onClose,
}: Props) {
  return (
    <aside
      className="
        fixed inset-y-0 right-0 z-50
        w-full max-w-[420px]
        overflow-y-auto
        border-l border-[var(--border)]
        bg-[var(--panel)]
        shadow-[-20px_0_60px_rgba(29,78,135,0.12)]
      "
    >
      {/* TOP BLUE ACCENT */}

      <div className="h-1 w-full bg-gradient-to-r from-blue-600 via-blue-500 to-sky-400" />

      <div className="p-6">
        {/* HEADER */}

        <div className="mb-7 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold tracking-[3px] text-[var(--blue)]">
              LEAD PROFILE
            </p>

            <h2 className="mt-2 truncate text-2xl font-bold text-[var(--text)]">
              {lead.name}
            </h2>

            <p className="mt-1 text-sm text-[var(--muted)]">
              {lead.source} Lead
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close lead profile"
            className="
              flex h-10 w-10 shrink-0
              items-center justify-center
              rounded-xl
              border border-[var(--border)]
              bg-white
              text-[var(--muted)]
              shadow-sm
              hover:border-[var(--border-strong)]
              hover:text-[var(--text)]
            "
          >
            <X size={18} />
          </button>
        </div>

        {/* SCORE + STAGE */}

        <div className="card mb-5 p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-[var(--muted)]">
                AI Score
              </p>

              <p className="mt-1 text-xs text-[var(--muted2)]">
                Lead qualification strength
              </p>
            </div>

            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-50 text-lg font-bold text-[var(--blue)]">
              {lead.score}
            </div>
          </div>

          <div className="my-5 h-px bg-[var(--border)]" />

          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs text-[var(--muted)]">
                Pipeline Stage
              </p>

              <p className="mt-1 text-xs text-[var(--muted2)]">
                Change stage directly
              </p>
            </div>

            <div className="relative min-w-[150px]">
              <select
                value={lead.stage}
                onChange={(e) =>
                  onStageChange(e.target.value)
                }
                className="
                  w-full appearance-none
                  rounded-xl
                  border border-[var(--border)]
                  bg-white
                  py-2.5 pl-3 pr-9
                  text-sm font-semibold
                  text-[var(--text)]
                  outline-none
                  hover:border-[var(--border-strong)]
                "
              >
                {stages.map((stage) => (
                  <option
                    key={stage}
                    value={stage}
                  >
                    {stage}
                  </option>
                ))}
              </select>

              <ChevronDown
                size={15}
                className="
                  pointer-events-none
                  absolute right-3 top-1/2
                  -translate-y-1/2
                  text-[var(--muted)]
                "
              />
            </div>
          </div>
        </div>

        {/* CONTACT INFORMATION */}

        <SectionTitle>
          CONTACT INFORMATION
        </SectionTitle>

        <div className="mb-6 space-y-3">
          <button
            type="button"
            className="
              flex w-full items-center gap-3
              rounded-xl
              border border-[var(--border)]
              bg-white
              p-3.5
              text-left
              shadow-sm
              hover:border-[var(--border-strong)]
              hover:shadow-md
            "
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-[var(--blue)]">
              <Phone size={16} />
            </div>

            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-wider text-[var(--muted)]">
                Phone
              </p>

              <p className="mt-0.5 truncate text-sm font-medium text-[var(--text)]">
                +91 98765 43210
              </p>
            </div>
          </button>

          <button
            type="button"
            className="
              flex w-full items-center gap-3
              rounded-xl
              border border-[var(--border)]
              bg-white
              p-3.5
              text-left
              shadow-sm
              hover:border-[var(--border-strong)]
              hover:shadow-md
            "
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-[var(--blue)]">
              <Mail size={16} />
            </div>

            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-wider text-[var(--muted)]">
                Email
              </p>

              <p className="mt-0.5 truncate text-sm font-medium text-[var(--text)]">
                {lead.email || "lead@example.com"}
              </p>
            </div>
          </button>
        </div>

        {/* ASSIGNED TO */}

        <SectionTitle>
          ASSIGNED TO
        </SectionTitle>

        <div className="card mb-6 flex items-center gap-3 p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-50 text-[var(--blue)]">
            <UserRound size={17} />
          </div>

          <div>
            <p className="text-sm font-semibold text-[var(--text)]">
              Uday
            </p>

            <p className="text-xs text-[var(--muted)]">
              Lead Owner
            </p>
          </div>
        </div>

        {/* NEXT FOLLOW-UP */}

        <SectionTitle>
          NEXT FOLLOW-UP
        </SectionTitle>

        <div className="card mb-6 flex items-center gap-3 p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-[var(--blue)]">
            <CalendarClock size={17} />
          </div>

          <div>
            <p className="text-sm font-semibold text-[var(--text)]">
              Tomorrow · 11:00 AM
            </p>

            <p className="text-xs text-[var(--muted)]">
              Scheduled follow-up
            </p>
          </div>
        </div>

        {/* NOTES */}

        <SectionTitle>
          NOTES
        </SectionTitle>

        <div className="card p-4">
          <p className="text-sm leading-6 text-[var(--muted)]">
            Interested in services. Follow up and qualify
            requirements.
          </p>
        </div>

        {/* QUICK ACTIONS */}

        <div className="mt-6 grid grid-cols-2 gap-3">
          <button
            type="button"
            className="
              rounded-xl
              border border-[var(--border)]
              bg-white
              px-4 py-3
              text-sm font-medium
              text-[var(--text)]
              shadow-sm
              hover:border-[var(--border-strong)]
              hover:shadow-md
            "
          >
            Create Task
          </button>

          <button
            type="button"
            className="
              rounded-xl
              bg-[var(--blue)]
              px-4 py-3
              text-sm font-medium
              text-white
              shadow-[0_8px_22px_rgba(11,104,239,0.22)]
              hover:shadow-[0_12px_28px_rgba(11,104,239,0.3)]
            "
          >
            Start Conversation
          </button>
        </div>
      </div>
    </aside>
  );
}

function SectionTitle({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <p className="mb-2 text-[10px] font-semibold tracking-[2px] text-[var(--muted)]">
      {children}
    </p>
  );
}