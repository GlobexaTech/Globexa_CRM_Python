"use client";

import {
  useEffect,
  useState,
} from "react";

import {
  Mail,
  MessageCircle,
  Pause,
  Play,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";

import Sidebar from "@/components/Sidebar";

type Campaign = {
  id: number;
  name: string;
  channel: "Email" | "WhatsApp" | "SMS";
  status: "Draft" | "Active" | "Paused";
  sent: number;
  replies: number;
};

type Lead = {
  id: number;
};

const KEY = "globexa-campaigns";

const defaults: Campaign[] = [
  {
    id: 1,
    name: "September Lead Follow-up",
    channel: "Email",
    status: "Active",
    sent: 126,
    replies: 18,
  },
  {
    id: 2,
    name: "High Intent WhatsApp",
    channel: "WhatsApp",
    status: "Paused",
    sent: 48,
    replies: 11,
  },
];

export default function CampaignsPage() {
  const [campaigns, setCampaigns] =
    useState<Campaign[]>([]);

  const [leadCount, setLeadCount] =
    useState(0);

  const [search, setSearch] =
    useState("");

  const [open, setOpen] =
    useState(false);

  const [name, setName] =
    useState("");

  const [channel, setChannel] =
    useState<Campaign["channel"]>("Email");

  const [message, setMessage] =
    useState("");

  useEffect(() => {
    try {
      const saved =
        localStorage.getItem(KEY);

      setCampaigns(
        saved
          ? JSON.parse(saved)
          : defaults
      );

      const leads: Lead[] =
        JSON.parse(
          localStorage.getItem(
            "globexa-pipeline"
          ) || "[]"
        );

      setLeadCount(leads.length);
    } catch {
      setCampaigns(defaults);
    }
  }, []);

  function save(updated: Campaign[]) {
    setCampaigns(updated);

    localStorage.setItem(
      KEY,
      JSON.stringify(updated)
    );
  }

  function addCampaign() {
    if (!name.trim()) return;

    save([
      {
        id: Date.now(),
        name: name.trim(),
        channel,
        status: "Draft",
        sent: 0,
        replies: 0,
      },
      ...campaigns,
    ]);

    setName("");
    setChannel("Email");
    setOpen(false);
  }

  function runCampaign(id: number) {
    const recipients =
      Math.max(leadCount, 1);

    save(
      campaigns.map((campaign) =>
        campaign.id === id
          ? {
              ...campaign,
              status: "Active",
              sent:
                campaign.sent +
                recipients,
              replies:
                campaign.replies +
                Math.floor(
                  recipients * 0.12
                ),
            }
          : campaign
      )
    );

    setMessage(
      `Demo campaign executed for ${recipients} lead(s).`
    );
  }

  function toggleCampaign(id: number) {
    save(
      campaigns.map((campaign) =>
        campaign.id === id
          ? {
              ...campaign,
              status:
                campaign.status ===
                "Active"
                  ? "Paused"
                  : "Active",
            }
          : campaign
      )
    );
  }

  const filtered =
    campaigns.filter((campaign) =>
      `${campaign.name} ${campaign.channel} ${campaign.status}`
        .toLowerCase()
        .includes(
          search.toLowerCase()
        )
    );

  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />

      <section className="min-w-0 flex-1 p-8">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <p className="text-xs tracking-[3px] text-[var(--blue2)]">
              GROWTH ENGINE
            </p>

            <h1 className="mt-2 text-3xl font-semibold">
              Campaigns
            </h1>

            <p className="mt-1 text-sm text-[var(--muted)]">
              Build and manage multi-channel outreach.
            </p>
          </div>

          <button
            onClick={() =>
              setOpen(true)
            }
            className="flex items-center gap-2 rounded-xl bg-[var(--blue)] px-4 py-2.5 text-sm"
          >
            <Plus size={17} />
            New Campaign
          </button>
        </header>

        <div className="card mb-4 flex items-center gap-3 px-4 py-3">
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
            placeholder="Search campaigns..."
            className="w-full bg-transparent text-sm outline-none"
          />
        </div>

        {message && (
          <p className="mb-4 text-xs text-[var(--cyan)]">
            ✦ {message}
          </p>
        )}

        <div className="grid gap-4 xl:grid-cols-2">
          {filtered.map((campaign) => {
            const responseRate =
              campaign.sent > 0
                ? Math.round(
                    (campaign.replies /
                      campaign.sent) *
                      100
                  )
                : 0;

            return (
              <div
                key={campaign.id}
                className="card p-5"
              >
                <div className="flex items-start justify-between">
                  <div className="flex gap-3">
                    <div className="rounded-xl bg-[var(--panel2)] p-3 text-[var(--cyan)]">
                      {campaign.channel ===
                      "Email" ? (
                        <Mail size={19} />
                      ) : (
                        <MessageCircle
                          size={19}
                        />
                      )}
                    </div>

                    <div>
                      <h2 className="font-semibold">
                        {campaign.name}
                      </h2>

                      <p className="mt-1 text-xs text-[var(--muted)]">
                        {campaign.channel}
                      </p>
                    </div>
                  </div>

                  <span
                    className={`text-xs ${
                      campaign.status ===
                      "Active"
                        ? "text-green-400"
                        : "text-[var(--muted)]"
                    }`}
                  >
                    ● {campaign.status}
                  </span>
                </div>

                <div className="mt-6 grid grid-cols-3 gap-3">
                  <Metric
                    label="Sent"
                    value={campaign.sent}
                  />

                  <Metric
                    label="Replies"
                    value={
                      campaign.replies
                    }
                  />

                  <Metric
                    label="Response"
                    value={`${responseRate}%`}
                  />
                </div>

                <div className="mt-5 flex gap-2">
                  <button
                    onClick={() =>
                      runCampaign(
                        campaign.id
                      )
                    }
                    className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-[var(--blue)] px-3 py-2 text-sm"
                  >
                    <Play size={15} />
                    Run Demo
                  </button>

                  <button
                    onClick={() =>
                      toggleCampaign(
                        campaign.id
                      )
                    }
                    className="rounded-lg border border-[var(--border)] p-2"
                  >
                    <Pause size={16} />
                  </button>

                  <button
                    onClick={() =>
                      save(
                        campaigns.filter(
                          (item) =>
                            item.id !==
                            campaign.id
                        )
                      )
                    }
                    className="rounded-lg border border-[var(--border)] p-2"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
          <div className="card w-full max-w-lg p-6">
            <div className="mb-5 flex justify-between">
              <h2 className="text-xl font-semibold">
                New Campaign
              </h2>

              <button
                onClick={() =>
                  setOpen(false)
                }
              >
                <X size={20} />
              </button>
            </div>

            <input
              value={name}
              onChange={(e) =>
                setName(e.target.value)
              }
              placeholder="Campaign name"
              className="card mb-3 w-full px-4 py-3 text-sm outline-none"
            />

            <select
              value={channel}
              onChange={(e) =>
                setChannel(
                  e.target
                    .value as Campaign["channel"]
                )
              }
              className="card w-full px-4 py-3 text-sm"
            >
              <option>Email</option>
              <option>WhatsApp</option>
              <option>SMS</option>
            </select>

            <button
              onClick={addCampaign}
              className="mt-5 w-full rounded-lg bg-[var(--blue)] py-2.5 text-sm"
            >
              Create Campaign
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
  value: string | number;
}) {
  return (
    <div className="rounded-lg bg-[var(--panel2)] p-3">
      <p className="text-xs text-[var(--muted)]">
        {label}
      </p>

      <b className="mt-1 block">
        {value}
      </b>
    </div>
  );
}