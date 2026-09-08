import type { Lead } from "@/types/crm";
import { label } from "@/services/crm";
export default function LeadTable({
  leads,
  selected,
  toggle,
  open,
  selectable,
}: {
  leads: Lead[];
  selected: string[];
  toggle: (id: string) => void;
  open: (lead: Lead) => void;
  selectable: boolean;
}) {
  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[700px] text-left text-sm">
        <thead className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted)]">
          <tr>
            {selectable && (
              <th className="p-4">
                <span className="sr-only">Select lead</span>
              </th>
            )}
            <th className="p-4">Lead</th>
            <th>Email / company</th>
            <th>Source</th>
            <th>Status</th>
            <th className="p-4">AI score</th>
          </tr>
        </thead>
        <tbody>
          {leads.map((lead) => (
            <tr
              key={lead.id}
              className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--panel2)]"
            >
              {selectable && (
                <td className="p-4">
                  <input
                    type="checkbox"
                    aria-label={`Select ${lead.title}`}
                    checked={selected.includes(lead.id)}
                    onChange={() => toggle(lead.id)}
                  />
                </td>
              )}
              <td className="p-4">
                <button
                  className="text-left font-semibold hover:text-[var(--blue)]"
                  onClick={() => open(lead)}
                >
                  {lead.title}
                </button>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  {lead.owner?.full_name || lead.owner?.email || "Unassigned"}
                </p>
              </td>
              <td>
                {lead.contact?.email || "No linked email"}
                <p className="text-xs text-[var(--muted)]">
                  {lead.company?.name}
                </p>
              </td>
              <td>{lead.source ? label(lead.source) : "Not specified"}</td>
              <td>
                <span className="rounded-lg bg-blue-50 px-2 py-1">
                  {label(lead.status ?? "new")}
                </span>
              </td>
              <td className="p-4 font-medium text-[var(--blue)]">
                {lead.ai_score ?? "Not scored"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
