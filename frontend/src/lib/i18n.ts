const translations: Record<string, Record<string, string>> = {
  es: {
    // Sidebar
    "nav.pipeline": "Pipeline",
    "nav.dms": "DMs",
    "nav.comments": "Comentarios",
    "nav.unibox": "Unibox",
    "nav.crm": "CRM",
    "nav.clients": "Clientes",
    "nav.settings": "Configuración",
    "nav.logs": "Live Logs",
    "nav.health": "System Health",
    "nav.docs": "API Docs",
    "nav.billing": "Facturación",
    "nav.onboarding": "Onboarding",
    "nav.notifications": "Notificaciones",
    "nav.logout": "Cerrar sesión",

    // Groups
    "group.pipeline": "Pipeline",
    "group.communication": "Comunicación",
    "group.management": "Gestión",
    "group.monitoring": "Monitoreo",

    // Pipeline
    "pipeline.title": "Pipeline",
    "pipeline.subtitle": "Campañas de DM automatizadas",
    "pipeline.newCampaign": "Nueva Campaña",
    "pipeline.startPipeline": "Iniciar Pipeline",
    "pipeline.sendDMs": "Enviar DMs",
    "pipeline.totalLeads": "Total Leads",
    "pipeline.avgScore": "Avg Score",
    "pipeline.qualified": "Qualified 70+",
    "pipeline.dmsGenerated": "DMs Generados",
    "pipeline.dmsSent": "DMs Enviados",
    "pipeline.replied": "Respondidos",
    "pipeline.failed": "Fallidos",
    "pipeline.status": "Status",

    // Campaign creation
    "campaign.template": "Plantilla (opcional)",
    "campaign.selectTemplate": "Seleccionar plantilla...",
    "campaign.name": "Nombre de la campaña",
    "campaign.selectClient": "Seleccionar cliente...",
    "campaign.source": "URL del post o hashtag",
    "campaign.maxLeads": "Max leads",
    "campaign.bioKeywords": "Filtro por palabras clave en bio",
    "campaign.bioHelp": "Solo se procesarán leads que tengan al menos una de estas palabras en su bio. Dejar vacío para procesar todos.",
    "campaign.schedule": "Horario de envío",
    "campaign.from": "Desde",
    "campaign.to": "Hasta",
    "campaign.timezone": "Zona",
    "campaign.cancel": "Cancelar",
    "campaign.create": "Crear",

    // Tabs
    "tab.stats": "Stats",
    "tab.leads": "Leads",
    "tab.dms": "DMs",
    "tab.inbox": "Inbox",
    "tab.followups": "Follow-ups",
    "tab.analytics": "Analytics",
    "tab.abTesting": "A/B Testing",
    "tab.content": "Contenido",
    "tab.export": "Exportar",

    // CRM
    "crm.title": "CRM Pipeline",
    "crm.new": "Nuevo",
    "crm.contacted": "Contactado",
    "crm.replied": "Respondió",
    "crm.interested": "Interesado",
    "crm.callScheduled": "Llamada Agendada",
    "crm.closedWon": "Cerrado (Ganado)",
    "crm.closedLost": "Cerrado (Perdido)",

    // Common
    "common.loading": "Cargando...",
    "common.save": "Guardar",
    "common.delete": "Eliminar",
    "common.edit": "Editar",
    "common.search": "Buscar...",
    "common.noResults": "No hay resultados",
    "common.confirm": "Confirmar",
  },
  en: {
    // Sidebar
    "nav.pipeline": "Pipeline",
    "nav.dms": "DMs",
    "nav.comments": "Comments",
    "nav.unibox": "Unibox",
    "nav.crm": "CRM",
    "nav.clients": "Clients",
    "nav.settings": "Settings",
    "nav.logs": "Live Logs",
    "nav.health": "System Health",
    "nav.docs": "API Docs",
    "nav.billing": "Billing",
    "nav.onboarding": "Onboarding",
    "nav.notifications": "Notifications",
    "nav.logout": "Log out",

    // Groups
    "group.pipeline": "Pipeline",
    "group.communication": "Communication",
    "group.management": "Management",
    "group.monitoring": "Monitoring",

    // Pipeline
    "pipeline.title": "Pipeline",
    "pipeline.subtitle": "Automated DM campaigns",
    "pipeline.newCampaign": "New Campaign",
    "pipeline.startPipeline": "Start Pipeline",
    "pipeline.sendDMs": "Send DMs",
    "pipeline.totalLeads": "Total Leads",
    "pipeline.avgScore": "Avg Score",
    "pipeline.qualified": "Qualified 70+",
    "pipeline.dmsGenerated": "DMs Generated",
    "pipeline.dmsSent": "DMs Sent",
    "pipeline.replied": "Replied",
    "pipeline.failed": "Failed",
    "pipeline.status": "Status",

    // Campaign creation
    "campaign.template": "Template (optional)",
    "campaign.selectTemplate": "Select template...",
    "campaign.name": "Campaign name",
    "campaign.selectClient": "Select client...",
    "campaign.source": "Post URL or hashtag",
    "campaign.maxLeads": "Max leads",
    "campaign.bioKeywords": "Bio keyword filter",
    "campaign.bioHelp": "Only leads with at least one of these words in their bio will be processed. Leave empty to process all.",
    "campaign.schedule": "Sending schedule",
    "campaign.from": "From",
    "campaign.to": "To",
    "campaign.timezone": "Timezone",
    "campaign.cancel": "Cancel",
    "campaign.create": "Create",

    // Tabs
    "tab.stats": "Stats",
    "tab.leads": "Leads",
    "tab.dms": "DMs",
    "tab.inbox": "Inbox",
    "tab.followups": "Follow-ups",
    "tab.analytics": "Analytics",
    "tab.abTesting": "A/B Testing",
    "tab.content": "Content",
    "tab.export": "Export",

    // CRM
    "crm.title": "CRM Pipeline",
    "crm.new": "New",
    "crm.contacted": "Contacted",
    "crm.replied": "Replied",
    "crm.interested": "Interested",
    "crm.callScheduled": "Call Scheduled",
    "crm.closedWon": "Closed (Won)",
    "crm.closedLost": "Closed (Lost)",

    // Common
    "common.loading": "Loading...",
    "common.save": "Save",
    "common.delete": "Delete",
    "common.edit": "Edit",
    "common.search": "Search...",
    "common.noResults": "No results",
    "common.confirm": "Confirm",
  },
};

export type Locale = "es" | "en";

export function getLocale(): Locale {
  if (typeof window === "undefined") return "es";
  return (localStorage.getItem("locale") as Locale) || "es";
}

export function setLocale(locale: Locale) {
  localStorage.setItem("locale", locale);
  window.dispatchEvent(new Event("locale-change"));
}

export function t(key: string, locale?: Locale): string {
  const lang = locale || getLocale();
  return translations[lang]?.[key] || translations.es[key] || key;
}
