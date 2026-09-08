"use client";

import {
  useEffect,
  useState,
} from "react";

import {
  BarChart3,
  RefreshCw,
} from "lucide-react";

import Sidebar from "@/components/Sidebar";

type Lead = {
  id: number;
  source: string;
  stage: string;
  score: number;
};

type ContactRecord = {
  id: number;
};

type Campaign = {
  id: number;
  sent: number;
  replies: number;
};

type Task = {
  id: number;
  status: string;
};

type StageCount = {
  name: string;
  count: number;
};

export default function AnalyticsPage() {
  const [leads, setLeads] =
    useState<Lead[]>([]);

  const [contacts, setContacts] =
    useState<ContactRecord[]>([]);

  const [campaigns, setCampaigns] =
    useState<Campaign[]>([]);

  const [tasks, setTasks] =
    useState<Task[]>([]);

  const [stages, setStages] =
    useState<string[]>([]);

  function loadData() {
    try {
      setLeads(
        JSON.parse(
          localStorage.getItem(
            "globexa-pipeline"
          ) || "[]"
        )
      );

      setContacts(
        JSON.parse(
          localStorage.getItem(
            "globexa-contacts"
          ) || "[]"
        )
      );

      setCampaigns(
        JSON.parse(
          localStorage.getItem(
            "globexa-campaigns"
          ) || "[]"
        )
      );

      setTasks(
        JSON.parse(
          localStorage.getItem(
            "globexa-tasks"
          ) || "[]"
        )
      );

      setStages(
        JSON.parse(
          localStorage.getItem(
            "globexa-stages"
          ) ||
            '["New","Contacted","Qualified","Proposal","Won","Lost"]'
        )
      );
    } catch {
      setLeads([]);
      setContacts([]);
      setCampaigns([]);
      setTasks([]);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const won =
    leads.filter(
      (lead) =>
        lead.stage === "Won"
    ).length;

  const conversion =
    leads.length
      ? Math.round(
          (won /
            leads.length) *
            100
        )
      : 0;

  const averageScore =
    leads.length
      ? Math.round(
          leads.reduce(
            (total, lead) =>
              total +
              lead.score,
            0
          ) / leads.length
        )
      : 0;

  const completedTasks =
    tasks.filter(
      (task) =>
        task.status === "Done"
    ).length;

  const totalSent =
    campaigns.reduce(
      (total, campaign) =>
        total +
        campaign.sent,
      0
    );

  const totalReplies =
    campaigns.reduce(
      (total, campaign) =>
        total +
        campaign.replies,
      0
    );

  const replyRate =
    totalSent
      ? Math.round(
          (totalReplies /
            totalSent) *
            100
        )
      : 0;

  const stageCounts: StageCount[] =
    stages.map((stage) => ({
      name: stage,
      count:
        leads.filter(
          (lead) =>
            lead.stage ===
            stage
        ).length,
    }));

  const sources =
    Array.from(
      new Set(
        leads.map(
          (lead) =>
            lead.source
        )
      )
    ).map((source) => ({
      name: source,
      count:
        leads.filter(
          (lead) =>
            lead.source ===
            source
        ).length,
    }));

  const maxStage =
    Math.max(
      1,
      ...stageCounts.map(
        (item) =>
          item.count
      )
    );

  const maxSource =
    Math.max(
      1,
      ...sources.map(
        (item) =>
          item.count
      )
    );

  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />

      <section className="min-w-0 flex-1 p-8">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <p className="text-xs tracking-[3px] text-[var(--blue2)]">
              BUSINESS INTELLIGENCE
            </p>

            <h1 className="mt-2 text-3xl font-semibold">
              Analytics
            </h1>

            <p className="mt-1 text-sm text-[var(--muted)]">
              Live performance across Globexa OS.
            </p>
          </div>

          <button
            onClick={loadData}
            className="flex items-center gap-2 rounded-xl border border-[var(--border)] px-4 py-2.5 text-sm"
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        </header>

        <div className="mb-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Metric
            label="Total Leads"
            value={leads.length}
          />

          <Metric
            label="Conversion"
            value={`${conversion}%`}
          />

          <Metric
            label="Average AI Score"
            value={averageScore}
          />

          <Metric
            label="Contacts"
            value={
              contacts.length
            }
          />
        </div>

        <div className="grid gap-5 xl:grid-cols-2">

          {/* PIPELINE */}

          <div className="card p-5">
            <div className="mb-5 flex items-center gap-2">
              <BarChart3
                size={17}
                className="text-[var(--cyan)]"
              />

              <div>
                <p className="text-xs tracking-[2px] text-[var(--blue2)]">
                  PIPELINE
                </p>

                <h2 className="font-semibold">
                  Leads by Stage
                </h2>
              </div>
            </div>

            <div className="space-y-4">
              {stageCounts.map(
                (item) => (
                  <Bar
                    key={
                      item.name
                    }
                    name={
                      item.name
                    }
                    value={
                      item.count
                    }
                    percent={
                      (item.count /
                        maxStage) *
                      100
                    }
                  />
                )
              )}
            </div>
          </div>

          {/* SOURCES */}

          <div className="card p-5">
            <div className="mb-5">
              <p className="text-xs tracking-[2px] text-[var(--blue2)]">
                ACQUISITION
              </p>

              <h2 className="font-semibold">
                Lead Sources
              </h2>
            </div>

            <div className="space-y-4">
              {sources.map(
                (item) => (
                  <Bar
                    key={
                      item.name
                    }
                    name={
                      item.name
                    }
                    value={
                      item.count
                    }
                    percent={
                      (item.count /
                        maxSource) *
                      100
                    }
                  />
                )
              )}

              {!sources.length && (
                <p className="text-sm text-[var(--muted)]">
                  No source data yet.
                </p>
              )}
            </div>
          </div>

          {/* CAMPAIGNS */}

          <div className="card p-5">
            <p className="text-xs tracking-[2px] text-[var(--blue2)]">
              CAMPAIGNS
            </p>

            <h2 className="mt-1 font-semibold">
              Outreach Performance
            </h2>

            <div className="mt-5 grid grid-cols-3 gap-3">
              <MiniMetric
                label="Sent"
                value={totalSent}
              />

              <MiniMetric
                label="Replies"
                value={
                  totalReplies
                }
              />

              <MiniMetric
                label="Reply Rate"
                value={`${replyRate}%`}
              />
            </div>
          </div>

          {/* TASKS */}

          <div className="card p-5">
            <p className="text-xs tracking-[2px] text-[var(--blue2)]">
              EXECUTION
            </p>

            <h2 className="mt-1 font-semibold">
              Task Performance
            </h2>

            <div className="mt-5 grid grid-cols-3 gap-3">
              <MiniMetric
                label="Total"
                value={tasks.length}
              />

              <MiniMetric
                label="Completed"
                value={
                  completedTasks
                }
              />

              <MiniMetric
                label="Pending"
                value={
                  tasks.length -
                  completedTasks
                }
              />
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="card p-5">
      <p className="text-xs text-[var(--muted)]">
        {label}
      </p>

      <b className="mt-2 block text-2xl">
        {value}
      </b>
    </div>
  );
}

function MiniMetric({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-lg bg-[var(--panel2)] p-4">
      <p className="text-xs text-[var(--muted)]">
        {label}
      </p>

      <b className="mt-2 block text-xl">
        {value}
      </b>
    </div>
  );
}

function Bar({
  name,
  value,
  percent,
}: {
  name: string;
  value: number;
  percent: number;
}) {
  return (
    <div>
      <div className="mb-2 flex justify-between text-sm">
        <span>{name}</span>

        <span className="text-[var(--cyan)]">
          {value}
        </span>
      </div>

      <div className="h-2 rounded-full bg-[var(--panel2)]">
        <div
          className="h-2 rounded-full bg-[var(--blue)]"
          style={{
            width: `${percent}%`,
          }}
        />
      </div>
    </div>
  );
}