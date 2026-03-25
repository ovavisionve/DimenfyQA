"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Search, Copy, Check } from "lucide-react";
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
  campaign_id: string;
}

export default function DMsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [search, setSearch] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    api<Lead[]>("/api/v1/leads/?status=dm_ready&limit=500")
      .then(setLeads)
      .catch(() => {});
  }, []);

  const copy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const filtered = leads.filter(
    (l) =>
      l.dm_message &&
      (l.ig_username?.toLowerCase().includes(search.toLowerCase()) ||
        l.ig_full_name?.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-900">DMs Generados</h1>
        <p className="text-sm text-zinc-500">
          {filtered.length} DMs listos para enviar
        </p>
      </div>

      <div className="relative max-w-md">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
        <input
          placeholder="Buscar por username..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-lg border border-zinc-200 bg-white pl-9 pr-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
        />
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

            {lead.category && (
              <span className="inline-block rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-600">
                {lead.category}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
