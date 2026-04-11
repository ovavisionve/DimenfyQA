"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  BarChart3,
  FileText,
  Printer,
  TrendingUp,
  Users,
  Send,
  MessageSquare,
  Loader2,
  Target,
  FileSpreadsheet,
  FileJson,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { t, getLocale, type Locale } from "@/lib/i18n";

interface Client {
  id: string;
  name: string;
  business_type: string;
}

interface Campaign {
  id: string;
  client_id: string;
  name: string;
  status: string;
  source_type: string;
  source_value: string;
  stats: Record<string, unknown>;
  created_at: string;
}

interface CampaignStatsRow {
  campaign_id: string;
  total_leads: number;
  scored_leads: number;
  researched_leads: number;
  dm_ready_leads: number;
  sent_leads: number;
  failed_leads: number;
  avg_score: number | null;
  status: string;
}

interface ClientAnalytics {
  client_id: string;
  total_campaigns: number;
  total_leads: number;
  total_sent: number;
  total_replied: number;
  avg_score: number;
  response_rate: number;
  total_scored: number;
  total_dm_ready: number;
}

type CampaignRow = Campaign & { stats_detail?: CampaignStatsRow };

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:1000";

export default function ReportsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [selectedClient, setSelectedClient] = useState<string>("");
  const [campaigns, setCampaigns] = useState<CampaignRow[]>([]);
  const [analytics, setAnalytics] = useState<ClientAnalytics | null>(null);
  const [loading, setLoading] = useState(false);
  const [locale, setLocaleState] = useState<Locale>("es");

  useEffect(() => {
    setLocaleState(getLocale());
    const handler = () => setLocaleState(getLocale());
    window.addEventListener("locale-change", handler);
    return () => window.removeEventListener("locale-change", handler);
  }, []);

  useEffect(() => {
    api<Client[]>("/api/v1/clients/")
      .then((data) => {
        setClients(data);
        if (data.length > 0 && !selectedClient) {
          setSelectedClient(data[0].id);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedClient) return;
    setLoading(true);
    setAnalytics(null);
    setCampaigns([]);

    (async () => {
      const [analyticsRes, campaignsRes] = await Promise.all([
        api<ClientAnalytics>(`/api/v1/clients/${selectedClient}/analytics`).catch(
          () => null
        ),
        api<Campaign[]>(`/api/v1/campaigns/?client_id=${selectedClient}`).catch(
          () => [] as Campaign[]
        ),
      ]);

      setAnalytics(analyticsRes);

      const rows: CampaignRow[] = await Promise.all(
        campaignsRes.map(async (c) => {
          const stats = await api<CampaignStatsRow>(
            `/api/v1/campaigns/${c.id}/stats`
          ).catch(() => undefined);
          return { ...c, stats_detail: stats };
        })
      );
      setCampaigns(rows);
      setLoading(false);
    })();
  }, [selectedClient]);

  const handlePrint = () => window.print();

  const handleExport = async (
    campaignId: string,
    format: "csv" | "json" | "excel"
  ) => {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("access_token")
        : null;
    const url = `${API_BASE}/api/v1/export/${campaignId}/${format}`;
    try {
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const link = document.createElement("a");
      const ext = format === "excel" ? "xlsx" : format;
      link.href = URL.createObjectURL(blob);
      link.download = `campaign_${campaignId}.${ext}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(link.href);
    } catch (err) {
      alert(
        t("reports.exportError", locale) +
          ": " +
          (err instanceof Error ? err.message : "")
      );
    }
  };

  const selectedClientName =
    clients.find((c) => c.id === selectedClient)?.name || "";

  const responseRate =
    analytics && analytics.total_sent > 0
      ? ((analytics.total_replied / analytics.total_sent) * 100).toFixed(1)
      : "0.0";

  return (
    <div className="p-6 space-y-6 print:p-0">
      {/* Header (hidden on print) */}
      <div className="flex items-center justify-between print:hidden">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 flex items-center gap-2">
            <BarChart3 size={20} className="text-amber-500" />
            {t("reports.title", locale)}
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            {t("reports.subtitle", locale)}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={selectedClient}
            onChange={(e) => setSelectedClient(e.target.value)}
            className="bg-white border border-zinc-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
          >
            {clients.length === 0 && (
              <option value="">{t("common.loading", locale)}</option>
            )}
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>

          <button
            onClick={handlePrint}
            disabled={!analytics}
            className="flex items-center gap-2 bg-zinc-900 text-white rounded-lg px-3 py-2 text-sm font-medium hover:bg-zinc-800 disabled:bg-zinc-400 disabled:cursor-not-allowed"
          >
            <Printer size={14} />
            {t("reports.print", locale)}
          </button>
        </div>
      </div>

      {/* Printable header */}
      <div className="hidden print:block border-b border-zinc-300 pb-4 mb-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-zinc-900">
              {t("reports.printTitle", locale)}
            </h1>
            <p className="text-sm text-zinc-600 mt-1">
              {t("reports.printClient", locale)}: {selectedClientName}
            </p>
          </div>
          <div className="text-right text-xs text-zinc-500">
            <p>
              {t("reports.printGenerated", locale)}:{" "}
              {new Date().toLocaleString()}
            </p>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-zinc-400" />
        </div>
      ) : !analytics ? (
        <div className="bg-white border border-zinc-200 rounded-xl p-12 text-center">
          <FileText size={32} className="mx-auto text-zinc-300 mb-3" />
          <p className="text-sm text-zinc-500">
            {t("reports.noClient", locale)}
          </p>
        </div>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <KpiCard
              icon={<BarChart3 size={14} />}
              label={t("reports.campaigns", locale)}
              value={analytics.total_campaigns}
              color="amber"
            />
            <KpiCard
              icon={<Users size={14} />}
              label={t("reports.leads", locale)}
              value={analytics.total_leads}
              color="blue"
            />
            <KpiCard
              icon={<Target size={14} />}
              label={t("reports.dmReady", locale)}
              value={analytics.total_dm_ready}
              color="sky"
            />
            <KpiCard
              icon={<Send size={14} />}
              label={t("reports.sent", locale)}
              value={analytics.total_sent}
              color="emerald"
            />
            <KpiCard
              icon={<MessageSquare size={14} />}
              label={t("reports.replied", locale)}
              value={analytics.total_replied}
              color="purple"
            />
            <KpiCard
              icon={<TrendingUp size={14} />}
              label={t("reports.responseRate", locale)}
              value={`${responseRate}%`}
              color="rose"
            />
          </div>

          {/* Summary box */}
          <div className="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-xl p-4 print:bg-white print:border-zinc-300">
            <h3 className="text-sm font-semibold text-zinc-900 mb-2">
              {t("reports.summary", locale)}
            </h3>
            <p className="text-sm text-zinc-700 leading-relaxed">
              {t("reports.summaryText", locale)
                .replace("{client}", selectedClientName)
                .replace("{campaigns}", String(analytics.total_campaigns))
                .replace("{leads}", String(analytics.total_leads))
                .replace("{sent}", String(analytics.total_sent))
                .replace("{replied}", String(analytics.total_replied))
                .replace("{rate}", responseRate)
                .replace("{avg}", analytics.avg_score.toFixed(1))}
            </p>
          </div>

          {/* Campaign Table */}
          <div className="bg-white border border-zinc-200 rounded-xl overflow-hidden">
            <div className="p-4 border-b border-zinc-200 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-zinc-900">
                {t("reports.campaignsTable", locale)}
              </h2>
              <span className="text-xs text-zinc-500">
                {campaigns.length} {t("reports.results", locale)}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-zinc-50">
                  <tr className="text-left text-xs font-medium text-zinc-500 uppercase">
                    <th className="px-4 py-3">
                      {t("reports.campaign", locale)}
                    </th>
                    <th className="px-4 py-3">
                      {t("reports.status", locale)}
                    </th>
                    <th className="px-4 py-3 text-right">
                      {t("reports.leads", locale)}
                    </th>
                    <th className="px-4 py-3 text-right">
                      {t("reports.scored", locale)}
                    </th>
                    <th className="px-4 py-3 text-right">
                      {t("reports.dmReady", locale)}
                    </th>
                    <th className="px-4 py-3 text-right">
                      {t("reports.sent", locale)}
                    </th>
                    <th className="px-4 py-3 text-right">
                      {t("reports.failed", locale)}
                    </th>
                    <th className="px-4 py-3 text-right">
                      {t("reports.avgScore", locale)}
                    </th>
                    <th className="px-4 py-3 text-right print:hidden">
                      {t("reports.export", locale)}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {campaigns.map((c) => {
                    const s = c.stats_detail;
                    return (
                      <tr
                        key={c.id}
                        className="border-t border-zinc-100 hover:bg-zinc-50"
                      >
                        <td className="px-4 py-3">
                          <div className="font-medium text-zinc-900">
                            {c.name}
                          </div>
                          <div className="text-xs text-zinc-500 mt-0.5">
                            {new Date(c.created_at).toLocaleDateString()} ·{" "}
                            {c.source_type}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={c.status} />
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {s?.total_leads ?? 0}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums text-zinc-600">
                          {s?.scored_leads ?? 0}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums text-zinc-600">
                          {s?.dm_ready_leads ?? 0}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums font-medium text-emerald-600">
                          {s?.sent_leads ?? 0}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums text-red-600">
                          {s?.failed_leads ?? 0}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {s?.avg_score != null
                            ? s.avg_score.toFixed(1)
                            : "—"}
                        </td>
                        <td className="px-4 py-3 text-right print:hidden">
                          <div className="flex justify-end gap-1">
                            <button
                              onClick={() => handleExport(c.id, "csv")}
                              className="px-2 py-1 rounded border border-zinc-200 text-[11px] text-zinc-600 hover:bg-zinc-100 hover:border-zinc-300"
                              title="CSV"
                            >
                              <FileText size={12} />
                            </button>
                            <button
                              onClick={() => handleExport(c.id, "excel")}
                              className="px-2 py-1 rounded border border-zinc-200 text-[11px] text-zinc-600 hover:bg-zinc-100 hover:border-zinc-300"
                              title="Excel"
                            >
                              <FileSpreadsheet size={12} />
                            </button>
                            <button
                              onClick={() => handleExport(c.id, "json")}
                              className="px-2 py-1 rounded border border-zinc-200 text-[11px] text-zinc-600 hover:bg-zinc-100 hover:border-zinc-300"
                              title="JSON"
                            >
                              <FileJson size={12} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {campaigns.length === 0 && (
                    <tr>
                      <td
                        colSpan={9}
                        className="px-4 py-12 text-center text-zinc-500"
                      >
                        {t("reports.noCampaigns", locale)}
                      </td>
                    </tr>
                  )}
                </tbody>
                {campaigns.length > 0 && (
                  <tfoot className="bg-zinc-50 font-medium">
                    <tr className="border-t-2 border-zinc-200">
                      <td className="px-4 py-3 text-xs uppercase text-zinc-500">
                        {t("reports.total", locale)}
                      </td>
                      <td className="px-4 py-3"></td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {analytics.total_leads}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {analytics.total_scored}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {analytics.total_dm_ready}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-emerald-600">
                        {analytics.total_sent}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">—</td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {analytics.avg_score.toFixed(1)}
                      </td>
                      <td className="print:hidden"></td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </div>

          {/* Footer (printable) */}
          <div className="hidden print:block text-center text-xs text-zinc-500 pt-4 border-t border-zinc-300">
            <p>IG DM Engine — {t("reports.printFooter", locale)}</p>
          </div>
        </>
      )}
    </div>
  );
}

function KpiCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  color: "amber" | "blue" | "sky" | "emerald" | "purple" | "rose";
}) {
  const bg = {
    amber: "bg-amber-50 text-amber-700",
    blue: "bg-blue-50 text-blue-700",
    sky: "bg-sky-50 text-sky-700",
    emerald: "bg-emerald-50 text-emerald-700",
    purple: "bg-purple-50 text-purple-700",
    rose: "bg-rose-50 text-rose-700",
  }[color];

  return (
    <div className="bg-white border border-zinc-200 rounded-xl p-4 print:border-zinc-300">
      <div
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-medium uppercase tracking-wide mb-2",
          bg
        )}
      >
        {icon}
        <span>{label}</span>
      </div>
      <p className="text-2xl font-bold text-zinc-900 tabular-nums">{value}</p>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    completed: "bg-emerald-100 text-emerald-700",
    sending: "bg-blue-100 text-blue-700",
    ready: "bg-sky-100 text-sky-700",
    pending: "bg-zinc-100 text-zinc-700",
    paused: "bg-amber-100 text-amber-700",
    failed: "bg-red-100 text-red-700",
    scraping: "bg-indigo-100 text-indigo-700",
    scoring: "bg-indigo-100 text-indigo-700",
    researching: "bg-indigo-100 text-indigo-700",
    writing: "bg-indigo-100 text-indigo-700",
  };
  return (
    <span
      className={cn(
        "inline-block px-2 py-1 rounded-full text-[10px] font-medium capitalize",
        colors[status] || "bg-zinc-100 text-zinc-700"
      )}
    >
      {status}
    </span>
  );
}
