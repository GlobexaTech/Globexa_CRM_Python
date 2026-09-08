type Lead = {
  id: number;
  name: string;
  email: string;
  source: string;
  score: number;
  stage: string;
};

type Props = {
  leads: Lead[];
  selected: number[];
  toggle: (id: number) => void;
  open: (lead: Lead) => void;
};

export default function LeadTable({
  leads,
  selected,
  toggle,
  open,
}: Props) {
  return (
    <div className="card overflow-hidden">

      <div className="grid grid-cols-[42px_1.4fr_1.7fr_1fr_1fr_80px] border-b border-[var(--border)] px-4 py-2 text-[11px] uppercase tracking-wider text-[var(--muted)]">
        <span />
        <span>Lead</span>
        <span>Email</span>
        <span>Source</span>
        <span>Stage</span>
        <span>Score</span>
      </div>

      {leads.map((lead) => (
        <div
          key={lead.id}
          className="grid grid-cols-[42px_1.4fr_1.7fr_1fr_1fr_80px] items-center border-b border-[var(--border)] px-4 py-2.5 text-sm last:border-0 hover:bg-[var(--panel2)]"
        >
          <input
            type="checkbox"
            checked={selected.includes(lead.id)}
            onChange={() => toggle(lead.id)}
          />

          <button
            onClick={() => open(lead)}
            className="truncate text-left font-medium hover:text-[var(--cyan)]"
          >
            {lead.name}
          </button>

          <span className="truncate text-[var(--muted)]">
            {lead.email}
          </span>

          <span>{lead.source}</span>

          <span>
            <span className="rounded-md bg-[var(--panel2)] px-2 py-1 text-xs">
              {lead.stage}
            </span>
          </span>

          <span className="font-medium text-[var(--cyan)]">
            {lead.score}
          </span>
        </div>
      ))}

      {!leads.length && (
        <p className="p-8 text-center text-sm text-[var(--muted)]">
          No leads found.
        </p>
      )}
    </div>
  );
}