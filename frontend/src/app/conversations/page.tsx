"use client";

import {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  Mail,
  MessageSquare,
  Search,
  Send,
} from "lucide-react";

import Sidebar from "@/components/Sidebar";

type Lead = {
  id: number;
  name: string;
  email: string;
  source: string;
  score: number;
  stage: string;
};

type ChatMessage = {
  id: number;
  sender: "agent" | "lead";
  text: string;
  time: string;
};

const LEADS_KEY = "globexa-pipeline";
const CHAT_KEY = "globexa-conversations";

const fallbackLeads: Lead[] = [
  {
    id: 1,
    name: "Aman Sharma",
    email: "aman@example.com",
    source: "Facebook",
    score: 92,
    stage: "New",
  },
  {
    id: 2,
    name: "Priya Singh",
    email: "priya@example.com",
    source: "Instagram",
    score: 95,
    stage: "Qualified",
  },
];

export default function ConversationsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [messages, setMessages] =
    useState<Record<string, ChatMessage[]>>({});

  const [selectedId, setSelectedId] =
    useState<number | null>(null);

  const [search, setSearch] = useState("");
  const [text, setText] = useState("");

  useEffect(() => {
    try {
      const savedLeads =
        localStorage.getItem(LEADS_KEY);

      const loadedLeads: Lead[] =
        savedLeads
          ? JSON.parse(savedLeads)
          : fallbackLeads;

      setLeads(loadedLeads);

      if (loadedLeads.length) {
        setSelectedId(loadedLeads[0].id);
      }

      const savedChats =
        localStorage.getItem(CHAT_KEY);

      if (savedChats) {
        setMessages(JSON.parse(savedChats));
      } else if (loadedLeads.length) {
        const starter: Record<
          string,
          ChatMessage[]
        > = {
          [String(loadedLeads[0].id)]: [
            {
              id: 1,
              sender: "lead",
              text: "Hi, I would like some more information.",
              time: "10:20 AM",
            },
            {
              id: 2,
              sender: "agent",
              text: "Sure. I can help you with that.",
              time: "10:22 AM",
            },
          ],
        };

        setMessages(starter);

        localStorage.setItem(
          CHAT_KEY,
          JSON.stringify(starter)
        );
      }
    } catch {
      setLeads(fallbackLeads);
    }
  }, []);

  const filteredLeads = leads.filter((lead) =>
    `${lead.name} ${lead.email} ${lead.source}`
      .toLowerCase()
      .includes(search.toLowerCase())
  );

  const selectedLead = useMemo(
    () =>
      leads.find(
        (lead) => lead.id === selectedId
      ) || null,
    [leads, selectedId]
  );

  const selectedMessages =
    selectedId !== null
      ? messages[String(selectedId)] || []
      : [];

  function saveMessages(
    updated: Record<string, ChatMessage[]>
  ) {
    setMessages(updated);

    localStorage.setItem(
      CHAT_KEY,
      JSON.stringify(updated)
    );
  }

  function sendMessage() {
    if (
      !selectedId ||
      !text.trim()
    ) {
      return;
    }

    const key = String(selectedId);

    const nextMessage: ChatMessage = {
      id: Date.now(),
      sender: "agent",
      text: text.trim(),
      time: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };

    saveMessages({
      ...messages,
      [key]: [
        ...(messages[key] || []),
        nextMessage,
      ],
    });

    setText("");
  }

  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />

      <section className="flex min-w-0 flex-1 p-8">
        <div className="flex min-w-0 flex-1 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--panel)]">

          {/* CONTACT LIST */}

          <aside className="w-80 shrink-0 border-r border-[var(--border)]">
            <div className="border-b border-[var(--border)] p-4">
              <p className="text-xs tracking-[2px] text-[var(--blue2)]">
                UNIFIED INBOX
              </p>

              <h1 className="mt-1 text-xl font-semibold">
                Conversations
              </h1>

              <div className="mt-4 flex items-center gap-2 rounded-lg border border-[var(--border)] px-3 py-2">
                <Search
                  size={15}
                  className="text-[var(--muted)]"
                />

                <input
                  value={search}
                  onChange={(e) =>
                    setSearch(e.target.value)
                  }
                  placeholder="Search conversations..."
                  className="w-full bg-transparent text-xs outline-none"
                />
              </div>
            </div>

            <div>
              {filteredLeads.map((lead) => (
                <button
                  key={lead.id}
                  onClick={() =>
                    setSelectedId(lead.id)
                  }
                  className={`w-full border-b border-[var(--border)] p-4 text-left ${
                    selectedId === lead.id
                      ? "bg-[var(--panel2)]"
                      : "hover:bg-[var(--panel2)]"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <b className="text-sm">
                      {lead.name}
                    </b>

                    <MessageSquare
                      size={14}
                      className="text-[var(--cyan)]"
                    />
                  </div>

                  <p className="mt-1 truncate text-xs text-[var(--muted)]">
                    {lead.email}
                  </p>

                  <p className="mt-2 text-[10px] uppercase tracking-wider text-[var(--blue2)]">
                    {lead.source}
                  </p>
                </button>
              ))}
            </div>
          </aside>

          {/* CHAT */}

          <section className="flex min-w-0 flex-1 flex-col">
            {selectedLead ? (
              <>
                <header className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
                  <div>
                    <h2 className="font-semibold">
                      {selectedLead.name}
                    </h2>

                    <p className="text-xs text-[var(--muted)]">
                      {selectedLead.email}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
                    <Mail size={15} />
                    Unified Channel
                  </div>
                </header>

                <div className="flex-1 space-y-3 overflow-y-auto p-6">
                  {selectedMessages.map((message) => (
                    <div
                      key={message.id}
                      className={`flex ${
                        message.sender === "agent"
                          ? "justify-end"
                          : "justify-start"
                      }`}
                    >
                      <div
                        className={`max-w-[70%] rounded-2xl px-4 py-3 text-sm ${
                          message.sender === "agent"
                            ? "bg-[var(--blue)] text-white"
                            : "bg-[var(--panel2)]"
                        }`}
                      >
                        <p>{message.text}</p>

                        <p className="mt-1 text-[10px] opacity-60">
                          {message.time}
                        </p>
                      </div>
                    </div>
                  ))}

                  {!selectedMessages.length && (
                    <p className="text-center text-sm text-[var(--muted)]">
                      No messages yet.
                    </p>
                  )}
                </div>

                <div className="border-t border-[var(--border)] p-4">
                  <div className="flex gap-2">
                    <input
                      value={text}
                      onChange={(e) =>
                        setText(e.target.value)
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          sendMessage();
                        }
                      }}
                      placeholder="Write a message..."
                      className="card min-w-0 flex-1 px-4 py-3 text-sm outline-none"
                    />

                    <button
                      onClick={sendMessage}
                      className="rounded-xl bg-[var(--blue)] px-4"
                    >
                      <Send size={18} />
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center text-sm text-[var(--muted)]">
                Select a conversation.
              </div>
            )}
          </section>
        </div>
      </section>
    </main>
  );
}