"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import {
  Target,
  Gauge,
  Flame,
  ShieldCheck,
  MessageCircle,
  MessageSquare,
  Brain,
  RefreshCw,
} from "lucide-react";

/* ───────────────────── Types ───────────────────── */

interface SystemSettings {
  scoring: {
    default_score_threshold: number;
    research_score_threshold: number;
    dm_score_threshold: number;
  };
  sending: {
    daily_dm_limit: number;
    hourly_dm_limit: number;
    dm_delay_min: number;
    dm_delay_max: number;
    use_playwright: boolean;
  };
  warmup: {
    warmup_days: number;
    warmup_start_limit: number;
  };
  safety: {
    pre_send_check_public: boolean;
    skip_private_accounts: boolean;
    challenge_cooldown_minutes: number;
    block_cooldown_hours: number;
    max_challenges_before_pause: number;
  };
  inbox: {
    inbox_check_interval: number;
    ab_test_enabled: boolean;
    ab_test_split: number;
    followup_check_interval: number;
    max_follow_up_steps: number;
  };
  comments: {
    comment_enabled: boolean;
    comment_score_threshold: number;
    daily_comment_limit: number;
    hourly_comment_limit: number;
    comment_delay_min: number;
    comment_delay_max: number;
  };
}

/* ───────────────────── Slider Component ───────────────────── */

function SettingSlider({
  label,
  desc,
  value,
  min,
  max,
  step,
  suffix,
  onChange,
}: {
  label: string;
  desc?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  onChange: (v: number) => void;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 border-b border-zinc-100 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-zinc-800">{label}</div>
        {desc && <div className="text-xs text-zinc-400 mt-0.5">{desc}</div>}
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-36 h-1.5 rounded-full appearance-none cursor-pointer accent-amber-500"
          style={{
            background: `linear-gradient(to right, #f59e0b ${pct}%, #e4e4e7 ${pct}%)`,
          }}
        />
        <span className="text-sm font-semibold text-zinc-900 w-16 text-right tabular-nums">
          {value}
          {suffix || ""}
        </span>
      </div>
    </div>
  );
}

/* ───────────────────── Toggle Component ───────────────────── */

function SettingToggle({
  label,
  desc,
  value,
  onChange,
}: {
  label: string;
  desc?: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 border-b border-zinc-100 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-zinc-800">{label}</div>
        {desc && <div className="text-xs text-zinc-400 mt-0.5">{desc}</div>}
      </div>
      <button
        onClick={() => onChange(!value)}
        className={`relative w-10 h-[22px] rounded-full transition-colors shrink-0 ${
          value ? "bg-amber-500" : "bg-zinc-300"
        }`}
      >
        <span
          className={`absolute top-0.5 h-[18px] w-[18px] rounded-full bg-white shadow transition-transform ${
            value ? "translate-x-[20px]" : "translate-x-0.5"
          }`}
        />
      </button>
    </div>
  );
}

/* ───────────────────── Locked Badge ───────────────────── */

function LockedSetting({ label, desc }: { label: string; desc: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 border-b border-zinc-100 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-zinc-800">{label}</div>
        <div className="text-xs text-zinc-400 mt-0.5">{desc}</div>
      </div>
      <span className="text-[11px] font-bold text-emerald-600 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full shrink-0">
        SIEMPRE ACTIVO
      </span>
    </div>
  );
}

/* ───────────────────── Read-only Row ───────────────────── */

function ReadOnlyRow({
  label,
  desc,
  value,
}: {
  label: string;
  desc?: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 border-b border-zinc-100 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-zinc-800">{label}</div>
        {desc && <div className="text-xs text-zinc-400 mt-0.5">{desc}</div>}
      </div>
      <span className="text-sm font-semibold text-zinc-500 italic">{value}</span>
    </div>
  );
}

/* ───────────────────── Card Wrapper ───────────────────── */

function Card({
  icon: Icon,
  title,
  children,
  fullWidth,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
  fullWidth?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border border-zinc-200 bg-white p-5 ${
        fullWidth ? "md:col-span-2" : ""
      }`}
    >
      <div className="flex items-center gap-2 mb-3">
        <Icon size={18} className="text-amber-600" />
        <h3 className="text-sm font-bold text-zinc-900 uppercase tracking-wide">
          {title}
        </h3>
      </div>
      {children}
    </div>
  );
}

/* ───────────────────── Toast ───────────────────── */

function Toast({
  message,
  type,
}: {
  message: string;
  type: "success" | "error";
}) {
  return (
    <div
      className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white transition-all ${
        type === "success" ? "bg-emerald-600" : "bg-red-600"
      }`}
    >
      {message}
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   MAIN PAGE
   ═══════════════════════════════════════════════════ */

export default function SettingsPage() {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
  } | null>(null);

  // Prompts state
  const [scoringPrompt, setScoringPrompt] = useState("");
  const [dmPrompt, setDmPrompt] = useState("");
  const [followupPrompt, setFollowupPrompt] = useState("");

  const showToast = (message: string, type: "success" | "error" = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const loadSettings = useCallback(() => {
    setLoading(true);
    api<SystemSettings>("/api/v1/system/settings")
      .then((s) => {
        setSettings(s);
        setLoading(false);
      })
      .catch(() => {
        showToast("Error cargando configuracion", "error");
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  /* ── helpers to update nested settings ── */

  const upd = <K extends keyof SystemSettings>(
    section: K,
    key: keyof SystemSettings[K],
    value: SystemSettings[K][keyof SystemSettings[K]]
  ) => {
    if (!settings) return;
    setSettings({
      ...settings,
      [section]: { ...settings[section], [key]: value },
    });
  };

  /* ── Save settings (placeholder — backend may not have PUT endpoint yet) ── */

  const saveSettings = async () => {
    if (!settings) return;
    try {
      await api("/api/v1/system/settings", {
        method: "PUT",
        body: JSON.stringify(settings),
      });
      showToast("Configuracion guardada");
    } catch {
      showToast("Error: el endpoint PUT /system/settings aun no existe en el backend", "error");
    }
  };

  const savePrompts = () => {
    showToast("Prompts guardados (funcionalidad pendiente de backend)");
  };

  /* ── Loading ── */

  if (loading || !settings) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-amber-500" />
      </div>
    );
  }

  const s = settings;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">
            Configuracion del Bot
          </h1>
        </div>
        <div className="flex gap-2">
          <button
            onClick={loadSettings}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-zinc-300 rounded-md text-zinc-600 hover:bg-zinc-50 transition-colors"
          >
            <RefreshCw size={14} />
            Actualizar
          </button>
          <button
            onClick={saveSettings}
            className="px-4 py-1.5 text-sm bg-amber-500 text-white rounded-md hover:bg-amber-600 font-medium transition-colors"
          >
            Guardar Cambios
          </button>
        </div>
      </div>

      {/* Safety Banner */}
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 flex items-center gap-3">
        <ShieldCheck size={20} className="text-red-500 shrink-0" />
        <div>
          <p className="text-sm font-bold text-red-700">
            Proteccion de Cuentas Privadas — SIEMPRE ACTIVO
          </p>
          <p className="text-xs text-red-600">
            El bot NUNCA enviara DMs a cuentas privadas. Esta regla de seguridad
            no se puede desactivar.
          </p>
        </div>
      </div>

      {/* Settings Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* ─── 1. Scoring Thresholds ─── */}
        <Card icon={Target} title="Umbrales de Puntuacion">
          <SettingSlider
            label="Puntuacion minima para conservar"
            desc="Los leads con puntuacion menor a este valor se descartan automaticamente del pipeline"
            value={s.scoring.default_score_threshold}
            min={0}
            max={100}
            step={5}
            onChange={(v) => upd("scoring", "default_score_threshold", v)}
          />
          <SettingSlider
            label="Puntuacion minima para investigar"
            desc="Solo se investiga (con Gemini/Perplexity) a leads que superen este score. Ahorra creditos de API"
            value={s.scoring.research_score_threshold}
            min={0}
            max={100}
            step={5}
            onChange={(v) => upd("scoring", "research_score_threshold", v)}
          />
          <SettingSlider
            label="Puntuacion minima para generar DM"
            desc="Solo se generan mensajes personalizados para leads con este score o mayor"
            value={s.scoring.dm_score_threshold}
            min={0}
            max={100}
            step={5}
            onChange={(v) => upd("scoring", "dm_score_threshold", v)}
          />
        </Card>

        {/* ─── 2. Sending Limits ─── */}
        <Card icon={Gauge} title="Limites de Envio">
          <SettingSlider
            label="Limite diario de DMs"
            desc="Maximo de DMs que cada cuenta de IG puede enviar por dia. Valores altos aumentan riesgo de bloqueo"
            value={s.sending.daily_dm_limit}
            min={5}
            max={100}
            step={5}
            onChange={(v) => upd("sending", "daily_dm_limit", v)}
          />
          <SettingSlider
            label="Limite por hora"
            desc="Maximo de DMs por hora por cuenta. Controla la velocidad de envio para parecer natural"
            value={s.sending.hourly_dm_limit}
            min={1}
            max={30}
            step={1}
            onChange={(v) => upd("sending", "hourly_dm_limit", v)}
          />
          <SettingSlider
            label="Delay minimo entre DMs"
            desc="Segundos minimos de espera entre cada envio. Simula comportamiento humano"
            value={s.sending.dm_delay_min}
            min={10}
            max={180}
            step={5}
            suffix="s"
            onChange={(v) => upd("sending", "dm_delay_min", v)}
          />
          <SettingSlider
            label="Delay maximo entre DMs"
            desc="Limite superior del delay aleatorio. El bot espera entre el min y max segundos"
            value={s.sending.dm_delay_max}
            min={30}
            max={300}
            step={5}
            suffix="s"
            onChange={(v) => upd("sending", "dm_delay_max", v)}
          />
          <ReadOnlyRow
            label="Motor de envio"
            desc="Cliente de API que usa el bot para enviar DMs a Instagram"
            value={s.sending.use_playwright ? "Playwright" : "instagrapi"}
          />
        </Card>

        {/* ─── 3. Warm-up ─── */}
        <Card icon={Flame} title="Calentamiento de Cuentas">
          <SettingSlider
            label="Periodo de calentamiento"
            desc="Dias que tarda una cuenta nueva en alcanzar el limite completo de DMs. Protege cuentas nuevas"
            value={s.warmup.warmup_days}
            min={1}
            max={21}
            step={1}
            suffix=" dias"
            onChange={(v) => upd("warmup", "warmup_days", v)}
          />
          <SettingSlider
            label="DMs iniciales por dia"
            desc="Cuantos DMs envia una cuenta nueva el primer dia. Sube gradualmente hasta el limite diario"
            value={s.warmup.warmup_start_limit}
            min={1}
            max={20}
            step={1}
            suffix="/dia"
            onChange={(v) => upd("warmup", "warmup_start_limit", v)}
          />
        </Card>

        {/* ─── 4. Security ─── */}
        <Card icon={ShieldCheck} title="Seguridad">
          <LockedSetting
            label="Verificacion pre-envio"
            desc="Antes de cada DM, verifica que la cuenta destino sea publica"
          />
          <LockedSetting
            label="Filtrar cuentas privadas"
            desc="Excluye automaticamente cuentas privadas durante el scraping"
          />
          <SettingSlider
            label="Pausa tras challenge"
            desc="Minutos que espera el bot despues de que Instagram pida verificacion. Evita bloqueos"
            value={s.safety.challenge_cooldown_minutes}
            min={15}
            max={180}
            step={15}
            suffix=" min"
            onChange={(v) => upd("safety", "challenge_cooldown_minutes", v)}
          />
          <SettingSlider
            label="Pausa tras bloqueo"
            desc="Horas de espera despues de un bloqueo de Instagram. Periodos largos protegen la cuenta"
            value={s.safety.block_cooldown_hours}
            min={1}
            max={72}
            step={1}
            suffix="h"
            onChange={(v) => upd("safety", "block_cooldown_hours", v)}
          />
          <SettingSlider
            label="Max challenges antes de pausar"
            desc="Si la cuenta recibe este numero de challenges en un dia, se pausa automaticamente"
            value={s.safety.max_challenges_before_pause}
            min={1}
            max={10}
            step={1}
            onChange={(v) => upd("safety", "max_challenges_before_pause", v)}
          />
        </Card>

        {/* ─── 5. Inbox & Follow-ups ─── */}
        <Card icon={MessageCircle} title="Bandeja de Entrada y Seguimiento">
          <SettingSlider
            label="Revisar bandeja cada"
            desc="Cada cuantos segundos el bot revisa si hay respuestas nuevas en Instagram"
            value={s.inbox.inbox_check_interval}
            min={60}
            max={900}
            step={30}
            suffix="s"
            onChange={(v) => upd("inbox", "inbox_check_interval", v)}
          />
          <SettingToggle
            label="Pruebas A/B"
            desc="Envia dos variantes de DM para comparar cual tiene mejor tasa de respuesta"
            value={s.inbox.ab_test_enabled}
            onChange={(v) => upd("inbox", "ab_test_enabled", v)}
          />
          <SettingSlider
            label="Division A/B"
            desc="Porcentaje de leads que reciben la variante A. El resto recibe variante B"
            value={Math.round(s.inbox.ab_test_split * 100)}
            min={10}
            max={90}
            step={5}
            suffix="%"
            onChange={(v) => upd("inbox", "ab_test_split", v / 100)}
          />
          <SettingSlider
            label="Revisar follow-ups cada"
            desc="Cada cuantos segundos el bot verifica si hay leads pendientes de seguimiento"
            value={s.inbox.followup_check_interval}
            min={300}
            max={7200}
            step={300}
            suffix="s"
            onChange={(v) => upd("inbox", "followup_check_interval", v)}
          />
          <SettingSlider
            label="Maximo de follow-ups"
            desc="Cuantos mensajes de seguimiento se envian como maximo si el lead no responde"
            value={s.inbox.max_follow_up_steps}
            min={1}
            max={10}
            step={1}
            onChange={(v) => upd("inbox", "max_follow_up_steps", v)}
          />
        </Card>

        {/* ─── 6. Comments ─── */}
        <Card icon={MessageSquare} title="Comentarios en Posts">
          <SettingToggle
            label="Comentarios habilitados"
            desc="Activa o desactiva el envio automatico de comentarios en posts"
            value={s.comments.comment_enabled}
            onChange={(v) => upd("comments", "comment_enabled", v)}
          />
          <SettingSlider
            label="Score minimo para comentar"
            desc="Solo se generan comentarios para leads con este puntaje o superior"
            value={s.comments.comment_score_threshold}
            min={0}
            max={100}
            step={5}
            onChange={(v) => upd("comments", "comment_score_threshold", v)}
          />
          <SettingSlider
            label="Limite diario de comentarios"
            desc="Maximo de comentarios por dia por cuenta. Valores bajos (5-10) son mas seguros"
            value={s.comments.daily_comment_limit}
            min={1}
            max={30}
            step={1}
            onChange={(v) => upd("comments", "daily_comment_limit", v)}
          />
          <SettingSlider
            label="Limite por hora"
            desc="Maximo de comentarios por hora. Controla velocidad para parecer natural"
            value={s.comments.hourly_comment_limit}
            min={1}
            max={10}
            step={1}
            onChange={(v) => upd("comments", "hourly_comment_limit", v)}
          />
          <SettingSlider
            label="Delay minimo entre comentarios"
            desc="Segundos minimos de espera entre cada comentario"
            value={s.comments.comment_delay_min}
            min={30}
            max={300}
            step={10}
            suffix="s"
            onChange={(v) => upd("comments", "comment_delay_min", v)}
          />
          <SettingSlider
            label="Delay maximo entre comentarios"
            desc="Limite superior del delay aleatorio entre comentarios"
            value={s.comments.comment_delay_max}
            min={60}
            max={600}
            step={10}
            suffix="s"
            onChange={(v) => upd("comments", "comment_delay_max", v)}
          />
        </Card>

        {/* ─── 7. AI Prompts (Global) ─── */}
        <Card icon={Brain} title="Prompts de IA (Globales)" fullWidth>
          <p className="text-xs text-zinc-400 mb-4">
            Estos prompts se aplican a TODAS las campanas. Para personalizar por
            cliente, edita el cliente desde la pagina de Clients.
          </p>

          <div className="space-y-5">
            {/* Scoring Prompt */}
            <div>
              <label className="text-sm font-medium text-zinc-800">
                Prompt de Scoring
              </label>
              <p className="text-xs text-zinc-400 mt-0.5 mb-2">
                Instrucciones que recibe Claude al puntuar leads (0-100). Define
                que tipo de perfiles son mas valiosos para tu negocio.
              </p>
              <textarea
                rows={4}
                value={scoringPrompt}
                onChange={(e) => setScoringPrompt(e.target.value)}
                placeholder="Ej: Prioriza cuentas con mas de 1000 seguidores, que tengan bio profesional, y que sean de Latinoamerica..."
                className="w-full rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2.5 text-sm text-zinc-800 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 resize-y"
              />
            </div>

            {/* DM Prompt */}
            <div>
              <label className="text-sm font-medium text-zinc-800">
                Prompt de DMs
              </label>
              <p className="text-xs text-zinc-400 mt-0.5 mb-2">
                Instrucciones para generar mensajes directos. Define tono,
                idioma, largo del mensaje, y que informacion incluir.
              </p>
              <textarea
                rows={4}
                value={dmPrompt}
                onChange={(e) => setDmPrompt(e.target.value)}
                placeholder="Ej: Escribe en espanol informal, maximo 3 oraciones, menciona algo especifico de su bio, ofrece una llamada gratuita..."
                className="w-full rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2.5 text-sm text-zinc-800 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 resize-y"
              />
            </div>

            {/* Follow-up Prompt */}
            <div>
              <label className="text-sm font-medium text-zinc-800">
                Prompt de Follow-up
              </label>
              <p className="text-xs text-zinc-400 mt-0.5 mb-2">
                Instrucciones para mensajes de seguimiento cuando un lead no
                responde al primer DM.
              </p>
              <textarea
                rows={3}
                value={followupPrompt}
                onChange={(e) => setFollowupPrompt(e.target.value)}
                placeholder="Ej: Se breve, no seas insistente, ofrece valor adicional como un caso de estudio o recurso gratis..."
                className="w-full rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2.5 text-sm text-zinc-800 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 resize-y"
              />
            </div>

            <div className="flex justify-end">
              <button
                onClick={savePrompts}
                className="px-4 py-1.5 text-sm bg-zinc-900 text-white rounded-md hover:bg-zinc-800 font-medium transition-colors"
              >
                Guardar Prompts
              </button>
            </div>
          </div>
        </Card>
      </div>

      {/* Toast */}
      {toast && <Toast message={toast.message} type={toast.type} />}
    </div>
  );
}
