"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Contact,
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
} from "lucide-react";

const groups = [
  [
    "CUSTOMERS",
    [
      [Users, "Leads", "/leads"],
      [Contact, "Contacts", "/contacts"],
      [Kanban, "Pipeline", "/pipeline"],
      [MessageSquare, "Conversations", "/conversations"],
    ],
  ],
  [
    "GROWTH",
    [
      [Megaphone, "Campaigns", "/campaigns"],
      [CheckSquare, "Tasks", "/tasks"],
      [Zap, "Automations", "/automations"],
    ],
  ],
  [
    "INTELLIGENCE",
    [
      [Bot, "AI Agents", "/ai-agents"],
      [BarChart3, "Analytics", "/analytics"],
    ],
  ],
  [
    "SYSTEM",
    [[Plug, "Integrations", "/integrations"]],
  ],
] as const;

export default function Sidebar() {
  const path = usePathname();

  function itemClass(href: string) {
    const active =
      path === href || (href !== "/" && path.startsWith(`${href}/`));

    return `sidebar-link group ${
      active ? "sidebar-link-active" : "sidebar-link-inactive"
    }`;
  }

  return (
    <aside className="sidebar-shell">
      <div className="sidebar-top">
        <Link href="/" className="brand-block">
          <div className="brand-logo-wrap">
            <Image
              src="/globexa-logo.jpg"
              alt="Globexa Tech Logo"
              width={160}
              height={60}
              className="brand-logo-image"
              priority
            />
          </div>

          <div className="brand-text-wrap">
            <h1 className="brand-title">GLOBEXA</h1>
            <p className="brand-subtitle">Business Growth Command</p>
          </div>
        </Link>

        <Link href="/" className={`${itemClass("/")} mt-5`}>
          <LayoutDashboard size={17} />
          <span>Command Center</span>
        </Link>
      </div>

      <div className="sidebar-groups">
        {groups.map(([title, items]) => (
          <div key={title} className="sidebar-group">
            <p className="sidebar-group-title">{title}</p>

            <div className="space-y-1">
              {items.map(([Icon, name, href]) => (
                <Link key={name} href={href} className={itemClass(href)}>
                  <Icon size={17} className="shrink-0" />
                  <span>{name}</span>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="sidebar-footer">
        <button className="sidebar-link sidebar-link-inactive w-full">
          <Settings size={17} />
          <span>Settings</span>
        </button>

        <button className="sidebar-link sidebar-link-inactive w-full">
          <CircleHelp size={17} />
          <span>Help</span>
        </button>
      </div>
    </aside>
  );
}