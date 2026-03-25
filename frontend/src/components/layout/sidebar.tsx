"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Workflow,
  Send,
  MessageSquare,
  Users,
  SlidersHorizontal,
  Terminal,
  HeartPulse,
  Bell,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { getUser, clearAuth } from "@/lib/auth";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const NAV_ITEMS = [
  { label: "Pipeline", href: "/pipeline", icon: Workflow, group: "Pipeline" },
  { label: "DMs", href: "/dms", icon: Send, group: "Pipeline" },
  { label: "Comentarios", href: "/comments", icon: MessageSquare, group: "Pipeline" },
  { label: "Clientes", href: "/clients", icon: Users, group: "Gestión" },
  { label: "Configuración", href: "/settings", icon: SlidersHorizontal, group: "Gestión" },
  { label: "Live Logs", href: "/logs", icon: Terminal, group: "Monitoreo" },
  { label: "System Health", href: "/health", icon: HeartPulse, group: "Monitoreo" },
];

export function Sidebar() {
  const pathname = usePathname();
  const user = getUser();
  const [unread, setUnread] = useState(0);

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
          const showGroup = item.group !== currentGroup;
          currentGroup = item.group;
          const active = pathname === item.href;
          const Icon = item.icon;

          return (
            <div key={item.href}>
              {showGroup && (
                <p className="text-[10px] uppercase tracking-widest text-zinc-600 font-medium mt-4 mb-1.5 px-2">
                  {item.group}
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
                {item.label}
              </Link>
            </div>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-zinc-800 p-3 space-y-2">
        {/* Notifications */}
        <Link
          href="#"
          className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
        >
          <Bell size={16} strokeWidth={1.8} />
          Notificaciones
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
              title="Cerrar sesión"
            >
              <LogOut size={14} />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
