"use client";

import { useEffect, useState } from "react";

import {
  Bot,
  Play,
  Pause,
  Plus,
  X,
} from "lucide-react";

import Sidebar from "@/components/Sidebar";

type Agent = {
  id: number;
  name: string;
  role: string;
  status: "Active" | "Paused";
  tasks: number;
  lastRun: string;
};

const KEY = "globexa-ai-agents";

const defaults: Agent[] = [
  {
    id: 1,
    name: "Supervisor",
    role: "Delegation & Agent Coordination",
    status: "Active",
    tasks: 12,
    lastRun: "Recently",
  },
  {
    id: 2,
    name: "Research Head",
    role: "Deep Research & Lead Intelligence",
    status: "Active",
    tasks: 8,
    lastRun: "Recently",
  },
  {
    id: 3,
    name: "CTO Tech",
    role: "Engineering & Technical Operations",
    status: "Active",
    tasks: 5,
    lastRun: "Recently",
  },
];

export default function AIAgentsPage() {
  const [agents, setAgents] =
    useState<Agent[]>([]);

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [role, setRole] = useState("");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY);

      setAgents(
        saved ? JSON.parse(saved) : defaults
      );
    } catch {
      setAgents(defaults);
    }
  }, []);

  function save(updated: Agent[]) {
    setAgents(updated);

    localStorage.setItem(
      KEY,
      JSON.stringify(updated)
    );
  }

  function toggle(id: number) {
    save(
      agents.map((agent) =>
        agent.id === id
          ? {
              ...agent,
              status:
                agent.status === "Active"
                  ? "Paused"
                  : "Active",
            }
          : agent
      )
    );
  }

  function run(id: number) {
    save(
      agents.map((agent) =>
        agent.id === id
          ? {
              ...agent,
              tasks: agent.tasks + 1,
              lastRun: new Date().toLocaleTimeString(),
            }
          : agent
      )
    );
  }

  function addAgent() {
    if (!name.trim()) return;

    save([
      ...agents,
      {
        id: Date.now(),
        name: name.trim(),
        role: role.trim() || "Custom AI Agent",
        status: "Paused",
        tasks: 0,
        lastRun: "Never",
      },
    ]);

    setName("");
    setRole("");
    setOpen(false);
  }

  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />

      <section className="min-w-0 flex-1 p-8">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <p className="text-xs tracking-[3px] text-[var(--blue2)]">
              INTELLIGENCE
            </p>

            <h1 className="mt-2 text-3xl font-semibold">
              AI Agents
            </h1>

            <p className="mt-1 text-sm text-[var(--muted)]">
              Manage Globexa's autonomous workforce.
            </p>
          </div>

          <button
            onClick={() => setOpen(true)}
            className="flex items-center gap-2 rounded-xl bg-[var(--blue)] px-4 py-2.5 text-sm"
          >
            <Plus size={17} />
            New Agent
          </button>
        </header>

        <div className="grid gap-4 xl:grid-cols-3">
          {agents.map((agent) => (
            <div key={agent.id} className="card p-5">
              <div className="flex items-start justify-between">
                <div className="flex gap-3">
                  <div className="rounded-xl bg-[var(--panel2)] p-3 text-[var(--cyan)]">
                    <Bot size={20} />
                  </div>

                  <div>
                    <h2 className="font-semibold">
                      {agent.name}
                    </h2>

                    <p className="mt-1 text-xs text-[var(--muted)]">
                      {agent.role}
                    </p>
                  </div>
                </div>

                <span
                  className={`text-xs ${
                    agent.status === "Active"
                      ? "text-green-400"
                      : "text-[var(--muted)]"
                  }`}
                >
                  ● {agent.status}
                </span>
              </div>

              <div className="mt-6 grid grid-cols-2 gap-3">
                <div className="rounded-lg bg-[var(--panel2)] p-3">
                  <p className="text-xs text-[var(--muted)]">
                    Tasks
                  </p>

                  <b className="mt-1 block">
                    {agent.tasks}
                  </b>
                </div>

                <div className="rounded-lg bg-[var(--panel2)] p-3">
                  <p className="text-xs text-[var(--muted)]">
                    Last Run
                  </p>

                  <b className="mt-1 block truncate text-xs">
                    {agent.lastRun}
                  </b>
                </div>
              </div>

              <div className="mt-5 flex gap-2">
                <button
                  onClick={() => run(agent.id)}
                  disabled={agent.status === "Paused"}
                  className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-[var(--blue)] px-3 py-2 text-sm disabled:opacity-40"
                >
                  <Play size={15} />
                  Run
                </button>

                <button
                  onClick={() => toggle(agent.id)}
                  className="flex items-center gap-2 rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
                >
                  <Pause size={15} />
                  {agent.status === "Active"
                    ? "Pause"
                    : "Activate"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
          <div className="card w-full max-w-lg p-6">
            <div className="mb-5 flex justify-between">
              <h2 className="text-xl font-semibold">
                Create AI Agent
              </h2>

              <button
                onClick={() => setOpen(false)}
              >
                <X size={20} />
              </button>
            </div>

            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Agent name"
              className="card mb-3 w-full px-4 py-3 text-sm outline-none"
            />

            <input
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="Role / responsibility"
              className="card w-full px-4 py-3 text-sm outline-none"
            />

            <button
              onClick={addAgent}
              className="mt-5 w-full rounded-lg bg-[var(--blue)] py-2.5 text-sm"
            >
              Create Agent
            </button>
          </div>
        </div>
      )}
    </main>
  );
}