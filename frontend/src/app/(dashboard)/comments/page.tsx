"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { MessageSquare, Send, Loader2 } from "lucide-react";
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
    api<Lead[]>(`/api/v1/campaigns/${selectedCampaign}/leads?limit=500`)
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
      // Poll for completion
      const poll = setInterval(async () => {
        const data = await api<Lead[]>(
          `/api/v1/campaigns/${selectedCampaign}/leads?limit=500`
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
    await api(
      `/api/v1/campaigns/${selectedCampaign}/send-comments?lead_id=${leadId}`,
      { method: "POST" }
    );
    const data = await api<Lead[]>(
      `/api/v1/campaigns/${selectedCampaign}/leads?limit=500`
    );
    setLeads(data);
  };

  const withComments = leads.filter((l) => l.comment_message);

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
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {withComments.map((lead) => (
          <div
            key={lead.id}
            className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-zinc-900">
                @{lead.ig_username}
              </p>
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

            <div className="rounded-md bg-zinc-50 p-3 text-sm text-zinc-700">
              {lead.comment_message}
            </div>

            {lead.commented_post_shortcode && (
              <p className="text-xs text-zinc-400">
                Post: {lead.commented_post_shortcode}
              </p>
            )}

            {lead.comment_status !== "sent" && (
              <button
                onClick={() => sendComment(lead.id)}
                className="flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500"
              >
                <Send size={12} /> Enviar
              </button>
            )}
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
