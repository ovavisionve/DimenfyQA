"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { HeartPulse, Database, Radio, Cpu, Camera, RefreshCw } from "lucide-react";
import { cn } from "@/lib/cn";

interface HealthData {
  database: string;
  redis: string;
  celery: string;
}

interface AccountHealth {
  username: string;
  logged_in: boolean;
  is_blocked: boolean;
  daily_sent: number;
  daily_failed: number;
  challenges_today: number;
  daily_limit: number;
}

interface AuditEntry {
  user_email: string;
  action: string;
  resource_type: string;
  details: Record<string, unknown>;
  created_at: string;
}

export default function HealthPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [accounts, setAccounts] = useState<AccountHealth[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [h, a, au] = await Promise.all([
        api<HealthData>("/api/v1/system/health"),
        api<AccountHealth[]>("/api/v1/system/ig-health").catch(() => []),
        api<AuditEntry[]>("/api/v1/system/audit-log?limit=50").catch(() => []),
      ]);
      setHealth(h);
      setAccounts(a);
      setAudit(au);
    } catch {
      /* ignore */
    }
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const healthItems = health
    ? [
        { label: "Database", value: health.database, icon: Database },
        { label: "Redis", value: health.redis, icon: Radio },
        { label: "Celery", value: health.celery, icon: Cpu },
      ]
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">System Health</h1>
          <p className="text-sm text-zinc-500">Estado de la infraestructura</p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-50"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Refrescar
        </button>
      </div>

      {/* Service Health Cards */}
      <div className="grid grid-cols-3 gap-4">
        {healthItems.map((item) => {
          const ok = item.value === "connected" || item.value?.includes("connected");
          const Icon = item.icon;
          return (
            <div
              key={item.label}
              className={cn(
                "rounded-lg border p-5",
                ok
                  ? "border-emerald-200 bg-emerald-50"
                  : "border-red-200 bg-red-50"
              )}
            >
              <div className="flex items-center gap-2 mb-2">
                <Icon
                  size={18}
                  className={ok ? "text-emerald-600" : "text-red-600"}
                />
                <h3 className="text-sm font-semibold text-zinc-900">
                  {item.label}
                </h3>
              </div>
              <p
                className={cn(
                  "text-sm font-medium",
                  ok ? "text-emerald-700" : "text-red-700"
                )}
              >
                {item.value}
              </p>
            </div>
          );
        })}
      </div>

      {/* IG Account Health */}
      {accounts.length > 0 && (
        <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
          <div className="flex items-center gap-2 px-5 py-3 border-b border-zinc-100">
            <Camera size={16} className="text-zinc-500" />
            <h3 className="text-sm font-semibold text-zinc-900">
              Cuentas de Instagram
            </h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50">
                <th className="px-5 py-2.5 text-left font-medium text-zinc-600">
                  Username
                </th>
                <th className="px-5 py-2.5 text-center font-medium text-zinc-600">
                  Estado
                </th>
                <th className="px-5 py-2.5 text-center font-medium text-zinc-600">
                  Enviados
                </th>
                <th className="px-5 py-2.5 text-center font-medium text-zinc-600">
                  Fallidos
                </th>
                <th className="px-5 py-2.5 text-center font-medium text-zinc-600">
                  Challenges
                </th>
                <th className="px-5 py-2.5 text-center font-medium text-zinc-600">
                  Límite
                </th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((acc) => (
                <tr key={acc.username} className="border-b border-zinc-50">
                  <td className="px-5 py-2.5 font-mono text-xs">
                    @{acc.username}
                  </td>
                  <td className="px-5 py-2.5 text-center">
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs font-medium",
                        acc.is_blocked
                          ? "bg-red-100 text-red-700"
                          : acc.logged_in
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-amber-100 text-amber-700"
                      )}
                    >
                      {acc.is_blocked
                        ? "Bloqueado"
                        : acc.logged_in
                        ? "Activo"
                        : "Offline"}
                    </span>
                  </td>
                  <td className="px-5 py-2.5 text-center">{acc.daily_sent}</td>
                  <td className="px-5 py-2.5 text-center text-red-600">
                    {acc.daily_failed}
                  </td>
                  <td className="px-5 py-2.5 text-center">{acc.challenges_today}</td>
                  <td className="px-5 py-2.5 text-center">{acc.daily_limit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Audit Log */}
      <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-zinc-100">
          <HeartPulse size={16} className="text-zinc-500" />
          <h3 className="text-sm font-semibold text-zinc-900">Audit Log</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50">
                <th className="px-5 py-2.5 text-left font-medium text-zinc-600">
                  Fecha
                </th>
                <th className="px-5 py-2.5 text-left font-medium text-zinc-600">
                  Usuario
                </th>
                <th className="px-5 py-2.5 text-left font-medium text-zinc-600">
                  Acción
                </th>
                <th className="px-5 py-2.5 text-left font-medium text-zinc-600">
                  Recurso
                </th>
                <th className="px-5 py-2.5 text-left font-medium text-zinc-600">
                  Detalles
                </th>
              </tr>
            </thead>
            <tbody>
              {audit.map((entry, i) => (
                <tr key={i} className="border-b border-zinc-50">
                  <td className="px-5 py-2.5 text-xs text-zinc-500">
                    {entry.created_at
                      ? new Date(entry.created_at).toLocaleString()
                      : "—"}
                  </td>
                  <td className="px-5 py-2.5 text-xs">{entry.user_email || "—"}</td>
                  <td className="px-5 py-2.5 text-xs font-mono">
                    {entry.action}
                  </td>
                  <td className="px-5 py-2.5 text-xs text-zinc-500">
                    {entry.resource_type || "—"}
                  </td>
                  <td className="px-5 py-2.5 text-xs text-zinc-500 max-w-[300px]">
                    {entry.details && Object.keys(entry.details).length > 0 ? (
                      <pre className="whitespace-pre-wrap break-all text-[11px] text-zinc-400 font-mono">
                        {JSON.stringify(entry.details, null, 1)}
                      </pre>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {audit.length === 0 && (
          <p className="text-center py-8 text-sm text-zinc-400">
            No hay entradas de audit log.
          </p>
        )}
      </div>
    </div>
  );
}
