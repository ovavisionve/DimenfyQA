"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Search, Copy, Check, Send, ClipboardList, Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

interface Lead {
  id: string;
  ig_username: string;
  ig_full_name: string;
  score: number | null;
  category: string | null;
  dm_message: string | null;
  dm_variant_b: string | null;
  status: string;
  delivery_status: string | null;
  campaign_id: string;
}

const DELIVERY_COLORS: Record<string, string> = {
  dm_ready: "bg-amber-100 text-amber-700",
  sent: "bg-emerald-100 text-emerald-700",
  delivered: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
  skipped_private: "bg-zinc-100 text-zinc-500",
  user_not_found: "bg-zinc-100 text-zinc-500",
  retry: "bg-amber-100 text-amber-700",
};

export default function DMsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [sendingId, setSendingId] = useState<string | null>(null);

  useEffect(() => {
    api<Lead[]>("/api/v1/leads/?has_dm=true&limit=500")
      .then(setLeads)
      .catch(() => {
        // Fallback to dm_ready filter
        api<Lead[]>("/api/v1/leads/?status=dm_ready&limit=500")
          .then(setLeads)
          .catch(() => {});
      });
  }, []);

  const copy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const copyAll = () => {
    const allDMs = filtered
      .map((l) => `@${l.ig_username}:\n${l.dm_message}`)
      .join("\n\n---\n\n");
    navigator.clipboard.writeText(allDMs);
    setCopiedId("all");
    setTimeout(() => setCopiedId(null), 2000);
  };

  const sendDM = async (lead: Lead) => {
    setSendingId(lead.id);
    try {
      await api(`/api/v1/campaigns/${lead.campaign_id}/send-dm/${lead.id}`, {
        method: "POST",
      });
      setLeads((prev) =>
        prev.map((l) =>
          l.id === lead.id ? { ...l, status: "sent", delivery_status: "sent" } : l
        )
      );
    } catch {
      /* ignore */
    }
    setSendingId(null);
  };

  // Get unique categories
  const categories = [...new Set(leads.map((l) => l.category).filter(Boolean))] as string[];

  const filtered = leads.filter((l) => {
    if (!l.dm_message) return false;
    const matchesSearch =
      l.ig_username?.toLowerCase().includes(search.toLowerCase()) ||
      l.ig_full_name?.toLowerCase().includes(search.toLowerCase()) ||
      l.dm_message?.toLowerCase().includes(search.toLowerCase());
    const matchesCategory = !categoryFilter || l.category === categoryFilter;
    return matchesSearch && matchesCategory;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">DMs Generados</h1>
          <p className="text-sm text-zinc-500">
            {filtered.length} DMs listos para enviar
          </p>
        </div>
        <button
          onClick={copyAll}
          disabled={filtered.length === 0}
          className="flex items-center gap-1.5 rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
        >
          {copiedId === "all" ? (
            <Check size={14} className="text-emerald-500" />
          ) : (
            <ClipboardList size={14} />
          )}
          {copiedId === "all" ? "Copiados!" : "Copiar Todos"}
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1 max-w-md">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            placeholder="Buscar por username, nombre o contenido del DM..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-zinc-200 bg-white pl-9 pr-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
          />
        </div>
        {categories.length > 0 && (
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="rounded-lg border border-zinc-200 px-3 py-2 text-sm"
          >
            <option value="">Todas las categorías</option>
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.slice(0, 60).map((lead) => (
          <div
            key={lead.id}
            className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-zinc-900">
                  @{lead.ig_username}
                </p>
                <p className="text-xs text-zinc-500">{lead.ig_full_name}</p>
              </div>
              <div className="flex items-center gap-2">
                {/* Status pill */}
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-medium",
                    DELIVERY_COLORS[lead.delivery_status || lead.status] || "bg-zinc-100 text-zinc-600"
                  )}
                >
                  {lead.delivery_status || lead.status}
                </span>
                {lead.score !== null && (
                  <span
                    className={cn(
                      "rounded-full h-8 w-8 flex items-center justify-center text-xs font-bold",
                      lead.score >= 70
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-amber-100 text-amber-700"
                    )}
                  >
                    {lead.score}
                  </span>
                )}
              </div>
            </div>

            {/* Variant A */}
            <div className="relative group">
              <p className="text-xs font-medium text-zinc-500 mb-1">Variante A</p>
              <div className="rounded-md bg-zinc-50 p-3 text-sm text-zinc-700 leading-relaxed">
                {lead.dm_message}
              </div>
              <button
                onClick={() => copy(lead.dm_message!, `a-${lead.id}`)}
                className="absolute top-7 right-2 p-1 rounded bg-white border border-zinc-200 opacity-0 group-hover:opacity-100 transition-opacity"
              >
                {copiedId === `a-${lead.id}` ? (
                  <Check size={12} className="text-emerald-500" />
                ) : (
                  <Copy size={12} className="text-zinc-400" />
                )}
              </button>
            </div>

            {/* Variant B */}
            {lead.dm_variant_b && (
              <div className="relative group">
                <p className="text-xs font-medium text-zinc-500 mb-1">Variante B</p>
                <div className="rounded-md bg-zinc-50 p-3 text-sm text-zinc-600 leading-relaxed">
                  {lead.dm_variant_b}
                </div>
                <button
                  onClick={() => copy(lead.dm_variant_b!, `b-${lead.id}`)}
                  className="absolute top-7 right-2 p-1 rounded bg-white border border-zinc-200 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  {copiedId === `b-${lead.id}` ? (
                    <Check size={12} className="text-emerald-500" />
                  ) : (
                    <Copy size={12} className="text-zinc-400" />
                  )}
                </button>
              </div>
            )}

            <div className="flex items-center justify-between">
              {lead.category && (
                <span className="inline-block rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-600">
                  {lead.category}
                </span>
              )}
              {/* Send button */}
              {lead.status !== "sent" && lead.delivery_status !== "sent" && (
                <button
                  onClick={() => sendDM(lead)}
                  disabled={sendingId === lead.id}
                  className="ml-auto flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                >
                  {sendingId === lead.id ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Send size={12} />
                  )}
                  Enviar DM
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-16 text-zinc-400">
          <ClipboardList size={40} className="mx-auto mb-3 opacity-40" />
          <p>No hay DMs generados.</p>
        </div>
      )}
    </div>
  );
}
