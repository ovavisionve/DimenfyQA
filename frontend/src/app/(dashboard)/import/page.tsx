"use client";

import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import {
  Upload,
  FileSpreadsheet,
  Check,
  AlertCircle,
  Loader2,
  Download,
} from "lucide-react";
import { cn } from "@/lib/cn";

interface Campaign {
  id: string;
  name: string;
  status: string;
  client_id: string;
}

interface ImportResult {
  imported_count: number;
  skipped_count: number;
  errors: string[];
}

const SAMPLE_CSV = `ig_username,ig_full_name,biography,follower_count
juancoach,"Juan García","Coach de vida y negocios | Mentor",15000
mariaagency,"María López","Agencia de marketing digital",8500
carlosfitness,"Carlos Ruiz","Personal trainer certificado | Nutrición",22000`;

export default function ImportPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<Campaign[]>("/api/v1/campaigns/")
      .then(setCampaigns)
      .catch(() => {});
  }, []);

  const handleFile = (f: File) => {
    if (!f.name.endsWith(".csv")) {
      setError("Solo se aceptan archivos CSV");
      return;
    }
    setFile(f);
    setError("");
    setResult(null);
  };

  const handleImport = async () => {
    if (!file || !selectedCampaign) return;

    setImporting(true);
    setError("");
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const token = localStorage.getItem("access_token");

      const res = await fetch(
        `/api/v1/lead-import/upload-csv?campaign_id=${selectedCampaign}`,
        {
          method: "POST",
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: formData,
        }
      );

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }

      const data: ImportResult = await res.json();
      setResult(data);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setImporting(false);
    }
  };

  const downloadSample = () => {
    const blob = new Blob([SAMPLE_CSV], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "leads_example.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-2xl mx-auto py-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-900 flex items-center gap-2">
          <Upload size={20} className="text-amber-500" />
          Importar Leads (CSV)
        </h1>
        <p className="text-sm text-zinc-500 mt-1">
          Sube un archivo CSV con leads para agregarlos a una campaña sin usar
          Apify.
        </p>
      </div>

      {/* Campaign selector */}
      <div>
        <label className="block text-sm font-medium text-zinc-700 mb-1.5">
          Campaña destino
        </label>
        <select
          value={selectedCampaign}
          onChange={(e) => setSelectedCampaign(e.target.value)}
          className="w-full rounded-lg border border-zinc-200 px-3 py-2.5 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
        >
          <option value="">Seleccionar campaña...</option>
          {campaigns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.status})
            </option>
          ))}
        </select>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
        }}
        onClick={() => fileRef.current?.click()}
        className={cn(
          "border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors",
          dragOver
            ? "border-amber-500 bg-amber-50"
            : file
            ? "border-emerald-300 bg-emerald-50"
            : "border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50"
        )}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".csv"
          onChange={(e) => {
            if (e.target.files?.[0]) handleFile(e.target.files[0]);
          }}
          className="hidden"
        />

        {file ? (
          <div className="space-y-2">
            <FileSpreadsheet size={32} className="mx-auto text-emerald-500" />
            <p className="text-sm font-medium text-zinc-900">{file.name}</p>
            <p className="text-xs text-zinc-500">
              {(file.size / 1024).toFixed(1)} KB
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            <Upload size={32} className="mx-auto text-zinc-400" />
            <p className="text-sm text-zinc-600">
              Arrastra un CSV aquí o haz click para seleccionar
            </p>
            <p className="text-xs text-zinc-400">
              Columnas: ig_username (requerido), ig_full_name, biography,
              follower_count
            </p>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleImport}
          disabled={!file || !selectedCampaign || importing}
          className="flex items-center gap-2 rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-medium text-black hover:bg-amber-400 disabled:opacity-50 transition-colors"
        >
          {importing ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Upload size={14} />
          )}
          {importing ? "Importando..." : "Importar Leads"}
        </button>

        <button
          onClick={downloadSample}
          className="flex items-center gap-2 rounded-lg border border-zinc-200 px-4 py-2.5 text-sm text-zinc-600 hover:bg-zinc-50 transition-colors"
        >
          <Download size={14} />
          Descargar ejemplo CSV
        </button>
      </div>

      {/* Result */}
      {result && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 space-y-2">
          <div className="flex items-center gap-2">
            <Check size={18} className="text-emerald-600" />
            <h3 className="text-sm font-semibold text-emerald-800">
              Importación completada
            </h3>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-emerald-600">Importados:</span>{" "}
              <span className="font-medium">{result.imported_count}</span>
            </div>
            <div>
              <span className="text-amber-600">Omitidos (duplicados):</span>{" "}
              <span className="font-medium">{result.skipped_count}</span>
            </div>
          </div>
          {result.errors.length > 0 && (
            <div className="mt-2">
              <p className="text-xs font-medium text-red-600 mb-1">
                Errores ({result.errors.length}):
              </p>
              <ul className="text-xs text-red-500 space-y-0.5 max-h-24 overflow-y-auto">
                {result.errors.map((err, i) => (
                  <li key={i}>- {err}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-2">
          <AlertCircle size={16} className="text-red-500 mt-0.5 shrink-0" />
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      {/* Format help */}
      <div className="bg-zinc-50 rounded-xl p-5 space-y-3">
        <h3 className="text-sm font-semibold text-zinc-700">
          Formato del CSV
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-zinc-200">
                <th className="text-left py-2 px-3 text-zinc-500 font-medium">
                  Columna
                </th>
                <th className="text-left py-2 px-3 text-zinc-500 font-medium">
                  Requerido
                </th>
                <th className="text-left py-2 px-3 text-zinc-500 font-medium">
                  Descripción
                </th>
              </tr>
            </thead>
            <tbody className="text-zinc-600">
              <tr className="border-b border-zinc-100">
                <td className="py-2 px-3 font-mono">ig_username</td>
                <td className="py-2 px-3 text-emerald-600">Sí</td>
                <td className="py-2 px-3">Username de Instagram (sin @)</td>
              </tr>
              <tr className="border-b border-zinc-100">
                <td className="py-2 px-3 font-mono">ig_full_name</td>
                <td className="py-2 px-3 text-zinc-400">No</td>
                <td className="py-2 px-3">Nombre completo</td>
              </tr>
              <tr className="border-b border-zinc-100">
                <td className="py-2 px-3 font-mono">biography</td>
                <td className="py-2 px-3 text-zinc-400">No</td>
                <td className="py-2 px-3">Biografía de Instagram</td>
              </tr>
              <tr>
                <td className="py-2 px-3 font-mono">follower_count</td>
                <td className="py-2 px-3 text-zinc-400">No</td>
                <td className="py-2 px-3">Número de seguidores</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
