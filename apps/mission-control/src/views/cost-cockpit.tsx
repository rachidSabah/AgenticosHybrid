"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type CostSummary } from "@/lib/api";

/**
 * Cost Cockpit — measured spend per agent / plan / model, budget alerts,
 * and a forecast that is exactly what it claims: a linear projection of
 * the measured burn rate.
 *
 * Honesty rules: totals come only from recorded cost events; a dimension a
 * producer never supplied (e.g. model) shows no invented rows; no entries
 * means NO DATA, and the forecast is labeled as a projection, not a
 * prediction.
 */

const usd = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `$${v.toFixed(6).replace(/0+$/, "").replace(/\.$/, ".0")}`;

export function CostCockpit() {
  const [summary, setSummary] = useState<CostSummary | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [windowHours, setWindowHours] = useState("");
  const [budgetDraft, setBudgetDraft] = useState("");

  const load = useCallback(async () => {
    try {
      const wh = Number.parseFloat(windowHours);
      setSummary(await api.costSummary(Number.isFinite(wh) && wh > 0 ? wh : undefined));
    } catch (e) {
      setSummary(null);
      setNotice(`Cost data unavailable: ${String(e)}`);
    }
  }, [windowHours]);

  useEffect(() => {
    void load();
  }, [load]);

  const saveBudget = async () => {
    setBusy("budget");
    setNotice(null);
    try {
      await api.costSetBudget(budgetDraft.trim() === "" ? null : Number(budgetDraft));
      await load();
    } catch (e) {
      setNotice(`Budget not saved: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const b = summary?.budget;

  return (
    <div className="min-h-screen bg-[#05060a] text-gray-200 p-6 space-y-6">
      <header className="border-b border-white/10 pb-4">
        <h1 className="text-xl font-bold text-white">Cost Cockpit</h1>
        <p className="text-sm text-gray-400 mt-1">
          Measured spend recorded from real cost events (orchestration runs and
          explicit integrations), aggregated per agent, per plan, and per model.
          The forecast is a linear projection of the measured burn rate — a
          projection of history, not a prediction.
        </p>
      </header>

      {notice && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm text-amber-200 font-mono break-all">
          {notice}
        </div>
      )}

      {summary === null ? (
        <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
          <p className="text-sm text-gray-500">
            NO DATA — cost totals cannot be loaded. Nothing below is estimated;
            fix the backend connection first.
          </p>
        </section>
      ) : !summary.has_data ? (
        <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
          <p className="text-sm text-gray-500 mb-4">
            NO DATA — no cost events recorded yet. Spend appears here as
            orchestration runs and integrations record real costs. Nothing is
            simulated.
          </p>
          <BudgetEditor
            budgetDraft={budgetDraft}
            setBudgetDraft={setBudgetDraft}
            busy={busy}
            saveBudget={saveBudget}
            note={b?.note}
          />
        </section>
      ) : (
        <>
          {/* ── Totals ──────────────────────────────────────────────── */}
          <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300">
                Measured spend
              </h2>
              <label className="text-xs text-gray-400 flex items-center gap-2">
                window (hours, empty = all)
                <input
                  className="w-24 rounded bg-black/40 border border-white/15 px-2 py-1 text-xs text-gray-100"
                  value={windowHours}
                  onChange={(e) => setWindowHours(e.target.value)}
                  inputMode="decimal"
                />
              </label>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-center mb-4">
              <Stat label="total (measured)" value={usd(summary.total_usd)} />
              <Stat label="entries" value={String(summary.entries)} />
              <Stat
                label="burn rate"
                value={
                  summary.burn_rate_usd_per_hour
                    ? `${usd(summary.burn_rate_usd_per_hour.usd_per_hour)}/h`
                    : "—"
                }
              />
              <Stat
                label="projected 24h"
                value={
                  summary.forecast ? usd(summary.forecast.next_24h_usd) : "—"
                }
              />
            </div>
            {summary.forecast && (
              <p className="text-xs text-gray-500 mb-3">
                forecast method: {summary.forecast.method} over the last{" "}
                {summary.burn_rate_usd_per_hour?.window_span_hours}h of measured
                entries ({summary.burn_rate_usd_per_hour?.entries_measured} entries)
              </p>
            )}

            <BudgetEditor
              budgetDraft={budgetDraft}
              setBudgetDraft={setBudgetDraft}
              busy={busy}
              saveBudget={saveBudget}
              status={b}
            />

            {summary.alerts.length > 0 && (
              <div className="mt-4 space-y-1">
                <p className="text-xs uppercase tracking-wider text-amber-300">
                  Budget alerts ({summary.alerts.length})
                </p>
                {summary.alerts
                  .slice()
                  .reverse()
                  .slice(0, 8)
                  .map((a, i) => (
                    <p key={`${a.ts}-${i}`} className="text-xs font-mono text-amber-200">
                      {new Date(a.ts * 1000).toISOString()} — threshold{" "}
                      {(a.threshold * 100).toFixed(0)}% crossed: spent{" "}
                      {usd(a.spent_usd)} of {usd(a.budget_usd)}
                    </p>
                  ))}
              </div>
            )}
          </section>

          {/* ── Breakdowns ──────────────────────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Breakdown title="By agent" rows={summary.by_agent} empty="no agent dimension recorded" />
            <Breakdown title="By plan / task" rows={summary.by_plan} empty="no plan dimension recorded" />
            <Breakdown title="By model" rows={summary.by_model} empty="no model dimension recorded" />
          </div>

          {/* ── By day ──────────────────────────────────────────────── */}
          <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
              Spend per day (measured)
            </h2>
            <div className="space-y-1">
              {summary.by_day.map((d) => (
                <p key={d.day} className="text-xs font-mono text-gray-300">
                  {d.day}: {usd(d.cost_usd)}
                </p>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-white/10 bg-black/30 p-2">
      <p className="text-lg font-semibold text-white">{value}</p>
      <p className="text-xs text-gray-500">{label}</p>
    </div>
  );
}

function Breakdown({
  title,
  rows,
  empty,
}: {
  title: string;
  rows: Array<{ key: string; cost_usd: number }>;
  empty: string;
}) {
  return (
    <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
        {title}
      </h2>
      {rows.length === 0 ? (
        <p className="text-xs text-gray-500">{empty} — nothing is inferred.</p>
      ) : (
        <div className="space-y-1">
          {rows.map((r) => (
            <div key={r.key} className="flex items-center justify-between text-xs">
              <span className="font-mono text-gray-300 truncate mr-2">{r.key}</span>
              <span className="text-gray-100">{usd(r.cost_usd)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function BudgetEditor({
  budgetDraft,
  setBudgetDraft,
  busy,
  saveBudget,
  status,
  note,
}: {
  budgetDraft: string;
  setBudgetDraft: (v: string) => void;
  busy: string | null;
  saveBudget: () => void;
  status?: {
    budget_usd: number | null;
    spent_usd: number;
    remaining_usd: number | null;
    used_ratio: number | null;
    note?: string;
  };
  note?: string;
}) {
  return (
    <div className="rounded border border-white/15 bg-black/30 p-3">
      <p className="text-xs uppercase tracking-wider text-gray-400 mb-2">Budget</p>
      {status && (
        <p className="text-xs text-gray-300 mb-2 font-mono">
          {status.budget_usd === null
            ? `no budget set · spent ${usd(status.spent_usd)}`
            : `spent ${usd(status.spent_usd)} of ${usd(status.budget_usd)} · remaining ${usd(
                status.remaining_usd
              )} · ${((status.used_ratio ?? 0) * 100).toFixed(1)}% used`}
        </p>
      )}
      {(note || (status && status.note)) && (
        <p className="text-xs text-gray-500 mb-2">{note ?? status?.note}</p>
      )}
      <div className="flex items-end gap-2">
        <label className="text-xs text-gray-400">
          Total budget (USD; empty = none)
          <input
            className="mt-1 w-40 rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100"
            value={budgetDraft}
            onChange={(e) => setBudgetDraft(e.target.value)}
            inputMode="decimal"
            placeholder="50.00"
          />
        </label>
        <button
          className="rounded bg-indigo-500/30 px-3 py-2 text-xs text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
          disabled={busy !== null}
          onClick={saveBudget}
        >
          {busy === "budget" ? "Saving…" : "Save budget"}
        </button>
      </div>
      <p className="text-xs text-gray-500 mt-2">
        alerts fire at 50% / 80% / 100% of the budget when measured spend crosses
        them
      </p>
    </div>
  );
}
