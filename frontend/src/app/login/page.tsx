"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { setAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [tab, setTab] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (tab === "register") {
        const data = await api<{
          access_token: string;
          refresh_token: string;
          user: { id: string; email: string; full_name: string; role: "admin" | "manager" | "viewer"; is_active: boolean };
        }>("/api/v1/auth/register", {
          method: "POST",
          body: JSON.stringify({ email, password, full_name: fullName }),
          noAuth: true,
        });
        setAuth(data.access_token, data.refresh_token, data.user);
      } else {
        const data = await api<{
          access_token: string;
          refresh_token: string;
          user: { id: string; email: string; full_name: string; role: "admin" | "manager" | "viewer"; is_active: boolean };
        }>("/api/v1/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password }),
          noAuth: true,
        });
        setAuth(data.access_token, data.refresh_token, data.user);
      }
      router.push("/pipeline");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <div className="h-10 w-10 rounded-xl bg-amber-500 flex items-center justify-center text-black font-bold">
            IG
          </div>
          <span className="text-xl font-semibold text-white tracking-tight">
            IG DM Engine
          </span>
        </div>

        {/* Tabs */}
        <div className="flex mb-6 bg-zinc-900 rounded-lg p-1">
          <button
            onClick={() => setTab("login")}
            className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
              tab === "login"
                ? "bg-zinc-800 text-white"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            Iniciar Sesión
          </button>
          <button
            onClick={() => setTab("register")}
            className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
              tab === "register"
                ? "bg-zinc-800 text-white"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            Registro
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {tab === "register" && (
            <input
              type="text"
              placeholder="Nombre completo"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
          )}
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
          />
          <input
            type="password"
            placeholder="Contraseña"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
          />

          {error && (
            <div className="rounded-lg bg-red-950/50 border border-red-900 px-3 py-2 text-xs text-red-400">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-semibold text-black hover:bg-amber-400 disabled:opacity-50 transition-colors"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-black/30 border-t-black" />
                Cargando...
              </span>
            ) : tab === "login" ? (
              "Iniciar Sesión"
            ) : (
              "Crear Cuenta"
            )}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-zinc-600">
          {tab === "login"
            ? "El primer usuario registrado será administrador."
            : "Mínimo 8 caracteres para la contraseña."}
        </p>
      </div>
    </div>
  );
}
