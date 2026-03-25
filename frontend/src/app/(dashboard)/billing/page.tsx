"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import {
  CreditCard,
  Check,
  Zap,
  Crown,
  Building2,
  ExternalLink,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/cn";

interface Plan {
  id: string;
  name: string;
  price: number;
  dms_per_month: number;
  ig_accounts: number | string;
  campaigns: number | string;
  features: string[];
  popular?: boolean;
}

interface Subscription {
  plan: string;
  status: string;
  current_period_end: string;
  usage: {
    dms_sent: number;
    dms_limit: number;
  };
}

const PLANS: Plan[] = [
  {
    id: "starter",
    name: "Starter",
    price: 49,
    dms_per_month: 500,
    ig_accounts: 1,
    campaigns: 3,
    features: [
      "500 DMs/mes",
      "1 cuenta de Instagram",
      "3 campañas activas",
      "Scoring con IA",
      "Bio keyword filter",
      "Exportar CSV/JSON",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: 99,
    dms_per_month: 2000,
    ig_accounts: 5,
    campaigns: "Ilimitadas",
    popular: true,
    features: [
      "2,000 DMs/mes",
      "5 cuentas de Instagram",
      "Campañas ilimitadas",
      "Unibox con IA",
      "CRM Kanban",
      "A/B Testing",
      "Research con Gemini",
      "Notificaciones Slack",
    ],
  },
  {
    id: "enterprise",
    name: "Enterprise",
    price: 249,
    dms_per_month: 10000,
    ig_accounts: "Ilimitadas",
    campaigns: "Ilimitadas",
    features: [
      "10,000 DMs/mes",
      "Cuentas ilimitadas",
      "Campañas ilimitadas",
      "Todo en Pro",
      "API access",
      "Soporte prioritario",
      "Onboarding dedicado",
      "Custom integrations",
    ],
  },
];

const PLAN_ICONS: Record<string, typeof Zap> = {
  starter: Zap,
  pro: Crown,
  enterprise: Building2,
};

export default function BillingPage() {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);

  useEffect(() => {
    // Try to load current subscription
    const clientId = localStorage.getItem("current_client_id");
    if (clientId) {
      api<Subscription>(`/api/v1/billing/subscription/${clientId}`)
        .then(setSubscription)
        .catch(() => {});
    }
    setLoading(false);
  }, []);

  const handleCheckout = async (planId: string) => {
    setCheckoutLoading(planId);
    try {
      const clientId = localStorage.getItem("current_client_id") || "";
      const data = await api<{ checkout_url: string }>("/api/v1/billing/create-checkout", {
        method: "POST",
        body: JSON.stringify({ plan: planId, client_id: clientId }),
      });
      window.open(data.checkout_url, "_blank");
    } catch (err) {
      const msg = (err as Error).message;
      if (msg.includes("503") || msg.includes("not configured")) {
        alert("Stripe no está configurado todavía. Contacta al administrador.");
      } else {
        alert("Error: " + msg);
      }
    } finally {
      setCheckoutLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={24} className="animate-spin text-zinc-400" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto py-6 space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-zinc-900 flex items-center gap-2">
          <CreditCard size={20} className="text-amber-500" />
          Facturación
        </h1>
        <p className="text-sm text-zinc-500 mt-1">
          Elige el plan que mejor se adapte a tu negocio
        </p>
      </div>

      {/* Current subscription */}
      {subscription && (
        <div className="bg-white border border-zinc-200 rounded-xl p-5 space-y-3">
          <h2 className="text-sm font-semibold text-zinc-700">
            Plan actual
          </h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-lg font-bold text-zinc-900 capitalize">
                {subscription.plan}
              </p>
              <p className="text-xs text-zinc-500">
                Próxima facturación:{" "}
                {new Date(subscription.current_period_end).toLocaleDateString()}
              </p>
            </div>
            <div
              className={cn(
                "px-2.5 py-1 rounded-full text-xs font-medium",
                subscription.status === "active"
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-red-100 text-red-700"
              )}
            >
              {subscription.status === "active" ? "Activo" : subscription.status}
            </div>
          </div>
          {/* Usage bar */}
          <div>
            <div className="flex justify-between text-xs text-zinc-500 mb-1">
              <span>DMs enviados este mes</span>
              <span>
                {subscription.usage.dms_sent} / {subscription.usage.dms_limit}
              </span>
            </div>
            <div className="h-2 bg-zinc-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-amber-500 rounded-full transition-all"
                style={{
                  width: `${Math.min(
                    100,
                    (subscription.usage.dms_sent / subscription.usage.dms_limit) * 100
                  )}%`,
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Plans */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {PLANS.map((plan) => {
          const Icon = PLAN_ICONS[plan.id] || Zap;
          const isCurrent = subscription?.plan === plan.id;

          return (
            <div
              key={plan.id}
              className={cn(
                "relative bg-white border rounded-xl p-5 space-y-4 transition-shadow",
                plan.popular
                  ? "border-amber-500 shadow-lg shadow-amber-500/10"
                  : "border-zinc-200",
                isCurrent && "ring-2 ring-amber-500"
              )}
            >
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-amber-500 text-black text-[10px] font-bold px-3 py-0.5 rounded-full">
                  MÁS POPULAR
                </div>
              )}

              <div className="flex items-center gap-2">
                <Icon
                  size={18}
                  className={plan.popular ? "text-amber-500" : "text-zinc-400"}
                />
                <h3 className="font-semibold text-zinc-900">{plan.name}</h3>
              </div>

              <div>
                <span className="text-3xl font-bold text-zinc-900">
                  ${plan.price}
                </span>
                <span className="text-sm text-zinc-500">/mes</span>
              </div>

              <ul className="space-y-2">
                {plan.features.map((feature) => (
                  <li
                    key={feature}
                    className="flex items-center gap-2 text-sm text-zinc-600"
                  >
                    <Check size={14} className="text-emerald-500 shrink-0" />
                    {feature}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => handleCheckout(plan.id)}
                disabled={isCurrent || checkoutLoading === plan.id}
                className={cn(
                  "w-full flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors",
                  isCurrent
                    ? "bg-zinc-100 text-zinc-400 cursor-not-allowed"
                    : plan.popular
                    ? "bg-amber-500 text-black hover:bg-amber-400"
                    : "bg-zinc-900 text-white hover:bg-zinc-800"
                )}
              >
                {checkoutLoading === plan.id ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : isCurrent ? (
                  "Plan actual"
                ) : (
                  <>
                    Elegir plan
                    <ExternalLink size={12} />
                  </>
                )}
              </button>
            </div>
          );
        })}
      </div>

      {/* FAQ */}
      <div className="bg-zinc-50 rounded-xl p-5 space-y-3">
        <h3 className="text-sm font-semibold text-zinc-700">
          Preguntas frecuentes
        </h3>
        <div className="space-y-3 text-sm">
          <div>
            <p className="font-medium text-zinc-700">
              ¿Puedo cambiar de plan?
            </p>
            <p className="text-zinc-500">
              Sí, puedes subir o bajar de plan en cualquier momento. El cambio
              se aplica al inicio del próximo ciclo de facturación.
            </p>
          </div>
          <div>
            <p className="font-medium text-zinc-700">
              ¿Qué pasa si alcanzo el límite de DMs?
            </p>
            <p className="text-zinc-500">
              Las campañas se pausarán automáticamente. Puedes subir de plan
              para obtener más DMs o esperar al próximo ciclo.
            </p>
          </div>
          <div>
            <p className="font-medium text-zinc-700">
              ¿Ofrecen prueba gratuita?
            </p>
            <p className="text-zinc-500">
              El plan Starter incluye los primeros 7 días gratis. Puedes
              cancelar sin cargo durante este periodo.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
