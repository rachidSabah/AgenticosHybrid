"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type CounterfactualDiff,
  type CounterfactualForkRecord,
  type CounterfactualMutation,
  type CounterfactualRun,
} from "@/lib/api";

/**
 * Counterfactual Fork Lab — fork a recorded event stream at any point,
 * apply explicit mutations, replay through the real event bus, and diff
 * the two universes. Everything shown is measured from the real journal:
 * nothing is predicted, simulated, or synthesized.
 */

const MUTATION_OPS: CounterfactualMutation["op"][] = [
  "replace_field",
  "drop_event",
  "replace_payload",
];

interface MutationDraft {
  op: CounterfactualMutation["op"];
  index: string;
  field_path: string;
  value: string;
}

const EMPTY_DRAFT: MutationDraft = { op: "replace_field", index: "0", field_path: "", value: "" };

export function CounterfactualLab() {
  const [runs, setRuns] = useState<CounterfactualRun[] | null>(null);
  const [forks, setForks] = useState<CounterfactualForkRecord[]>([]);
  const [source, setSource] = useState<string>("");
  const [forkAt, setForkAt] = useState<string>("0");
  const [replay, setReplay] = useState(false);
  const [drafts, setDrafts] = useState<MutationDraft[]>([{ ...EMPTY_DRAFT }]);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastFork, setLastFork] = useState<CounterfactualForkRecord | null>(null);
  const [diff, setDiff] = useState<CounterfactualDiff | null>(null);
  const [diffA, setDiffA] = useState<string>("");
  const [diffB, setDiffB] = useState<string>("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [runsRes, forksRes] = await Promise.all([
        api.counterfactualRuns(50),
        api.counterfactualForks(),
      ]);
      setRuns(runsRes.runs ?? []);
      setForks(forksRes.forks ?? []);
    } catch (e) {
      setRuns([]);
      setForks([]);
      setNotice(`Event journal unavailable — no recorded runs can be shown: ${String(e)}`);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const sourceRun = (runs ?? []).find((r) => r.correlation_id === source) ?? null;

  const buildMutations = (): CounterfactualMutation[] => {
    const out: CounterfactualMutation[] = [];
    for (const d of drafts) {
      const index = Number.parseInt(d.index, 10);
      if (d.op === "drop_event") {
        out.push({ op: "drop_event", index });
        continue;
      }
      if (d.op === "replace_field") {
        let value: unknown = d.value;
        try {
          value = JSON.parse(d.value);
        } catch {
          // keep raw string — an honest scalar edit
        }
        out.push({ op: "replace_field", index, field_path: d.field_path, value });
        continue;
      }
      let payload: Record<string, unknown> = {};
      try {
        payload = JSON.parse(d.value) as Record<string, unknown>;
      } catch {
        payload = {};
      }
      out.push({ op: "replace_payload", index, payload });
    }
    return out;
  };

  const executeFork = async () => {
    if (!source) {
      setNotice("Pick a recorded run first — nothing has been forked.");
      return;
    }
    setBusy("fork");
    setNotice(null);
    try {
      const record = await api.counterfactualFork({
        source_correlation_id: source,
        fork_at: Number.parseInt(forkAt, 10) || 0,
        mutations: buildMutations(),
        replay,
      });
      setLastFork(record);
      setDiffB(record.fork_id);
      if (!diffA) setDiffA(source);
      await load();
    } catch (e) {
      setLastFork(null);
      setNotice(`Fork rejected: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const runDiff = async () => {
    if (!diffA || !diffB) {
      setNotice("Pick both universes (A and B) to diff.");
      return;
    }
    setBusy("diff");
    setNotice(null);
    setDiff(null);
    try {
      setDiff(await api.counterfactualDiff(diffA, diffB));
    } catch (e) {
      setNotice(`Diff failed: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#05060a] text-gray-200 p-6 space-y-6">
      <header className="border-b border-white/10 pb-4">
        <h1 className="text-xl font-bold text-white">Counterfactual Fork Lab</h1>
        <p className="text-sm text-gray-400 mt-1">
          Fork a recorded run at any event, apply explicit mutations, and replay the
          fork through the real event bus. Forks are persisted journal streams — the
          future is produced by real subscribers, never predicted.
        </p>
      </header>

      {notice && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm text-amber-200">
          {notice}
        </div>
      )}

      {/* ── Recorded runs ─────────────────────────────────────────────── */}
      <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
          Recorded runs (event journal)
        </h2>
        {runs === null ? (
          <p className="text-sm text-gray-500">Loading journal…</p>
        ) : runs.length === 0 ? (
          <p className="text-sm text-gray-500">
            NO DATA — no recorded event streams yet. Run a mission first; everything
            journaled under a correlation id appears here.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b border-white/10">
                  <th className="py-2 pr-3">Correlation ID</th>
                  <th className="py-2 pr-3">Events</th>
                  <th className="py-2 pr-3">Span (ms)</th>
                  <th className="py-2 pr-3">Event types</th>
                  <th className="py-2 pr-3">Kind</th>
                  <th className="py-2 pr-3">Use as</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.correlation_id} className="border-b border-white/5">
                    <td className="py-2 pr-3 font-mono text-xs text-gray-200">{r.correlation_id}</td>
                    <td className="py-2 pr-3">{r.event_count}</td>
                    <td className="py-2 pr-3">{r.span_ms}</td>
                    <td className="py-2 pr-3 text-xs text-gray-400">{r.event_types.join(", ")}</td>
                    <td className="py-2 pr-3">
                      {r.forked ? (
                        <span className="rounded bg-fuchsia-500/20 px-2 py-0.5 text-xs text-fuchsia-300">
                          FORK
                        </span>
                      ) : (
                        <span className="rounded bg-white/10 px-2 py-0.5 text-xs text-gray-300">
                          ORIGINAL
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-3 space-x-2">
                      <button
                        className="rounded bg-indigo-500/20 px-2 py-1 text-xs text-indigo-300 hover:bg-indigo-500/30"
                        onClick={() => {
                          setSource(r.correlation_id);
                          setForkAt(String(r.event_count));
                        }}
                      >
                        Fork source
                      </button>
                      <button
                        className="rounded bg-white/10 px-2 py-1 text-xs text-gray-300 hover:bg-white/20"
                        onClick={() => {
                          if (!diffA) setDiffA(r.correlation_id);
                          else setDiffB(r.correlation_id);
                        }}
                      >
                        → A/B
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Fork builder ──────────────────────────────────────────────── */}
      <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
          Fork builder
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <label className="text-xs text-gray-400">
            Source run
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none font-mono"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="correlation_id"
            />
          </label>
          <label className="text-xs text-gray-400">
            Fork at event index (0–{sourceRun ? sourceRun.event_count : "?"} — the prefix
            up to this index is carried; the rest is the counterfactual future)
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none"
              value={forkAt}
              onChange={(e) => setForkAt(e.target.value)}
              inputMode="numeric"
            />
          </label>
          <label className="text-xs text-gray-400 flex items-end gap-2">
            <input
              type="checkbox"
              checked={replay}
              onChange={(e) => setReplay(e.target.checked)}
            />
            <span>Replay through the real event bus</span>
          </label>
        </div>

        <div className="space-y-2 mb-3">
          {drafts.map((d, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 items-end">
              <select
                className="col-span-3 rounded bg-black/40 border border-white/15 px-2 py-2 text-xs text-gray-100"
                value={d.op}
                onChange={(e) => {
                  const next = [...drafts];
                  next[i] = { ...d, op: e.target.value as MutationDraft["op"] };
                  setDrafts(next);
                }}
              >
                {MUTATION_OPS.map((op) => (
                  <option key={op} value={op}>
                    {op}
                  </option>
                ))}
              </select>
              <input
                className="col-span-2 rounded bg-black/40 border border-white/15 px-2 py-2 text-xs text-gray-100"
                value={d.index}
                onChange={(e) => {
                  const next = [...drafts];
                  next[i] = { ...d, index: e.target.value };
                  setDrafts(next);
                }}
                placeholder="orig index"
                inputMode="numeric"
              />
              {d.op === "replace_field" && (
                <>
                  <input
                    className="col-span-3 rounded bg-black/40 border border-white/15 px-2 py-2 text-xs text-gray-100"
                    value={d.field_path}
                    onChange={(e) => {
                      const next = [...drafts];
                      next[i] = { ...d, field_path: e.target.value };
                      setDrafts(next);
                    }}
                    placeholder="payload field path (dotted)"
                  />
                  <input
                    className="col-span-3 rounded bg-black/40 border border-white/15 px-2 py-2 text-xs text-gray-100"
                    value={d.value}
                    onChange={(e) => {
                      const next = [...drafts];
                      next[i] = { ...d, value: e.target.value };
                      setDrafts(next);
                    }}
                    placeholder='JSON value e.g. "x" or 42'
                  />
                </>
              )}
              {d.op === "replace_payload" && (
                <input
                  className="col-span-6 rounded bg-black/40 border border-white/15 px-2 py-2 text-xs text-gray-100"
                  value={d.value}
                  onChange={(e) => {
                    const next = [...drafts];
                    next[i] = { ...d, value: e.target.value };
                    setDrafts(next);
                  }}
                  placeholder='full payload JSON e.g. {"seq": 0}'
                />
              )}
              {d.op === "drop_event" && (
                <p className="col-span-6 text-xs text-gray-500 self-center">
                  removes the event at the given original index from the fork
                </p>
              )}
              <button
                className="col-span-1 rounded bg-red-500/20 px-2 py-2 text-xs text-red-300 hover:bg-red-500/30"
                onClick={() => setDrafts(drafts.filter((_, j) => j !== i))}
                aria-label="remove mutation"
              >
                ✕
              </button>
            </div>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <button
            className="rounded bg-indigo-500/30 px-4 py-2 text-sm text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
            disabled={busy !== null}
            onClick={() => void executeFork()}
          >
            {busy === "fork" ? "Forking…" : "Create fork"}
          </button>
          <button
            className="rounded bg-white/10 px-3 py-2 text-xs text-gray-300 hover:bg-white/20"
            onClick={() => setDrafts([...drafts, { ...EMPTY_DRAFT }])}
          >
            + mutation
          </button>
        </div>

        {lastFork && (
          <div className="mt-3 rounded border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-xs text-emerald-200 font-mono">
            {lastFork.fork_id}: retained {lastFork.lineage.retained_prefix}/
            {lastFork.lineage.source_event_count} events, {lastFork.lineage.mutations.length}{" "}
            mutation(s) applied verbatim, {lastFork.replayed} event(s) replayed on the bus.
          </div>
        )}
      </section>

      {/* ── Diff ──────────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
          Universe diff
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end mb-3">
          <label className="text-xs text-gray-400">
            Universe A
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none font-mono"
              value={diffA}
              onChange={(e) => setDiffA(e.target.value)}
            />
          </label>
          <label className="text-xs text-gray-400">
            Universe B
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none font-mono"
              value={diffB}
              onChange={(e) => setDiffB(e.target.value)}
            />
          </label>
          <button
            className="rounded bg-indigo-500/30 px-4 py-2 text-sm text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
            disabled={busy !== null}
            onClick={() => void runDiff()}
          >
            {busy === "diff" ? "Diffing…" : "Diff"}
          </button>
        </div>

        {diff && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-center">
              <Stat label="matched" value={diff.summary.matched} />
              <Stat label="changed" value={diff.summary.changed} />
              <Stat label="only in A" value={diff.summary.only_in_a} />
              <Stat label="only in B" value={diff.summary.only_in_b} />
              <Stat
                label="span Δ (ms)"
                value={diff.summary.span_delta_ms === null ? "—" : diff.summary.span_delta_ms}
              />
            </div>

            {diff.changed.length === 0 && diff.only_in_a.length === 0 && diff.only_in_b.length === 0 && (
              <p className="text-sm text-gray-500">
                The two streams are event-for-event identical as recorded.
              </p>
            )}

            {diff.changed.map((c) => (
              <div key={`c-${c.index}`} className="rounded border border-amber-500/30 bg-amber-500/5 p-3">
                <p className="text-xs text-amber-300 font-mono mb-2">
                  #{c.index} {c.event_type} — differing: {c.differing_fields.join(", ")}
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <pre className="overflow-x-auto rounded bg-black/40 p-2 text-xs text-gray-300">
                    A: {JSON.stringify(c.payload_a, null, 2)}
                  </pre>
                  <pre className="overflow-x-auto rounded bg-black/40 p-2 text-xs text-gray-300">
                    B: {JSON.stringify(c.payload_b, null, 2)}
                  </pre>
                </div>
              </div>
            ))}

            {(diff.only_in_a.length > 0 || diff.only_in_b.length > 0) && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                <div className="rounded border border-white/10 p-2">
                  <p className="text-xs uppercase text-gray-400 mb-1">Only in A</p>
                  {diff.only_in_a.map((o) => (
                    <p key={`a-${o.index}`} className="text-xs text-gray-400 font-mono">
                      #{o.index} {o.event_type}
                    </p>
                  ))}
                  {diff.only_in_a.length === 0 && <p className="text-xs text-gray-600">—</p>}
                </div>
                <div className="rounded border border-white/10 p-2">
                  <p className="text-xs uppercase text-gray-400 mb-1">Only in B</p>
                  {diff.only_in_b.map((o) => (
                    <p key={`b-${o.index}`} className="text-xs text-gray-400 font-mono">
                      #{o.index} {o.event_type}
                    </p>
                  ))}
                  {diff.only_in_b.length === 0 && <p className="text-xs text-gray-600">—</p>}
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded border border-white/10 bg-black/30 p-2">
      <p className="text-lg font-semibold text-white">{value}</p>
      <p className="text-xs text-gray-500">{label}</p>
    </div>
  );
}
