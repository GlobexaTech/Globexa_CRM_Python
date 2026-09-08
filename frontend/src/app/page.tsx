"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  Activity,
  ArrowRight,
  BarChart3,
  Bot,
  CheckCircle2,
  GitBranch,
  Sparkles,
  Users,
  Zap,
} from "lucide-react";

import Sidebar from "@/components/Sidebar";

type Lead = {
  id: number;
  name?: string;
  source?: string;
  score: number;
  stage: string;
};

type Task = {
  id: number;
  status: string;
};

type Automation = {
  id: number;
  enabled: boolean;
};

type Campaign = {
  id: number;
  sent: number;
  replies: number;
};

const defaultStages = [
  "New",
  "Contacted",
  "Qualified",
  "Proposal",
  "Won",
  "Lost",
];

export default function Home() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [automations, setAutomations] =
    useState<Automation[]>([]);
  const [campaigns, setCampaigns] =
    useState<Campaign[]>([]);
  const [stages, setStages] =
    useState<string[]>(defaultStages);

  function loadData() {
    try {
      setLeads(
        JSON.parse(
          localStorage.getItem("globexa-pipeline") || "[]"
        )
      );

      setTasks(
        JSON.parse(
          localStorage.getItem("globexa-tasks") || "[]"
        )
      );

      setAutomations(
        JSON.parse(
          localStorage.getItem("globexa-automations") || "[]"
        )
      );

      setCampaigns(
        JSON.parse(
          localStorage.getItem("globexa-campaigns") || "[]"
        )
      );

      setStages(
        JSON.parse(
          localStorage.getItem("globexa-stages") ||
            JSON.stringify(defaultStages)
        )
      );
    } catch {
      setLeads([]);
      setTasks([]);
      setAutomations([]);
      setCampaigns([]);
      setStages(defaultStages);
    }
  }

  useEffect(() => {
    loadData();

    window.addEventListener("focus", loadData);
    window.addEventListener("storage", loadData);

    return () => {
      window.removeEventListener("focus", loadData);
      window.removeEventListener("storage", loadData);
    };
  }, []);

  const qualified = leads.filter(
    (lead) =>
      lead.stage === "Qualified" ||
      lead.stage === "Proposal" ||
      lead.stage === "Won"
  ).length;

  const won = leads.filter(
    (lead) => lead.stage === "Won"
  ).length;

  const completedTasks = tasks.filter(
    (task) => task.status === "Done"
  ).length;

  const activeAutomations = automations.filter(
    (automation) => automation.enabled
  ).length;

  const averageScore = leads.length
    ? Math.round(
        leads.reduce(
          (total, lead) => total + (lead.score || 0),
          0
        ) / leads.length
      )
    : 0;

  const totalSent = campaigns.reduce(
    (total, campaign) => total + (campaign.sent || 0),
    0
  );

  const totalReplies = campaigns.reduce(
    (total, campaign) =>
      total + (campaign.replies || 0),
    0
  );

  const responseRate = totalSent
    ? Math.round((totalReplies / totalSent) * 100)
    : 0;

  return (
    <main className="page-shell">
      <Sidebar />

      <section className="page-content min-w-0">
        {/* HERO */}

        <section className="crm-hero fade-in-up">
          <div className="hero-grid" />

          <div className="hero-orb hero-orb-one" />
          <div className="hero-orb hero-orb-two" />

          <div className="relative z-10 grid gap-10 xl:grid-cols-[1.15fr_0.85fr]">
            {/* LEFT */}

            <div className="flex flex-col justify-center py-5">
              <div className="hero-kicker">
                <span className="hero-kicker-line" />

                <Sparkles size={14} />

                GLOBEXA OS
              </div>

              <h1 className="hero-title">
                Your business.
                <br />

                <span className="hero-title-blue">
                  One intelligent command center.
                </span>
              </h1>

              <p className="hero-description">
                Capture leads, manage customer journeys,
                coordinate AI agents and automate growth from
                one connected operating system.
              </p>

              <div className="mt-7 flex flex-wrap gap-3">
                <Link
                  href="/pipeline"
                  className="hero-primary-button"
                >
                  Open Pipeline
                  <ArrowRight size={16} />
                </Link>

                <Link
                  href="/integrations"
                  className="hero-secondary-button"
                >
                  Connect Apps
                </Link>
              </div>

              <div className="mt-8 flex flex-wrap gap-x-7 gap-y-3">
                <HeroMiniStat
                  label="Leads"
                  value={leads.length}
                />

                <HeroMiniStat
                  label="AI Score"
                  value={averageScore}
                />

                <HeroMiniStat
                  label="Automations"
                  value={activeAutomations}
                />
              </div>
            </div>

            {/* RIGHT ANIMATED SYSTEM */}

            <div className="hero-system">
              <div className="hero-system-label">
                LIVE CUSTOMER JOURNEY
              </div>

              <FlowCard
                icon={<Users size={18} />}
                label="Capture"
                value="Leads"
                className="flow-one"
              />

              <FlowConnector className="connector-one" />

              <FlowCard
                icon={<Sparkles size={18} />}
                label="Intelligence"
                value="AI Qualification"
                className="flow-two"
              />

              <FlowConnector className="connector-two" />

              <FlowCard
                icon={<GitBranch size={18} />}
                label="Journey"
                value="Pipeline"
                className="flow-three"
              />

              <FlowConnector className="connector-three" />

              <FlowCard
                icon={<Zap size={18} />}
                label="Execution"
                value="Automation"
                className="flow-four"
              />

              <div className="hero-system-pulse hero-system-pulse-one" />
              <div className="hero-system-pulse hero-system-pulse-two" />
            </div>
          </div>
        </section>

        {/* METRICS */}

        <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Metric
            icon={<Users size={18} />}
            label="Total Leads"
            value={leads.length}
            note={`${qualified} qualified`}
          />

          <Metric
            icon={<CheckCircle2 size={18} />}
            label="Won"
            value={won}
            note={
              leads.length
                ? `${Math.round(
                    (won / leads.length) * 100
                  )}% conversion`
                : "0% conversion"
            }
          />

          <Metric
            icon={<Activity size={18} />}
            label="Tasks Completed"
            value={completedTasks}
            note={`${tasks.length} total tasks`}
          />

          <Metric
            icon={<BarChart3 size={18} />}
            label="Campaign Response"
            value={`${responseRate}%`}
            note={`${totalReplies} replies`}
          />
        </section>

        {/* PIPELINE STAGES */}

        <section className="mt-6 card p-6">
          <div className="mb-5 flex items-center justify-between">
            <div>
              <p className="page-eyebrow">
                CUSTOMER JOURNEY
              </p>

              <h2 className="mt-1 text-xl font-bold">
                Pipeline Overview
              </h2>
            </div>

            <Link
              href="/pipeline"
              className="flex items-center gap-2 text-sm font-semibold text-[var(--blue)]"
            >
              View Pipeline
              <ArrowRight size={15} />
            </Link>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            {stages.map((stage, index) => {
              const count = leads.filter(
                (lead) => lead.stage === stage
              ).length;

              return (
                <div
                  key={stage}
                  className="stage-summary-card"
                  style={{
                    animationDelay: `${index * 55}ms`,
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-[var(--muted)]">
                      {String(index + 1).padStart(2, "0")}
                    </span>

                    <span className="stage-summary-dot" />
                  </div>

                  <p className="mt-4 text-sm font-semibold">
                    {stage}
                  </p>

                  <p className="mt-2 text-2xl font-bold text-[var(--blue)]">
                    {count}
                  </p>

                  <p className="mt-1 text-xs text-[var(--muted)]">
                    lead{count === 1 ? "" : "s"}
                  </p>
                </div>
              );
            })}
          </div>
        </section>

        {/* SYSTEM STATUS */}

        <section className="mt-6 grid gap-4 xl:grid-cols-3">
          <StatusCard
            title="AI Workforce"
            value={`${activeAutomations} automations active`}
            icon={<Bot size={18} />}
          />

          <StatusCard
            title="Customer Execution"
            value={`${completedTasks}/${tasks.length} tasks completed`}
            icon={<CheckCircle2 size={18} />}
          />

          <StatusCard
            title="Growth Activity"
            value={`${totalSent} campaign messages sent`}
            icon={<Activity size={18} />}
          />
        </section>
      </section>
    </main>
  );
}

function HeroMiniStat({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div>
      <p className="text-lg font-bold text-[var(--text)]">
        {value}
      </p>

      <p className="text-xs text-[var(--muted)]">
        {label}
      </p>
    </div>
  );
}

function FlowCard({
  icon,
  label,
  value,
  className,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  className: string;
}) {
  return (
    <div className={`hero-flow-card ${className}`}>
      <div className="hero-flow-icon">{icon}</div>

      <div>
        <p className="hero-flow-label">
          {label}
        </p>

        <p className="hero-flow-value">
          {value}
        </p>
      </div>
    </div>
  );
}

function FlowConnector({
  className,
}: {
  className: string;
}) {
  return (
    <div className={`hero-connector ${className}`}>
      <span />
    </div>
  );
}

function Metric({
  icon,
  label,
  value,
  note,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  note: string;
}) {
  return (
    <div className="metric-card">
      <div className="mb-5 flex items-center justify-between">
        <span className="metric-label">
          {label}
        </span>

        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-50 text-[var(--blue)]">
          {icon}
        </div>
      </div>

      <p className="metric-value">
        {value}
      </p>

      <p className="mt-2 text-xs text-[var(--muted)]">
        {note}
      </p>
    </div>
  );
}

function StatusCard({
  title,
  value,
  icon,
}: {
  title: string;
  value: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="card flex items-center gap-4 p-5">
      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-[var(--blue)]">
        {icon}
      </div>

      <div>
        <p className="text-sm font-semibold">
          {title}
        </p>

        <p className="mt-1 text-xs text-[var(--muted)]">
          {value}
        </p>
      </div>
    </div>
  );
}