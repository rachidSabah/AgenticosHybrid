"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

/**
 * Manual Proxy Bindings — operator-bound OpenAI-compatible endpoints.
 *
 * AgenticOS ships with ZERO preconfigured proxies (full isolation from any
 * external gateway product). Every binding here is created manually by the
 * operator, probed live, and displayed exactly as measured:
 *   - unreachable endpoints show UNREACHABLE + the transport error
 *   - latency is wall-clock measured, never estimated
 *   - model catalogs are real /models fetches, never invented
 */

interface ProxyProfileRow {
  name: string;
  base_url: string;
  api_key_env: string;
  model: string;
  wire: string;
}

interface TestReport {
  reachable: boolean;
  status_code: number | null;
  latency_ms: number | null;
  error: string | null;
  models_count: number | null;
  models_sample: string[];
  models_error: string | null;
}

interface HealthRow {
  name: string;
  base_url: string;
  reachable: boolean;
  latency_ms: number | null;
  error: string | null;
}

const EMPTY_FORM = { name: "", base_url: "", api_key_env: "", model: "", wire: "chat" };

export function ProxyBindings() {
  const [profiles, setProfiles] = useState<ProxyProfileRow[] | null>(null);
  const [health, setHealth] = useState<Record<string, HealthRow>>({});
  const [reports, setReports] = useState<Record<string, TestReport>>({});
  const [models, setModels] = useState<Record<string, string[] | null>>({});
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const loadProfiles = useCallback(async () => {
    try {
      const res = await api.requestExact<{ profiles: ProxyProfileRow[] }>("/api/proxy/profile");
      setProfiles(res.profiles ?? []);
    } catch (e) {
      setProfiles([]);
      setNotice(`Backend unreachable — cannot load bindings: ${String(e)}`);
    }
  }, []);

  const loadHealth = useCallback(async () => {
    try {
      const res = await api.requestExact<{ proxies: HealthRow[] }>("/api/proxy/health");
      const map: Record<string, HealthRow> = {};
      for (const row of res.proxies ?? []) map[row.name] = row;
      setHealth(map);
    } catch (e) {
      // Probing failed at the control-plane level — show it, never fake it.
      setHealth({});
      setNotice(`Health probe unavailable: ${String(e)}`);
    }
  }, []);

  useEffect(() => {
    void loadProfiles();
    void loadHealth();
  }, [loadProfiles, loadHealth]);

  const testBinding = async (p: ProxyProfileRow) => {
    setBusy(`test:${p.name}`);
    setNotice(null);
    try {
      const res = await api.requestExact<TestReport>("/api/proxy/test", {
        method: "POST",
        body: JSON.stringify({ ...p }),
      });
      setReports((prev) => ({ ...prev, [p.name]: res }));
    } catch (e) {
      setNotice(`Test failed: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const discoverModels = async (p: ProxyProfileRow) => {
    setBusy(`models:${p.name}`);
    setNotice(null);
    try {
      const res = await api.requestExact<{ models: string[] | null; error: string | null }>(
        `/api/proxy/models?name=${encodeURIComponent(p.name)}`
      );
      setModels((prev) => ({ ...prev, [p.name]: res.error ? null : res.models }));
      if (res.error) setNotice(`Model discovery: ${res.error}`);
    } catch (e) {
      setNotice(`Model discovery failed: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const addBinding = async () => {
    setBusy("add");
    setNotice(null);
    try {
      await api.requestExact("/api/proxy/profile/add", {
        method: "POST",
        body: JSON.stringify({ ...form }),
      });
      setForm({ ...EMPTY_FORM });
      await loadProfiles();
      await loadHealth();
    } catch (e) {
      setNotice(`Bind rejected: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const removeBinding = async (name: string) => {
    setBusy(`remove:${name}`);
    setNotice(null);
    try {
      await api.requestExact(`/api/proxy/profile/${encodeURIComponent(name)}`, {
        method: "DELETE",
      });
      await loadProfiles();
      await loadHealth();
    } catch (e) {
      setNotice(`Remove failed: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const formValid = form.name.trim().length > 0 && form.base_url.trim().startsWith("http");

  return (
    <div className="min-h-screen bg-[#05060a] text-gray-200 p-6 space-y-6">
      <header className="border-b border-white/10 pb-4">
        <h1 className="text-xl font-bold text-white">Proxy Bindings</h1>
        <p className="text-sm text-gray-400 mt-1">
          Manually bind any OpenAI-compatible endpoint (external agent gateways,
          LiteLLM, OpenRouter, Ollama, vLLM, LM Studio, direct providers).
          AgenticOS ships with none — bindings exist only because you create them.
        </p>
      </header>

      {notice && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm text-amber-200">
          {notice}
        </div>
      )}

      {/* ── Add binding ─────────────────────────────────────────────── */}
      <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
          Bind a new endpoint
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="text-xs text-gray-400">
            Name (unique)
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. litellm-local"
            />
          </label>
          <label className="text-xs text-gray-400">
            Base URL (http/https)
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none"
              value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
              placeholder="e.g. http://127.0.0.1:4000/v1"
            />
          </label>
          <label className="text-xs text-gray-400">
            API key env var (optional)
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none"
              value={form.api_key_env}
              onChange={(e) => setForm({ ...form, api_key_env: e.target.value })}
              placeholder="e.g. OPENROUTER_API_KEY"
            />
          </label>
          <label className="text-xs text-gray-400">
            Default model (optional)
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none"
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
              placeholder="e.g. claude-sonnet-4"
            />
          </label>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <button
            className="rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed px-4 py-2 text-sm font-semibold text-white"
            disabled={!formValid || busy === "add"}
            onClick={addBinding}
          >
            {busy === "add" ? "Binding…" : "Bind endpoint"}
          </button>
          <span className="text-xs text-gray-500">
            Wire: chat (the only implemented wire — others are rejected honestly)
          </span>
        </div>
      </section>

      {/* ── Binding list ────────────────────────────────────────────── */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300">
          Bound endpoints
        </h2>

        {profiles === null && <p className="text-sm text-gray-500">Loading…</p>}

        {profiles !== null && profiles.length === 0 && (
          <div className="rounded-lg border border-dashed border-white/15 p-6 text-center">
            <p className="text-sm text-gray-300 font-semibold">No proxy bindings configured.</p>
            <p className="text-xs text-gray-500 mt-2">
              AgenticOS is fully independent of external gateway products. Model
              routing stays unavailable (—) until you bind an endpoint above.
            </p>
          </div>
        )}

        {profiles?.map((p) => {
          const h = health[p.name];
          const r = reports[p.name];
          const ml = models[p.name];
          return (
            <div key={p.name} className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="font-mono text-sm text-white">{p.name}</span>
                  <span className="ml-3 text-xs text-gray-400">{p.base_url}</span>
                  {p.api_key_env && (
                    <span className="ml-3 text-xs text-gray-500">key: {p.api_key_env}</span>
                  )}
                  {p.model && <span className="ml-3 text-xs text-gray-500">model: {p.model}</span>}
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                      h === undefined
                        ? "bg-gray-700/40 text-gray-400"
                        : h.reachable
                          ? "bg-emerald-500/15 text-emerald-300"
                          : "bg-red-500/15 text-red-300"
                    }`}
                  >
                    {h === undefined ? "Not probed" : h.reachable ? "Reachable" : "Unreachable"}
                  </span>
                  <button
                    className="rounded border border-white/15 px-3 py-1 text-xs hover:bg-white/5 disabled:opacity-40"
                    disabled={busy !== null}
                    onClick={() => testBinding(p)}
                  >
                    {busy === `test:${p.name}` ? "Testing…" : "Test connection"}
                  </button>
                  <button
                    className="rounded border border-white/15 px-3 py-1 text-xs hover:bg-white/5 disabled:opacity-40"
                    disabled={busy !== null}
                    onClick={() => discoverModels(p)}
                  >
                    {busy === `models:${p.name}` ? "Fetching…" : "Discover models"}
                  </button>
                  <button
                    className="rounded border border-red-500/30 px-3 py-1 text-xs text-red-300 hover:bg-red-500/10 disabled:opacity-40"
                    disabled={busy !== null}
                    onClick={() => removeBinding(p.name)}
                  >
                    {busy === `remove:${p.name}` ? "Removing…" : "Unbind"}
                  </button>
                </div>
              </div>

              {/* Honest per-binding report — only measured values */}
              <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                <div className="rounded bg-black/30 px-3 py-2">
                  <span className="block text-gray-500">Health probe</span>
                  <span className="text-gray-200">
                    {h === undefined ? "—" : h.reachable ? `OK (${h.latency_ms ?? "?"} ms)` : "UNREACHABLE"}
                  </span>
                </div>
                <div className="rounded bg-black/30 px-3 py-2">
                  <span className="block text-gray-500">Test latency</span>
                  <span className="text-gray-200">
                    {r === undefined ? "—" : r.reachable ? `${r.latency_ms ?? "?"} ms` : "FAILED"}
                  </span>
                </div>
                <div className="rounded bg-black/30 px-3 py-2">
                  <span className="block text-gray-500">Models found</span>
                  <span className="text-gray-200">
                    {r === undefined ? "—" : r.models_count ?? "—"}
                  </span>
                </div>
                <div className="rounded bg-black/30 px-3 py-2">
                  <span className="block text-gray-500">HTTP status</span>
                  <span className="text-gray-200">
                    {r === undefined ? "—" : r.status_code ?? "no response"}
                  </span>
                </div>
              </div>

              {r && !r.reachable && r.error && (
                <p className="mt-2 text-xs text-red-300">Transport error: {r.error}</p>
              )}
              {r && r.models_error && (
                <p className="mt-2 text-xs text-amber-300">Model catalog: {r.models_error}</p>
              )}

              {ml !== undefined && (
                <div className="mt-2 rounded bg-black/30 px-3 py-2">
                  <span className="block text-[10px] uppercase tracking-wider text-gray-500">
                    Live model catalog
                  </span>
                  {ml === null ? (
                    <span className="text-xs text-red-300">No data — endpoint unreachable</span>
                  ) : ml.length === 0 ? (
                    <span className="text-xs text-gray-400">Empty catalog (0 models)</span>
                  ) : (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {ml.slice(0, 40).map((m) => (
                        <span
                          key={m}
                          className="rounded bg-white/5 border border-white/10 px-2 py-0.5 font-mono text-[10px] text-gray-300"
                        >
                          {m}
                        </span>
                      ))}
                      {ml.length > 40 && (
                        <span className="text-[10px] text-gray-500">+{ml.length - 40} more</span>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </section>
    </div>
  );
}
