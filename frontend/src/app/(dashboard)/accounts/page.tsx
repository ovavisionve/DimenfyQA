"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getUser } from "@/lib/auth";
import { KeyRound, Plus, Trash2, Eye, EyeOff, Shield, Globe, Lock } from "lucide-react";
import { cn } from "@/lib/cn";
import { getLocale, t, type Locale } from "@/lib/i18n";

interface IGAccountEntry {
  username: string;
  password: string;
  proxy: string;
}

interface ProxyEntry {
  url: string;
  label: string;
}

interface SavedConfig {
  accounts: IGAccountEntry[];
  proxies: ProxyEntry[];
}

export default function AccountsPage() {
  const [locale, setLocaleState] = useState<Locale>("es");
  const [authenticated, setAuthenticated] = useState(false);
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState("");

  const [accounts, setAccounts] = useState<IGAccountEntry[]>([]);
  const [proxies, setProxies] = useState<ProxyEntry[]>([]);
  const [showPasswords, setShowPasswords] = useState<Record<number, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [loading, setLoading] = useState(false);

  // New account form
  const [newAccount, setNewAccount] = useState({ username: "", password: "", proxy: "" });
  const [showNewAccount, setShowNewAccount] = useState(false);

  // New proxy form
  const [newProxy, setNewProxy] = useState({ url: "", label: "" });
  const [showNewProxy, setShowNewProxy] = useState(false);

  useEffect(() => {
    setLocaleState(getLocale());
    const handler = () => setLocaleState(getLocale());
    window.addEventListener("locale-change", handler);
    return () => window.removeEventListener("locale-change", handler);
  }, []);

  // Re-authenticate user to access this section
  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    try {
      const res = await api<{ access_token: string }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: authEmail, password: authPassword }),
      });
      if (res.access_token) {
        setAuthenticated(true);
        loadConfig();
      }
    } catch {
      setAuthError(locale === "es" ? "Credenciales incorrectas" : "Invalid credentials");
    }
  };

  const loadConfig = async () => {
    setLoading(true);
    try {
      const data = await api<SavedConfig>("/api/v1/system/ig-config");
      setAccounts(data.accounts || []);
      setProxies(data.proxies || []);
    } catch {
      // If endpoint doesn't exist yet, just use empty
      setAccounts([]);
      setProxies([]);
    }
    setLoading(false);
  };

  const saveConfig = async () => {
    setSaving(true);
    setSaveError("");
    try {
      await api("/api/v1/system/ig-config", {
        method: "PUT",
        body: JSON.stringify({ accounts, proxies }),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Error guardando configuración");
      setTimeout(() => setSaveError(""), 6000);
    }
    setSaving(false);
  };

  const addAccount = () => {
    if (!newAccount.username || !newAccount.password) return;
    setAccounts([...accounts, { ...newAccount }]);
    setNewAccount({ username: "", password: "", proxy: "" });
    setShowNewAccount(false);
  };

  const removeAccount = (index: number) => {
    setAccounts(accounts.filter((_, i) => i !== index));
  };

  const addProxy = () => {
    if (!newProxy.url) return;
    setProxies([...proxies, { ...newProxy }]);
    setNewProxy({ url: "", label: "" });
    setShowNewProxy(false);
  };

  const removeProxy = (index: number) => {
    setProxies(proxies.filter((_, i) => i !== index));
  };

  // Auto-fill email from current user
  useEffect(() => {
    const user = getUser();
    if (user) setAuthEmail(user.email);
  }, []);

  // Auth gate
  if (!authenticated) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <form
          onSubmit={handleAuth}
          className="w-full max-w-sm rounded-xl border border-zinc-200 bg-white p-8 shadow-sm space-y-4"
        >
          <div className="text-center">
            <div className="mx-auto h-12 w-12 rounded-full bg-amber-100 flex items-center justify-center mb-3">
              <Lock size={24} className="text-amber-600" />
            </div>
            <h2 className="text-lg font-semibold text-zinc-900">
              {t("accounts.authRequired", locale)}
            </h2>
            <p className="text-sm text-zinc-500 mt-1">
              {t("accounts.authHint", locale)}
            </p>
          </div>

          <input
            type="email"
            value={authEmail}
            onChange={(e) => setAuthEmail(e.target.value)}
            placeholder="Email"
            required
            className="w-full rounded-lg border border-zinc-200 px-3 py-2.5 text-sm focus:border-amber-500 focus:outline-none"
          />
          <input
            type="password"
            value={authPassword}
            onChange={(e) => setAuthPassword(e.target.value)}
            placeholder={t("accounts.password", locale)}
            required
            className="w-full rounded-lg border border-zinc-200 px-3 py-2.5 text-sm focus:border-amber-500 focus:outline-none"
          />

          {authError && (
            <p className="text-sm text-red-600 text-center">{authError}</p>
          )}

          <button
            type="submit"
            className="w-full rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-black hover:bg-amber-400 transition-colors"
          >
            {t("accounts.confirm", locale)}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">
            {t("accounts.title", locale)}
          </h1>
          <p className="text-sm text-zinc-500">
            {t("accounts.subtitle", locale)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {saved && (
            <span className="text-sm text-emerald-600 font-medium">
              {locale === "es" ? "Guardado" : "Saved"}
            </span>
          )}
          {saveError && (
            <span className="text-sm text-red-600 font-medium">
              {saveError}
            </span>
          )}
          <button
            onClick={saveConfig}
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-black hover:bg-amber-400 transition-colors disabled:opacity-50"
          >
            <Shield size={14} />
            {saving
              ? (locale === "es" ? "Guardando..." : "Saving...")
              : t("accounts.save", locale)}
          </button>
        </div>
      </div>

      {/* Instagram Accounts Section */}
      <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-100">
          <div className="flex items-center gap-2">
            <KeyRound size={16} className="text-zinc-500" />
            <h3 className="text-sm font-semibold text-zinc-900">
              {locale === "es" ? "Cuentas de Instagram" : "Instagram Accounts"} ({accounts.length})
            </h3>
          </div>
          <button
            onClick={() => setShowNewAccount(true)}
            className="flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-800"
          >
            <Plus size={12} />
            {t("accounts.addAccount", locale)}
          </button>
        </div>

        {/* New Account Form */}
        {showNewAccount && (
          <div className="px-5 py-4 border-b border-zinc-100 bg-zinc-50">
            <div className="grid grid-cols-3 gap-3">
              <input
                placeholder={t("accounts.username", locale)}
                value={newAccount.username}
                onChange={(e) => setNewAccount({ ...newAccount, username: e.target.value })}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
              />
              <input
                type="password"
                placeholder={t("accounts.password", locale)}
                value={newAccount.password}
                onChange={(e) => setNewAccount({ ...newAccount, password: e.target.value })}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
              />
              <div className="flex gap-2">
                <select
                  value={newAccount.proxy}
                  onChange={(e) => setNewAccount({ ...newAccount, proxy: e.target.value })}
                  className="flex-1 rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
                >
                  <option value="">{locale === "es" ? "Sin proxy" : "No proxy"}</option>
                  {proxies.map((p, i) => (
                    <option key={i} value={p.url}>
                      {p.label || p.url}
                    </option>
                  ))}
                </select>
                <button
                  onClick={addAccount}
                  className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500"
                >
                  {locale === "es" ? "Agregar" : "Add"}
                </button>
                <button
                  onClick={() => setShowNewAccount(false)}
                  className="rounded-lg border border-zinc-200 px-3 py-2 text-sm hover:bg-zinc-100"
                >
                  {t("accounts.cancel", locale)}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Account List */}
        {accounts.length > 0 ? (
          <div className="divide-y divide-zinc-100">
            {accounts.map((acc, i) => (
              <div key={i} className="px-5 py-3 flex items-center gap-4">
                <div className="flex items-center gap-2 min-w-[180px]">
                  <span className="h-8 w-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white text-xs font-bold">
                    {acc.username[0]?.toUpperCase()}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-zinc-900">@{acc.username}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1 min-w-[200px]">
                  <span className="text-sm text-zinc-500 font-mono">
                    {showPasswords[i] ? acc.password : "••••••••"}
                  </span>
                  <button
                    onClick={() => setShowPasswords({ ...showPasswords, [i]: !showPasswords[i] })}
                    className="text-zinc-400 hover:text-zinc-600"
                  >
                    {showPasswords[i] ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                <div className="flex-1">
                  {acc.proxy ? (
                    <span className="text-xs text-zinc-400 font-mono">{acc.proxy}</span>
                  ) : (
                    <span className="text-xs text-zinc-300">{locale === "es" ? "Sin proxy" : "No proxy"}</span>
                  )}
                </div>
                <button
                  onClick={() => removeAccount(i)}
                  className="text-zinc-400 hover:text-red-500 transition-colors"
                  title={t("accounts.delete", locale)}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-8 text-center text-zinc-400">
            <KeyRound size={32} className="mx-auto mb-2 opacity-40" />
            <p className="text-sm">{t("accounts.noAccounts", locale)}</p>
            <p className="text-xs mt-1">{t("accounts.noAccountsHint", locale)}</p>
          </div>
        )}
      </div>

      {/* Proxies Section */}
      <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-100">
          <div className="flex items-center gap-2">
            <Globe size={16} className="text-zinc-500" />
            <h3 className="text-sm font-semibold text-zinc-900">
              Proxies ({proxies.length})
            </h3>
          </div>
          <button
            onClick={() => setShowNewProxy(true)}
            className="flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-800"
          >
            <Plus size={12} />
            {t("accounts.addProxy", locale)}
          </button>
        </div>

        {/* New Proxy Form */}
        {showNewProxy && (
          <div className="px-5 py-4 border-b border-zinc-100 bg-zinc-50">
            <div className="grid grid-cols-3 gap-3">
              <input
                placeholder={t("accounts.proxyPlaceholder", locale)}
                value={newProxy.url}
                onChange={(e) => setNewProxy({ ...newProxy, url: e.target.value })}
                className="col-span-2 rounded-lg border border-zinc-200 px-3 py-2 text-sm font-mono focus:border-amber-500 focus:outline-none"
              />
              <div className="flex gap-2">
                <input
                  placeholder={locale === "es" ? "Etiqueta (opcional)" : "Label (optional)"}
                  value={newProxy.label}
                  onChange={(e) => setNewProxy({ ...newProxy, label: e.target.value })}
                  className="flex-1 rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
                />
                <button
                  onClick={addProxy}
                  className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500"
                >
                  {locale === "es" ? "Agregar" : "Add"}
                </button>
                <button
                  onClick={() => setShowNewProxy(false)}
                  className="rounded-lg border border-zinc-200 px-3 py-2 text-sm hover:bg-zinc-100"
                >
                  {t("accounts.cancel", locale)}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Proxy List */}
        {proxies.length > 0 ? (
          <div className="divide-y divide-zinc-100">
            {proxies.map((proxy, i) => (
              <div key={i} className="px-5 py-3 flex items-center gap-4">
                <div className="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center">
                  <Globe size={14} className="text-blue-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-mono text-zinc-700 truncate">{proxy.url}</p>
                  {proxy.label && (
                    <p className="text-xs text-zinc-400">{proxy.label}</p>
                  )}
                </div>
                <span className="text-xs text-zinc-400">
                  {accounts.filter((a) => a.proxy === proxy.url).length} {locale === "es" ? "cuentas" : "accounts"}
                </span>
                <button
                  onClick={() => removeProxy(i)}
                  className="text-zinc-400 hover:text-red-500 transition-colors"
                  title={t("accounts.delete", locale)}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-8 text-center text-zinc-400">
            <Globe size={32} className="mx-auto mb-2 opacity-40" />
            <p className="text-sm">{t("accounts.noProxies", locale)}</p>
            <p className="text-xs mt-1">{t("accounts.noProxiesHint", locale)}</p>
          </div>
        )}
      </div>

      {/* Info Banner */}
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
        <p className="text-sm text-blue-800">
          {locale === "es"
            ? "Las cuentas y proxies se guardan de forma encriptada. Usa proxies residenciales para mayor seguridad. Cada cuenta debe tener su propio proxy para evitar detecciones."
            : "Accounts and proxies are saved encrypted. Use residential proxies for better security. Each account should have its own proxy to avoid detection."}
        </p>
      </div>
    </div>
  );
}
