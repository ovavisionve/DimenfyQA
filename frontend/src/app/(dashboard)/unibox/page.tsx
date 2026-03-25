"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  Inbox,
  Search,
  Send,
  Sparkles,
  Loader2,
  RefreshCw,
  MessageCircle,
  ArrowRight,
  User,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */
interface Conversation {
  lead_id: string;
  campaign_id: string;
  ig_username: string;
  ig_full_name: string | null;
  ig_profile_pic_url: string | null;
  score: number | null;
  has_reply: boolean;
  reply_classification: string | null;
  conversation_status: string | null;
  last_message_preview: string | null;
  last_message_at: string | null;
  crm_stage: string | null;
}

interface ConvResponse {
  conversations: Conversation[];
  total: number;
}

interface ThreadMessage {
  direction: "outbound" | "inbound";
  message_type: string;
  content: string;
  sent_at: string;
}

interface LeadInfo {
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
}

interface ThreadResponse {
  lead: LeadInfo;
  messages: ThreadMessage[];
  suggestions: Suggestion[] | null;
}

interface Suggestion {
  intent: string;
  label: string;
  message: string;
}

interface SuggestionResponse {
  suggestions: Suggestion[] | null;
  generated_at: string | null;
}

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */
const CLASSIFICATION_COLORS: Record<string, string> = {
  positive: "bg-emerald-100 text-emerald-700",
  negative: "bg-red-100 text-red-700",
  not_interested: "bg-red-100 text-red-700",
  question: "bg-blue-100 text-blue-700",
  spam: "bg-zinc-200 text-zinc-500",
  neutral: "bg-zinc-100 text-zinc-600",
};

const CLASSIFICATION_LABELS: Record<string, string> = {
  positive: "Positivo",
  negative: "Negativo",
  not_interested: "No interesado",
  question: "Pregunta",
  spam: "Spam",
  neutral: "Neutral",
};

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */
export default function UniboxPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sortBy, setSortBy] = useState("recent");

  // Thread panel
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [thread, setThread] = useState<ThreadResponse | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);

  // Suggestions
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [sugLoading, setSugLoading] = useState(false);

  // Reply input
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);

  /* ---------- Load conversations ---------- */
  const loadConversations = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (classFilter) params.set("classification", classFilter);
      if (statusFilter) params.set("conversation_status", statusFilter);
      params.set("sort_by", sortBy);
      params.set("limit", "100");

      const res = await api<ConvResponse>(
        `/api/v1/unibox/conversations?${params.toString()}`
      );
      setConversations(res.conversations);
      setTotal(res.total);
    } catch {
      /* ignore */
    }
    setLoading(false);
  }, [search, classFilter, statusFilter, sortBy]);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  /* ---------- Open thread ---------- */
  const openThread = async (leadId: string) => {
    setSelectedId(leadId);
    setThreadLoading(true);
    setThread(null);
    setSuggestions(null);
    setReplyText("");

    try {
      const [threadRes, sugRes] = await Promise.all([
        api<ThreadResponse>(`/api/v1/unibox/conversations/${leadId}/thread`),
        api<SuggestionResponse>(`/api/v1/unibox/conversations/${leadId}/suggestions`),
      ]);
      setThread(threadRes);
      setSuggestions(sugRes.suggestions || threadRes.suggestions || null);
    } catch {
      /* ignore */
    }
    setThreadLoading(false);
  };

  /* ---------- Regenerate suggestions ---------- */
  const regenerate = async () => {
    if (!selectedId) return;
    setSugLoading(true);
    try {
      const res = await api<{ suggestions: Suggestion[] }>(
        `/api/v1/unibox/conversations/${selectedId}/suggest`,
        { method: "POST" }
      );
      setSuggestions(res.suggestions);
    } catch {
      /* ignore */
    }
    setSugLoading(false);
  };

  /* ---------- Send reply ---------- */
  const sendReply = async () => {
    if (!selectedId || !replyText.trim()) return;
    setSending(true);
    try {
      await api(`/api/v1/unibox/conversations/${selectedId}/reply`, {
        method: "POST",
        body: JSON.stringify({ message: replyText.trim() }),
      });
      // Reload thread
      const threadRes = await api<ThreadResponse>(
        `/api/v1/unibox/conversations/${selectedId}/thread`
      );
      setThread(threadRes);
      setReplyText("");
      loadConversations();
    } catch {
      /* ignore */
    }
    setSending(false);
  };

  /* ---------- Use suggestion ---------- */
  const useSuggestion = (msg: string) => {
    setReplyText(msg);
  };

  /* ---------- Helpers ---------- */
  const timeAgo = (iso: string | null) => {
    if (!iso) return "";
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h`;
    const days = Math.floor(hrs / 24);
    return `${days}d`;
  };

  return (
    <div className="flex h-[calc(100vh-2rem)] gap-0 -m-6">
      {/* ============ LEFT PANEL — Conversation List ============ */}
      <div className="w-96 shrink-0 border-r border-zinc-200 flex flex-col bg-white">
        {/* Header */}
        <div className="border-b border-zinc-200 p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Inbox size={18} className="text-amber-500" />
              <h1 className="text-lg font-semibold text-zinc-900">Unibox</h1>
            </div>
            <span className="text-xs text-zinc-500">{total} conversaciones</span>
          </div>

          {/* Search */}
          <div className="relative mb-2">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400"
            />
            <input
              placeholder="Buscar por username..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border border-zinc-200 bg-zinc-50 pl-9 pr-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
            />
          </div>

          {/* Filters */}
          <div className="flex gap-2">
            <select
              value={classFilter}
              onChange={(e) => setClassFilter(e.target.value)}
              className="flex-1 rounded-md border border-zinc-200 px-2 py-1.5 text-xs"
            >
              <option value="">Clasificación</option>
              <option value="positive">Positivo</option>
              <option value="negative">Negativo</option>
              <option value="question">Pregunta</option>
              <option value="spam">Spam</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="flex-1 rounded-md border border-zinc-200 px-2 py-1.5 text-xs"
            >
              <option value="">Estado</option>
              <option value="awaiting_reply">Esperando</option>
              <option value="replied">Respondió</option>
              <option value="closed">Cerrada</option>
            </select>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="flex-1 rounded-md border border-zinc-200 px-2 py-1.5 text-xs"
            >
              <option value="recent">Reciente</option>
              <option value="score">Score</option>
              <option value="unread">No leído</option>
            </select>
          </div>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={24} className="animate-spin text-zinc-400" />
            </div>
          ) : conversations.length === 0 ? (
            <div className="text-center py-16 text-zinc-400">
              <MessageCircle size={32} className="mx-auto mb-2 opacity-40" />
              <p className="text-sm">No hay conversaciones</p>
            </div>
          ) : (
            conversations.map((conv) => (
              <button
                key={conv.lead_id}
                onClick={() => openThread(conv.lead_id)}
                className={cn(
                  "w-full text-left px-4 py-3 border-b border-zinc-100 hover:bg-zinc-50 transition-colors",
                  selectedId === conv.lead_id && "bg-amber-50 border-l-2 border-l-amber-500"
                )}
              >
                <div className="flex items-start gap-3">
                  {/* Avatar */}
                  <div className="h-9 w-9 rounded-full bg-zinc-200 flex items-center justify-center text-xs font-medium text-zinc-600 shrink-0">
                    {conv.ig_full_name?.[0]?.toUpperCase() ||
                      conv.ig_username[0].toUpperCase()}
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium text-zinc-900 truncate">
                        @{conv.ig_username}
                      </p>
                      <span className="text-[10px] text-zinc-400 shrink-0 ml-2">
                        {timeAgo(conv.last_message_at)}
                      </span>
                    </div>
                    <p className="text-xs text-zinc-500 truncate mt-0.5">
                      {conv.last_message_preview || "Sin mensaje"}
                    </p>
                    <div className="flex items-center gap-1.5 mt-1">
                      {conv.score !== null && (
                        <span
                          className={cn(
                            "rounded-full px-1.5 py-0.5 text-[9px] font-bold",
                            conv.score >= 70
                              ? "bg-emerald-100 text-emerald-700"
                              : conv.score >= 40
                              ? "bg-amber-100 text-amber-700"
                              : "bg-red-100 text-red-700"
                          )}
                        >
                          {conv.score}
                        </span>
                      )}
                      {conv.reply_classification && (
                        <span
                          className={cn(
                            "rounded-full px-1.5 py-0.5 text-[9px] font-medium",
                            CLASSIFICATION_COLORS[conv.reply_classification] ||
                              "bg-zinc-100 text-zinc-500"
                          )}
                        >
                          {CLASSIFICATION_LABELS[conv.reply_classification] ||
                            conv.reply_classification}
                        </span>
                      )}
                      {conv.crm_stage && conv.crm_stage !== "new" && (
                        <span className="rounded-full px-1.5 py-0.5 text-[9px] bg-zinc-100 text-zinc-500">
                          {conv.crm_stage}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* ============ RIGHT PANEL — Thread ============ */}
      <div className="flex-1 flex flex-col bg-zinc-50">
        {!selectedId ? (
          <div className="flex-1 flex items-center justify-center text-zinc-400">
            <div className="text-center">
              <Inbox size={48} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">Selecciona una conversación</p>
            </div>
          </div>
        ) : threadLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 size={24} className="animate-spin text-zinc-400" />
          </div>
        ) : thread ? (
          <>
            {/* Thread header */}
            <div className="bg-white border-b border-zinc-200 px-5 py-3 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-zinc-200 flex items-center justify-center">
                  <User size={16} className="text-zinc-500" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-zinc-900">
                    @{thread.lead.ig_username}
                  </p>
                  <p className="text-xs text-zinc-500">
                    {thread.lead.ig_full_name}
                    {thread.lead.score !== null && (
                      <span className="ml-2 text-amber-600 font-medium">
                        Score: {thread.lead.score}
                      </span>
                    )}
                    {thread.lead.crm_stage && (
                      <span className="ml-2 text-zinc-400">
                        CRM: {thread.lead.crm_stage}
                      </span>
                    )}
                  </p>
                </div>
              </div>
              {thread.lead.ig_bio && (
                <p className="text-xs text-zinc-400 max-w-xs truncate" title={thread.lead.ig_bio}>
                  {thread.lead.ig_bio}
                </p>
              )}
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
              {thread.messages.map((msg, i) => (
                <div
                  key={i}
                  className={cn(
                    "flex",
                    msg.direction === "outbound" ? "justify-end" : "justify-start"
                  )}
                >
                  <div
                    className={cn(
                      "max-w-[70%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
                      msg.direction === "outbound"
                        ? "bg-amber-500 text-white rounded-br-md"
                        : "bg-white border border-zinc-200 text-zinc-800 rounded-bl-md"
                    )}
                  >
                    <p>{msg.content}</p>
                    <p
                      className={cn(
                        "text-[10px] mt-1",
                        msg.direction === "outbound"
                          ? "text-amber-200"
                          : "text-zinc-400"
                      )}
                    >
                      {new Date(msg.sent_at).toLocaleString("es-VE", {
                        day: "2-digit",
                        month: "short",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                      {msg.message_type !== "dm" && msg.message_type !== "reply" && (
                        <span className="ml-1 opacity-70">
                          ({msg.message_type === "follow_up" ? "follow-up" : msg.message_type})
                        </span>
                      )}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            {/* AI Suggestions */}
            {suggestions && suggestions.length > 0 && (
              <div className="bg-white border-t border-zinc-200 px-5 py-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                    <Sparkles size={12} className="text-amber-500" />
                    Sugerencias IA
                  </div>
                  <button
                    onClick={regenerate}
                    disabled={sugLoading}
                    className="text-[10px] text-zinc-400 hover:text-amber-500 flex items-center gap-1"
                  >
                    {sugLoading ? (
                      <Loader2 size={10} className="animate-spin" />
                    ) : (
                      <RefreshCw size={10} />
                    )}
                    Regenerar
                  </button>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {suggestions.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => useSuggestion(s.message)}
                      className="text-left rounded-lg border border-zinc-200 p-2.5 hover:border-amber-400 hover:bg-amber-50 transition-colors"
                    >
                      <p className="text-[10px] font-medium text-amber-600 uppercase mb-1">
                        {s.label || s.intent}
                      </p>
                      <p className="text-xs text-zinc-600 line-clamp-2">
                        {s.message}
                      </p>
                      <div className="flex items-center gap-1 mt-1.5 text-[10px] text-amber-500">
                        <ArrowRight size={8} />
                        Usar
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* No suggestions yet — option to generate */}
            {(!suggestions || suggestions.length === 0) && thread.lead.reply_classification && (
              <div className="bg-white border-t border-zinc-200 px-5 py-2">
                <button
                  onClick={regenerate}
                  disabled={sugLoading}
                  className="flex items-center gap-1.5 text-xs text-amber-600 hover:text-amber-700"
                >
                  {sugLoading ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Sparkles size={12} />
                  )}
                  Generar sugerencias IA
                </button>
              </div>
            )}

            {/* Reply input */}
            <div className="bg-white border-t border-zinc-200 px-5 py-3">
              <div className="flex gap-2">
                <input
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendReply();
                    }
                  }}
                  placeholder="Escribe tu respuesta..."
                  className="flex-1 rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-sm focus:border-amber-500 focus:outline-none"
                />
                <button
                  onClick={sendReply}
                  disabled={sending || !replyText.trim()}
                  className="rounded-lg bg-amber-500 px-4 py-2.5 text-white hover:bg-amber-600 disabled:opacity-50 transition-colors"
                >
                  {sending ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Send size={16} />
                  )}
                </button>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
