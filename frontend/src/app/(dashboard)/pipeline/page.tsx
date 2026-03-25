"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import {
  Play,
  Send,
  Pause,
  RefreshCw,
  Plus,
  Search,
  ChevronDown,
} from "lucide-react";
import { cn } from "@/lib/cn";

interface Campaign {
  id: string;
  name: string;
  status: string;
  client_id: string;
  source_type: string;
  source_value: string;
  max_leads: number;
  stats: Record<string, unknown>;
  created_at: string;
}

interface Lead {
  id: string;
  ig_username: string;
  ig_full_name: string;
  status: string;
  score: number | null;
  category: string | null;
  dm_message: string | null;
  dm_variant_b: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-zinc-200 text-zinc-700",
  scraping: "bg-blue-100 text-blue-700",
  scoring: "bg-violet-100 text-violet-700",
  researching: "bg-indigo-100 text-indigo-700",
  writing: "bg-amber-100 text-amber-700",
  ready: "bg-emerald-100 text-emerald-700",
  sending: "bg-orange-100 text-orange-700",
  completed: "bg-green-100 text-green-700",
  paused: "bg-yellow-100 text-yellow-700",
  failed: "bg-red-100 text-red-700",
};

export default function PipelinePage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selected, setSelected] = useState<Campaign | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [tab, setTab] = useState<"stats" | "leads" | "dms">("stats");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  // New campaign form
  const [showNew, setShowNew] = useState(false);
  const [clients, setClients] = useState<Array<{ id: string; name: string }>>([]);
  const [newCampaign, setNewCampaign] = useState({
    name: "",
    client_id: "",
    source_type: "comments",
    source_value: "",
    max_leads: 50,
  });

  const loadCampaigns = useCallback(async () => {
    try {
      const data = await api<Campaign[]>("/api/v1/campaigns/");
      setCampaigns(data);
      if (data.length && !selected) setSelected(data[0]);
    } catch {
      /* ignore */
    }
  }, [selected]);

  const loadLeads = useCallback(async () => {
    if (!selected) return;
    try {
      const data = await api<Lead[]>(
        `/api/v1/campaigns/${selected.id}/leads?limit=500`
      );
      setLeads(data);
    } catch {
      /* ignore */
    }
  }, [selected]);

  useEffect(() => {
    setLoading(true);
    loadCampaigns().finally(() => setLoading(false));
    api<Array<{ id: string; name: string }>>("/api/v1/clients/")
      .then(setClients)
      .catch(() => {});
  }, [loadCampaigns]);

  useEffect(() => {
    loadLeads();
  }, [loadLeads]);

  // Poll campaign status when active
  useEffect(() => {
    if (
      !selected ||
      ["draft", "ready", "completed", "failed"].includes(selected.status)
    )
      return;
    const id = setInterval(async () => {
      const c = await api<Campaign>(`/api/v1/campaigns/${selected.id}`);
      setSelected(c);
      if (["ready", "completed", "failed", "paused"].includes(c.status)) {
        loadLeads();
      }
    }, 3000);
    return () => clearInterval(id);
  }, [selected, loadLeads]);

  const startPipeline = async () => {
    if (!selected) return;
    await api(`/api/v1/campaigns/${selected.id}/start`, { method: "POST" });
    const c = await api<Campaign>(`/api/v1/campaigns/${selected.id}`);
    setSelected(c);
  };

  const sendDMs = async () => {
    if (!selected) return;
    await api(`/api/v1/campaigns/${selected.id}/send-dms`, { method: "POST" });
    const c = await api<Campaign>(`/api/v1/campaigns/${selected.id}`);
    setSelected(c);
  };

  const createCampaign = async (e: React.FormEvent) => {
    e.preventDefault();
    const data = await api<Campaign>("/api/v1/campaigns/", {
      method: "POST",
      body: JSON.stringify(newCampaign),
    });
    setCampaigns((prev) => [data, ...prev]);
    setSelected(data);
    setShowNew(false);
    setNewCampaign({ name: "", client_id: "", source_type: "comments", source_value: "", max_leads: 50 });
  };

  // Stats
  const stats = selected?.stats || {};
  const progress = (stats as Record<string, Record<string, unknown>>).progress || {};
  const statItems = [
    { label: "Scraped", value: leads.filter((l) => l.status !== "new").length },
    { label: "Scored", value: leads.filter((l) => l.score !== null).length },
    { label: "DM Ready", value: leads.filter((l) => l.status === "dm_ready").length },
    { label: "Sent", value: leads.filter((l) => l.status === "sent").length },
    { label: "Replied", value: leads.filter((l) => l.status === "replied").length },
    { label: "Failed", value: leads.filter((l) => l.status === "failed").length },
  ];

  const filteredLeads = leads.filter(
    (l) =>
      l.ig_username?.toLowerCase().includes(search.toLowerCase()) ||
      l.ig_full_name?.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-amber-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Pipeline</h1>
          <p className="text-sm text-zinc-500">
            Campañas de DM automatizadas
          </p>
        </div>
        <button
          onClick={() => setShowNew(true)}
          className="flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-800 transition-colors"
        >
          <Plus size={16} />
          Nueva Campaña
        </button>
      </div>

      {/* New Campaign Modal */}
      {showNew && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <form
            onSubmit={createCampaign}
            className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl space-y-4"
          >
            <h2 className="text-lg font-semibold">Nueva Campaña</h2>
            <input
              placeholder="Nombre de la campaña"
              value={newCampaign.name}
              onChange={(e) => setNewCampaign({ ...newCampaign, name: e.target.value })}
              required
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
            <select
              value={newCampaign.client_id}
              onChange={(e) => setNewCampaign({ ...newCampaign, client_id: e.target.value })}
              required
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
            >
              <option value="">Seleccionar cliente...</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            <select
              value={newCampaign.source_type}
              onChange={(e) => setNewCampaign({ ...newCampaign, source_type: e.target.value })}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
            >
              <option value="comments">Comentarios</option>
              <option value="followers">Seguidores</option>
              <option value="hashtag">Hashtag</option>
            </select>
            <input
              placeholder="URL del post o hashtag"
              value={newCampaign.source_value}
              onChange={(e) => setNewCampaign({ ...newCampaign, source_value: e.target.value })}
              required
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
            />
            <input
              type="number"
              placeholder="Max leads"
              value={newCampaign.max_leads}
              onChange={(e) => setNewCampaign({ ...newCampaign, max_leads: parseInt(e.target.value) || 50 })}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
            />
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => setShowNew(false)}
                className="rounded-lg border border-zinc-200 px-4 py-2 text-sm hover:bg-zinc-50"
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-black hover:bg-amber-400"
              >
                Crear
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Campaign Selector */}
      <div className="flex items-center gap-3">
        <div className="relative">
          <select
            value={selected?.id || ""}
            onChange={(e) => {
              const c = campaigns.find((c) => c.id === e.target.value);
              setSelected(c || null);
            }}
            className="appearance-none rounded-lg border border-zinc-200 bg-white pl-3 pr-8 py-2 text-sm font-medium focus:border-amber-500 focus:outline-none min-w-[250px]"
          >
            {campaigns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <ChevronDown
            size={14}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none"
          />
        </div>

        {selected && (
          <span
            className={cn(
              "rounded-full px-2.5 py-0.5 text-xs font-medium",
              STATUS_COLORS[selected.status] || "bg-zinc-200 text-zinc-700"
            )}
          >
            {selected.status}
          </span>
        )}

        <div className="ml-auto flex gap-2">
          {selected?.status === "draft" && (
            <button
              onClick={startPipeline}
              className="flex items-center gap-1.5 rounded-lg bg-amber-500 px-3 py-2 text-sm font-medium text-black hover:bg-amber-400"
            >
              <Play size={14} /> Start Pipeline
            </button>
          )}
          {selected?.status === "ready" && (
            <button
              onClick={sendDMs}
              className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500"
            >
              <Send size={14} /> Send DMs
            </button>
          )}
          <button
            onClick={() => {
              loadCampaigns();
              loadLeads();
            }}
            className="rounded-lg border border-zinc-200 p-2 text-zinc-500 hover:bg-zinc-50"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* Progress indicator */}
      {selected && !["draft", "ready", "completed", "failed"].includes(selected.status) && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
          <div className="flex items-center gap-2 text-sm text-amber-800">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-amber-300 border-t-amber-600" />
            <span className="font-medium capitalize">{selected.status}...</span>
            <span className="text-amber-600">
              {(progress as Record<string, unknown>).message as string || "Procesando"}
            </span>
          </div>
        </div>
      )}

      {/* Stats Row */}
      {selected && (
        <div className="grid grid-cols-6 gap-3">
          {statItems.map((s) => (
            <div
              key={s.label}
              className="rounded-lg border border-zinc-200 bg-white p-3 text-center"
            >
              <p className="text-2xl font-semibold text-zinc-900">{s.value}</p>
              <p className="text-xs text-zinc-500 mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      {selected && (
        <div className="flex border-b border-zinc-200">
          {(["stats", "leads", "dms"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
                tab === t
                  ? "border-amber-500 text-zinc-900"
                  : "border-transparent text-zinc-500 hover:text-zinc-700"
              )}
            >
              {t === "stats" ? "Resumen" : t === "leads" ? "Leads" : "DMs"}
            </button>
          ))}
        </div>
      )}

      {/* Tab Content */}
      {selected && tab === "leads" && (
        <div className="space-y-3">
          <div className="relative">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400"
            />
            <input
              placeholder="Buscar por username o nombre..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border border-zinc-200 bg-white pl-9 pr-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
            />
          </div>

          <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-100 bg-zinc-50">
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-600">
                    Username
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-600">
                    Nombre
                  </th>
                  <th className="px-4 py-2.5 text-center font-medium text-zinc-600">
                    Score
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-600">
                    Categoría
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-600">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredLeads.slice(0, 100).map((lead) => (
                  <tr
                    key={lead.id}
                    className="border-b border-zinc-50 hover:bg-zinc-50"
                  >
                    <td className="px-4 py-2.5 font-mono text-xs">
                      @{lead.ig_username}
                    </td>
                    <td className="px-4 py-2.5 text-zinc-700">
                      {lead.ig_full_name || "—"}
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      {lead.score !== null ? (
                        <span
                          className={cn(
                            "inline-flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold",
                            lead.score >= 70
                              ? "bg-emerald-100 text-emerald-700"
                              : lead.score >= 40
                              ? "bg-amber-100 text-amber-700"
                              : "bg-zinc-100 text-zinc-500"
                          )}
                        >
                          {lead.score}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-zinc-500">
                      {lead.category || "—"}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-xs font-medium",
                          STATUS_COLORS[lead.status] || "bg-zinc-100 text-zinc-600"
                        )}
                      >
                        {lead.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filteredLeads.length > 100 && (
              <p className="px-4 py-2 text-xs text-zinc-400 border-t border-zinc-100">
                Mostrando 100 de {filteredLeads.length} leads
              </p>
            )}
          </div>
        </div>
      )}

      {/* DMs Tab */}
      {selected && tab === "dms" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {leads
            .filter((l) => l.dm_message)
            .slice(0, 50)
            .map((lead) => (
              <div
                key={lead.id}
                className="rounded-lg border border-zinc-200 bg-white p-4 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-zinc-900">
                    @{lead.ig_username}
                  </span>
                  {lead.score !== null && (
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs font-bold",
                        lead.score >= 70
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-amber-100 text-amber-700"
                      )}
                    >
                      {lead.score}
                    </span>
                  )}
                </div>
                <div className="rounded-md bg-zinc-50 p-3 text-sm text-zinc-700 leading-relaxed">
                  {lead.dm_message}
                </div>
                {lead.dm_variant_b && (
                  <details className="text-xs">
                    <summary className="cursor-pointer text-zinc-500 hover:text-zinc-700">
                      Variante B
                    </summary>
                    <div className="mt-1 rounded-md bg-zinc-50 p-3 text-sm text-zinc-600">
                      {lead.dm_variant_b}
                    </div>
                  </details>
                )}
              </div>
            ))}
        </div>
      )}

      {/* Stats Tab */}
      {selected && tab === "stats" && (
        <div className="rounded-lg border border-zinc-200 bg-white p-6">
          <h3 className="text-sm font-semibold text-zinc-900 mb-4">
            Resumen de Campaña
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-zinc-500">Fuente:</span>{" "}
              <span className="font-medium">{selected.source_type}</span>
            </div>
            <div>
              <span className="text-zinc-500">URL/Valor:</span>{" "}
              <span className="font-medium text-xs break-all">
                {selected.source_value}
              </span>
            </div>
            <div>
              <span className="text-zinc-500">Max Leads:</span>{" "}
              <span className="font-medium">{selected.max_leads}</span>
            </div>
            <div>
              <span className="text-zinc-500">Creada:</span>{" "}
              <span className="font-medium">
                {new Date(selected.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
