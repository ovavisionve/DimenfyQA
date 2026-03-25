"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Target, Gauge, Flame, ShieldCheck, MessageCircle, Inbox } from "lucide-react";

interface SystemSettings {
  scoring: Record<string, number>;
  sending: Record<string, unknown>;
  warmup: Record<string, number>;
  safety: Record<string, unknown>;
  inbox: Record<string, unknown>;
  comments: Record<string, unknown>;
}

const ICONS: Record<string, React.ElementType> = {
  scoring: Target,
  sending: Gauge,
  warmup: Flame,
  safety: ShieldCheck,
  inbox: Inbox,
  comments: MessageCircle,
};

const LABELS: Record<string, string> = {
  scoring: "Scoring",
  sending: "Envío de DMs",
  warmup: "Warm-up",
  safety: "Seguridad",
  inbox: "Inbox & Follow-up",
  comments: "Comentarios",
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<SystemSettings | null>(null);

  useEffect(() => {
    api<SystemSettings>("/api/v1/system/settings")
      .then(setSettings)
      .catch(() => {});
  }, []);

  if (!settings) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-amber-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-900">Configuración</h1>
        <p className="text-sm text-zinc-500">
          Configuración del sistema (solo lectura)
        </p>
      </div>

      {/* Safety Banner */}
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 flex items-center gap-3">
        <ShieldCheck size={20} className="text-emerald-600 shrink-0" />
        <div>
          <p className="text-sm font-medium text-emerald-800">
            Protección de Cuentas Privadas — SIEMPRE ACTIVA
          </p>
          <p className="text-xs text-emerald-600">
            Las cuentas privadas se filtran en scraping, scoring y pre-envío.
            No se puede desactivar.
          </p>
        </div>
      </div>

      {/* Settings Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.entries(settings).map(([key, values]) => {
          const Icon = ICONS[key] || Target;
          const label = LABELS[key] || key;

          return (
            <div
              key={key}
              className="rounded-lg border border-zinc-200 bg-white p-5"
            >
              <div className="flex items-center gap-2 mb-4">
                <Icon size={18} className="text-amber-600" />
                <h3 className="text-sm font-semibold text-zinc-900">{label}</h3>
              </div>
              <div className="space-y-2">
                {Object.entries(values as Record<string, unknown>).map(
                  ([k, v]) => (
                    <div
                      key={k}
                      className="flex items-center justify-between py-1.5 border-b border-zinc-50 last:border-0"
                    >
                      <span className="text-xs text-zinc-500">
                        {k.replace(/_/g, " ")}
                      </span>
                      <span className="text-xs font-medium text-zinc-900">
                        {typeof v === "boolean" ? (v ? "Sí" : "No") : String(v)}
                      </span>
                    </div>
                  )
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
