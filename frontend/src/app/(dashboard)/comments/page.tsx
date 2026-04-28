"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { MessageSquare, Send, Loader2, Search, Copy, Check } from "lucide-react";
import { cn } from "@/lib/cn";

interface Lead {
  id: string;
  ig_username: string;
  ig_full_name: string;
  score: number | null;
  comment_message: string | null;
  comment_variant_b: string | null;
  comment_status: string | null;
  commented_post_shortcode: string | null;
  campaign_id: string;
}

export default function CommentsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [campaigns, setCampaigns] = useState<Array<{ id: string; name: string }>>([]);
  const [selectedCampaign, setSelectedCampaign] = useState("");
  const [generating, setGenerating] = useState(false);
  const [bulkSending, setBulkSending] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [showVariantB, setShowVariantB] = useState<Set<string>>(new Set());
  const [sendingId, setSendingId] = useState<string | null>(null);

  useEffect(() => {
    api<Array<{ id: string; name: string }>>("/api/v1/campaigns/")
      .then((c) => {
        setCampaigns(c);
        if (c.length) setSelectedCampaign(c[0].id);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedCampaign) return;
    api<Lead[]>(`/api/v1/leads/?campaign_id=${selectedCampaign}&limit=500`)
      .then(setLeads)
      .catch(() => {});
  }, [selectedCampaign]);

  const generate = async () => {
    if (!selectedCampaign) return;
    setGenerating(true);
    try {
      await api(`/api/v1/campaigns/${selectedCampaign}/generate-comments`, {
        method: "POST",
      });
      const poll = setInterval(async () => {
        const data = await api<Lead[]>(
          `/api/v1/leads/?campaign_id=${selectedCampaign}&limit=500`
        );
        setLeads(data);
        if (data.some((l) => l.comment_message)) {
          clearInterval(poll);
          setGenerating(false);
        }
      }, 3000);
      setTimeout(() => {
        clearInterval(poll);
        setGenerating(false);
      }, 300_000);
    } catch {
      setGenerating(false);
    }
  };

  const sendComment = async (leadId: string) => {
    setSendingId(leadId);
    try {
      await api(
        `/api/v1/campaigns/${selectedCampaign}/send-comments?lead_id=${leadId}`,
        { method: "POST" }
      );
      const data = await api<Lead[]>(
        `/api/v1/leads/?campaign_id=${selectedCampaign}&limit=500`
      );
      setLeads(data);
    } catch {
      /* ignore — API errors don't crash the page */
    } finally {
      setSendingId(null);
    }
  };

  const bulkSend = async () => {
    setBulkSending(true);
    try {
      await api(`/api/v1/campaigns/${selectedCampaign}/send-comments`, {
        method: "POST",
      });
      const data = await api<Lead[]>(
        `/api/v1/leads/?campaign_id=${selectedCampaign}&limit=500`
      );
      setLeads(data);
    } catch {
      /* ignore */
    }
    setBulkSending(false);
  };

  const copy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const toggleVariantB = (id: string) => {
    setShowVariantB((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const withComments = leads.filter((l) => l.comment_message);

  // Stats
  const pendingCount = withComments.filter((l) => !l.comment_status || l.comment_status === "pending").length;
  const sentCount = withComments.filter((l) => l.comment_status === "sent").length;
  const failedCount = withComments.filter((l) => l.comment_status === "failed").length;

  // Filtered
  const filtered = withComments.filter((l) => {
    const matchesSearch =
      !search ||
      l.ig_username?.toLowerCase().includes(search.toLowerCase()) ||
      l.comment_message?.toLowerCase().includes(search.toLowerCase());
    const matchesStatus =
      !statusFilter ||
      (statusFilter === "pending" && (!l.comment_status || l.comment_status === "pending")) ||
      l.comment_status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Comentarios</h1>
          <p className="text-sm text-zinc-500">
            {withComments.length} comentarios generados
          </p>
        </div>
        <div className="flex gap-2">
          <select
            value={selectedCampaign}
            onChange={(e) => setSelectedCampaign(e.target.value)}
            className="rounded-lg border border-zinc-200 px-3 py-2 text-sm"
          >
            {campaigns.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <button
            onClick={generate}
            disabled={generating}
            className="flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
          >
            {generating ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <MessageSquare size={14} />
            )}
            {generating ? "Generando..." : "Generar Comentarios"}
          </button>
          {pendingCount > 0 && (
            <button
              onClick={bulkSend}
              disabled={bulkSending}
              className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              {bulkSending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Send size={14} />
              )}
              Enviar Masivo ({pendingCount})
            </button>
          )}
        </div>
      </div>

      {/* Stats */}
      {withComments.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-lg border border-zinc-200 bg-white p-3 text-center">
            <p className="text-2xl font-semibold text-amber-600">{pendingCount}</p>
            <p className="text-xs text-zinc-500">Pendientes</p>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white p-3 text-center">
            <p className="text-2xl font-semibold text-emerald-600">{sentCount}</p>
            <p className="text-xs text-zinc-500">Enviados</p>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white p-3 text-center">
            <p className="text-2xl font-semibold text-red-600">{failedCount}</p>
            <p className="text-xs text-zinc-500">Fallidos</p>
          </div>
        </div>
      )}

      {/* Search & Filter */}
      <div className="flex gap-3">
        <div className="relative flex-1 max-w-md">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            placeholder="Buscar por username o contenido..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-zinc-200 bg-white pl-9 pr-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-zinc-200 px-3 py-2 text-sm"
        >
          <option value="">Todos los estados</option>
          <option value="pending">Pendiente</option>
          <option value="sent">Enviado</option>
          <option value="failed">Fallido</option>
        </select>
      </div>

      {/* Info banner */}
      {withComments.length > 0 && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-2.5 text-xs text-blue-700">
          Los comentarios se auto-generan para leads con score alto. Puedes enviarlos individualmente o en masa.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((lead) => (
          <div
            key={lead.id}
            className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-zinc-900">
                @{lead.ig_username}
              </p>
              <div className="flex items-center gap-2">
                {lead.score !== null && (
                  <span
                    className={cn(
                      "rounded-full h-7 w-7 flex items-center justify-center text-[10px] font-bold",
                      (lead.score || 0) >= 70
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-amber-100 text-amber-700"
                    )}
                  >
                    {lead.score}
                  </span>
                )}
                {lead.comment_status && (
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-medium",
                      lead.comment_status === "sent"
                        ? "bg-green-100 text-green-700"
                        : lead.comment_status === "failed"
                        ? "bg-red-100 text-red-700"
                        : "bg-zinc-100 text-zinc-600"
                    )}
                  >
                    {lead.comment_status}
                  </span>
                )}
              </div>
            </div>

            {/* Variant A */}
            <div className="relative group">
              <div className="rounded-md bg-zinc-50 p-3 text-sm text-zinc-700">
                {lead.comment_message}
              </div>
              <button
                onClick={() => copy(lead.comment_message!, `c-${lead.id}`)}
                className="absolute top-2 right-2 p-1 rounded bg-white border border-zinc-200 opacity-0 group-hover:opacity-100 transition-opacity"
              >
                {copiedId === `c-${lead.id}` ? (
                  <Check size={12} className="text-emerald-500" />
                ) : (
                  <Copy size={12} className="text-zinc-400" />
                )}
              </button>
            </div>

            {/* Variant B toggle */}
            {lead.comment_variant_b && (
              <>
                <button
                  onClick={() => toggleVariantB(lead.id)}
                  className="text-xs text-zinc-500 hover:text-zinc-700"
                >
                  {showVariantB.has(lead.id) ? "Ocultar Variante B" : "Ver Variante B"}
                </button>
                {showVariantB.has(lead.id) && (
                  <div className="relative group">
                    <div className="rounded-md bg-zinc-50 p-3 text-sm text-zinc-600">
                      {lead.comment_variant_b}
                    </div>
                    <button
                      onClick={() => copy(lead.comment_variant_b!, `cb-${lead.id}`)}
                      className="absolute top-2 right-2 p-1 rounded bg-white border border-zinc-200 opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      {copiedId === `cb-${lead.id}` ? (
                        <Check size={12} className="text-emerald-500" />
                      ) : (
                        <Copy size={12} className="text-zinc-400" />
                      )}
                    </button>
                  </div>
                )}
              </>
            )}

            <div className="flex items-center justify-between">
              {lead.commented_post_shortcode && (
                <p className="text-xs text-zinc-400">
                  Post: {lead.commented_post_shortcode}
                </p>
              )}
              {lead.comment_status !== "sent" && (
                <button
                  onClick={() => sendComment(lead.id)}
                  disabled={sendingId === lead.id}
                  className="ml-auto flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                >
                  {sendingId === lead.id ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Send size={12} />
                  )}
                  Enviar
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {withComments.length === 0 && !generating && (
        <div className="text-center py-16 text-zinc-400">
          <MessageSquare size={40} className="mx-auto mb-3 opacity-40" />
          <p>No hay comentarios generados para esta campaña.</p>
          <p className="text-sm">Haz clic en &quot;Generar Comentarios&quot; para empezar.</p>
        </div>
      )}
    </div>
  );
}
