"use client";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import {
  LayoutDashboard,
  Users,
  Contact,
  Building2,
  Kanban,
  MessageSquare,
  Megaphone,
  CheckSquare,
  Zap,
  Bot,
  BarChart3,
  Plug,
  Settings,
  CircleHelp,
  Search,
  Menu,
  LogOut,
  type LucideIcon,
} from "lucide-react";
import { useSession } from "@/auth/SessionProvider";
import { Dialog } from "./Dialog";
const groups: [string, [LucideIcon, string, string, string][]][] = [
  [
    "CUSTOMERS",
    [
      [Users, "Leads", "/leads", "leads:read"],
      [Contact, "Contacts", "/contacts", "contacts:read"],
      [Building2, "Companies", "/companies", "companies:read"],
      [Kanban, "Pipeline", "/pipeline", "deals:read"],
      [MessageSquare, "Conversations", "/conversations", "conversations:read"],
    ],
  ],
  [
    "GROWTH",
    [
      [Megaphone, "Campaigns", "/campaigns", "campaigns:read"],
      [CheckSquare, "Tasks", "/tasks", "tasks:read"],
      [Zap, "Automations", "/automations", "automation:read"],
    ],
  ],
  [
    "INTELLIGENCE",
    [
      [Bot, "AI workspace", "/ai-agents", "ai:chat"],
      [BarChart3, "Analytics", "/analytics", "analytics:read"],
    ],
  ],
  [
    "SYSTEM",
    [
      [Plug, "Integrations", "/integrations", "integrations:read"],
      [Search, "Search", "/search", ""],
    ],
  ],
];
export default function Sidebar() {
  const path = usePathname();
  const { session, can, switchTenant, logout } = useSession();
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  function itemClass(href: string) {
    return (
      "sidebar-link " +
      (path === href || (href !== "/" && path.startsWith(href + "/"))
        ? "sidebar-link-active"
        : "sidebar-link-inactive")
    );
  }
  const content = (
    <>
      <div className="sidebar-top">
        <Link href="/" className="brand-block" onClick={() => setOpen(false)}>
          <div className="brand-logo-wrap">
            <Image
              src="/Globexa-Logo.jpg"
              alt="Globexa Tech"
              width={160}
              height={60}
              className="brand-logo-image"
              priority
            />
          </div>
          <div className="brand-text-wrap">
            <p className="brand-title">GLOBEXA</p>
            <p className="brand-subtitle">Business Growth Command</p>
          </div>
        </Link>
        <Link
          href="/"
          className={itemClass("/") + " mt-3"}
          onClick={() => setOpen(false)}
        >
          <LayoutDashboard size={17} aria-hidden="true" />
          <span>Command Center</span>
        </Link>
      </div>
      <label className="crm-field px-2">
        Workspace
        <select
          aria-label="Workspace"
          className="crm-input"
          value={session?.tenant_id ?? ""}
          disabled={switching}
          onChange={async (event) => {
            if (busy.current) return;
            busy.current = true;
            setSwitching(true);
            setError(null);
            try {
              await switchTenant(event.target.value);
            } catch (failure) {
              setError(
                failure instanceof Error
                  ? failure.message
                  : "Workspace switch failed.",
              );
            } finally {
              busy.current = false;
              setSwitching(false);
            }
          }}
        >
          {session?.tenants.map((tenant) => (
            <option key={tenant.id} value={tenant.id}>
              {tenant.name}
            </option>
          ))}
        </select>
      </label>
      {error && (
        <p role="alert" className="crm-error">
          {error}
        </p>
      )}
      <nav className="sidebar-groups" aria-label="Main navigation">
        {groups.map(([title, items]) => {
          const visible = items.filter(
            ([, , , permission]) => !permission || can(permission),
          );
          return visible.length ? (
            <div key={title} className="sidebar-group">
              <p className="sidebar-group-title">{title}</p>
              <div className="space-y-1">
                {visible.map(([Icon, name, href]) => (
                  <Link
                    key={href}
                    href={href}
                    className={itemClass(href)}
                    aria-current={path === href ? "page" : undefined}
                    onClick={() => setOpen(false)}
                  >
                    <Icon size={17} aria-hidden="true" />
                    <span>{name}</span>
                  </Link>
                ))}
              </div>
            </div>
          ) : null;
        })}
      </nav>
      <div className="sidebar-footer">
        <p className="crm-muted px-3 text-xs break-all">
          {session?.user.email} · {session?.role.replaceAll("_", " ")}
        </p>
        <Link
          href="/settings"
          className={itemClass("/settings")}
          onClick={() => setOpen(false)}
        >
          <Settings size={17} aria-hidden="true" />
          Settings
        </Link>
        <Link
          href="/help"
          className={itemClass("/help")}
          onClick={() => setOpen(false)}
        >
          <CircleHelp size={17} aria-hidden="true" />
          Help
        </Link>
        <button
          className="sidebar-link sidebar-link-inactive"
          onClick={() => void logout()}
        >
          <LogOut size={17} aria-hidden="true" />
          Sign out
        </button>
      </div>
    </>
  );
  return (
    <>
      <a href="#workspace-content" className="skip-link">
        Skip to workspace
      </a>
      <div className="mobile-topbar">
        <button
          className="crm-secondary"
          aria-label="Open navigation"
          onClick={() => setOpen(true)}
        >
          <Menu size={20} />
        </button>
        <span>
          GLOBEXA ·{" "}
          {session?.tenants.find((t) => t.id === session.tenant_id)?.name}
        </span>
      </div>
      <aside className="sidebar-shell desktop-sidebar">{content}</aside>
      <Dialog open={open} title="Navigation" onClose={() => setOpen(false)}>
        <div className="mobile-sidebar-content">{content}</div>
      </Dialog>
      <span id="workspace-content" tabIndex={-1} />
    </>
  );
}
