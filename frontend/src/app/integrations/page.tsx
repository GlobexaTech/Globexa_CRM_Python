"use client";

import {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  Calendar,
  CheckCircle2,
  Database,
  Globe,
  HardDrive,
  Mail,
  Megaphone,
  MessageSquare,
  Plug,
  RefreshCw,
  Search,
  Send,
  Settings2,
  Table2,
  Webhook,
  X,
} from "lucide-react";

import Sidebar from "@/components/Sidebar";

type Status =
  | "Connected"
  | "Disconnected"
  | "Attention";

type Category =
  | "Meta"
  | "Google"
  | "Messaging"
  | "Sales"
  | "Developer";

type Integration = {
  id: string;
  name: string;
  description: string;
  category: Category;
  status: Status;
  lastSync: string;
  account: string;
  syncMode: string;
  autoSync: boolean;
};

const KEY = "globexa-integrations";

const defaults: Integration[] = [
  {
    id: "facebook-leads",
    name: "Facebook Lead Ads",
    description:
      "Import leads generated from Facebook Lead Ads directly into Globexa CRM.",
    category: "Meta",
    status: "Disconnected",
    lastSync: "Never",
    account: "",
    syncMode: "Two-way",
    autoSync: true,
  },
  {
    id: "instagram",
    name: "Instagram Business",
    description:
      "Connect Instagram conversations and lead activity with the CRM.",
    category: "Meta",
    status: "Disconnected",
    lastSync: "Never",
    account: "",
    syncMode: "Inbound",
    autoSync: true,
  },
  {
    id: "whatsapp",
    name: "WhatsApp Cloud API",
    description:
      "Handle WhatsApp conversations, notifications and customer follow-ups.",
    category: "Meta",
    status: "Disconnected",
    lastSync: "Never",
    account: "",
    syncMode: "Two-way",
    autoSync: true,
  },
  {
    id: "meta-ads",
    name: "Meta Ads",
    description:
      "Sync campaign, spend and conversion information from Meta advertising.",
    category: "Meta",
    status: "Disconnected",
    lastSync: "Never",
    account: "",
    syncMode: "Inbound",
    autoSync: true,
  },

  {
    id: "gmail",
    name: "Gmail / Google Workspace",
    description:
      "Send and receive CRM email through a connected Google Workspace account.",
    category: "Google",
    status: "Disconnected",
    lastSync: "Never",
    account: "",
    syncMode: "Two-way",
    autoSync: true,
  },
  {
    id: "calendar",
    name: "Google Calendar",
    description:
      "Sync appointments, follow-ups and CRM meetings.",
    category: "Google",
    status: "Disconnected",
    lastSync: "Never",
    account: "",
    syncMode: "Two-way",
    autoSync: true,
  },
  {
    id: "drive",
    name: "Google Drive",
    description:
      "Attach documents and customer files directly to CRM records.",
    category: "Google",
    status: "Disconnected",
    lastSync: "Never",
    account: "",
    syncMode: "Two-way",
    autoSync: true,
  },
  {
    id: "sheets",
    name: "Google Sheets",
    description:
      "Import and export lead lists, reports and CRM datasets.",
    category: "Google",
    status: "Disconnected",
    lastSync: "Never",
    account: "",
    syncMode: "Two-way",
    autoSync: true,
  },

  {
    id: "telegram",
    name: "Telegram",
    description:
      "Connect Telegram bots and customer conversations.",
    category: "Messaging",
    status: "Disconnected",
    lastSync: "Never",
    account: "",
    syncMode: "Two-way",
    autoSync: true,
  },
  {
    id: "slack",
    name: "Slack",
    description:
      "Send CRM notifications and workflow alerts to Slack.",
    category: "Messaging",
    status: "Disconnected",
    lastSync: "Never",
    account: "",
    syncMode: "Outbound",
    autoSync: true,
  },

  {
    id: "linkedin",
    name: "LinkedIn",
    description:
      "Link professional prospect activity and business development workflows.",
    category: "Sales",
    status: "Disconnected",
    lastSync: "Never",
    account: "",
    syncMode: "Inbound",
    autoSync: true,
  },
  {
    id: "apollo",
    name: "Apollo",
    description:
      "Import prospecting and enriched B2B lead information.",
    category: "Sales",
    status: "Disconnected",
    lastSync: "Never",
    account: "",
    syncMode: "Inbound",
    autoSync: true,
  },

  {
    id: "webhook",
    name: "Webhook / REST API",
    description:
      "Connect custom websites, forms and external software through APIs.",
    category: "Developer",
    status: "Disconnected",
    lastSync: "Never",
    account: "",
    syncMode: "Two-way",
    autoSync: false,
  },
];

export default function IntegrationsPage() {
  const [items, setItems] =
    useState<Integration[]>([]);

  const [search, setSearch] =
    useState("");

  const [category, setCategory] =
    useState<Category | "All">("All");

  const [selected, setSelected] =
    useState<Integration | null>(null);

  const [message, setMessage] =
    useState("");

  useEffect(() => {
    try {
      const saved =
        localStorage.getItem(KEY);

      setItems(
        saved
          ? JSON.parse(saved)
          : defaults
      );
    } catch {
      setItems(defaults);
    }
  }, []);

  function save(
    updated: Integration[]
  ) {
    setItems(updated);

    localStorage.setItem(
      KEY,
      JSON.stringify(updated)
    );
  }

  function connect(id: string) {
    save(
      items.map((item) =>
        item.id === id
          ? {
              ...item,
              status: "Connected",
              account:
                item.account ||
                "Connected account",
              lastSync: "Just now",
            }
          : item
      )
    );

    setMessage(
      "Frontend connection enabled. Backend OAuth will be added during integration."
    );
  }

  function disconnect(id: string) {
    save(
      items.map((item) =>
        item.id === id
          ? {
              ...item,
              status: "Disconnected",
              lastSync: "Never",
            }
          : item
      )
    );

    setMessage(
      "Integration disconnected."
    );
  }

  function sync(id: string) {
    save(
      items.map((item) =>
        item.id === id
          ? {
              ...item,
              lastSync:
                new Date().toLocaleTimeString(
                  [],
                  {
                    hour: "2-digit",
                    minute: "2-digit",
                  }
                ),
            }
          : item
      )
    );

    setMessage(
      "Sync completed in UI demo mode."
    );
  }

  function updateIntegration(
    updated: Integration
  ) {
    save(
      items.map((item) =>
        item.id === updated.id
          ? updated
          : item
      )
    );

    setSelected(updated);
  }

  const filtered = useMemo(
    () =>
      items.filter((item) => {
        const matchesSearch =
          `${item.name} ${item.description} ${item.category}`
            .toLowerCase()
            .includes(
              search.toLowerCase()
            );

        const matchesCategory =
          category === "All" ||
          item.category === category;

        return (
          matchesSearch &&
          matchesCategory
        );
      }),
    [items, search, category]
  );

  const connected =
    items.filter(
      (item) =>
        item.status === "Connected"
    ).length;

  const attention =
    items.filter(
      (item) =>
        item.status === "Attention"
    ).length;

  return (
    <main className="flex min-h-screen bg-[var(--bg)]">

      <Sidebar />

      <section className="min-w-0 flex-1 p-8">

        {/* HEADER */}

        <header className="mb-8">

          <p className="text-xs tracking-[3px] text-[var(--blue2)]">
            CONNECTIVITY
          </p>

          <h1 className="mt-2 text-3xl font-semibold">
            Integrations
          </h1>

          <p className="mt-1 text-sm text-[var(--muted)]">
            Connect Globexa CRM with your communication,
            advertising, productivity and sales systems.
          </p>

        </header>

        {/* SUMMARY */}

        <div className="mb-6 grid gap-4 md:grid-cols-3">

          <Metric
            label="Available Integrations"
            value={items.length}
          />

          <Metric
            label="Connected"
            value={connected}
          />

          <Metric
            label="Needs Attention"
            value={attention}
          />

        </div>

        {/* SEARCH */}

        <div className="card mb-5 flex flex-wrap items-center gap-3 p-3">

          <div className="flex min-w-[280px] flex-1 items-center gap-2 px-2">

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
              placeholder="Search integrations..."
              className="w-full bg-transparent text-sm outline-none"
            />

          </div>

          <select
            value={category}
            onChange={(e) =>
              setCategory(
                e.target
                  .value as Category | "All"
              )
            }
            className="rounded-lg border border-[var(--border)] bg-[var(--panel)] px-3 py-2 text-sm"
          >
            <option>All</option>
            <option>Meta</option>
            <option>Google</option>
            <option>Messaging</option>
            <option>Sales</option>
            <option>Developer</option>
          </select>

        </div>

        {message && (
          <p className="mb-4 text-xs text-[var(--cyan)]">
            ✦ {message}
          </p>
        )}

        {/* INTEGRATIONS */}

        <div className="space-y-8">

          {[
            "Meta",
            "Google",
            "Messaging",
            "Sales",
            "Developer",
          ].map((group) => {
            const groupItems =
              filtered.filter(
                (item) =>
                  item.category === group
              );

            if (!groupItems.length) {
              return null;
            }

            return (
              <section key={group}>

                <div className="mb-3">

                  <p className="text-xs tracking-[2px] text-[var(--blue2)]">
                    {group.toUpperCase()}
                  </p>

                  <h2 className="mt-1 font-semibold">
                    {group} Integrations
                  </h2>

                </div>

                <div className="grid gap-4 xl:grid-cols-2">

                  {groupItems.map(
                    (integration) => (
                      <IntegrationCard
                        key={
                          integration.id
                        }
                        integration={
                          integration
                        }
                        onConnect={() =>
                          connect(
                            integration.id
                          )
                        }
                        onDisconnect={() =>
                          disconnect(
                            integration.id
                          )
                        }
                        onSync={() =>
                          sync(
                            integration.id
                          )
                        }
                        onConfigure={() =>
                          setSelected(
                            integration
                          )
                        }
                      />
                    )
                  )}

                </div>

              </section>
            );
          })}

        </div>

      </section>

      {/* CONFIGURATION MODAL */}

      {selected && (
        <ConfigurationModal
          integration={selected}
          onChange={
            updateIntegration
          }
          onClose={() =>
            setSelected(null)
          }
        />
      )}

    </main>
  );
}

function IntegrationCard({
  integration,
  onConnect,
  onDisconnect,
  onSync,
  onConfigure,
}: {
  integration: Integration;
  onConnect: () => void;
  onDisconnect: () => void;
  onSync: () => void;
  onConfigure: () => void;
}) {
  const Icon =
    getIcon(integration.id);

  const connected =
    integration.status ===
    "Connected";

  return (
    <div className="card p-5">

      <div className="flex items-start justify-between">

        <div className="flex gap-4">

          <div className="rounded-xl bg-[var(--panel2)] p-3 text-[var(--cyan)]">
            <Icon size={20} />
          </div>

          <div>
            <h3 className="font-semibold">
              {integration.name}
            </h3>

            <p className="mt-1 max-w-xl text-xs leading-5 text-[var(--muted)]">
              {integration.description}
            </p>
          </div>

        </div>

        <StatusBadge
          status={
            integration.status
          }
        />

      </div>

      <div className="mt-5 grid grid-cols-2 gap-3">

        <div className="rounded-lg bg-[var(--panel2)] p-3">

          <p className="text-[10px] uppercase tracking-wider text-[var(--muted)]">
            Account
          </p>

          <p className="mt-1 truncate text-xs">
            {integration.account ||
              "Not connected"}
          </p>

        </div>

        <div className="rounded-lg bg-[var(--panel2)] p-3">

          <p className="text-[10px] uppercase tracking-wider text-[var(--muted)]">
            Last Sync
          </p>

          <p className="mt-1 text-xs">
            {integration.lastSync}
          </p>

        </div>

      </div>

      <div className="mt-5 flex flex-wrap gap-2">

        {connected ? (
          <>
            <button
              onClick={onSync}
              className="flex items-center gap-2 rounded-lg bg-[var(--blue)] px-3 py-2 text-sm"
            >
              <RefreshCw size={15} />
              Sync Now
            </button>

            <button
              onClick={onConfigure}
              className="flex items-center gap-2 rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
            >
              <Settings2 size={15} />
              Configure
            </button>

            <button
              onClick={
                onDisconnect
              }
              className="ml-auto rounded-lg border border-[var(--border)] px-3 py-2 text-xs text-[var(--muted)]"
            >
              Disconnect
            </button>
          </>
        ) : (
          <button
            onClick={onConnect}
            className="flex items-center gap-2 rounded-lg bg-[var(--blue)] px-4 py-2 text-sm"
          >
            <Plug size={15} />
            Connect
          </button>
        )}

      </div>

    </div>
  );
}

function ConfigurationModal({
  integration,
  onChange,
  onClose,
}: {
  integration: Integration;
  onChange: (
    updated: Integration
  ) => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">

      <div className="card w-full max-w-xl p-6">

        <div className="mb-6 flex items-start justify-between">

          <div>
            <p className="text-xs tracking-[2px] text-[var(--blue2)]">
              INTEGRATION SETTINGS
            </p>

            <h2 className="mt-1 text-xl font-semibold">
              {integration.name}
            </h2>
          </div>

          <button
            onClick={onClose}
          >
            <X size={20} />
          </button>

        </div>

        <div className="space-y-4">

          <div>
            <label className="mb-2 block text-xs text-[var(--muted)]">
              Connected Account
            </label>

            <input
              value={
                integration.account
              }
              onChange={(e) =>
                onChange({
                  ...integration,
                  account:
                    e.target.value,
                })
              }
              placeholder="Account name"
              className="card w-full px-4 py-3 text-sm outline-none"
            />
          </div>

          <div>
            <label className="mb-2 block text-xs text-[var(--muted)]">
              Sync Direction
            </label>

            <select
              value={
                integration.syncMode
              }
              onChange={(e) =>
                onChange({
                  ...integration,
                  syncMode:
                    e.target.value,
                })
              }
              className="card w-full px-4 py-3 text-sm"
            >
              <option>
                Two-way
              </option>

              <option>
                Inbound
              </option>

              <option>
                Outbound
              </option>
            </select>
          </div>

          <label className="flex items-center justify-between rounded-xl border border-[var(--border)] p-4">

            <div>
              <p className="text-sm font-medium">
                Automatic Sync
              </p>

              <p className="mt-1 text-xs text-[var(--muted)]">
                Automatically keep CRM data synchronized.
              </p>
            </div>

            <input
              type="checkbox"
              checked={
                integration.autoSync
              }
              onChange={(e) =>
                onChange({
                  ...integration,
                  autoSync:
                    e.target.checked,
                })
              }
            />

          </label>

        </div>

        <div className="mt-6 flex justify-end">

          <button
            onClick={onClose}
            className="rounded-lg bg-[var(--blue)] px-5 py-2.5 text-sm"
          >
            Save Settings
          </button>

        </div>

      </div>

    </div>
  );
}

function StatusBadge({
  status,
}: {
  status: Status;
}) {
  if (status === "Connected") {
    return (
      <span className="flex items-center gap-1 rounded-full bg-green-500/10 px-3 py-1 text-xs text-green-400">
        <CheckCircle2 size={12} />
        Connected
      </span>
    );
  }

  if (status === "Attention") {
    return (
      <span className="rounded-full bg-amber-500/10 px-3 py-1 text-xs text-amber-400">
        Attention
      </span>
    );
  }

  return (
    <span className="rounded-full bg-[var(--panel2)] px-3 py-1 text-xs text-[var(--muted)]">
      Disconnected
    </span>
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

function getIcon(id: string) {
  switch (id) {
    case "facebook-leads":
      return Globe;

    case "instagram":
      return MessageSquare;

    case "whatsapp":
      return MessageSquare;

    case "meta-ads":
      return Megaphone;

    case "gmail":
      return Mail;

    case "calendar":
      return Calendar;

    case "drive":
      return HardDrive;

    case "sheets":
      return Table2;

    case "telegram":
      return Send;

    case "slack":
      return MessageSquare;

    case "linkedin":
      return Globe;

    case "apollo":
      return Database;

    case "webhook":
      return Webhook;

    default:
      return Plug;
  }
}