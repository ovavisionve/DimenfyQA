"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Users, Plus, X } from "lucide-react";

interface Client {
  id: string;
  name: string;
  business_type: string;
  dm_prompt: string | null;
  scoring_prompt: string | null;
  max_daily_dms: number | null;
  created_at: string;
}

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<Client | null>(null);
  const [form, setForm] = useState({
    name: "",
    business_type: "agency",
    dm_prompt: "",
    scoring_prompt: "",
  });

  useEffect(() => {
    api<Client[]>("/api/v1/clients/").then(setClients).catch(() => {});
  }, []);

  const openNew = () => {
    setEditing(null);
    setForm({ name: "", business_type: "agency", dm_prompt: "", scoring_prompt: "" });
    setShowModal(true);
  };

  const openEdit = (c: Client) => {
    setEditing(c);
    setForm({
      name: c.name,
      business_type: c.business_type || "agency",
      dm_prompt: c.dm_prompt || "",
      scoring_prompt: c.scoring_prompt || "",
    });
    setShowModal(true);
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (editing) {
      const updated = await api<Client>(`/api/v1/clients/${editing.id}`, {
        method: "PUT",
        body: JSON.stringify(form),
      });
      setClients((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
    } else {
      const created = await api<Client>("/api/v1/clients/", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setClients((prev) => [created, ...prev]);
    }
    setShowModal(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Clientes</h1>
          <p className="text-sm text-zinc-500">{clients.length} clientes</p>
        </div>
        <button
          onClick={openNew}
          className="flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-800"
        >
          <Plus size={16} /> Nuevo Cliente
        </button>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {clients.map((c) => (
          <button
            key={c.id}
            onClick={() => openEdit(c)}
            className="rounded-lg border border-zinc-200 bg-white p-5 text-left hover:border-amber-300 transition-colors"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="h-10 w-10 rounded-lg bg-amber-100 flex items-center justify-center">
                <Users size={18} className="text-amber-700" />
              </div>
              <div>
                <p className="font-medium text-zinc-900">{c.name}</p>
                <p className="text-xs text-zinc-500 capitalize">
                  {c.business_type}
                </p>
              </div>
            </div>
            {c.dm_prompt && (
              <p className="text-xs text-zinc-500 line-clamp-2">
                {c.dm_prompt}
              </p>
            )}
            <p className="text-xs text-zinc-400 mt-2">
              Creado: {new Date(c.created_at).toLocaleDateString()}
            </p>
          </button>
        ))}
      </div>

      {clients.length === 0 && (
        <div className="text-center py-16 text-zinc-400">
          <Users size={40} className="mx-auto mb-3 opacity-40" />
          <p>No hay clientes aún.</p>
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <form
            onSubmit={save}
            className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl space-y-4 max-h-[90vh] overflow-y-auto"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                {editing ? "Editar Cliente" : "Nuevo Cliente"}
              </h2>
              <button type="button" onClick={() => setShowModal(false)}>
                <X size={18} className="text-zinc-400" />
              </button>
            </div>

            <input
              placeholder="Nombre del cliente"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
            />
            <select
              value={form.business_type}
              onChange={(e) => setForm({ ...form, business_type: e.target.value })}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
            >
              <option value="agency">Agencia</option>
              <option value="coach">Coach</option>
              <option value="saas">SaaS</option>
              <option value="ecommerce">E-commerce</option>
              <option value="restaurant">Restaurante</option>
              <option value="other">Otro</option>
            </select>

            <div>
              <label className="text-xs font-medium text-zinc-600 mb-1 block">
                Prompt de DM (instrucciones para Claude)
              </label>
              <textarea
                value={form.dm_prompt}
                onChange={(e) => setForm({ ...form, dm_prompt: e.target.value })}
                rows={4}
                placeholder="Describe el tono, estilo y objetivo de los DMs para este cliente..."
                className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none resize-none"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-zinc-600 mb-1 block">
                Prompt de Scoring (instrucciones para evaluación)
              </label>
              <textarea
                value={form.scoring_prompt}
                onChange={(e) => setForm({ ...form, scoring_prompt: e.target.value })}
                rows={3}
                placeholder="Describe qué tipo de leads son valiosos para este cliente..."
                className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none resize-none"
              />
            </div>

            <div className="flex gap-2 justify-end pt-2">
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="rounded-lg border border-zinc-200 px-4 py-2 text-sm hover:bg-zinc-50"
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-black hover:bg-amber-400"
              >
                {editing ? "Guardar" : "Crear"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
