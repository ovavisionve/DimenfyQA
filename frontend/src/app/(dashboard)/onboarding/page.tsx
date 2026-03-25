"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import {
  ChevronRight,
  ChevronLeft,
  Check,
  Users,
  Target,
  Send,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/cn";

interface StepProps {
  active: boolean;
}

const STEPS = [
  { label: "Cliente", icon: Users },
  { label: "Campaña", icon: Target },
  { label: "Envío", icon: Send },
  { label: "Listo", icon: Sparkles },
];

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="flex items-center justify-center gap-2 mb-8">
      {STEPS.map((step, i) => {
        const Icon = step.icon;
        const done = i < current;
        const active = i === current;
        return (
          <div key={step.label} className="flex items-center gap-2">
            <div
              className={cn(
                "flex items-center justify-center h-9 w-9 rounded-full border-2 transition-colors",
                done
                  ? "bg-amber-500 border-amber-500 text-black"
                  : active
                  ? "border-amber-500 text-amber-500"
                  : "border-zinc-300 text-zinc-400"
              )}
            >
              {done ? <Check size={16} /> : <Icon size={16} />}
            </div>
            <span
              className={cn(
                "text-xs font-medium hidden sm:inline",
                active ? "text-zinc-900" : "text-zinc-400"
              )}
            >
              {step.label}
            </span>
            {i < STEPS.length - 1 && (
              <div
                className={cn(
                  "w-8 h-0.5 mx-1",
                  done ? "bg-amber-500" : "bg-zinc-200"
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);

  // Step 1: Client
  const [clientName, setClientName] = useState("");
  const [clientIg, setClientIg] = useState("");
  const [clientIndustry, setClientIndustry] = useState("");
  const [clientId, setClientId] = useState("");

  // Step 2: Campaign
  const [campaignName, setCampaignName] = useState("");
  const [sourceType, setSourceType] = useState("comments");
  const [sourceValue, setSourceValue] = useState("");
  const [maxLeads, setMaxLeads] = useState(50);
  const [campaignId, setCampaignId] = useState("");

  // Step 3: Sending config
  const [igUsername, setIgUsername] = useState("");
  const [dailyLimit, setDailyLimit] = useState(30);
  const [scheduleStart, setScheduleStart] = useState("09:00");
  const [scheduleEnd, setScheduleEnd] = useState("21:00");

  const handleCreateClient = async () => {
    setSaving(true);
    try {
      const data = await api<{ id: string }>("/api/v1/clients/", {
        method: "POST",
        body: JSON.stringify({
          name: clientName,
          ig_username: clientIg,
          industry: clientIndustry,
        }),
      });
      setClientId(data.id);
      setStep(1);
    } catch (err) {
      alert("Error creando cliente: " + (err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleCreateCampaign = async () => {
    setSaving(true);
    try {
      const data = await api<{ id: string }>("/api/v1/campaigns/", {
        method: "POST",
        body: JSON.stringify({
          name: campaignName,
          client_id: clientId,
          source_type: sourceType,
          source_value: sourceValue,
          max_leads: maxLeads,
          settings: {
            sending_hours_start: scheduleStart,
            sending_hours_end: scheduleEnd,
            sending_timezone: "America/Caracas",
          },
        }),
      });
      setCampaignId(data.id);
      setStep(2);
    } catch (err) {
      alert("Error creando campaña: " + (err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleFinish = () => {
    // Save sending preferences to localStorage
    localStorage.setItem("onboarding_complete", "true");
    localStorage.setItem("ig_daily_limit", String(dailyLimit));
    setStep(3);
  };

  const goToPipeline = () => {
    router.push("/pipeline");
  };

  return (
    <div className="max-w-xl mx-auto py-12">
      <div className="text-center mb-2">
        <h1 className="text-2xl font-bold text-zinc-900">
          Configuración Inicial
        </h1>
        <p className="text-sm text-zinc-500 mt-1">
          Configura tu primer cliente y campaña en 3 pasos
        </p>
      </div>

      <StepIndicator current={step} />

      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
        {/* Step 0: Create Client */}
        {step === 0 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-zinc-900">
              1. Crea tu primer cliente
            </h2>
            <p className="text-sm text-zinc-500">
              Un cliente representa tu negocio o el de tu cliente. Todas las
              campañas se organizan bajo un cliente.
            </p>
            <input
              placeholder="Nombre del negocio"
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2.5 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
            <input
              placeholder="Username de Instagram (sin @)"
              value={clientIg}
              onChange={(e) => setClientIg(e.target.value)}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2.5 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
            <select
              value={clientIndustry}
              onChange={(e) => setClientIndustry(e.target.value)}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2.5 text-sm focus:border-amber-500 focus:outline-none"
            >
              <option value="">Seleccionar industria...</option>
              <option value="marketing">Marketing / Agencia</option>
              <option value="coaching">Coaching / Consultoría</option>
              <option value="ecommerce">E-Commerce</option>
              <option value="saas">SaaS / Software</option>
              <option value="restaurant">Restaurante / Comida</option>
              <option value="fitness">Fitness / Bienestar</option>
              <option value="real_estate">Bienes Raíces</option>
              <option value="education">Educación</option>
              <option value="other">Otro</option>
            </select>
            <button
              onClick={handleCreateClient}
              disabled={!clientName || saving}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-black hover:bg-amber-400 disabled:opacity-50 transition-colors"
            >
              {saving ? "Creando..." : "Crear Cliente"}
              <ChevronRight size={16} />
            </button>
          </div>
        )}

        {/* Step 1: Create Campaign */}
        {step === 1 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-zinc-900">
              2. Crea tu primera campaña
            </h2>
            <p className="text-sm text-zinc-500">
              Una campaña define a quién contactar y de dónde obtener los leads.
            </p>
            <input
              placeholder="Nombre de la campaña"
              value={campaignName}
              onChange={(e) => setCampaignName(e.target.value)}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2.5 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
            <select
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value)}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2.5 text-sm"
            >
              <option value="comments">Comentarios de un post</option>
              <option value="followers">Seguidores de una cuenta</option>
              <option value="hashtag">Hashtag</option>
            </select>
            <input
              placeholder="URL del post de Instagram o hashtag"
              value={sourceValue}
              onChange={(e) => setSourceValue(e.target.value)}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2.5 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
            <div>
              <label className="block text-xs text-zinc-500 mb-1">
                Máximo de leads a procesar
              </label>
              <input
                type="number"
                value={maxLeads}
                onChange={(e) => setMaxLeads(parseInt(e.target.value) || 50)}
                className="w-full rounded-lg border border-zinc-200 px-3 py-2.5 text-sm"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setStep(0)}
                className="flex items-center gap-1 rounded-lg border border-zinc-200 px-4 py-2.5 text-sm hover:bg-zinc-50"
              >
                <ChevronLeft size={16} />
                Atrás
              </button>
              <button
                onClick={handleCreateCampaign}
                disabled={!campaignName || !sourceValue || saving}
                className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-black hover:bg-amber-400 disabled:opacity-50 transition-colors"
              >
                {saving ? "Creando..." : "Crear Campaña"}
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Sending Config */}
        {step === 2 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-zinc-900">
              3. Configura el envío
            </h2>
            <p className="text-sm text-zinc-500">
              Define los parámetros para enviar DMs de forma segura.
            </p>
            <input
              placeholder="Username de Instagram para enviar DMs"
              value={igUsername}
              onChange={(e) => setIgUsername(e.target.value)}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2.5 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
            <div>
              <label className="block text-xs text-zinc-500 mb-1">
                Límite diario de DMs (recomendado: 20-30)
              </label>
              <input
                type="range"
                min={5}
                max={50}
                value={dailyLimit}
                onChange={(e) => setDailyLimit(parseInt(e.target.value))}
                className="w-full accent-amber-500"
              />
              <div className="flex justify-between text-xs text-zinc-400 mt-1">
                <span>5</span>
                <span className="font-medium text-zinc-700">{dailyLimit} DMs/día</span>
                <span>50</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-zinc-500 mb-1">
                  Hora inicio
                </label>
                <select
                  value={scheduleStart}
                  onChange={(e) => setScheduleStart(e.target.value)}
                  className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
                >
                  {Array.from({ length: 24 }, (_, i) => {
                    const h = String(i).padStart(2, "0");
                    return (
                      <option key={h} value={`${h}:00`}>{`${h}:00`}</option>
                    );
                  })}
                </select>
              </div>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">
                  Hora fin
                </label>
                <select
                  value={scheduleEnd}
                  onChange={(e) => setScheduleEnd(e.target.value)}
                  className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
                >
                  {Array.from({ length: 24 }, (_, i) => {
                    const h = String(i).padStart(2, "0");
                    return (
                      <option key={h} value={`${h}:00`}>{`${h}:00`}</option>
                    );
                  })}
                </select>
              </div>
            </div>
            <div className="bg-amber-50 rounded-lg p-3 text-xs text-amber-800">
              Los DMs se enviarán entre {scheduleStart} y {scheduleEnd} con
              delays aleatorios de 45-120s entre cada mensaje para evitar
              detección.
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setStep(1)}
                className="flex items-center gap-1 rounded-lg border border-zinc-200 px-4 py-2.5 text-sm hover:bg-zinc-50"
              >
                <ChevronLeft size={16} />
                Atrás
              </button>
              <button
                onClick={handleFinish}
                className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-black hover:bg-amber-400 transition-colors"
              >
                Finalizar
                <Check size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Done */}
        {step === 3 && (
          <div className="text-center space-y-4 py-4">
            <div className="h-16 w-16 rounded-full bg-emerald-100 flex items-center justify-center mx-auto">
              <Check size={32} className="text-emerald-600" />
            </div>
            <h2 className="text-lg font-semibold text-zinc-900">
              Todo listo!
            </h2>
            <p className="text-sm text-zinc-500">
              Tu cliente y campaña están configurados. Ahora puedes ir al
              Pipeline para ejecutar tu primera campaña.
            </p>
            <div className="bg-zinc-50 rounded-lg p-4 text-left text-sm space-y-1">
              <p>
                <span className="text-zinc-500">Cliente:</span>{" "}
                <span className="font-medium">{clientName}</span>
              </p>
              <p>
                <span className="text-zinc-500">Campaña:</span>{" "}
                <span className="font-medium">{campaignName}</span>
              </p>
              <p>
                <span className="text-zinc-500">Fuente:</span>{" "}
                <span className="font-medium">{sourceType}</span>
              </p>
              <p>
                <span className="text-zinc-500">Límite diario:</span>{" "}
                <span className="font-medium">{dailyLimit} DMs</span>
              </p>
            </div>
            <button
              onClick={goToPipeline}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-zinc-800 transition-colors"
            >
              Ir al Pipeline
              <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
