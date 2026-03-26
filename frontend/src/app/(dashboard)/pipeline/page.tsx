"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import {
  Play,
  Send,
  RefreshCw,
  Plus,
  Search,
  ChevronDown,
  X,
  Download,
  BarChart3,
  FlaskConical,
  Sparkles,
  Loader2,
  Clock,
  Inbox,
  ListOrdered,
  Trash2,
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
  ig_bio_clean: string | null;
  ig_follower_count: number | null;
  status: string;
  score: number | null;
  category: string | null;
  lead_category: string | null;
  dm_message: string | null;
  dm_variant_b: string | null;
  delivery_status: string | null;
  dm_variant_used: string | null;
  replied_at: string | null;
  reply_text: string | null;
  reply_classification: string | null;
}

type TabKey = "stats" | "leads" | "dms" | "inbox" | "followups" | "analytics" | "ab_testing" | "content" | "export";

interface FollowUpRule {
  id: string;
  campaign_id: string;
  client_id: string;
  step_number: number;
  delay_days: number;
  template_prompt: string | null;
  max_attempts: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface RepliesResponse {
  campaign_id: string;
  total_replies: number;
  leads: Lead[];
}

interface FunnelStep {
  name: string;
  count: number;
  percentage: number;
}

interface ScoreBucket {
  range_label: string;
  count: number;
}

interface CategoryItem {
  category: string;
  count: number;
  percentage: number;
}

interface CampaignAnalytics {
  funnel: FunnelStep[];
  score_distribution: ScoreBucket[];
  category_breakdown: CategoryItem[];
  response_rate: number;
  avg_score: number;
  total_leads: number;
  total_sent: number;
  total_replied: number;
}

interface VariantStats {
  sent: number;
  replied: number;
  reply_rate: number;
  positive_replies: number;
  conversion_rate: number;
}

interface ABTestResults {
  campaign_id: string;
  variant_a: VariantStats;
  variant_b: VariantStats;
  winner: string | null;
  confidence: string;
  total_sent: number;
  recommendation: string;
}

interface ContentAnalysis {
  business_summary: string;
  value_propositions: string[];
  target_audience: string;
  tone_style: string;
  key_differentiators: string[];
  pain_points_addressed: string[];
  content_type_detected: string;
}

interface ActivityEvent {
  id: string;
  event_type: string;
  message: string;
  level: string;
  created_at: string;
  details?: Record<string, unknown>;
}

const LEVEL_COLORS: Record<string, string> = {
  success: "text-emerald-600",
  info: "text-blue-600",
  warning: "text-amber-600",
  error: "text-red-600",
};

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-zinc-200 text-zinc-700",
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
  const [tab, setTab] = useState<TabKey>("stats");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [dmPreview, setDmPreview] = useState<Lead | null>(null);

  // Analytics, A/B, Content Analysis state
  const [analytics, setAnalytics] = useState<CampaignAnalytics | null>(null);
  const [abResults, setAbResults] = useState<ABTestResults | null>(null);
  const [contentAnalysis, setContentAnalysis] = useState<ContentAnalysis | null>(null);
  const [contentUrls, setContentUrls] = useState("");
  const [contentText, setContentText] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const [activityLog, setActivityLog] = useState<ActivityEvent[]>([]);
  const [replies, setReplies] = useState<Lead[]>([]);
  const [replyFilter, setReplyFilter] = useState("");
  const [followUpRules, setFollowUpRules] = useState<FollowUpRule[]>([]);
  const [showNewRule, setShowNewRule] = useState(false);
  const [newRule, setNewRule] = useState({ step_number: 1, delay_days: 3, template_prompt: "", max_attempts: 3 });

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
  const [bioKeywords, setBioKeywords] = useState<string[]>([]);
  const [keywordInput, setKeywordInput] = useState("");
  const [sendingStart, setSendingStart] = useState("09:00");
  const [sendingEnd, setSendingEnd] = useState("21:00");
  const [sendingTimezone, setSendingTimezone] = useState("America/Caracas");
  const [scheduleEnabled, setScheduleEnabled] = useState(false);

  const loadCampaigns = useCallback(async () => {
    try {
      const data = await api<Campaign[]>("/api/v1/campaigns/");
      setCampaigns(data);
      setSelected((prev) => {
        if (prev) {
          // Update selected campaign data if it's still in the list
          const updated = data.find((c) => c.id === prev.id);
          return updated || prev;
        }
        return data.length ? data[0] : null;
      });
    } catch {
      /* ignore */
    }
  }, []);

  const loadLeads = useCallback(async (campaignId: string) => {
    try {
      const data = await api<Lead[]>(
        `/api/v1/leads/?campaign_id=${campaignId}&limit=500`
      );
      setLeads(data);
    } catch {
      /* ignore */
    }
  }, []);

  // Initial load
  useEffect(() => {
    setLoading(true);
    loadCampaigns().finally(() => setLoading(false));
    api<Array<{ id: string; name: string }>>("/api/v1/clients/")
      .then(setClients)
      .catch(() => {});
  }, [loadCampaigns]);

  // Load leads when selected campaign changes
  useEffect(() => {
    if (selected) loadLeads(selected.id);
    else setLeads([]);
  }, [selected?.id, loadLeads]);

  // Poll campaign status when actively processing
  useEffect(() => {
    if (
      !selected ||
      ["draft", "pending", "ready", "completed", "failed", "paused"].includes(selected.status)
    )
      return;
    const id = setInterval(async () => {
      try {
        const c = await api<Campaign>(`/api/v1/campaigns/${selected.id}`);
        setSelected(c);
        if (["ready", "completed", "failed", "paused"].includes(c.status)) {
          loadLeads(c.id);
        }
      } catch {
        /* ignore */
      }
    }, 3000);
    return () => clearInterval(id);
  }, [selected?.id, selected?.status, loadLeads]);

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

  // Load analytics when tab switches
  useEffect(() => {
    if (!selected) return;
    if (tab === "analytics" && !analytics) {
      api<CampaignAnalytics>(`/api/v1/campaigns/${selected.id}/analytics`)
        .then(setAnalytics)
        .catch(() => {});
    }
    if (tab === "ab_testing" && !abResults) {
      api<ABTestResults>(`/api/v1/campaigns/${selected.id}/ab-results`)
        .then(setAbResults)
        .catch(() => {});
    }
    if (tab === "followups") {
      api<FollowUpRule[]>(`/api/v1/follow-ups/?campaign_id=${selected.id}`)
        .then(setFollowUpRules)
        .catch(() => setFollowUpRules([]));
    }
    if (tab === "inbox") {
      const url = replyFilter
        ? `/api/v1/campaigns/${selected.id}/replies?classification=${replyFilter}`
        : `/api/v1/campaigns/${selected.id}/replies`;
      api<RepliesResponse>(url)
        .then((r) => setReplies(r.leads || []))
        .catch(() => setReplies([]));
    }
    if (tab === "content" && !contentAnalysis) {
      api<{ analysis: ContentAnalysis | null }>(`/api/v1/content/campaign/${selected.id}`)
        .then((r) => { if (r.analysis) setContentAnalysis(r.analysis); })
        .catch(() => {});
    }
  }, [tab, selected, analytics, abResults, contentAnalysis, replyFilter]);

  // Reset tab data when campaign changes
  useEffect(() => {
    setAnalytics(null);
    setAbResults(null);
    setContentAnalysis(null);
    if (selected?.id) {
      api<ActivityEvent[]>(`/api/v1/campaigns/${selected.id}/activity?limit=20`)
        .then(setActivityLog)
        .catch(() => setActivityLog([]));
    }
  }, [selected?.id]);

  const runContentAnalysis = async () => {
    if (!selected) return;
    setAnalyzing(true);
    try {
      const urls = contentUrls.split("\n").map((u) => u.trim()).filter(Boolean);
      const result = await api<{ analysis: ContentAnalysis }>("/api/v1/content/analyze-for-campaign", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selected.id,
          content_urls: urls.length ? urls : undefined,
          content_text: contentText || undefined,
        }),
      });
      setContentAnalysis(result.analysis);
    } catch {
      /* ignore */
    }
    setAnalyzing(false);
  };

  const downloadExport = async (format: "csv" | "json" | "excel") => {
    if (!selected) return;
    setExporting(format);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:1000"}/api/v1/export/${selected.id}/${format}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${selected.name}_leads.${format === "excel" ? "xlsx" : format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      /* ignore */
    }
    setExporting(null);
  };

  const createCampaign = async (e: React.FormEvent) => {
    e.preventDefault();
    const campaignSettings: Record<string, unknown> = {};
    if (bioKeywords.length > 0) campaignSettings.bio_keywords = bioKeywords;
    if (scheduleEnabled) {
      campaignSettings.sending_hours_start = sendingStart;
      campaignSettings.sending_hours_end = sendingEnd;
      campaignSettings.sending_timezone = sendingTimezone;
    }
    const payload = {
      ...newCampaign,
      settings: campaignSettings,
    };
    const data = await api<Campaign>("/api/v1/campaigns/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setCampaigns((prev) => [data, ...prev]);
    setSelected(data);
    setShowNew(false);
    setNewCampaign({ name: "", client_id: "", source_type: "comments", source_value: "", max_leads: 50 });
    setBioKeywords([]);
    setKeywordInput("");
    setScheduleEnabled(false);
    setSendingStart("09:00");
    setSendingEnd("21:00");
    setSendingTimezone("America/Caracas");
  };

  // Stats
  const stats = selected?.stats || {};
  const progress = (stats as Record<string, Record<string, unknown>>).progress || {};
  const scoredLeads = leads.filter((l) => l.score !== null);
  const avgScore = scoredLeads.length
    ? Math.round(scoredLeads.reduce((sum, l) => sum + (l.score || 0), 0) / scoredLeads.length)
    : 0;
  const statItems = [
    { label: "Total Leads", value: leads.length },
    { label: "Score Prom.", value: avgScore },
    { label: "Calificados 70+", value: leads.filter((l) => (l.score || 0) >= 70).length },
    { label: "DMs Generados", value: leads.filter((l) => l.dm_message).length },
    { label: "DMs Enviados", value: leads.filter((l) => l.status === "sent").length },
    { label: "Respondidos", value: leads.filter((l) => l.status === "replied").length },
    { label: "Fallidos", value: leads.filter((l) => l.status === "failed").length },
    { label: "Estado", value: selected?.status || "—", isText: true },
  ] as Array<{ label: string; value: number | string; isText?: boolean }>;

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

            {/* Template Selector */}
            <div>
              <label className="block text-xs font-medium text-zinc-600 mb-1">
                Plantilla (opcional)
              </label>
              <select
                onChange={async (e) => {
                  const tid = e.target.value;
                  if (!tid) return;
                  try {
                    const tpl = await api<{
                      id: string;
                      name: string;
                      source_type: string;
                      suggested_source_value: string;
                      settings: Record<string, unknown>;
                    }>(`/api/v1/templates/${tid}`);
                    setNewCampaign((prev) => ({
                      ...prev,
                      name: prev.name || tpl.name,
                      source_type: tpl.source_type || prev.source_type,
                      source_value: tpl.suggested_source_value || prev.source_value,
                      max_leads: (tpl.settings.max_leads as number) || prev.max_leads,
                    }));
                    if (tpl.settings.bio_keywords) setBioKeywords(tpl.settings.bio_keywords as string[]);
                    if (tpl.settings.sending_hours_start) {
                      setScheduleEnabled(true);
                      setSendingStart(tpl.settings.sending_hours_start as string);
                      setSendingEnd(tpl.settings.sending_hours_end as string);
                      setSendingTimezone(tpl.settings.sending_timezone as string);
                    }
                  } catch { /* ignore */ }
                  e.target.value = "";
                }}
                className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
              >
                <option value="">Seleccionar plantilla...</option>
                <option value="agency_outreach">Agencias de Marketing</option>
                <option value="coach_outreach">Coaches y Consultores</option>
                <option value="ecommerce_outreach">E-Commerce / Tiendas Online</option>
                <option value="saas_outreach">SaaS / Software</option>
                <option value="restaurant_outreach">Restaurantes y Comida</option>
                <option value="fitness_outreach">Fitness y Bienestar</option>
              </select>
            </div>

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

            {/* Bio Keyword Filter */}
            <div>
              <label className="block text-xs font-medium text-zinc-600 mb-1">
                Filtro por palabras clave en bio
              </label>
              <div className="flex gap-2">
                <input
                  placeholder="Ej: coach, marketing, agency..."
                  value={keywordInput}
                  onChange={(e) => setKeywordInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === ",") {
                      e.preventDefault();
                      const kw = keywordInput.trim().replace(/,/g, "");
                      if (kw && !bioKeywords.includes(kw)) {
                        setBioKeywords([...bioKeywords, kw]);
                      }
                      setKeywordInput("");
                    }
                  }}
                  className="flex-1 rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => {
                    const kw = keywordInput.trim().replace(/,/g, "");
                    if (kw && !bioKeywords.includes(kw)) {
                      setBioKeywords([...bioKeywords, kw]);
                    }
                    setKeywordInput("");
                  }}
                  className="rounded-lg border border-zinc-200 px-3 py-2 text-sm hover:bg-zinc-50"
                >
                  +
                </button>
              </div>
              {bioKeywords.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {bioKeywords.map((kw) => (
                    <span
                      key={kw}
                      className="inline-flex items-center gap-1 rounded-full bg-amber-100 text-amber-800 px-2.5 py-0.5 text-xs font-medium"
                    >
                      {kw}
                      <button
                        type="button"
                        onClick={() => setBioKeywords(bioKeywords.filter((k) => k !== kw))}
                        className="hover:text-red-600 text-amber-600"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <p className="text-[10px] text-zinc-400 mt-1">
                Solo se procesarán leads que tengan al menos una de estas palabras en su bio. Dejar vacío para procesar todos.
              </p>
            </div>

            {/* Sending Schedule */}
            <div>
              <label className="flex items-center gap-2 text-xs font-medium text-zinc-600 mb-2">
                <input
                  type="checkbox"
                  checked={scheduleEnabled}
                  onChange={(e) => setScheduleEnabled(e.target.checked)}
                  className="rounded border-zinc-300 accent-amber-500"
                />
                Horario de envío
              </label>
              {scheduleEnabled && (
                <div className="space-y-2 pl-5">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-zinc-500 w-10">Desde</span>
                    <select
                      value={sendingStart}
                      onChange={(e) => setSendingStart(e.target.value)}
                      className="flex-1 rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
                    >
                      {Array.from({ length: 48 }, (_, i) => {
                        const h = String(Math.floor(i / 2)).padStart(2, "0");
                        const m = i % 2 === 0 ? "00" : "30";
                        return <option key={`s${i}`} value={`${h}:${m}`}>{`${h}:${m}`}</option>;
                      })}
                    </select>
                    <span className="text-xs text-zinc-500 w-10">Hasta</span>
                    <select
                      value={sendingEnd}
                      onChange={(e) => setSendingEnd(e.target.value)}
                      className="flex-1 rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
                    >
                      {Array.from({ length: 48 }, (_, i) => {
                        const h = String(Math.floor(i / 2)).padStart(2, "0");
                        const m = i % 2 === 0 ? "00" : "30";
                        return <option key={`e${i}`} value={`${h}:${m}`}>{`${h}:${m}`}</option>;
                      })}
                    </select>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-zinc-500 w-10">Zona</span>
                    <select
                      value={sendingTimezone}
                      onChange={(e) => setSendingTimezone(e.target.value)}
                      className="flex-1 rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
                    >
                      <option value="America/Caracas">Caracas (VET -04:00)</option>
                      <option value="America/Bogota">Bogotá (COT -05:00)</option>
                      <option value="America/Lima">Lima (PET -05:00)</option>
                      <option value="America/Mexico_City">Ciudad de México (CST -06:00)</option>
                      <option value="America/Argentina/Buenos_Aires">Buenos Aires (ART -03:00)</option>
                      <option value="America/Santiago">Santiago (CLT -04:00)</option>
                      <option value="America/Sao_Paulo">São Paulo (BRT -03:00)</option>
                      <option value="America/New_York">New York (EST -05:00)</option>
                      <option value="America/Los_Angeles">Los Angeles (PST -08:00)</option>
                      <option value="Europe/Madrid">Madrid (CET +01:00)</option>
                      <option value="Europe/London">London (GMT +00:00)</option>
                    </select>
                  </div>
                  <p className="text-[10px] text-zinc-400">
                    Los DMs se enviarán entre {sendingStart} y {sendingEnd} (hora {sendingTimezone.split("/").pop()?.replace("_", " ")}).
                  </p>
                </div>
              )}
            </div>

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
              <Play size={14} /> Iniciar Pipeline
            </button>
          )}
          {selected?.status === "ready" && (
            <button
              onClick={sendDMs}
              className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500"
            >
              <Send size={14} /> Enviar DMs
            </button>
          )}
          <button
            onClick={() => {
              loadCampaigns();
              if (selected) loadLeads(selected.id);
            }}
            className="rounded-lg border border-zinc-200 p-2 text-zinc-500 hover:bg-zinc-50"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* Progress indicator */}
      {selected && !["draft", "pending", "ready", "completed", "failed", "paused"].includes(selected.status) && (
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

      {/* Pending/Paused banner */}
      {selected?.status === "pending" && (
        <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
          <p className="text-sm text-zinc-600">
            Campaña en cola — esperando un worker disponible. Puedes seleccionar otra campaña mientras tanto.
          </p>
        </div>
      )}
      {selected?.status === "paused" && (
        <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-3">
          <p className="text-sm text-yellow-800">
            Campaña pausada — puede ser por rate limit, bloqueo de cuenta o cooldown activo.
          </p>
        </div>
      )}

      {/* Stats Row */}
      {selected && (
        <div className="grid grid-cols-4 md:grid-cols-8 gap-3">
          {statItems.map((s) => (
            <div
              key={s.label}
              className="rounded-lg border border-zinc-200 bg-white p-3 text-center"
            >
              <p className={cn(
                "font-semibold text-zinc-900",
                s.isText ? "text-sm capitalize" : "text-2xl"
              )}>{s.value}</p>
              <p className="text-xs text-zinc-500 mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      {selected && (
        <div className="flex border-b border-zinc-200 overflow-x-auto">
          {([
            { key: "stats" as TabKey, label: "Resumen" },
            { key: "leads" as TabKey, label: "Leads" },
            { key: "dms" as TabKey, label: "DMs" },
            { key: "inbox" as TabKey, label: "Inbox" },
            { key: "followups" as TabKey, label: "Seguimientos" },
            { key: "analytics" as TabKey, label: "Analíticas" },
            { key: "ab_testing" as TabKey, label: "A/B Testing" },
            { key: "content" as TabKey, label: "Análisis de Contenido" },
            { key: "export" as TabKey, label: "Exportar" },
          ]).map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap",
                tab === t.key
                  ? "border-amber-500 text-zinc-900"
                  : "border-transparent text-zinc-500 hover:text-zinc-700"
              )}
            >
              {t.label}
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

          <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-100 bg-zinc-50">
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-600">
                    Username
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-600">
                    Bio
                  </th>
                  <th className="px-4 py-2.5 text-right font-medium text-zinc-600">
                    Seguidores
                  </th>
                  <th className="px-4 py-2.5 text-center font-medium text-zinc-600">
                    Score
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-600">
                    Categoría
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-600">
                    Estado
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-zinc-600">
                    Preview DM
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredLeads.slice(0, 100).map((lead) => (
                  <tr
                    key={lead.id}
                    className="border-b border-zinc-50 hover:bg-zinc-50"
                  >
                    <td className="px-4 py-2.5">
                      <div className="font-mono text-xs">@{lead.ig_username}</div>
                      {lead.ig_full_name && (
                        <div className="text-xs text-zinc-400">{lead.ig_full_name}</div>
                      )}
                    </td>
                    <td className="px-4 py-2.5 max-w-[200px]">
                      {lead.ig_bio_clean ? (
                        <p className="text-xs text-zinc-500 line-clamp-2" title={lead.ig_bio_clean}>
                          {lead.ig_bio_clean}
                        </p>
                      ) : (
                        <span className="text-xs text-zinc-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs tabular-nums text-zinc-600">
                      {lead.ig_follower_count != null
                        ? lead.ig_follower_count.toLocaleString()
                        : "—"}
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
                        <span className="text-xs text-zinc-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {(lead.category || lead.lead_category) ? (
                        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
                          {lead.category || lead.lead_category}
                        </span>
                      ) : (
                        <span className="text-xs text-zinc-300">—</span>
                      )}
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
                    <td className="px-4 py-2.5 max-w-[250px]">
                      {lead.dm_message ? (
                        <button
                          onClick={() => setDmPreview(lead)}
                          className="text-xs text-amber-600 hover:text-amber-800 text-left line-clamp-2 cursor-pointer"
                          title="Click para ver DM completo"
                        >
                          {lead.dm_message}
                        </button>
                      ) : (
                        <span className="text-xs text-zinc-300">—</span>
                      )}
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

          {/* DM Preview Modal */}
          {dmPreview && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setDmPreview(null)}>
              <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl space-y-4" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-zinc-900">
                    DM para @{dmPreview.ig_username}
                  </h3>
                  <button onClick={() => setDmPreview(null)} className="text-zinc-400 hover:text-zinc-600">
                    <X size={18} />
                  </button>
                </div>
                <div>
                  <p className="text-xs font-medium text-zinc-500 mb-1">Variante A</p>
                  <div className="rounded-md bg-zinc-50 p-3 text-sm text-zinc-700 leading-relaxed">
                    {dmPreview.dm_message}
                  </div>
                </div>
                {dmPreview.dm_variant_b && (
                  <div>
                    <p className="text-xs font-medium text-zinc-500 mb-1">Variante B</p>
                    <div className="rounded-md bg-zinc-50 p-3 text-sm text-zinc-600 leading-relaxed">
                      {dmPreview.dm_variant_b}
                    </div>
                  </div>
                )}
                {dmPreview.score !== null && (
                  <div className="flex items-center gap-2 text-xs text-zinc-500">
                    <span>Score: <strong>{dmPreview.score}</strong></span>
                    {(dmPreview.category || dmPreview.lead_category) && (
                      <span className="rounded-full bg-zinc-100 px-2 py-0.5">
                        {dmPreview.category || dmPreview.lead_category}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
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

      {/* ═══ Follow-ups Tab ═══ */}
      {selected && tab === "followups" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
              <ListOrdered size={16} className="text-amber-600" />
              Reglas de Follow-up ({followUpRules.length})
            </h3>
            <button
              onClick={() => {
                setNewRule({
                  step_number: followUpRules.length + 1,
                  delay_days: 3,
                  template_prompt: "",
                  max_attempts: 3,
                });
                setShowNewRule(true);
              }}
              className="flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-800"
            >
              <Plus size={14} /> Nueva Regla
            </button>
          </div>

          <p className="text-xs text-zinc-500">
            Define pasos de seguimiento automático. Si un lead no responde después de X días, se envía un follow-up generado por IA.
          </p>

          {/* New rule form */}
          {showNewRule && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-3">
              <h4 className="text-sm font-semibold text-zinc-900">Crear Regla</h4>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-xs font-medium text-zinc-600 mb-1 block">Paso #</label>
                  <input
                    type="number"
                    min={1}
                    value={newRule.step_number}
                    onChange={(e) => setNewRule({ ...newRule, step_number: parseInt(e.target.value) || 1 })}
                    className="w-full rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-zinc-600 mb-1 block">Esperar (días)</label>
                  <input
                    type="number"
                    min={1}
                    value={newRule.delay_days}
                    onChange={(e) => setNewRule({ ...newRule, delay_days: parseInt(e.target.value) || 1 })}
                    className="w-full rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-zinc-600 mb-1 block">Max intentos</label>
                  <input
                    type="number"
                    min={1}
                    max={5}
                    value={newRule.max_attempts}
                    onChange={(e) => setNewRule({ ...newRule, max_attempts: parseInt(e.target.value) || 3 })}
                    className="w-full rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-zinc-600 mb-1 block">Prompt para Claude (opcional)</label>
                <textarea
                  rows={2}
                  value={newRule.template_prompt}
                  onChange={(e) => setNewRule({ ...newRule, template_prompt: e.target.value })}
                  placeholder="Ej: Sé breve, ofrece un caso de estudio como valor adicional..."
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm resize-none"
                />
              </div>
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => setShowNewRule(false)}
                  className="rounded-md border border-zinc-200 px-3 py-1.5 text-sm hover:bg-white"
                >
                  Cancelar
                </button>
                <button
                  onClick={async () => {
                    try {
                      await api("/api/v1/follow-ups/", {
                        method: "POST",
                        body: JSON.stringify({
                          campaign_id: selected.id,
                          ...newRule,
                          template_prompt: newRule.template_prompt || null,
                        }),
                      });
                      const rules = await api<FollowUpRule[]>(`/api/v1/follow-ups/?campaign_id=${selected.id}`);
                      setFollowUpRules(rules);
                      setShowNewRule(false);
                    } catch { /* ignore */ }
                  }}
                  className="rounded-md bg-amber-500 px-3 py-1.5 text-sm font-medium text-black hover:bg-amber-400"
                >
                  Crear
                </button>
              </div>
            </div>
          )}

          {/* Rules list */}
          {followUpRules.length === 0 && !showNewRule ? (
            <div className="text-center py-16 text-zinc-400">
              <ListOrdered size={40} className="mx-auto mb-3 opacity-40" />
              <p>No hay reglas de follow-up para esta campaña.</p>
              <p className="text-sm mt-1">Crea una regla para que el bot haga seguimiento automático a leads que no responden.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {followUpRules.map((rule) => (
                <div
                  key={rule.id}
                  className={cn(
                    "rounded-lg border bg-white p-4 flex items-center justify-between",
                    rule.is_active ? "border-zinc-200" : "border-zinc-100 opacity-60"
                  )}
                >
                  <div className="flex items-center gap-4">
                    <div className="h-9 w-9 rounded-full bg-amber-100 flex items-center justify-center text-sm font-bold text-amber-700">
                      {rule.step_number}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-zinc-900">
                        Paso {rule.step_number}: Esperar {rule.delay_days} día{rule.delay_days !== 1 ? "s" : ""} sin respuesta
                      </p>
                      <p className="text-xs text-zinc-500">
                        Max {rule.max_attempts} intentos
                        {rule.template_prompt && ` — Prompt: "${rule.template_prompt.slice(0, 60)}${rule.template_prompt.length > 60 ? "..." : ""}"`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={async () => {
                        await api(`/api/v1/follow-ups/${rule.id}`, {
                          method: "PUT",
                          body: JSON.stringify({ is_active: !rule.is_active }),
                        });
                        const rules = await api<FollowUpRule[]>(`/api/v1/follow-ups/?campaign_id=${selected.id}`);
                        setFollowUpRules(rules);
                      }}
                      className={cn(
                        "rounded-full px-2.5 py-0.5 text-xs font-medium",
                        rule.is_active ? "bg-emerald-100 text-emerald-700" : "bg-zinc-100 text-zinc-500"
                      )}
                    >
                      {rule.is_active ? "Activo" : "Inactivo"}
                    </button>
                    <button
                      onClick={async () => {
                        if (!confirm("¿Eliminar esta regla?")) return;
                        await api(`/api/v1/follow-ups/${rule.id}`, { method: "DELETE" });
                        setFollowUpRules((prev) => prev.filter((r) => r.id !== rule.id));
                      }}
                      className="p-1.5 rounded text-zinc-400 hover:text-red-500 hover:bg-red-50"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ═══ Inbox Tab ═══ */}
      {selected && tab === "inbox" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
              <Inbox size={16} className="text-amber-600" />
              Respuestas Recibidas ({replies.length})
            </h3>
            <select
              value={replyFilter}
              onChange={(e) => setReplyFilter(e.target.value)}
              className="rounded-lg border border-zinc-200 px-3 py-1.5 text-sm"
            >
              <option value="">Todas</option>
              <option value="positive">Positivas</option>
              <option value="negative">Negativas</option>
              <option value="question">Preguntas</option>
              <option value="spam">Spam</option>
            </select>
          </div>

          {/* Classification summary */}
          {replies.length > 0 && (
            <div className="grid grid-cols-4 gap-3">
              {(["positive", "negative", "question", "spam"] as const).map((cls) => {
                const count = replies.filter((r) => r.reply_classification === cls).length;
                const colors: Record<string, string> = {
                  positive: "text-emerald-600 bg-emerald-50 border-emerald-200",
                  negative: "text-red-600 bg-red-50 border-red-200",
                  question: "text-blue-600 bg-blue-50 border-blue-200",
                  spam: "text-zinc-500 bg-zinc-50 border-zinc-200",
                };
                return (
                  <button
                    key={cls}
                    onClick={() => setReplyFilter(replyFilter === cls ? "" : cls)}
                    className={cn(
                      "rounded-lg border p-3 text-center transition-colors",
                      replyFilter === cls ? colors[cls] : "border-zinc-200 bg-white hover:bg-zinc-50"
                    )}
                  >
                    <p className={cn("text-2xl font-bold", replyFilter === cls ? "" : "text-zinc-900")}>{count}</p>
                    <p className="text-xs capitalize">{cls === "question" ? "Preguntas" : cls === "positive" ? "Positivas" : cls === "negative" ? "Negativas" : "Spam"}</p>
                  </button>
                );
              })}
            </div>
          )}

          {/* Reply cards */}
          {replies.length === 0 ? (
            <div className="text-center py-16 text-zinc-400">
              <Inbox size={40} className="mx-auto mb-3 opacity-40" />
              <p>No hay respuestas {replyFilter ? `clasificadas como "${replyFilter}"` : "todavía"}.</p>
              <p className="text-sm mt-1">Las respuestas aparecen cuando el inbox monitor detecta replies.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {replies.map((lead) => {
                const clsColors: Record<string, string> = {
                  positive: "border-l-emerald-500",
                  negative: "border-l-red-500",
                  question: "border-l-blue-500",
                  spam: "border-l-zinc-400",
                };
                return (
                  <div
                    key={lead.id}
                    className={cn(
                      "rounded-lg border border-zinc-200 bg-white p-4 border-l-4",
                      clsColors[lead.reply_classification || ""] || "border-l-zinc-300"
                    )}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-zinc-900">@{lead.ig_username}</span>
                        {lead.score !== null && (
                          <span className={cn(
                            "rounded-full h-6 w-6 flex items-center justify-center text-[10px] font-bold",
                            (lead.score || 0) >= 70 ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
                          )}>
                            {lead.score}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        {lead.reply_classification && (
                          <span className={cn(
                            "rounded-full px-2 py-0.5 text-xs font-medium capitalize",
                            lead.reply_classification === "positive" ? "bg-emerald-100 text-emerald-700" :
                            lead.reply_classification === "negative" ? "bg-red-100 text-red-700" :
                            lead.reply_classification === "question" ? "bg-blue-100 text-blue-700" :
                            "bg-zinc-100 text-zinc-600"
                          )}>
                            {lead.reply_classification}
                          </span>
                        )}
                        {lead.replied_at && (
                          <span className="text-[11px] text-zinc-400">
                            {new Date(lead.replied_at).toLocaleString()}
                          </span>
                        )}
                      </div>
                    </div>
                    {/* Original DM sent */}
                    {lead.dm_message && (
                      <div className="rounded-md bg-zinc-50 p-2.5 text-xs text-zinc-500 mb-2">
                        <span className="font-medium text-zinc-400">Tu DM:</span> {lead.dm_message}
                      </div>
                    )}
                    {/* Reply */}
                    {lead.reply_text && (
                      <div className="rounded-md bg-amber-50 border border-amber-100 p-2.5 text-sm text-zinc-800">
                        <span className="font-medium text-amber-600">Respuesta:</span> {lead.reply_text}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
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

      {/* ═══ Analytics Tab ═══ */}
      {selected && tab === "analytics" && (
        <div className="space-y-4">
          {!analytics ? (
            <div className="flex items-center justify-center h-40">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-amber-500" />
            </div>
          ) : (
            <>
              {/* Key Metrics */}
              <div className="grid grid-cols-3 gap-4">
                <div className="rounded-lg border border-zinc-200 bg-white p-5 text-center">
                  <p className="text-3xl font-bold text-zinc-900">{analytics.total_leads}</p>
                  <p className="text-xs text-zinc-500 mt-1">Total Leads</p>
                </div>
                <div className="rounded-lg border border-zinc-200 bg-white p-5 text-center">
                  <p className="text-3xl font-bold text-amber-600">{analytics.response_rate.toFixed(1)}%</p>
                  <p className="text-xs text-zinc-500 mt-1">Tasa de Respuesta</p>
                </div>
                <div className="rounded-lg border border-zinc-200 bg-white p-5 text-center">
                  <p className="text-3xl font-bold text-zinc-900">{analytics.avg_score.toFixed(0)}</p>
                  <p className="text-xs text-zinc-500 mt-1">Score Promedio</p>
                </div>
              </div>

              {/* Funnel */}
              <div className="rounded-lg border border-zinc-200 bg-white p-5">
                <h3 className="text-sm font-semibold text-zinc-900 mb-4 flex items-center gap-2">
                  <BarChart3 size={16} className="text-amber-600" />
                  Funnel de Conversión
                </h3>
                <div className="space-y-3">
                  {analytics.funnel.map((step, i) => {
                    const maxCount = analytics.funnel[0]?.count || 1;
                    const widthPct = Math.max((step.count / maxCount) * 100, 4);
                    return (
                      <div key={step.name} className="flex items-center gap-3">
                        <span className="text-xs text-zinc-500 w-24 text-right capitalize">{step.name}</span>
                        <div className="flex-1 h-7 bg-zinc-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-amber-500 rounded-full flex items-center justify-end pr-2 transition-all"
                            style={{ width: `${widthPct}%` }}
                          >
                            <span className="text-[10px] font-bold text-white">{step.count}</span>
                          </div>
                        </div>
                        <span className="text-xs text-zinc-400 w-12">{step.percentage.toFixed(0)}%</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Score Distribution */}
                <div className="rounded-lg border border-zinc-200 bg-white p-5">
                  <h3 className="text-sm font-semibold text-zinc-900 mb-4">Distribución de Scores</h3>
                  <div className="space-y-2">
                    {analytics.score_distribution.map((bucket) => {
                      const maxBucket = Math.max(...analytics.score_distribution.map((b) => b.count), 1);
                      return (
                        <div key={bucket.range_label} className="flex items-center gap-2">
                          <span className="text-xs text-zinc-500 w-12">{bucket.range_label}</span>
                          <div className="flex-1 h-5 bg-zinc-100 rounded overflow-hidden">
                            <div
                              className="h-full bg-emerald-500 rounded transition-all"
                              style={{ width: `${(bucket.count / maxBucket) * 100}%` }}
                            />
                          </div>
                          <span className="text-xs font-medium text-zinc-700 w-8 text-right">{bucket.count}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Category Breakdown */}
                <div className="rounded-lg border border-zinc-200 bg-white p-5">
                  <h3 className="text-sm font-semibold text-zinc-900 mb-4">Categorías</h3>
                  {analytics.category_breakdown.length === 0 ? (
                    <p className="text-sm text-zinc-400">Sin datos de categorías</p>
                  ) : (
                    <div className="space-y-2">
                      {analytics.category_breakdown.map((cat) => (
                        <div key={cat.category} className="flex items-center justify-between py-1.5 border-b border-zinc-50 last:border-0">
                          <span className="text-sm text-zinc-700 capitalize">{cat.category || "Sin categoría"}</span>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-zinc-400">{cat.percentage.toFixed(0)}%</span>
                            <span className="text-sm font-semibold text-zinc-900">{cat.count}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ═══ A/B Testing Tab ═══ */}
      {selected && tab === "ab_testing" && (
        <div className="space-y-4">
          {!abResults ? (
            <div className="flex items-center justify-center h-40">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-amber-500" />
            </div>
          ) : abResults.total_sent === 0 ? (
            <div className="text-center py-16 text-zinc-400">
              <FlaskConical size={40} className="mx-auto mb-3 opacity-40" />
              <p>No hay datos de A/B testing todavía.</p>
              <p className="text-sm">Los resultados aparecerán cuando se envíen DMs.</p>
            </div>
          ) : (
            <>
              {/* Winner Banner */}
              {abResults.winner && (
                <div className={cn(
                  "rounded-lg border p-4 flex items-center gap-3",
                  abResults.confidence === "high"
                    ? "border-emerald-200 bg-emerald-50"
                    : "border-amber-200 bg-amber-50"
                )}>
                  <FlaskConical size={20} className={abResults.confidence === "high" ? "text-emerald-600" : "text-amber-600"} />
                  <div>
                    <p className={cn("text-sm font-bold", abResults.confidence === "high" ? "text-emerald-800" : "text-amber-800")}>
                      Ganador: Variante {abResults.winner}
                    </p>
                    <p className={cn("text-xs", abResults.confidence === "high" ? "text-emerald-600" : "text-amber-600")}>
                      Confianza: {abResults.confidence} — {abResults.recommendation}
                    </p>
                  </div>
                </div>
              )}

              {/* Side by side comparison */}
              <div className="grid grid-cols-2 gap-4">
                {(["variant_a", "variant_b"] as const).map((variant) => {
                  const data = abResults[variant];
                  const isWinner = abResults.winner === (variant === "variant_a" ? "A" : "B");
                  return (
                    <div
                      key={variant}
                      className={cn(
                        "rounded-lg border bg-white p-5",
                        isWinner ? "border-emerald-300 ring-2 ring-emerald-100" : "border-zinc-200"
                      )}
                    >
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="text-sm font-bold text-zinc-900">
                          Variante {variant === "variant_a" ? "A" : "B"}
                        </h3>
                        {isWinner && (
                          <span className="text-[10px] font-bold bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">
                            GANADOR
                          </span>
                        )}
                      </div>
                      <div className="space-y-3">
                        <div className="flex justify-between border-b border-zinc-50 pb-2">
                          <span className="text-xs text-zinc-500">Enviados</span>
                          <span className="text-sm font-semibold">{data.sent}</span>
                        </div>
                        <div className="flex justify-between border-b border-zinc-50 pb-2">
                          <span className="text-xs text-zinc-500">Respondidos</span>
                          <span className="text-sm font-semibold">{data.replied}</span>
                        </div>
                        <div className="flex justify-between border-b border-zinc-50 pb-2">
                          <span className="text-xs text-zinc-500">Tasa de respuesta</span>
                          <span className="text-sm font-bold text-amber-600">{data.reply_rate.toFixed(1)}%</span>
                        </div>
                        <div className="flex justify-between border-b border-zinc-50 pb-2">
                          <span className="text-xs text-zinc-500">Respuestas positivas</span>
                          <span className="text-sm font-semibold text-emerald-600">{data.positive_replies}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-xs text-zinc-500">Tasa de conversión</span>
                          <span className="text-sm font-bold text-emerald-600">{data.conversion_rate.toFixed(1)}%</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="text-center text-xs text-zinc-400">
                Total enviados: {abResults.total_sent} — Confianza: {abResults.confidence}
              </div>
            </>
          )}
        </div>
      )}

      {/* ═══ Content Analysis Tab ═══ */}
      {selected && tab === "content" && (
        <div className="space-y-4">
          {/* Input Panel */}
          <div className="rounded-lg border border-zinc-200 bg-white p-5 space-y-4">
            <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
              <Sparkles size={16} className="text-amber-600" />
              Análisis de Contenido con Gemini
            </h3>
            <p className="text-xs text-zinc-500">
              Analiza el contenido de tu negocio (videos, imágenes, páginas web) para que la IA genere mejores DMs personalizados.
            </p>
            <div>
              <label className="text-xs font-medium text-zinc-600 mb-1 block">
                URLs de contenido (una por línea)
              </label>
              <textarea
                rows={3}
                value={contentUrls}
                onChange={(e) => setContentUrls(e.target.value)}
                placeholder={"https://youtube.com/watch?v=...\nhttps://instagram.com/reel/...\nhttps://tu-sitio-web.com"}
                className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none resize-y"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-zinc-600 mb-1 block">
                Texto adicional (descripción de tu negocio, propuesta de valor, etc.)
              </label>
              <textarea
                rows={3}
                value={contentText}
                onChange={(e) => setContentText(e.target.value)}
                placeholder="Describe tu negocio, servicios, público objetivo..."
                className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none resize-y"
              />
            </div>
            <button
              onClick={runContentAnalysis}
              disabled={analyzing || (!contentUrls.trim() && !contentText.trim())}
              className="flex items-center gap-1.5 rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-black hover:bg-amber-400 disabled:opacity-50"
            >
              {analyzing ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Sparkles size={14} />
              )}
              {analyzing ? "Analizando..." : "Analizar con Gemini"}
            </button>
          </div>

          {/* Results */}
          {contentAnalysis && (
            <div className="rounded-lg border border-zinc-200 bg-white p-5 space-y-4">
              <h3 className="text-sm font-semibold text-zinc-900">Resultados del Análisis</h3>

              <div>
                <p className="text-xs font-medium text-zinc-500 mb-1">Resumen del Negocio</p>
                <p className="text-sm text-zinc-700 leading-relaxed">{contentAnalysis.business_summary}</p>
              </div>

              <div>
                <p className="text-xs font-medium text-zinc-500 mb-1">Público Objetivo</p>
                <p className="text-sm text-zinc-700">{contentAnalysis.target_audience}</p>
              </div>

              <div>
                <p className="text-xs font-medium text-zinc-500 mb-1">Tono y Estilo</p>
                <p className="text-sm text-zinc-700">{contentAnalysis.tone_style}</p>
              </div>

              {contentAnalysis.value_propositions?.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-zinc-500 mb-1">Propuestas de Valor</p>
                  <ul className="space-y-1">
                    {contentAnalysis.value_propositions.map((vp, i) => (
                      <li key={i} className="text-sm text-zinc-700 flex items-start gap-2">
                        <span className="text-amber-500 mt-0.5">•</span> {vp}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {contentAnalysis.key_differentiators?.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-zinc-500 mb-1">Diferenciadores Clave</p>
                  <div className="flex flex-wrap gap-2">
                    {contentAnalysis.key_differentiators.map((d, i) => (
                      <span key={i} className="rounded-full bg-amber-50 border border-amber-200 px-2.5 py-0.5 text-xs text-amber-700">
                        {d}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {contentAnalysis.pain_points_addressed?.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-zinc-500 mb-1">Pain Points que Resuelve</p>
                  <ul className="space-y-1">
                    {contentAnalysis.pain_points_addressed.map((pp, i) => (
                      <li key={i} className="text-sm text-zinc-700 flex items-start gap-2">
                        <span className="text-red-400 mt-0.5">•</span> {pp}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="pt-2 border-t border-zinc-100 text-xs text-zinc-400">
                Tipo de contenido detectado: {contentAnalysis.content_type_detected}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ═══ Export Tab ═══ */}
      {selected && tab === "export" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-zinc-200 bg-white p-6">
            <h3 className="text-sm font-semibold text-zinc-900 mb-2 flex items-center gap-2">
              <Download size={16} className="text-amber-600" />
              Exportar Leads con DMs
            </h3>
            <p className="text-xs text-zinc-500 mb-6">
              Descarga los leads con DMs generados (status: dm_ready) en el formato que prefieras.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {(["csv", "json", "excel"] as const).map((fmt) => (
                <button
                  key={fmt}
                  onClick={() => downloadExport(fmt)}
                  disabled={exporting !== null}
                  className="rounded-lg border-2 border-dashed border-zinc-300 p-6 text-center hover:border-amber-400 hover:bg-amber-50 transition-colors disabled:opacity-50"
                >
                  {exporting === fmt ? (
                    <Loader2 size={24} className="mx-auto mb-2 text-amber-500 animate-spin" />
                  ) : (
                    <Download size={24} className="mx-auto mb-2 text-zinc-400" />
                  )}
                  <p className="text-sm font-semibold text-zinc-900">{fmt.toUpperCase()}</p>
                  <p className="text-xs text-zinc-500 mt-1">
                    {fmt === "csv" ? "Ideal para hojas de cálculo" : fmt === "json" ? "Para integración con APIs" : "Con formato y colores"}
                  </p>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ═══ Activity Log ═══ */}
      {selected && activityLog.length > 0 && (
        <div className="rounded-lg border border-zinc-200 bg-white">
          <div className="flex items-center gap-2 px-5 py-3 border-b border-zinc-100">
            <Clock size={14} className="text-zinc-400" />
            <h3 className="text-sm font-semibold text-zinc-900">Actividad Reciente</h3>
          </div>
          <div className="divide-y divide-zinc-50">
            {activityLog.map((event) => (
              <div key={event.id} className="flex items-start gap-3 px-5 py-3">
                <div className={`mt-0.5 h-2 w-2 rounded-full shrink-0 ${
                  event.level === "success" ? "bg-emerald-500" :
                  event.level === "warning" ? "bg-amber-500" :
                  event.level === "error" ? "bg-red-500" :
                  "bg-blue-500"
                }`} />
                <div className="flex-1 min-w-0">
                  <p className={`text-sm ${LEVEL_COLORS[event.level] || "text-zinc-700"}`}>
                    {event.message}
                  </p>
                  <p className="text-[11px] text-zinc-400 mt-0.5">
                    {new Date(event.created_at).toLocaleString()} — {event.event_type}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
