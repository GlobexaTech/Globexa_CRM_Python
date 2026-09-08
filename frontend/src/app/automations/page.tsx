"use client";

import { useEffect, useState } from "react";

import {
  Zap,
  Play,
  Plus,
  Trash2,
  X,
} from "lucide-react";

import Sidebar from "@/components/Sidebar";

type Automation = {
  id: number;
  name: string;
  trigger: string;
  action: string;
  enabled: boolean;
  runs: number;
};

const KEY = "globexa-automations";

const defaults: Automation[] = [
  {
    id: 1,
    name: "New Lead Follow-up",
    trigger: "Lead enters New",
    action: "Send follow-up email",
    enabled: true,
    runs: 48,
  },
  {
    id: 2,
    name: "High Intent Alert",
    trigger: "AI Score ≥ 90",
    action: "Notify assigned agent",
    enabled: true,
    runs: 17,
  },
  {
    id: 3,
    name: "Daily Pipeline Summary",
    trigger: "Every day at 9:00 AM",
    action: "Generate pipeline report",
    enabled: false,
    runs: 6,
  },
];

export default function AutomationsPage() {
  const [items, setItems] =
    useState<Automation[]>([]);

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState("");
  const [action, setAction] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY);

      setItems(
        saved ? JSON.parse(saved) : defaults
      );
    } catch {
      setItems(defaults);
    }
  }, []);

  function save(updated: Automation[]) {
    setItems(updated);

    localStorage.setItem(
      KEY,
      JSON.stringify(updated)
    );
  }

  function toggle(id: number) {
    save(
      items.map((item) =>
        item.id === id
          ? {
              ...item,
              enabled: !item.enabled,
            }
          : item
      )
    );
  }

  function runNow(id: number) {
    save(
      items.map((item) =>
        item.id === id
          ? {
              ...item,
              runs: item.runs + 1,
            }
          : item
      )
    );

    setMessage("Automation executed in demo mode.");
  }

  function addAutomation() {
    if (!name.trim()) return;

    save([
      ...items,
      {
        id: Date.now(),
        name: name.trim(),
        trigger:
          trigger.trim() || "Manual trigger",
        action:
          action.trim() || "No action configured",
        enabled: false,
        runs: 0,
      },
    ]);

    setName("");
    setTrigger("");
    setAction("");
    setOpen(false);
  }

  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />

      <section className="min-w-0 flex-1 p-8">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <p className="text-xs tracking-[3px] text-[var(--blue2)]">
              WORKFLOW ENGINE
            </p>

            <h1 className="mt-2 text-3xl font-semibold">
              Automations
            </h1>

            <p className="mt-1 text-sm text-[var(--muted)]">
              Build trigger-based workflows across Globexa OS.
            </p>
          </div>

          <button
            onClick={() => setOpen(true)}
            className="flex items-center gap-2 rounded-xl bg-[var(--blue)] px-4 py-2.5 text-sm"
          >
            <Plus size={17} />
            New Automation
          </button>
        </header>

        {message && (
          <p className="mb-4 text-xs text-[var(--cyan)]">
            ✦ {message}
          </p>
        )}

        <div className="space-y-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="card grid grid-cols-[1.4fr_1.2fr_1.2fr_100px_150px] items-center gap-4 p-4"
            >
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-[var(--panel2)] p-2 text-[var(--cyan)]">
                  <Zap size={17} />
                </div>

                <div>
                  <b className="text-sm">
                    {item.name}
                  </b>

                  <p className="mt-1 text-xs text-[var(--muted)]">
                    {item.runs} runs
                  </p>
                </div>
              </div>

              <div>
                <p className="text-[10px] uppercase tracking-wider text-[var(--muted)]">
                  Trigger
                </p>

                <p className="mt-1 text-sm">
                  {item.trigger}
                </p>
              </div>

              <div>
                <p className="text-[10px] uppercase tracking-wider text-[var(--muted)]">
                  Action
                </p>

                <p className="mt-1 text-sm">
                  {item.action}
                </p>
              </div>

              <button
                onClick={() => toggle(item.id)}
                className={`rounded-full px-3 py-1.5 text-xs ${
                  item.enabled
                    ? "bg-green-500/15 text-green-400"
                    : "bg-[var(--panel2)] text-[var(--muted)]"
                }`}
              >
                {item.enabled
                  ? "Active"
                  : "Paused"}
              </button>

              <div className="flex justify-end gap-2">
                <button
                  onClick={() => runNow(item.id)}
                  className="rounded-lg border border-[var(--border)] p-2"
                  title="Run now"
                >
                  <Play size={15} />
                </button>

                <button
                  onClick={() =>
                    save(
                      items.filter(
                        (automation) =>
                          automation.id !== item.id
                      )
                    )
                  }
                  className="rounded-lg border border-[var(--border)] p-2"
                  title="Delete"
                >
                  <Trash2 size={15} />
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
                New Automation
              </h2>

              <button
                onClick={() => setOpen(false)}
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-3">
              <input
                value={name}
                onChange={(e) =>
                  setName(e.target.value)
                }
                placeholder="Automation name"
                className="card w-full px-4 py-3 text-sm outline-none"
              />

              <input
                value={trigger}
                onChange={(e) =>
                  setTrigger(e.target.value)
                }
                placeholder="Trigger"
                className="card w-full px-4 py-3 text-sm outline-none"
              />

              <input
                value={action}
                onChange={(e) =>
                  setAction(e.target.value)
                }
                placeholder="Action"
                className="card w-full px-4 py-3 text-sm outline-none"
              />
            </div>

            <button
              onClick={addAutomation}
              className="mt-5 w-full rounded-lg bg-[var(--blue)] py-2.5 text-sm"
            >
              Create Automation
            </button>
          </div>
        </div>
      )}
    </main>
  );
}