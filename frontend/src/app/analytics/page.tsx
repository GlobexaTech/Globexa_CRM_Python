"use client";
import { useState } from "react";
import Sidebar from "@/components/Sidebar";
import { ResourceState } from "@/components/ResourceState";
import { AnalyticsData } from "@/components/AnalyticsData";
import { useSession } from "@/auth/SessionProvider";
import { useResource } from "@/hooks/useResource";
import {
  analyticsPermissions,
  type Analytics,
  type AnalyticsView,
} from "@/services/workspace";
export default function AnalyticsPage() {
  const { can } = useSession();
  const available = (
    Object.keys(analyticsPermissions) as AnalyticsView[]
  ).filter((view) => analyticsPermissions[view].every(can));
  const [choice, setChoice] = useState<AnalyticsView>("dashboard");
  const view = available.includes(choice) ? choice : available[0];
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [range, setRange] = useState("");
  const [validation, setValidation] = useState("");
  const resource = useResource<Analytics>(
    "/operations/analytics/" + (view ?? "dashboard") + range,
    !!view,
  );
  return (
    <main className="page-shell">
      <Sidebar />
      <section className="page-content">
        <p className="page-eyebrow">INTELLIGENCE</p>
        <h1 className="page-title">Analytics</h1>
        <p className="page-subtitle">
          Tenant aggregates calculated by the backend. Date ranges use UTC and
          an exclusive end.
        </p>
        {view ? (
          <>
            <div className="crm-actions my-6" aria-label="Analytics views">
              {available.map((name) => (
                <button
                  key={name}
                  className={view === name ? "crm-button" : "crm-secondary"}
                  aria-pressed={view === name}
                  onClick={() => setChoice(name)}
                >
                  {name === "ai"
                    ? "AI usage"
                    : name[0].toUpperCase() + name.slice(1)}
                </button>
              ))}
            </div>
            <form
              className="crm-actions mb-6"
              onSubmit={(event) => {
                event.preventDefault();
                if (start && end && start >= end) {
                  setValidation("End must be after start.");
                  return;
                }
                const query = new URLSearchParams();
                if (start) query.set("start", start + "T00:00:00Z");
                if (end) query.set("end", end + "T00:00:00Z");
                setRange(query.size ? "?" + query : "");
                setValidation("");
              }}
            >
              <label className="crm-field">
                Start (UTC)
                <input
                  className="crm-input"
                  type="date"
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                />
              </label>
              <label className="crm-field">
                End, exclusive (UTC)
                <input
                  className="crm-input"
                  type="date"
                  value={end}
                  onChange={(event) => setEnd(event.target.value)}
                />
              </label>
              <button className="crm-button">Apply range</button>
              <button
                type="button"
                className="crm-secondary"
                onClick={() => {
                  setStart("");
                  setEnd("");
                  setRange("");
                }}
              >
                All time
              </button>
            </form>
            {validation && (
              <p className="crm-error" role="alert">
                {validation}
              </p>
            )}
            <ResourceState
              loading={resource.isLoading}
              error={resource.error}
              onRetry={resource.refetch}
            >
              {resource.data && (
                <div className="card p-6">
                  <h2 className="text-lg font-bold mb-4">
                    {view === "ai"
                      ? "AI usage"
                      : view[0].toUpperCase() + view.slice(1)}
                  </h2>
                  <AnalyticsData view={view} data={resource.data} />
                </div>
              )}
            </ResourceState>
          </>
        ) : (
          <div className="card p-6 mt-6">
            Your role does not have access to these analytics views.
          </div>
        )}
      </section>
    </main>
  );
}
