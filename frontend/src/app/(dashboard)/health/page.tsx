"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { HeartPulse, Database, Radio, Cpu, Camera, RefreshCw, Shield, Clock, Zap } from "lucide-react";
import { cn } from "@/lib/cn";

interface HealthData {
  db: string;
  redis: string;
  celery: string;
}

interface IGAccount {
  username: string;
  proxy: string;
  logged_in: boolean;
  is_blocked: boolean;
  in_cooldown: boolean;
  cooldown_reason: string | null;
  hourly_sends_remaining: number;
  daily_limit: number;
  warmup_percent: number;
  total_sent: number;
  total_failed: number;
  challenges: number;
  challenges_today: number;
  created_at: string | null;
}

interface IGAccountsResponse {
  account_count: number;
  accounts: IGAccount[];
  rotation_index: number;
  global_daily_limit: number;
  global_hourly_limit: number;
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
  const [igData, setIgData] = useState<IGAccountsResponse | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [h, ig, au] = await Promise.all([
        api<HealthData>("/api/v1/system/health"),
        api<IGAccountsResponse>("/api/v1/system/ig-accounts").catch(() => null),
        api<AuditEntry[]>("/api/v1/system/audit-log?limit=50").catch(() => []),
      ]);
      setHealth(h);
      setIgData(ig);
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
        { label: "Database", value: health.db, icon: Database },
        { label: "Redis", value: health.redis, icon: Radio },
        { label: "Celery", value: health.celery, icon: Cpu },
      ]
    : [];

  const accounts = igData?.accounts || [];

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

      {/* IG Accounts — Full Detail */}
      {accounts.length > 0 && (
        <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-100">
            <div className="flex items-center gap-2">
              <Camera size={16} className="text-zinc-500" />
              <h3 className="text-sm font-semibold text-zinc-900">
                Cuentas de Instagram ({igData?.account_count})
              </h3>
            </div>
            {igData && (
              <div className="flex items-center gap-3 text-xs text-zinc-500">
                <span>Límite global: {igData.global_daily_limit}/día, {igData.global_hourly_limit}/hora</span>
              </div>
            )}
          </div>

          <div className="divide-y divide-zinc-100">
            {accounts.map((acc, i) => (
              <div key={acc.username} className="px-5 py-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-sm font-medium text-zinc-900">@{acc.username}</span>
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs font-medium",
                        acc.is_blocked
                          ? "bg-red-100 text-red-700"
                          : acc.in_cooldown
                          ? "bg-amber-100 text-amber-700"
                          : acc.logged_in
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-zinc-100 text-zinc-500"
                      )}
                    >
                      {acc.is_blocked
                        ? "Bloqueado"
                        : acc.in_cooldown
                        ? "Cooldown"
                        : acc.logged_in
                        ? "Activo"
                        : "Offline"}
                    </span>
                    {igData?.rotation_index === i && (
                      <span className="rounded-full bg-blue-100 text-blue-700 px-2 py-0.5 text-xs font-medium">
                        Activa
                      </span>
                    )}
                  </div>
                  {acc.proxy && (
                    <span className="text-xs text-zinc-400 font-mono">{acc.proxy}</span>
                  )}
                </div>

                {acc.in_cooldown && acc.cooldown_reason && (
                  <div className="mb-3 rounded-md bg-amber-50 border border-amber-200 px-3 py-1.5 text-xs text-amber-700 flex items-center gap-1.5">
                    <Clock size={12} />
                    {acc.cooldown_reason}
                  </div>
                )}

                <div className="grid grid-cols-5 gap-4 text-center">
                  <div>
                    <p className="text-lg font-semibold text-zinc-900">{acc.total_sent}</p>
                    <p className="text-xs text-zinc-500">Enviados</p>
                  </div>
                  <div>
                    <p className="text-lg font-semibold text-red-600">{acc.total_failed}</p>
                    <p className="text-xs text-zinc-500">Fallidos</p>
                  </div>
                  <div>
                    <p className="text-lg font-semibold text-zinc-900">{acc.hourly_sends_remaining}</p>
                    <p className="text-xs text-zinc-500">Restantes/hora</p>
                  </div>
                  <div>
                    <p className="text-lg font-semibold text-zinc-900">{acc.daily_limit}</p>
                    <p className="text-xs text-zinc-500">Límite/día</p>
                  </div>
                  <div>
                    <p className="text-lg font-semibold text-amber-600">{acc.challenges_today}</p>
                    <p className="text-xs text-zinc-500">Challenges hoy</p>
                  </div>
                </div>

                {/* Warm-up progress bar */}
                <div className="mt-3">
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-zinc-500 flex items-center gap-1">
                      <Zap size={11} /> Warm-up
                    </span>
                    <span className={cn(
                      "font-medium",
                      acc.warmup_percent >= 100 ? "text-emerald-600" : "text-amber-600"
                    )}>
                      {acc.warmup_percent}%
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-zinc-100 overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        acc.warmup_percent >= 100 ? "bg-emerald-500" : "bg-amber-400"
                      )}
                      style={{ width: `${Math.min(acc.warmup_percent, 100)}%` }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {accounts.length === 0 && !loading && (
        <div className="rounded-lg border border-zinc-200 bg-white p-8 text-center text-zinc-400">
          <Camera size={32} className="mx-auto mb-2 opacity-40" />
          <p className="text-sm">No hay cuentas de Instagram configuradas.</p>
          <p className="text-xs mt-1">Configura IG_USERNAME/IG_ACCOUNTS en el .env del backend.</p>
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
