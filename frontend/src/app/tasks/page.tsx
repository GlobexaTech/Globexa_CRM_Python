"use client";

import {
  useEffect,
  useState,
} from "react";

import {
  CheckCircle2,
  Circle,
  Clock3,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";

import Sidebar from "@/components/Sidebar";

type TaskStatus =
  | "Open"
  | "In Progress"
  | "Done";

type Priority =
  | "Low"
  | "Medium"
  | "High";

type Task = {
  id: number;
  title: string;
  lead: string;
  assignedTo: string;
  dueDate: string;
  priority: Priority;
  status: TaskStatus;
};

type Lead = {
  id: number;
  name: string;
};

const KEY = "globexa-tasks";

const defaults: Task[] = [
  {
    id: 1,
    title: "Call Aman Sharma",
    lead: "Aman Sharma",
    assignedTo: "Uday",
    dueDate: "2026-09-03",
    priority: "High",
    status: "Open",
  },
  {
    id: 2,
    title: "Prepare proposal",
    lead: "Sarah Khan",
    assignedTo: "Uday",
    dueDate: "2026-09-04",
    priority: "Medium",
    status: "In Progress",
  },
];

export default function TasksPage() {
  const [tasks, setTasks] =
    useState<Task[]>([]);

  const [leads, setLeads] =
    useState<Lead[]>([]);

  const [search, setSearch] =
    useState("");

  const [statusFilter, setStatusFilter] =
    useState("");

  const [open, setOpen] =
    useState(false);

  const [title, setTitle] =
    useState("");

  const [lead, setLead] =
    useState("");

  const [assignedTo, setAssignedTo] =
    useState("Uday");

  const [dueDate, setDueDate] =
    useState("");

  const [priority, setPriority] =
    useState<Priority>("Medium");

  useEffect(() => {
    try {
      const saved =
        localStorage.getItem(KEY);

      setTasks(
        saved
          ? JSON.parse(saved)
          : defaults
      );

      const savedLeads: Lead[] =
        JSON.parse(
          localStorage.getItem(
            "globexa-pipeline"
          ) || "[]"
        );

      setLeads(savedLeads);

      if (savedLeads.length) {
        setLead(
          savedLeads[0].name
        );
      }
    } catch {
      setTasks(defaults);
    }
  }, []);

  function save(updated: Task[]) {
    setTasks(updated);

    localStorage.setItem(
      KEY,
      JSON.stringify(updated)
    );
  }

  function addTask() {
    if (!title.trim()) return;

    save([
      {
        id: Date.now(),
        title: title.trim(),
        lead,
        assignedTo,
        dueDate,
        priority,
        status: "Open",
      },
      ...tasks,
    ]);

    setTitle("");
    setDueDate("");
    setPriority("Medium");
    setOpen(false);
  }

  function changeStatus(
    id: number,
    status: TaskStatus
  ) {
    save(
      tasks.map((task) =>
        task.id === id
          ? {
              ...task,
              status,
            }
          : task
      )
    );
  }

  const filtered =
    tasks.filter((task) => {
      const matchesSearch =
        `${task.title} ${task.lead} ${task.assignedTo}`
          .toLowerCase()
          .includes(
            search.toLowerCase()
          );

      const matchesStatus =
        !statusFilter ||
        task.status ===
          statusFilter;

      return (
        matchesSearch &&
        matchesStatus
      );
    });

  const completed =
    tasks.filter(
      (task) =>
        task.status === "Done"
    ).length;

  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />

      <section className="min-w-0 flex-1 p-8">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <p className="text-xs tracking-[3px] text-[var(--blue2)]">
              EXECUTION
            </p>

            <h1 className="mt-2 text-3xl font-semibold">
              Tasks
            </h1>

            <p className="mt-1 text-sm text-[var(--muted)]">
              Organize follow-ups and team actions.
            </p>
          </div>

          <button
            onClick={() =>
              setOpen(true)
            }
            className="flex items-center gap-2 rounded-xl bg-[var(--blue)] px-4 py-2.5 text-sm"
          >
            <Plus size={17} />
            New Task
          </button>
        </header>

        <div className="mb-5 grid gap-3 md:grid-cols-3">
          <Metric
            label="Total Tasks"
            value={tasks.length}
          />

          <Metric
            label="Completed"
            value={completed}
          />

          <Metric
            label="Pending"
            value={
              tasks.length -
              completed
            }
          />
        </div>

        <div className="card mb-4 flex gap-3 p-3">
          <div className="flex flex-1 items-center gap-2">
            <Search
              size={17}
              className="text-[var(--muted)]"
            />

            <input
              value={search}
              onChange={(e) =>
                setSearch(
                  e.target.value
                )
              }
              placeholder="Search tasks..."
              className="w-full bg-transparent text-sm outline-none"
            />
          </div>

          <select
            value={statusFilter}
            onChange={(e) =>
              setStatusFilter(
                e.target.value
              )
            }
            className="rounded-lg border border-[var(--border)] bg-[var(--panel)] px-3 py-2 text-sm"
          >
            <option value="">
              All Statuses
            </option>

            <option>Open</option>
            <option>
              In Progress
            </option>
            <option>Done</option>
          </select>
        </div>

        <div className="space-y-3">
          {filtered.map((task) => (
            <div
              key={task.id}
              className="card grid grid-cols-[1.6fr_1fr_1fr_120px_140px_50px] items-center gap-4 p-4"
            >
              <div className="flex items-center gap-3">
                {task.status ===
                "Done" ? (
                  <CheckCircle2
                    size={18}
                    className="text-green-400"
                  />
                ) : (
                  <Circle
                    size={18}
                    className="text-[var(--muted)]"
                  />
                )}

                <div>
                  <b className="text-sm">
                    {task.title}
                  </b>

                  <p className="mt-1 text-xs text-[var(--muted)]">
                    {task.lead ||
                      "No lead"}
                  </p>
                </div>
              </div>

              <span className="text-sm">
                {task.assignedTo}
              </span>

              <div className="flex items-center gap-2 text-sm text-[var(--muted)]">
                <Clock3 size={14} />

                {task.dueDate ||
                  "No due date"}
              </div>

              <span
                className={`text-xs ${
                  task.priority ===
                  "High"
                    ? "text-red-400"
                    : task.priority ===
                        "Medium"
                      ? "text-amber-400"
                      : "text-[var(--muted)]"
                }`}
              >
                {task.priority}
              </span>

              <select
                value={task.status}
                onChange={(e) =>
                  changeStatus(
                    task.id,
                    e.target
                      .value as TaskStatus
                  )
                }
                className="rounded-lg border border-[var(--border)] bg-[var(--panel)] px-2 py-2 text-xs"
              >
                <option>Open</option>
                <option>
                  In Progress
                </option>
                <option>Done</option>
              </select>

              <button
                onClick={() =>
                  save(
                    tasks.filter(
                      (item) =>
                        item.id !==
                        task.id
                    )
                  )
                }
                className="text-[var(--muted)] hover:text-red-400"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      </section>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
          <div className="card w-full max-w-lg p-6">
            <div className="mb-5 flex justify-between">
              <h2 className="text-xl font-semibold">
                New Task
              </h2>

              <button
                onClick={() =>
                  setOpen(false)
                }
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-3">
              <input
                value={title}
                onChange={(e) =>
                  setTitle(
                    e.target.value
                  )
                }
                placeholder="Task title"
                className="card w-full px-4 py-3 text-sm outline-none"
              />

              <select
                value={lead}
                onChange={(e) =>
                  setLead(
                    e.target.value
                  )
                }
                className="card w-full px-4 py-3 text-sm"
              >
                <option value="">
                  No Lead
                </option>

                {leads.map(
                  (item) => (
                    <option
                      key={item.id}
                      value={item.name}
                    >
                      {item.name}
                    </option>
                  )
                )}
              </select>

              <input
                value={assignedTo}
                onChange={(e) =>
                  setAssignedTo(
                    e.target.value
                  )
                }
                placeholder="Assigned to"
                className="card w-full px-4 py-3 text-sm outline-none"
              />

              <input
                type="date"
                value={dueDate}
                onChange={(e) =>
                  setDueDate(
                    e.target.value
                  )
                }
                className="card w-full px-4 py-3 text-sm"
              />

              <select
                value={priority}
                onChange={(e) =>
                  setPriority(
                    e.target
                      .value as Priority
                  )
                }
                className="card w-full px-4 py-3 text-sm"
              >
                <option>Low</option>
                <option>
                  Medium
                </option>
                <option>High</option>
              </select>
            </div>

            <button
              onClick={addTask}
              className="mt-5 w-full rounded-lg bg-[var(--blue)] py-2.5 text-sm"
            >
              Create Task
            </button>
          </div>
        </div>
      )}
    </main>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="card p-4">
      <p className="text-xs text-[var(--muted)]">
        {label}
      </p>

      <b className="mt-2 block text-2xl">
        {value}
      </b>
    </div>
  );
}