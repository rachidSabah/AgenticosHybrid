"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type FleetAgent, type FleetBidResult, type FleetRunRecord } from "@/lib/api";

/**
 * Agent Fleet — every agentic CLI the discovery layer actually found, shown
 * with its real adapter status, operator-declared capabilities, measured
 * dispatch history, and the controls to bid tasks and dispatch prompts.
 *
 * Honesty rules carried over from the driver: a brain with no headless
 * adapter says so; a brain with no history shows no invented score; a
 * dispatch reports the real exit code, stdout, and stderr.
 */

const fmtRate = (r: number | null) => (r === null ? "—" : `${Math.round(r * 100)}%`);
const fmtAvg = (v: number | null) => (v === null ? "—" : `${v} ms`);

export function FleetOrchestra() {
  const [agents, setAgents] = useState<FleetAgent[] | null>(null);
  const [runs, setRuns] = useState<FleetRunRecord[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // per-agent editors
  const [capDraft, setCapDraft] = useState<Record<string, string>>({});
  const [argsDraft, setArgsDraft] = useState<Record<string, string>>({});
  const [openEditor, setOpenEditor] = useState<string | null>(null);

  // bid panel
  const [bidTask, setBidTask] = useState("");
  const [bidCaps, setBidCaps] = useState("");
  const [bidResult, setBidResult] = useState<FleetBidResult | null>(null);

  // dispatch panel
  const [dispatchAgent, setDispatchAgent] = useState("");
  const [dispatchPrompt, setDispatchPrompt] = useState("");
  const [dispatchTimeout, setDispatchTimeout] = useState("120");
  const [lastRun, setLastRun] = useState<FleetRunRecord | null>(null);

  const load = useCallback(async () => {
    try {
      const [fleetRes, runsRes] = await Promise.all([api.fleet(), api.fleetRuns(undefined, 25)]);
      setAgents(fleetRes.agents ?? []);
      setRuns(runsRes.runs ?? []);
    } catch (e) {
      setAgents([]);
      setRuns([]);
      setNotice(`Fleet unavailable — discovery snapshot could not be read: ${String(e)}`);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const saveCapabilities = async (a: FleetAgent) => {
    const raw = capDraft[a.agent_id];
    if (raw === undefined) {
      setOpenEditor(null);
      return;
    }
    setBusy(`caps-${a.agent_id}`);
    setNotice(null);
    try {
      await api.fleetSetCapabilities(
        a.agent_id,
        raw
          .split(",")
          .map((c) => c.trim())
          .filter(Boolean)
      );
      await load();
      setOpenEditor(null);
    } catch (e) {
      setNotice(`Capabilities not saved: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const saveArgs = async (a: FleetAgent) => {
    const raw = argsDraft[a.agent_id];
    if (raw === undefined) {
      setOpenEditor(null);
      return;
    }
    setBusy(`args-${a.agent_id}`);
    setNotice(null);
    try {
      // shellwords-style split honoring simple quotes, done client-side for
      // the operator's convenience; each token is sent as one argv element.
      const tokens = raw.match(/(?:[^\s"]+|"[^"]*")+/g)?.map((t) => t.replaceAll('"', "")) ?? [];
      await api.fleetSetArgsPrefix(a.agent_id, tokens);
      await load();
      setOpenEditor(null);
    } catch (e) {
      setNotice(`Args prefix not saved: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const runBid = async () => {
    setBusy("bid");
    setNotice(null);
    setBidResult(null);
    try {
      setBidResult(
        await api.fleetBid({
          task_description: bidTask,
          required_capabilities: bidCaps
            .split(",")
            .map((c) => c.trim())
            .filter(Boolean),
          top: 5,
        })
      );
    } catch (e) {
      setNotice(`Bid failed: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const runDispatch = async () => {
    if (!dispatchAgent) {
      setNotice("Pick an agent to dispatch to — nothing has been sent.");
      return;
    }
    if (!dispatchPrompt.trim()) {
      setNotice("Write the prompt to send — an empty dispatch sends nothing.");
      return;
    }
    setBusy("dispatch");
    setNotice(null);
    setLastRun(null);
    try {
      const rec = await api.fleetDispatch({
        agent_id: dispatchAgent,
        prompt: dispatchPrompt,
        timeout_s: Number.parseInt(dispatchTimeout, 10) || 120,
      });
      setLastRun(rec);
      await load();
    } catch (e) {
      setNotice(`Dispatch refused: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#05060a] text-gray-200 p-6 space-y-6">
      <header className="border-b border-white/10 pb-4">
        <h1 className="text-xl font-bold text-white">Agent Fleet</h1>
        <p className="text-sm text-gray-400 mt-1">
          Every agentic CLI the discovery layer found, drivable from one place. Known
          CLIs use their documented headless mode; unknown ones require an explicit
          args prefix — AgenticOS never guesses how to drive a binary. Bidding ranks
          with measured history only; dispatch runs the real process and reports the
          real exit code, stdout, and stderr.
        </p>
      </header>

      {notice && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm text-amber-200">
          {notice}
        </div>
      )}

      {/* ── Fleet roster ──────────────────────────────────────────────── */}
      <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
          Fleet roster (live discovery snapshot)
        </h2>
        {agents === null ? (
          <p className="text-sm text-gray-500">Loading discovery snapshot…</p>
        ) : agents.length === 0 ? (
          <p className="text-sm text-gray-500">
            NO DATA — no CLIs in the current discovery snapshot. Install or expose an
            agentic CLI and re-scan; nothing is listed until discovery actually finds it.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b border-white/10">
                  <th className="py-2 pr-3">Agent</th>
                  <th className="py-2 pr-3">Kind</th>
                  <th className="py-2 pr-3">Adapter</th>
                  <th className="py-2 pr-3">Capabilities</th>
                  <th className="py-2 pr-3">Args prefix</th>
                  <th className="py-2 pr-3">Measured history</th>
                  <th className="py-2 pr-3">Configure</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((a) => (
                  <tr key={a.agent_id} className="border-b border-white/5 align-top">
                    <td className="py-2 pr-3">
                      <p className="text-gray-100">{a.name}</p>
                      <p className="text-xs text-gray-500 font-mono">{a.agent_id}</p>
                      <p className="text-xs mt-1">
                        {a.is_active ? (
                          <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-xs text-emerald-300">
                            {a.status}
                          </span>
                        ) : (
                          <span className="rounded bg-white/10 px-2 py-0.5 text-xs text-gray-400">
                            {a.status}
                          </span>
                        )}
                      </p>
                    </td>
                    <td className="py-2 pr-3 text-xs text-gray-400">{a.kind}</td>
                    <td className="py-2 pr-3">
                      <p className="text-xs text-gray-200">{a.adapter}</p>
                      <p className="text-xs text-gray-500 max-w-[16rem]">{a.adapter_note}</p>
                    </td>
                    <td className="py-2 pr-3">
                      {a.declared_capabilities.length === 0 ? (
                        <span className="text-xs text-gray-500">none declared</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {a.declared_capabilities.map((c) => (
                            <span
                              key={c}
                              className="rounded bg-sky-500/15 px-2 py-0.5 text-xs text-sky-300"
                            >
                              {c}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-xs font-mono text-gray-400">
                      {a.args_prefix.length === 0 ? "—" : a.args_prefix.join(" ")}
                    </td>
                    <td className="py-2 pr-3 text-xs text-gray-300">
                      <p>
                        {a.stats.runs} run(s) · {fmtRate(a.stats.success_rate)} success
                      </p>
                      <p className="text-gray-500">avg {fmtAvg(a.stats.avg_duration_ms)}</p>
                    </td>
                    <td className="py-2 pr-3">
                      <button
                        className="rounded bg-white/10 px-2 py-1 text-xs text-gray-300 hover:bg-white/20"
                        onClick={() => {
                          setOpenEditor(openEditor === a.agent_id ? null : a.agent_id);
                          setCapDraft((d) => ({
                            ...d,
                            [a.agent_id]: d[a.agent_id] ?? a.declared_capabilities.join(", "),
                          }));
                          setArgsDraft((d) => ({
                            ...d,
                            [a.agent_id]: d[a.agent_id] ?? a.args_prefix.join(" "),
                          }));
                        }}
                      >
                        {openEditor === a.agent_id ? "close" : "edit"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {openEditor && (() => {
          const a = (agents ?? []).find((x) => x.agent_id === openEditor);
          if (!a) return null;
          return (
            <div className="mt-4 rounded border border-white/15 bg-black/30 p-4 space-y-3">
              <p className="text-xs uppercase tracking-wider text-gray-400">
                Configure {a.name} <span className="font-mono">({a.agent_id})</span>
              </p>
              <label className="block text-xs text-gray-400">
                Capabilities (comma-separated; saved set replaces the previous set)
                <input
                  className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none"
                  value={capDraft[a.agent_id] ?? ""}
                  onChange={(e) => setCapDraft((d) => ({ ...d, [a.agent_id]: e.target.value }))}
                  placeholder="coding, review"
                />
              </label>
              <label className="block text-xs text-gray-400">
                Args prefix for generic adapter (argv tokens before the prompt; quoted
                tokens are honored; empty means the prompt is the only argument)
                <input
                  className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none font-mono"
                  value={argsDraft[a.agent_id] ?? ""}
                  onChange={(e) => setArgsDraft((d) => ({ ...d, [a.agent_id]: e.target.value }))}
                  placeholder="--task --verbose"
                />
              </label>
              <div className="flex gap-2">
                <button
                  className="rounded bg-indigo-500/30 px-3 py-1.5 text-xs text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
                  disabled={busy !== null}
                  onClick={() => void saveCapabilities(a)}
                >
                  {busy === `caps-${a.agent_id}` ? "Saving…" : "Save capabilities"}
                </button>
                <button
                  className="rounded bg-indigo-500/30 px-3 py-1.5 text-xs text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
                  disabled={busy !== null}
                  onClick={() => void saveArgs(a)}
                >
                  {busy === `args-${a.agent_id}` ? "Saving…" : "Save args prefix"}
                </button>
              </div>
            </div>
          );
        })()}
      </section>

      {/* ── Contract-net bidding ──────────────────────────────────────── */}
      <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-1">
          Contract-net bidding
        </h2>
        <p className="text-xs text-gray-500 mb-3">
          Ranks eligible brains using only measured success rate and measured average
          duration of real past dispatches. Brains with no history rank last — unknown
          is not a score.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end mb-3">
          <label className="text-xs text-gray-400 md:col-span-2">
            Task description
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none"
              value={bidTask}
              onChange={(e) => setBidTask(e.target.value)}
              placeholder="refactor the auth module"
            />
          </label>
          <label className="text-xs text-gray-400">
            Required capabilities (comma-separated)
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none"
              value={bidCaps}
              onChange={(e) => setBidCaps(e.target.value)}
              placeholder="coding"
            />
          </label>
        </div>
        <button
          className="rounded bg-indigo-500/30 px-4 py-2 text-sm text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
          disabled={busy !== null}
          onClick={() => void runBid()}
        >
          {busy === "bid" ? "Bidding…" : "Run bid"}
        </button>

        {bidResult && (
          <div className="mt-4">
            {bidResult.eligible_count === 0 ? (
              <p className="text-sm text-gray-500">
                NO DATA — no active, drivable brain declares the required capabilities.
                Nothing is ranked because nothing is eligible.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-gray-400 border-b border-white/10">
                      <th className="py-2 pr-3">#</th>
                      <th className="py-2 pr-3">Brain</th>
                      <th className="py-2 pr-3">Adapter</th>
                      <th className="py-2 pr-3">Capabilities</th>
                      <th className="py-2 pr-3">Success rate</th>
                      <th className="py-2 pr-3">Avg duration</th>
                      <th className="py-2 pr-3"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {bidResult.ranking.map((r, i) => (
                      <tr key={r.agent_id} className="border-b border-white/5">
                        <td className="py-2 pr-3 text-gray-400">{i + 1}</td>
                        <td className="py-2 pr-3 text-gray-100">{r.name}</td>
                        <td className="py-2 pr-3 text-xs text-gray-400">{r.adapter}</td>
                        <td className="py-2 pr-3 text-xs text-gray-400">
                          {r.declared_capabilities.join(", ") || "—"}
                        </td>
                        <td className="py-2 pr-3">{fmtRate(r.stats.success_rate)}</td>
                        <td className="py-2 pr-3">{fmtAvg(r.stats.avg_duration_ms)}</td>
                        <td className="py-2 pr-3">
                          <button
                            className="rounded bg-indigo-500/20 px-2 py-1 text-xs text-indigo-300 hover:bg-indigo-500/30"
                            onClick={() => {
                              setDispatchAgent(r.agent_id);
                              if (!dispatchPrompt) setDispatchPrompt(bidTask);
                            }}
                          >
                            dispatch here
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ── Dispatch ──────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
          Dispatch (real subprocess, no shell)
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end mb-3">
          <label className="text-xs text-gray-400">
            Agent
            <select
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none"
              value={dispatchAgent}
              onChange={(e) => setDispatchAgent(e.target.value)}
            >
              <option value="">— pick an agent —</option>
              {(agents ?? [])
                .filter((a) => a.is_active && a.adapter !== "none")
                .map((a) => (
                  <option key={a.agent_id} value={a.agent_id}>
                    {a.name} ({a.adapter})
                  </option>
                ))}
            </select>
          </label>
          <label className="text-xs text-gray-400 md:col-span-2">
            Prompt
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none"
              value={dispatchPrompt}
              onChange={(e) => setDispatchPrompt(e.target.value)}
              placeholder="summarize the repo README"
            />
          </label>
          <label className="text-xs text-gray-400">
            Timeout (s, 1–600)
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none"
              value={dispatchTimeout}
              onChange={(e) => setDispatchTimeout(e.target.value)}
              inputMode="numeric"
            />
          </label>
        </div>
        <button
          className="rounded bg-indigo-500/30 px-4 py-2 text-sm text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
          disabled={busy !== null}
          onClick={() => void runDispatch()}
        >
          {busy === "dispatch" ? "Dispatching…" : "Dispatch"}
        </button>

        {lastRun && (
          <div className="mt-4 rounded border border-white/15 bg-black/30 p-3 space-y-1 text-xs">
            <p className="font-mono text-gray-300">
              {lastRun.run_id} · {lastRun.agent_name} · adapter {lastRun.adapter} ·{" "}
              {lastRun.duration_ms} ms
            </p>
            <p>
              status{" "}
              <span
                className={
                  lastRun.status === "completed"
                    ? "text-emerald-300"
                    : lastRun.status === "timeout"
                      ? "text-amber-300"
                      : "text-red-300"
                }
              >
                {lastRun.status}
              </span>
              {lastRun.exit_code !== null && (
                <span className="text-gray-400"> · exit code {lastRun.exit_code}</span>
              )}
              {lastRun.error && <span className="text-red-300"> · {lastRun.error}</span>}
            </p>
            {lastRun.stdout_preview && (
              <pre className="overflow-x-auto rounded bg-black/40 p-2 text-gray-300 whitespace-pre-wrap">
                stdout: {lastRun.stdout_preview}
              </pre>
            )}
            {lastRun.stderr_preview && (
              <pre className="overflow-x-auto rounded bg-black/40 p-2 text-gray-300 whitespace-pre-wrap">
                stderr: {lastRun.stderr_preview}
              </pre>
            )}
            {!lastRun.stdout_preview && !lastRun.stderr_preview && !lastRun.error && (
              <p className="text-gray-500">no output captured</p>
            )}
          </div>
        )}
      </section>

      {/* ── Run history ───────────────────────────────────────────────── */}
      <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
          Dispatch history (persisted, measured)
        </h2>
        {runs.length === 0 ? (
          <p className="text-sm text-gray-500">
            NO DATA — no fleet dispatch has run yet. Every real dispatch is recorded
            here with its duration, exit code, and output previews.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b border-white/10">
                  <th className="py-2 pr-3">Started</th>
                  <th className="py-2 pr-3">Agent</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2 pr-3">Duration</th>
                  <th className="py-2 pr-3">Prompt</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.run_id} className="border-b border-white/5">
                    <td className="py-2 pr-3 text-xs text-gray-400 font-mono">{r.started_at}</td>
                    <td className="py-2 pr-3">{r.agent_name}</td>
                    <td className="py-2 pr-3">
                      <span
                        className={
                          r.status === "completed"
                            ? "text-emerald-300"
                            : r.status === "timeout"
                              ? "text-amber-300"
                              : "text-red-300"
                        }
                      >
                        {r.status}
                        {r.exit_code !== null ? ` (${r.exit_code})` : ""}
                      </span>
                    </td>
                    <td className="py-2 pr-3 text-xs text-gray-400">{r.duration_ms} ms</td>
                    <td className="py-2 pr-3 text-xs text-gray-400 max-w-[24rem] truncate">
                      {r.prompt_preview}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
