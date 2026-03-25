"use client";

import { useState } from "react";
import {
  Book,
  ChevronRight,
  Copy,
  Check,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/cn";

interface Endpoint {
  method: "GET" | "POST" | "PATCH" | "DELETE" | "PUT";
  path: string;
  description: string;
  body?: string;
  response?: string;
}

interface Section {
  title: string;
  description: string;
  endpoints: Endpoint[];
}

const METHOD_COLORS: Record<string, string> = {
  GET: "bg-emerald-100 text-emerald-700",
  POST: "bg-blue-100 text-blue-700",
  PATCH: "bg-amber-100 text-amber-700",
  DELETE: "bg-red-100 text-red-700",
  PUT: "bg-violet-100 text-violet-700",
};

const SECTIONS: Section[] = [
  {
    title: "Autenticación",
    description:
      "Registra usuarios y obtén tokens JWT para acceder a la API.",
    endpoints: [
      {
        method: "POST",
        path: "/api/v1/auth/register",
        description: "Registrar nuevo usuario",
        body: '{"email": "user@example.com", "password": "secret123", "full_name": "John Doe"}',
        response: '{"id": "uuid", "email": "user@example.com", "role": "viewer"}',
      },
      {
        method: "POST",
        path: "/api/v1/auth/login",
        description: "Iniciar sesión y obtener token JWT",
        body: '{"email": "user@example.com", "password": "secret123"}',
        response:
          '{"access_token": "eyJ...", "token_type": "bearer", "user": {...}}',
      },
    ],
  },
  {
    title: "Clientes",
    description: "Gestiona los clientes (negocios) del sistema.",
    endpoints: [
      {
        method: "GET",
        path: "/api/v1/clients/",
        description: "Listar todos los clientes",
      },
      {
        method: "POST",
        path: "/api/v1/clients/",
        description: "Crear un nuevo cliente",
        body: '{"name": "Mi Agencia", "ig_username": "miagencia", "industry": "marketing"}',
      },
      {
        method: "GET",
        path: "/api/v1/clients/{id}",
        description: "Obtener detalle de un cliente",
      },
      {
        method: "PATCH",
        path: "/api/v1/clients/{id}",
        description: "Actualizar un cliente",
      },
    ],
  },
  {
    title: "Campañas",
    description:
      "Crea y gestiona campañas de DM. Cada campaña pasa por un pipeline de 6 fases.",
    endpoints: [
      {
        method: "GET",
        path: "/api/v1/campaigns/",
        description: "Listar campañas (filtrar por client_id)",
      },
      {
        method: "POST",
        path: "/api/v1/campaigns/",
        description: "Crear campaña",
        body: '{"name": "Q1 Outreach", "client_id": "uuid", "source_type": "comments", "source_value": "https://instagram.com/p/...", "max_leads": 100, "settings": {"bio_keywords": ["coach"], "sending_hours_start": "09:00", "sending_hours_end": "21:00", "sending_timezone": "America/Caracas"}}',
      },
      {
        method: "GET",
        path: "/api/v1/campaigns/{id}",
        description: "Obtener campaña con stats y progreso",
      },
      {
        method: "GET",
        path: "/api/v1/campaigns/{id}/analytics",
        description: "Analytics: funnel, score distribution, timeline",
      },
      {
        method: "GET",
        path: "/api/v1/campaigns/{id}/ab-results",
        description: "Resultados de A/B testing entre variante A y B",
      },
    ],
  },
  {
    title: "Pipeline (Scraping)",
    description: "Ejecuta el pipeline completo o fases individuales.",
    endpoints: [
      {
        method: "POST",
        path: "/api/v1/scraping/start",
        description: "Iniciar pipeline completo (scrape → score → research → write → send)",
        body: '{"campaign_id": "uuid"}',
      },
      {
        method: "POST",
        path: "/api/v1/scraping/send-dms",
        description: "Enviar DMs de una campaña",
        body: '{"campaign_id": "uuid"}',
      },
    ],
  },
  {
    title: "Leads",
    description: "Consulta y filtra los leads generados por cada campaña.",
    endpoints: [
      {
        method: "GET",
        path: "/api/v1/leads/?campaign_id={id}&limit=500",
        description: "Listar leads de una campaña",
      },
      {
        method: "GET",
        path: "/api/v1/leads/{id}",
        description: "Obtener detalle de un lead",
      },
    ],
  },
  {
    title: "Unibox",
    description:
      "Bandeja unificada de conversaciones con sugerencias de respuesta por IA.",
    endpoints: [
      {
        method: "GET",
        path: "/api/v1/unibox/conversations",
        description: "Listar conversaciones con filtros y paginación",
      },
      {
        method: "GET",
        path: "/api/v1/unibox/conversations/{lead_id}/thread",
        description: "Historial completo de una conversación",
      },
      {
        method: "POST",
        path: "/api/v1/unibox/conversations/{lead_id}/reply",
        description: "Enviar respuesta a un lead",
        body: '{"message": "Hola, gracias por tu interés...", "account_id": "uuid"}',
      },
      {
        method: "GET",
        path: "/api/v1/unibox/conversations/{lead_id}/suggestions",
        description: "Obtener sugerencias de respuesta generadas por IA",
      },
      {
        method: "POST",
        path: "/api/v1/unibox/conversations/{lead_id}/suggest",
        description: "Regenerar sugerencias de respuesta",
      },
      {
        method: "GET",
        path: "/api/v1/unibox/stats",
        description: "Stats: no leídos, por clasificación, tiempo de respuesta promedio",
      },
    ],
  },
  {
    title: "CRM",
    description:
      "Pipeline visual tipo Kanban con scoring dinámico basado en conversaciones.",
    endpoints: [
      {
        method: "GET",
        path: "/api/v1/crm/board",
        description: "Board completo con leads por etapa",
      },
      {
        method: "GET",
        path: "/api/v1/crm/board/stats",
        description: "Métricas por etapa: conteo, score promedio",
      },
      {
        method: "PATCH",
        path: "/api/v1/crm/leads/{lead_id}/stage",
        description: "Mover lead a otra etapa",
        body: '{"stage": "interested"}',
      },
      {
        method: "GET",
        path: "/api/v1/crm/leads/{lead_id}",
        description: "Detalle de lead con historial de score y notas",
      },
      {
        method: "POST",
        path: "/api/v1/crm/leads/{lead_id}/notes",
        description: "Agregar nota a un lead",
        body: '{"content": "Llamada agendada para el viernes"}',
      },
    ],
  },
  {
    title: "Plantillas",
    description: "Plantillas pre-configuradas para crear campañas rápidamente.",
    endpoints: [
      {
        method: "GET",
        path: "/api/v1/templates/",
        description: "Listar todas las plantillas disponibles",
      },
      {
        method: "GET",
        path: "/api/v1/templates/{template_id}",
        description: "Obtener una plantilla específica",
      },
    ],
  },
  {
    title: "Exportar",
    description: "Descarga leads y DMs en diferentes formatos.",
    endpoints: [
      {
        method: "GET",
        path: "/api/v1/export/{campaign_id}/csv",
        description: "Descargar leads como CSV",
      },
      {
        method: "GET",
        path: "/api/v1/export/{campaign_id}/json",
        description: "Descargar leads como JSON",
      },
      {
        method: "GET",
        path: "/api/v1/export/{campaign_id}/excel",
        description: "Descargar leads como Excel (.xlsx)",
      },
    ],
  },
];

function CodeBlock({ code, language }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group">
      <pre className="bg-zinc-900 text-zinc-100 rounded-lg p-3 text-xs overflow-x-auto">
        <code>{code}</code>
      </pre>
      <button
        onClick={copy}
        className="absolute top-2 right-2 p-1.5 rounded-md bg-zinc-700/50 text-zinc-400 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
      >
        {copied ? <Check size={12} /> : <Copy size={12} />}
      </button>
    </div>
  );
}

export default function DocsPage() {
  const [activeSection, setActiveSection] = useState(0);
  const [expandedEndpoint, setExpandedEndpoint] = useState<string | null>(null);

  return (
    <div className="flex gap-6">
      {/* Sidebar nav */}
      <div className="w-48 shrink-0 sticky top-0 h-screen overflow-y-auto py-6">
        <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3 px-2">
          Endpoints
        </h3>
        <nav className="space-y-0.5">
          {SECTIONS.map((section, i) => (
            <button
              key={section.title}
              onClick={() => setActiveSection(i)}
              className={cn(
                "w-full text-left px-2 py-1.5 rounded-md text-sm transition-colors",
                activeSection === i
                  ? "bg-zinc-100 text-zinc-900 font-medium"
                  : "text-zinc-500 hover:text-zinc-700 hover:bg-zinc-50"
              )}
            >
              {section.title}
            </button>
          ))}
        </nav>

        <div className="mt-6 px-2">
          <a
            href="/docs"
            target="_blank"
            className="flex items-center gap-1 text-xs text-amber-600 hover:text-amber-700"
          >
            Swagger UI
            <ExternalLink size={10} />
          </a>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 max-w-3xl py-6 space-y-8">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Book size={20} className="text-amber-500" />
            <h1 className="text-xl font-semibold text-zinc-900">
              API Documentation
            </h1>
          </div>
          <p className="text-sm text-zinc-500">
            Referencia completa de la API REST de IG DM Engine. Base URL:{" "}
            <code className="bg-zinc-100 px-1.5 py-0.5 rounded text-xs">
              http://localhost:1000/api/v1
            </code>
          </p>
        </div>

        {/* Auth example */}
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 space-y-2">
          <h3 className="text-sm font-semibold text-amber-900">
            Autenticación
          </h3>
          <p className="text-xs text-amber-800">
            Todas las peticiones requieren un header Authorization con un token
            JWT:
          </p>
          <CodeBlock
            code={`curl -H "Authorization: Bearer eyJhbGciOi..." \\
     http://localhost:1000/api/v1/campaigns/`}
          />
        </div>

        {/* Sections */}
        {SECTIONS.map((section, si) => (
          <div
            key={section.title}
            id={section.title}
            className={cn(
              "space-y-3",
              activeSection !== si && "hidden"
            )}
          >
            <div>
              <h2 className="text-lg font-semibold text-zinc-900">
                {section.title}
              </h2>
              <p className="text-sm text-zinc-500">{section.description}</p>
            </div>

            <div className="space-y-2">
              {section.endpoints.map((ep) => {
                const key = `${ep.method}-${ep.path}`;
                const expanded = expandedEndpoint === key;

                return (
                  <div
                    key={key}
                    className="border border-zinc-200 rounded-lg overflow-hidden"
                  >
                    <button
                      onClick={() =>
                        setExpandedEndpoint(expanded ? null : key)
                      }
                      className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-zinc-50 transition-colors"
                    >
                      <span
                        className={cn(
                          "text-[10px] font-bold px-2 py-0.5 rounded",
                          METHOD_COLORS[ep.method]
                        )}
                      >
                        {ep.method}
                      </span>
                      <code className="text-sm text-zinc-700 font-mono flex-1">
                        {ep.path}
                      </code>
                      <span className="text-xs text-zinc-400 hidden sm:inline">
                        {ep.description}
                      </span>
                      <ChevronRight
                        size={14}
                        className={cn(
                          "text-zinc-400 transition-transform",
                          expanded && "rotate-90"
                        )}
                      />
                    </button>

                    {expanded && (
                      <div className="border-t border-zinc-100 px-4 py-3 space-y-3 bg-zinc-50/50">
                        <p className="text-sm text-zinc-600">
                          {ep.description}
                        </p>
                        {ep.body && (
                          <div>
                            <p className="text-xs font-medium text-zinc-500 mb-1">
                              Request Body
                            </p>
                            <CodeBlock
                              code={JSON.stringify(
                                JSON.parse(ep.body),
                                null,
                                2
                              )}
                              language="json"
                            />
                          </div>
                        )}
                        {ep.response && (
                          <div>
                            <p className="text-xs font-medium text-zinc-500 mb-1">
                              Response
                            </p>
                            <CodeBlock
                              code={JSON.stringify(
                                JSON.parse(ep.response),
                                null,
                                2
                              )}
                              language="json"
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
