"use client";
import Link from "next/link";
import { Sparkles, ArrowRight, Users, GitBranch } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import { ResourceState } from "@/components/ResourceState";
import { AnalyticsData, PipelineMetrics } from "@/components/AnalyticsData";
import { useSession } from "@/auth/SessionProvider";
import { useResource } from "@/hooks/useResource";
import {
  analyticsPermissions,
  localTime,
  type Dashboard,
  type Summary,
} from "@/services/workspace";
function Feed({
  title,
  rows,
  href,
}: {
  title: string;
  rows: Summary[];
  href: string;
}) {
  return (
    <div className="card p-5">
      <h2>{title}</h2>
      {rows.length ? (
        <ul className="crm-list">
          {rows.map((row) => (
            <li key={row.id}>
              <Link className="font-semibold text-blue-800" href={href}>
                {row.title ??
                  row.subject ??
                  row.name ??
                  row.capability?.replaceAll("_", " ") ??
                  "Record"}
              </Link>
              <p className="crm-muted text-sm">
                {row.description ?? row.content ?? row.status}
              </p>
              <p className="crm-muted text-xs">
                {localTime(row.due_date ?? row.created_at)}
              </p>
              {row.output && (
                <p className="text-sm whitespace-pre-wrap">
                  {Object.values(row.output)
                    .filter((value) => typeof value === "string")
                    .join(" · ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="crm-muted mt-4">No records yet.</p>
      )}
    </div>
  );
}
export default function Home() {
  const { can, session } = useSession();
  const allowed = analyticsPermissions.dashboard.every(can);
  const resource = useResource<Dashboard>(
    "/operations/analytics/dashboard",
    allowed,
  );
  return (
    <main className="page-shell">
      <Sidebar />
      <section className="page-content min-w-0">
        <section className="crm-hero fade-in-up">
          <div className="hero-grid" aria-hidden="true" />
          <div className="hero-orb hero-orb-one" aria-hidden="true" />
          <div className="hero-orb hero-orb-two" aria-hidden="true" />
          <div className="relative z-10 grid gap-8 xl:grid-cols-[1.25fr_.75fr]">
            <div>
              <p className="hero-kicker">
                <span className="hero-kicker-line" />
                <Sparkles size={14} aria-hidden="true" />
                GLOBEXA OS
              </p>
              <h1 className="hero-title">
                Your business.
                <br />
                <span className="hero-title-blue">
                  One intelligent command center.
                </span>
              </h1>
              <p className="hero-description">
                Welcome, {session?.user.first_name}. Your customers, deals and
                next actions in one workspace.
              </p>
              <div className="crm-actions mt-6">
                {can("leads:read") && (
                  <Link className="crm-button" href="/leads">
                    <Users size={16} aria-hidden="true" />
                    Open leads
                    <ArrowRight size={16} aria-hidden="true" />
                  </Link>
                )}
                {can("deals:read") && (
                  <Link className="crm-secondary" href="/pipeline">
                    <GitBranch size={16} aria-hidden="true" />
                    View pipeline
                  </Link>
                )}
              </div>
            </div>
            <div className="glass-panel p-6 self-center">
              <p className="page-eyebrow">CONNECTED WORKSPACE</p>
              <h2 className="text-2xl font-bold mt-3">
                {session?.tenants.find((t) => t.id === session.tenant_id)?.name}
              </h2>
              <p className="crm-muted mt-4">
                Changes are saved to your team workspace. Operational results
                appear after the backend confirms them.
              </p>
              <Link href="/search" className="crm-secondary mt-6">
                Search your CRM
              </Link>
            </div>
          </div>
        </section>
        <div className="crm-actions justify-between my-6">
          <h2 className="text-xl font-bold">Workspace overview</h2>
          {allowed && (
            <button
              className="crm-secondary"
              onClick={() => void resource.refetch()}
              disabled={resource.isFetching}
            >
              Refresh overview
            </button>
          )}
        </div>
        {!allowed ? (
          <div className="card p-6">
            <p>
              Your role does not have access to the complete dashboard. Use the
              navigation to open your permitted CRM records.
            </p>
          </div>
        ) : (
          <ResourceState
            loading={resource.isLoading}
            error={resource.error}
            onRetry={resource.refetch}
          >
            {resource.data && (
              <>
                <AnalyticsData view="dashboard" data={resource.data} />
                <p className="crm-muted text-xs mt-3">
                  Generated {localTime(resource.data.generated_at)} · Values
                  reflect the server aggregate.
                </p>
                <div className="dashboard-grid">
                  <div className="card p-5">
                    <h2>Pipeline summary</h2>
                    <PipelineMetrics stages={resource.data.pipeline} />
                  </div>
                  <Feed
                    title="Upcoming tasks"
                    rows={resource.data.tasks}
                    href="/tasks"
                  />
                  <Feed
                    title="Recent activity"
                    rows={resource.data.activities}
                    href="/tasks"
                  />
                  {can("ai:chat") && (
                    <Feed
                      title="AI insights"
                      rows={resource.data.ai_insights ?? []}
                      href="/ai-agents"
                    />
                  )}
                </div>
              </>
            )}
          </ResourceState>
        )}
      </section>
    </main>
  );
}
