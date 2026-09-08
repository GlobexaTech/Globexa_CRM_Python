import Link from "next/link";
import Sidebar from "@/components/Sidebar";
export default function HelpPage() {
  return (
    <main className="page-shell">
      <Sidebar />
      <section className="page-content">
        <p className="page-eyebrow">GLOBEXA CRM</p>
        <h1 className="page-title">Workspace help</h1>
        <div className="dashboard-grid">
          <article className="card p-6">
            <h2>Customers and deals</h2>
            <p className="mt-3">
              Create a company and contact, then link them to a lead. Open
              Customer 360 to review their history. Qualified opportunities
              belong in a pipeline as deals. A deal stage change is saved only
              after the backend accepts it.
            </p>
            <Link href="/search" className="crm-secondary mt-4">
              Find a record
            </Link>
          </article>
          <article className="card p-6">
            <h2>Messages and campaigns</h2>
            <p className="mt-3">
              Connect an available email provider in Integrations. Review the
              audience, opt-outs, content and sender before launching a
              campaign. A queued operation is still in progress. When delivery
              is unknown, check the provider before sending again.
            </p>
          </article>
          <article className="card p-6">
            <h2>Permissions and workspaces</h2>
            <p className="mt-3">
              The workspace selector shows your memberships. Switching
              workspaces clears the previous workspace from view. Your role
              controls both visible actions and backend authorization. Ask your
              workspace owner to adjust access.
            </p>
            <Link href="/settings" className="crm-secondary mt-4">
              Open settings
            </Link>
          </article>
          <article className="card p-6">
            <h2>AI and workflow operations</h2>
            <p className="mt-3">
              AI outputs are suggestions with provider, model and usage
              provenance. Review every draft before taking action. Workflow
              execution logs show the persisted outcome. Retry is offered only
              when the backend supports a safe retry.
            </p>
          </article>
        </div>
      </section>
    </main>
  );
}
