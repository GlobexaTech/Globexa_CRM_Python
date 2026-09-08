"use client";

import { useEffect, useState } from "react";
import {
  Plus,
  Search,
  Mail,
  Phone,
  Trash2,
  X,
} from "lucide-react";

import Sidebar from "@/components/Sidebar";

type ContactRecord = {
  id: number;
  name: string;
  company: string;
  email: string;
  phone: string;
  status: string;
};

const KEY = "globexa-contacts";

const defaults: ContactRecord[] = [
  {
    id: 1,
    name: "Arjun Malhotra",
    company: "Malhotra Group",
    email: "arjun@example.com",
    phone: "+91 98765 10001",
    status: "Customer",
  },
  {
    id: 2,
    name: "Neha Kapoor",
    company: "NK Consulting",
    email: "neha@example.com",
    phone: "+91 98765 10002",
    status: "Prospect",
  },
];

export default function ContactsPage() {
  const [contacts, setContacts] =
    useState<ContactRecord[]>([]);

  const [search, setSearch] = useState("");
  const [addOpen, setAddOpen] = useState(false);

  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [status, setStatus] = useState("Prospect");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY);

      setContacts(
        saved ? JSON.parse(saved) : defaults
      );
    } catch {
      setContacts(defaults);
    }
  }, []);

  function save(updated: ContactRecord[]) {
    setContacts(updated);

    localStorage.setItem(
      KEY,
      JSON.stringify(updated)
    );
  }

  function addContact() {
    if (!name.trim()) return;

    save([
      {
        id: Date.now(),
        name: name.trim(),
        company: company.trim(),
        email: email.trim(),
        phone: phone.trim(),
        status,
      },
      ...contacts,
    ]);

    setName("");
    setCompany("");
    setEmail("");
    setPhone("");
    setStatus("Prospect");
    setAddOpen(false);
  }

  const filtered = contacts.filter((contact) =>
    `${contact.name} ${contact.company} ${contact.email} ${contact.phone}`
      .toLowerCase()
      .includes(search.toLowerCase())
  );

  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />

      <section className="min-w-0 flex-1 p-8">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <p className="text-xs tracking-[3px] text-[var(--blue2)]">
              CUSTOMER DATABASE
            </p>

            <h1 className="mt-2 text-3xl font-semibold">
              Contacts
            </h1>

            <p className="mt-1 text-sm text-[var(--muted)]">
              Central directory for customers and business relationships.
            </p>
          </div>

          <button
            onClick={() => setAddOpen(true)}
            className="flex items-center gap-2 rounded-xl bg-[var(--blue)] px-4 py-2.5 text-sm"
          >
            <Plus size={17} />
            New Contact
          </button>
        </header>

        <div className="card mb-4 flex items-center gap-3 px-4 py-3">
          <Search
            size={17}
            className="text-[var(--muted)]"
          />

          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search contacts..."
            className="w-full bg-transparent text-sm outline-none"
          />
        </div>

        <div className="grid gap-3 xl:grid-cols-2">
          {filtered.map((contact) => (
            <div key={contact.id} className="card p-5">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="font-semibold">
                    {contact.name}
                  </h2>

                  <p className="mt-1 text-xs text-[var(--muted)]">
                    {contact.company || "No company"}
                  </p>
                </div>

                <button
                  onClick={() =>
                    save(
                      contacts.filter(
                        (item) =>
                          item.id !== contact.id
                      )
                    )
                  }
                  className="text-[var(--muted)] hover:text-red-400"
                >
                  <Trash2 size={16} />
                </button>
              </div>

              <div className="mt-5 grid gap-3 text-sm">
                <div className="flex items-center gap-3">
                  <Mail
                    size={15}
                    className="text-[var(--muted)]"
                  />

                  {contact.email || "No email"}
                </div>

                <div className="flex items-center gap-3">
                  <Phone
                    size={15}
                    className="text-[var(--muted)]"
                  />

                  {contact.phone || "No phone"}
                </div>
              </div>

              <div className="mt-5">
                <select
                  value={contact.status}
                  onChange={(e) =>
                    save(
                      contacts.map((item) =>
                        item.id === contact.id
                          ? {
                              ...item,
                              status: e.target.value,
                            }
                          : item
                      )
                    )
                  }
                  className="rounded-lg border border-[var(--border)] bg-[var(--panel)] px-3 py-2 text-xs"
                >
                  <option>Prospect</option>
                  <option>Customer</option>
                  <option>Partner</option>
                  <option>Inactive</option>
                </select>
              </div>
            </div>
          ))}
        </div>
      </section>

      {addOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="card w-full max-w-lg p-6">
            <div className="mb-5 flex justify-between">
              <h2 className="text-xl font-semibold">
                New Contact
              </h2>

              <button
                onClick={() => setAddOpen(false)}
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-3">
              {[
                ["Name", name, setName],
                ["Company", company, setCompany],
                ["Email", email, setEmail],
                ["Phone", phone, setPhone],
              ].map(([placeholder, value, setter]) => {
                const update = setter as (
                  value: string
                ) => void;

                return (
                  <input
                    key={placeholder as string}
                    value={value as string}
                    onChange={(e) =>
                      update(e.target.value)
                    }
                    placeholder={placeholder as string}
                    className="card w-full px-4 py-3 text-sm outline-none"
                  />
                );
              })}

              <select
                value={status}
                onChange={(e) =>
                  setStatus(e.target.value)
                }
                className="card w-full px-4 py-3 text-sm"
              >
                <option>Prospect</option>
                <option>Customer</option>
                <option>Partner</option>
              </select>
            </div>

            <button
              onClick={addContact}
              className="mt-5 w-full rounded-lg bg-[var(--blue)] py-2.5 text-sm"
            >
              Add Contact
            </button>
          </div>
        </div>
      )}
    </main>
  );
}