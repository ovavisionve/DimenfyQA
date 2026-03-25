"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { wsUrl } from "@/lib/api";
import { Terminal, Trash2 } from "lucide-react";
import { cn } from "@/lib/cn";

interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: "text-zinc-500",
  INFO: "text-blue-400",
  WARNING: "text-amber-400",
  ERROR: "text-red-400",
};

const LEVEL_FILTERS = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR"] as const;

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState<string>("ALL");
  const [search, setSearch] = useState("");
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    const ws = new WebSocket(wsUrl("/ws/logs"));
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      setTimeout(connect, 3000);
    };
    ws.onmessage = (e) => {
      try {
        const entry: LogEntry = JSON.parse(e.data);
        setLogs((prev) => [...prev.slice(-999), entry]);
      } catch {
        /* ignore */
      }
    };
  }, []);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, [connect]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const filtered = logs.filter((l) => {
    if (filter !== "ALL" && l.level !== filter) return false;
    if (search && !l.message.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-zinc-900">Live Logs</h1>
          <span
            className={cn(
              "flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
              connected
                ? "bg-emerald-100 text-emerald-700"
                : "bg-red-100 text-red-700"
            )}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                connected ? "bg-emerald-500" : "bg-red-500"
              )}
            />
            {connected ? "Conectado" : "Desconectado"}
          </span>
        </div>
        <button
          onClick={() => setLogs([])}
          className="flex items-center gap-1.5 rounded-lg border border-zinc-200 px-3 py-1.5 text-xs text-zinc-500 hover:bg-zinc-50"
        >
          <Trash2 size={12} /> Limpiar
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2">
        {LEVEL_FILTERS.map((lvl) => (
          <button
            key={lvl}
            onClick={() => setFilter(lvl)}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              filter === lvl
                ? "bg-zinc-900 text-white"
                : "bg-zinc-100 text-zinc-500 hover:bg-zinc-200"
            )}
          >
            {lvl}
          </button>
        ))}
        <input
          placeholder="Filtrar..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="ml-2 rounded-md border border-zinc-200 px-2.5 py-1 text-xs w-48 focus:border-amber-500 focus:outline-none"
        />
      </div>

      {/* Terminal */}
      <div className="rounded-lg bg-zinc-950 border border-zinc-800 overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-zinc-800">
          <Terminal size={14} className="text-zinc-500" />
          <span className="text-xs text-zinc-500">
            {filtered.length} entries
          </span>
        </div>
        <div className="h-[calc(100vh-300px)] overflow-y-auto p-4 font-mono text-xs leading-6">
          {filtered.map((log, i) => (
            <div key={i} className="flex gap-3 hover:bg-zinc-900/50 px-1 -mx-1 rounded">
              <span className="text-zinc-600 shrink-0 w-20">
                {log.timestamp?.split(" ")[1] || ""}
              </span>
              <span
                className={cn(
                  "shrink-0 w-16 font-semibold",
                  LEVEL_COLORS[log.level] || "text-zinc-500"
                )}
              >
                {log.level}
              </span>
              <span className="text-zinc-400">{log.message}</span>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}
