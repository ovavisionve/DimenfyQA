"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Workflow,
  Send,
  MessageSquare,
  Inbox,
  Kanban,
  Users,
  SlidersHorizontal,
  Terminal,
  HeartPulse,
  Bell,
  LogOut,
  Book,
  CreditCard,
  Rocket,
  Globe,
  Upload,
  KeyRound,
  BarChart3,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { getUser, clearAuth } from "@/lib/auth";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getLocale, setLocale, t, type Locale } from "@/lib/i18n";

const NAV_ITEMS = [
  { i18n: "nav.pipeline", href: "/pipeline", icon: Workflow, group: "group.pipeline" },
  { i18n: "nav.dms", href: "/dms", icon: Send, group: "group.pipeline" },
  { i18n: "nav.comments", href: "/comments", icon: MessageSquare, group: "group.pipeline" },
  { i18n: "nav.import", href: "/import", icon: Upload, group: "group.pipeline" },
  { i18n: "nav.unibox", href: "/unibox", icon: Inbox, group: "group.communication" },
  { i18n: "nav.crm", href: "/crm", icon: Kanban, group: "group.communication" },
  { i18n: "nav.reports", href: "/reports", icon: BarChart3, group: "group.communication" },
  { i18n: "nav.clients", href: "/clients", icon: Users, group: "group.management" },
  { i18n: "nav.accounts", href: "/accounts", icon: KeyRound, group: "group.management" },
  { i18n: "nav.settings", href: "/settings", icon: SlidersHorizontal, group: "group.management" },
  { i18n: "nav.billing", href: "/billing", icon: CreditCard, group: "group.management" },
  { i18n: "nav.logs", href: "/logs", icon: Terminal, group: "group.monitoring" },
  { i18n: "nav.health", href: "/health", icon: HeartPulse, group: "group.monitoring" },
  { i18n: "nav.docs", href: "/docs", icon: Book, group: "group.monitoring" },
  { i18n: "nav.onboarding", href: "/onboarding", icon: Rocket, group: "group.monitoring" },
];

export function Sidebar() {
  const pathname = usePathname();
  const user = getUser();
  const [unread, setUnread] = useState(0);
  const [locale, setLocaleState] = useState<Locale>("es");

  useEffect(() => {
    setLocaleState(getLocale());
    const handler = () => setLocaleState(getLocale());
    window.addEventListener("locale-change", handler);
    return () => window.removeEventListener("locale-change", handler);
  }, []);

  useEffect(() => {
    const load = () =>
      api<Array<{ id: string }>>("/api/v1/notifications?unread_only=true&limit=50")
        .then((n) => setUnread(n.length))
        .catch(() => {});
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  const handleLogout = () => {
    clearAuth();
    window.location.href = "/login";
  };

  let currentGroup = "";

  return (
    <aside className="flex w-60 shrink-0 flex-col bg-zinc-950 text-zinc-300 h-screen sticky top-0">
      {/* Brand */}
      <div className="flex items-center gap-2 px-5 py-5 border-b border-zinc-800">
        <div className="h-8 w-8 rounded-lg bg-amber-500 flex items-center justify-center text-black font-bold text-sm">
          IG
        </div>
        <span className="font-semibold text-white text-sm tracking-tight">
          IG DM Engine
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-3 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const groupKey = item.group;
          const showGroup = groupKey !== currentGroup;
          currentGroup = groupKey;
          const active = pathname === item.href;
          const Icon = item.icon;

          return (
            <div key={item.href}>
              {showGroup && (
                <p className="text-[10px] uppercase tracking-widest text-zinc-600 font-medium mt-4 mb-1.5 px-2">
                  {t(groupKey, locale)}
                </p>
              )}
              <Link
                href={item.href}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
                  active
                    ? "bg-zinc-800 text-white font-medium"
                    : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                )}
              >
                <Icon size={16} strokeWidth={1.8} />
                {t(item.i18n, locale)}
              </Link>
            </div>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-zinc-800 p-3 space-y-2">
        {/* Language Toggle */}
        <button
          onClick={() => {
            const next = locale === "es" ? "en" : "es";
            setLocale(next);
            setLocaleState(next);
          }}
          className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200 w-full"
        >
          <Globe size={16} strokeWidth={1.8} />
          {locale === "es" ? "English" : "Español"}
        </button>

        {/* Notifications */}
        <Link
          href="#"
          className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
        >
          <Bell size={16} strokeWidth={1.8} />
          {t("nav.notifications", locale)}
          {unread > 0 && (
            <span className="ml-auto bg-amber-500 text-black text-[10px] font-bold rounded-full h-5 min-w-5 flex items-center justify-center px-1">
              {unread}
            </span>
          )}
        </Link>

        {/* User */}
        {user && (
          <div className="flex items-center gap-2.5 px-2.5">
            <div className="h-7 w-7 rounded-full bg-zinc-700 flex items-center justify-center text-xs font-medium text-white shrink-0">
              {user.full_name?.[0]?.toUpperCase() || user.email[0].toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-zinc-200 truncate">
                {user.full_name || user.email}
              </p>
              <p className="text-[10px] text-zinc-500 capitalize">{user.role}</p>
            </div>
            <button
              onClick={handleLogout}
              className="text-zinc-600 hover:text-red-400 transition-colors"
              title={t("nav.logout", locale)}
            >
              <LogOut size={14} />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
