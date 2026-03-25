"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  Kanban,
  Loader2,
  X,
  MessageCircle,
  TrendingUp,
  TrendingDown,
  Minus,
  Send as SendIcon,
  StickyNote,
  BarChart3,
  Users,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */
interface LeadCard {
  lead_id: string;
  campaign_id: string;
  ig_username: string;
  ig_full_name: string | null;
  ig_profile_pic_url: string | null;
  score: number | null;
  crm_stage: string;
  reply_classification: string | null;
  conversation_status: string | null;
  last_message_preview: string | null;
  last_message_at: string | null;
  has_reply: boolean;
  follow_up_count: number | null;
  lead_category: string | null;
}

interface BoardResponse {
  stages: Record<string, LeadCard[]>;
  stage_labels: Record<string, string>;
}

interface BoardStats {
  stages: Record<string, { count: number; avg_score: number; label: string }>;
  total_leads: number;
  response_rate: number;
  interest_rate: number;
  closed_won: number;
}

interface ScoreHistoryEntry {
  old_score: number;
  new_score: number;
  delta: number;
  reason: string;
  created_at: string;
}

interface Note {
  id: string;
  content: string;
  user_id: string | null;
  created_at: string;
}

interface LeadDetailMsg {
  direction: string;
  message_type: string;
  content: string;
  sent_at: string;
}

interface LeadDetail {
  id: string;
  ig_username: string;
  ig_full_name: string | null;
  ig_bio: string | null;
  ig_profile_pic_url: string | null;
  ig_follower_count: number | null;
  ig_following_count: number | null;
  score: number | null;
  score_reason: string | null;
  lead_category: string | null;
  research_summary: string | null;
  crm_stage: string | null;
  reply_classification: string | null;
  conversation_status: string | null;
  sent_at: string | null;
  replied_at: string | null;
}

interface LeadDetailResponse {
  lead: LeadDetail;
  score_history: ScoreHistoryEntry[];
  notes: Note[];
  messages: LeadDetailMsg[];
}

interface Campaign {
  id: string;
  name: string;
}

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */
const STAGE_ORDER = [
  "new",
  "contacted",
  "replied",
  "interested",
  "call_scheduled",
  "closed_won",
  "closed_lost",
];

const STAGE_COLORS: Record<string, string> = {
  new: "border-t-zinc-400",
  contacted: "border-t-blue-400",
  replied: "border-t-cyan-400",
  interested: "border-t-amber-400",
  call_scheduled: "border-t-purple-400",
  closed_won: "border-t-emerald-400",
  closed_lost: "border-t-red-400",
};

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */
export default function CrmPage() {
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [stats, setStats] = useState<BoardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState("");

  // Detail panel
  const [detailId, setDetailId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LeadDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [addingNote, setAddingNote] = useState(false);

  // Drag state
  const [draggedLead, setDraggedLead] = useState<string | null>(null);

  /* ---------- Load board ---------- */
  const loadBoard = useCallback(async () => {
    setLoading(true);
    try {
      const params = selectedCampaign ? `?campaign_id=${selectedCampaign}` : "";
      const [boardRes, statsRes] = await Promise.all([
        api<BoardResponse>(`/api/v1/crm/board${params}`),
        api<BoardStats>(`/api/v1/crm/board/stats${params}`),
      ]);
      setBoard(boardRes);
      setStats(statsRes);
    } catch {
      /* ignore */
    }
    setLoading(false);
  }, [selectedCampaign]);

  useEffect(() => {
    loadBoard();
  }, [loadBoard]);

  /* ---------- Load campaigns ---------- */
  useEffect(() => {
    api<Campaign[]>("/api/v1/campaigns/")
      .then(setCampaigns)
      .catch(() => {});
  }, []);

  /* ---------- Open detail ---------- */
  const openDetail = async (leadId: string) => {
    setDetailId(leadId);
    setDetailLoading(true);
    setDetail(null);
    setNoteText("");
    try {
      const res = await api<LeadDetailResponse>(`/api/v1/crm/leads/${leadId}`);
      setDetail(res);
    } catch {
      /* ignore */
    }
    setDetailLoading(false);
  };

  /* ---------- Add note ---------- */
  const addNote = async () => {
    if (!detailId || !noteText.trim()) return;
    setAddingNote(true);
    try {
      const res = await api<Note>(`/api/v1/crm/leads/${detailId}/notes`, {
        method: "POST",
        body: JSON.stringify({ content: noteText.trim() }),
      });
      setDetail((prev) =>
        prev ? { ...prev, notes: [res, ...prev.notes] } : prev
      );
      setNoteText("");
    } catch {
      /* ignore */
    }
    setAddingNote(false);
  };

  /* ---------- Drag & drop ---------- */
  const handleDragStart = (leadId: string) => {
    setDraggedLead(leadId);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };

  const handleDrop = async (e: React.DragEvent, targetStage: string) => {
    e.preventDefault();
    if (!draggedLead || !board) return;

    try {
      await api(`/api/v1/crm/leads/${draggedLead}/stage`, {
        method: "PATCH",
        body: JSON.stringify({ stage: targetStage }),
      });
      loadBoard();
    } catch {
      /* ignore */
    }
    setDraggedLead(null);
  };

  /* ---------- Helpers ---------- */
  const scoreTrend = (history: ScoreHistoryEntry[]) => {
    if (!history.length) return null;
    const latest = history[0];
    if (latest.delta > 0) return "up";
    if (latest.delta < 0) return "down";
    return "flat";
  };

  if (loading && !board) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 size={24} className="animate-spin text-zinc-400" />
      </div>
    );
  }

  return (
    <div className="space-y-4 -mx-6 -mt-6">
      {/* Header */}
      <div className="bg-white border-b border-zinc-200 px-6 py-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Kanban size={18} className="text-amber-500" />
            <h1 className="text-lg font-semibold text-zinc-900">CRM Pipeline</h1>
          </div>
          <select
            value={selectedCampaign}
            onChange={(e) => setSelectedCampaign(e.target.value)}
            className="rounded-lg border border-zinc-200 px-3 py-2 text-sm"
          >
            <option value="">Todas las campañas</option>
            {campaigns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        {/* Stats bar */}
        {stats && (
          <div className="grid grid-cols-4 gap-3">
            <div className="rounded-lg bg-zinc-50 border border-zinc-200 p-3 text-center">
              <p className="text-xl font-bold text-zinc-900">{stats.total_leads}</p>
              <p className="text-[10px] text-zinc-500 uppercase tracking-wide">Total Leads</p>
            </div>
            <div className="rounded-lg bg-zinc-50 border border-zinc-200 p-3 text-center">
              <p className="text-xl font-bold text-emerald-600">{stats.response_rate}%</p>
              <p className="text-[10px] text-zinc-500 uppercase tracking-wide">Tasa Respuesta</p>
            </div>
            <div className="rounded-lg bg-zinc-50 border border-zinc-200 p-3 text-center">
              <p className="text-xl font-bold text-amber-600">{stats.interest_rate}%</p>
              <p className="text-[10px] text-zinc-500 uppercase tracking-wide">Tasa Interés</p>
            </div>
            <div className="rounded-lg bg-zinc-50 border border-zinc-200 p-3 text-center">
              <p className="text-xl font-bold text-emerald-600">{stats.closed_won}</p>
              <p className="text-[10px] text-zinc-500 uppercase tracking-wide">Cerrados</p>
            </div>
          </div>
        )}
      </div>

      {/* Kanban Board */}
      <div className="px-6 overflow-x-auto">
        <div className="flex gap-3 min-w-max pb-4">
          {STAGE_ORDER.map((stage) => {
            const cards = board?.stages[stage] || [];
            const label = board?.stage_labels[stage] || stage;
            const stageStats = stats?.stages[stage];

            return (
              <div
                key={stage}
                className={cn(
                  "w-64 shrink-0 bg-zinc-100 rounded-lg border-t-4",
                  STAGE_COLORS[stage] || "border-t-zinc-300"
                )}
                onDragOver={handleDragOver}
                onDrop={(e) => handleDrop(e, stage)}
              >
                {/* Column header */}
                <div className="px-3 py-2.5 flex items-center justify-between">
                  <div>
                    <p className="text-xs font-semibold text-zinc-700">{label}</p>
                    {stageStats && (
                      <p className="text-[10px] text-zinc-400">
                        Avg: {stageStats.avg_score}
                      </p>
                    )}
                  </div>
                  <span className="rounded-full bg-zinc-200 px-2 py-0.5 text-[10px] font-bold text-zinc-600">
                    {cards.length}
                  </span>
                </div>

                {/* Cards */}
                <div className="px-2 pb-2 space-y-2 max-h-[60vh] overflow-y-auto">
                  {cards.map((card) => (
                    <div
                      key={card.lead_id}
                      draggable
                      onDragStart={() => handleDragStart(card.lead_id)}
                      onClick={() => openDetail(card.lead_id)}
                      className="bg-white rounded-lg border border-zinc-200 p-3 cursor-pointer hover:border-amber-300 hover:shadow-sm transition-all"
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <p className="text-sm font-medium text-zinc-900 truncate">
                          @{card.ig_username}
                        </p>
                        {card.score !== null && (
                          <span
                            className={cn(
                              "rounded-full h-6 w-6 flex items-center justify-center text-[10px] font-bold",
                              card.score >= 70
                                ? "bg-emerald-100 text-emerald-700"
                                : card.score >= 40
                                ? "bg-amber-100 text-amber-700"
                                : "bg-red-100 text-red-700"
                            )}
                          >
                            {card.score}
                          </span>
                        )}
                      </div>
                      {card.ig_full_name && (
                        <p className="text-[10px] text-zinc-500 truncate mb-1">
                          {card.ig_full_name}
                        </p>
                      )}
                      {card.last_message_preview && (
                        <p className="text-xs text-zinc-400 truncate">
                          {card.last_message_preview}
                        </p>
                      )}
                      <div className="flex items-center gap-1.5 mt-2">
                        {card.has_reply && (
                          <MessageCircle size={10} className="text-emerald-500" />
                        )}
                        {card.lead_category && (
                          <span className="text-[9px] bg-zinc-100 text-zinc-500 rounded px-1">
                            {card.lead_category}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}

                  {cards.length === 0 && (
                    <div className="text-center py-6 text-zinc-400">
                      <p className="text-[10px]">Sin leads</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ============ Detail Side Panel (Overlay) ============ */}
      {detailId && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setDetailId(null)}
          />

          {/* Panel */}
          <div className="relative w-[480px] bg-white h-full shadow-xl overflow-y-auto">
            {detailLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 size={24} className="animate-spin text-zinc-400" />
              </div>
            ) : detail ? (
              <div className="flex flex-col h-full">
                {/* Header */}
                <div className="border-b border-zinc-200 px-5 py-4 flex items-center justify-between sticky top-0 bg-white z-10">
                  <div>
                    <p className="text-base font-semibold text-zinc-900">
                      @{detail.lead.ig_username}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {detail.lead.ig_full_name}
                    </p>
                  </div>
                  <button
                    onClick={() => setDetailId(null)}
                    className="p-1 rounded hover:bg-zinc-100"
                  >
                    <X size={18} className="text-zinc-400" />
                  </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
                  {/* Lead info */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-lg bg-zinc-50 p-3">
                      <p className="text-[10px] text-zinc-500 uppercase">Score</p>
                      <div className="flex items-center gap-2 mt-1">
                        <p className="text-xl font-bold text-zinc-900">
                          {detail.lead.score ?? "—"}
                        </p>
                        {(() => {
                          const trend = scoreTrend(detail.score_history);
                          if (trend === "up")
                            return <TrendingUp size={14} className="text-emerald-500" />;
                          if (trend === "down")
                            return <TrendingDown size={14} className="text-red-500" />;
                          if (trend === "flat")
                            return <Minus size={14} className="text-zinc-400" />;
                          return null;
                        })()}
                      </div>
                    </div>
                    <div className="rounded-lg bg-zinc-50 p-3">
                      <p className="text-[10px] text-zinc-500 uppercase">Etapa CRM</p>
                      <p className="text-sm font-medium text-zinc-900 mt-1">
                        {board?.stage_labels[detail.lead.crm_stage || ""] ||
                          detail.lead.crm_stage ||
                          "Nuevo"}
                      </p>
                    </div>
                  </div>

                  {/* Bio */}
                  {detail.lead.ig_bio && (
                    <div>
                      <p className="text-[10px] text-zinc-500 uppercase mb-1">Bio</p>
                      <p className="text-sm text-zinc-700">
                        {detail.lead.ig_bio as string}
                      </p>
                    </div>
                  )}

                  {/* Research */}
                  {detail.lead.research_summary && (
                    <div>
                      <p className="text-[10px] text-zinc-500 uppercase mb-1">Research</p>
                      <p className="text-sm text-zinc-600">
                        {detail.lead.research_summary as string}
                      </p>
                    </div>
                  )}

                  {/* Conversation */}
                  {detail.messages.length > 0 && (
                    <div>
                      <p className="text-[10px] text-zinc-500 uppercase mb-2 flex items-center gap-1">
                        <SendIcon size={10} /> Conversación
                      </p>
                      <div className="space-y-2">
                        {detail.messages.map((msg, i) => (
                          <div
                            key={i}
                            className={cn(
                              "rounded-lg p-2.5 text-xs",
                              msg.direction === "outbound"
                                ? "bg-amber-50 border border-amber-200 ml-8"
                                : "bg-zinc-50 border border-zinc-200 mr-8"
                            )}
                          >
                            <p className="text-zinc-700">{msg.content}</p>
                            <p className="text-[9px] text-zinc-400 mt-1">
                              {new Date(msg.sent_at).toLocaleString("es-VE", {
                                day: "2-digit",
                                month: "short",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Score history */}
                  {detail.score_history.length > 0 && (
                    <div>
                      <p className="text-[10px] text-zinc-500 uppercase mb-2 flex items-center gap-1">
                        <BarChart3 size={10} /> Historial de Score
                      </p>
                      <div className="space-y-1.5">
                        {detail.score_history.slice(0, 10).map((entry, i) => (
                          <div
                            key={i}
                            className="flex items-center gap-2 text-xs"
                          >
                            <span
                              className={cn(
                                "font-bold",
                                entry.delta > 0
                                  ? "text-emerald-600"
                                  : entry.delta < 0
                                  ? "text-red-600"
                                  : "text-zinc-400"
                              )}
                            >
                              {entry.delta > 0 ? "+" : ""}
                              {entry.delta}
                            </span>
                            <span className="text-zinc-500">
                              {entry.old_score} → {entry.new_score}
                            </span>
                            <span className="text-zinc-400 truncate flex-1">
                              {entry.reason}
                            </span>
                            <span className="text-[9px] text-zinc-400 shrink-0">
                              {new Date(entry.created_at).toLocaleDateString("es-VE", {
                                day: "2-digit",
                                month: "short",
                              })}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Notes */}
                  <div>
                    <p className="text-[10px] text-zinc-500 uppercase mb-2 flex items-center gap-1">
                      <StickyNote size={10} /> Notas ({detail.notes.length})
                    </p>

                    {/* Add note */}
                    <div className="flex gap-2 mb-3">
                      <input
                        value={noteText}
                        onChange={(e) => setNoteText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") addNote();
                        }}
                        placeholder="Agregar nota..."
                        className="flex-1 rounded-md border border-zinc-200 px-3 py-2 text-xs focus:border-amber-500 focus:outline-none"
                      />
                      <button
                        onClick={addNote}
                        disabled={addingNote || !noteText.trim()}
                        className="rounded-md bg-amber-500 px-3 py-2 text-xs text-white hover:bg-amber-600 disabled:opacity-50"
                      >
                        {addingNote ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          "Agregar"
                        )}
                      </button>
                    </div>

                    {detail.notes.map((note) => (
                      <div
                        key={note.id}
                        className="rounded-md bg-zinc-50 border border-zinc-100 p-2.5 mb-2"
                      >
                        <p className="text-xs text-zinc-700">{note.content}</p>
                        <p className="text-[9px] text-zinc-400 mt-1">
                          {new Date(note.created_at).toLocaleString("es-VE", {
                            day: "2-digit",
                            month: "short",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </p>
                      </div>
                    ))}
                  </div>

                  {/* Open in Unibox link */}
                  <a
                    href={`/unibox`}
                    className="block text-center text-xs text-amber-600 hover:text-amber-700 py-2"
                  >
                    Abrir en Unibox →
                  </a>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
