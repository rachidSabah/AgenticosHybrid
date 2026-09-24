"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type EgressPolicy as EgressPolicyType,
  type EgressVerdict,
  type RedactionReport,
} from "@/lib/api";

/**
 * Egress Policy — the rules every outgoing byte and tool call must obey:
 * PII/secret redaction, per-binding tool allow/deny, per-call cost caps,
 * and air-gap mode (loopback endpoints only).
 *
 * Honesty rules: the inspector counts exactly what the patterns matched;
 * an unmeasurable cost cap verdict says so; nothing pretends to be safe
 * without measurement.
 */

const SAMPLE_TEXT = `deploy with token ghp_0123456789abcdef0123456789abcdef0123
mail jane.doe@example.com, card 4111 1111 1111 1111, ssn 123-45-6789`;

export function EgressPolicyView() {
  const [policy, setPolicy] = useState<EgressPolicyType | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [denyDraft, setDenyDraft] = useState("");
  const [allowDraft, setAllowDraft] = useState("");
  const [capDraft, setCapDraft] = useState("");
  const [rxName, setRxName] = useState("");
  const [rxPattern, setRxPattern] = useState("");

  const [inspectInput, setInspectInput] = useState(SAMPLE_TEXT);
  const [inspectReport, setInspectReport] = useState<RedactionReport | null>(null);
  const [redacted, setRedacted] = useState<string | null>(null);

  const [toolCheck, setToolCheck] = useState("");
  const [toolVerdict, setToolVerdict] = useState<EgressVerdict | null>(null);
  const [urlCheck, setUrlCheck] = useState("");
  const [urlVerdict, setUrlVerdict] = useState<EgressVerdict | null>(null);

  const load = useCallback(async () => {
    try {
      const p = await api.egressPolicy();
      setPolicy(p);
      setDenyDraft(p.tools_deny.join(", "));
      setAllowDraft(p.tools_allow.join(", "));
      setCapDraft(p.max_cost_per_call_usd === null ? "" : String(p.max_cost_per_call_usd));
    } catch (e) {
      setPolicy(null);
      setNotice(`Egress policy unavailable: ${String(e)}`);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (changes: Partial<EgressPolicyType>, label: string) => {
    setBusy(label);
    setNotice(null);
    try {
      setPolicy(await api.egressPolicyUpdate(changes));
    } catch (e) {
      setNotice(`Policy not saved: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const runInspect = async () => {
    setBusy("inspect");
    setNotice(null);
    setRedacted(null);
    try {
      setInspectReport(await api.egressInspect(inspectInput));
    } catch (e) {
      setNotice(`Inspect failed: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const runRedact = async () => {
    setBusy("redact");
    setNotice(null);
    try {
      const res = await api.egressRedact(inspectInput);
      setInspectReport(res.report);
      setRedacted(res.redacted);
    } catch (e) {
      setNotice(`Redact failed: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const runToolCheck = async () => {
    setBusy("toolcheck");
    setNotice(null);
    setToolVerdict(null);
    try {
      setToolVerdict(await api.egressCheckTool(toolCheck));
    } catch (e) {
      setNotice(`Tool check failed: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const runUrlCheck = async () => {
    setBusy("urlcheck");
    setNotice(null);
    setUrlVerdict(null);
    try {
      setUrlVerdict(await api.egressCheckUrl(urlCheck));
    } catch (e) {
      setNotice(`URL check failed: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#05060a] text-gray-200 p-6 space-y-6">
      <header className="border-b border-white/10 pb-4">
        <h1 className="text-xl font-bold text-white">Egress Policy</h1>
        <p className="text-sm text-gray-400 mt-1">
          One policy layer for everything leaving the machine: PII and secret
          redaction on the gateway egress path, tool allow/deny rules, per-call
          cost caps measured against operator prices, and air-gap mode that
          permits loopback endpoints only. Checked at bind time and again at
          request time.
        </p>
      </header>

      {notice && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm text-amber-200 font-mono break-all">
          {notice}
        </div>
      )}

      {policy === null ? (
        <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
          <p className="text-sm text-gray-500">
            NO DATA — the policy could not be loaded. Nothing below is editable
            state; fix the backend connection first.
          </p>
        </section>
      ) : (
        <>
          {/* ── Policy switches ─────────────────────────────────────── */}
          <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
              Policy switches (persisted on change)
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Toggle
                label="Redact secrets"
                desc="API keys, tokens, bearer headers, PEM key blocks, KEY=value"
                checked={policy.redact_secrets}
                disabled={busy !== null}
                onChange={(v) => void save({ redact_secrets: v }, "secrets")}
              />
              <Toggle
                label="Redact PII"
                desc="emails, SSNs, NANP phones, Luhn-verified card numbers"
                checked={policy.redact_pii}
                disabled={busy !== null}
                onChange={(v) => void save({ redact_pii: v }, "pii")}
              />
              <Toggle
                label="Air-gap mode"
                desc="only loopback endpoints may be bound or used"
                checked={policy.air_gap}
                disabled={busy !== null}
                onChange={(v) => void save({ air_gap: v }, "airgap")}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4 items-end">
              <label className="text-xs text-gray-400">
                Per-call cost cap (USD; empty = no cap)
                <input
                  className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100"
                  value={capDraft}
                  onChange={(e) => setCapDraft(e.target.value)}
                  inputMode="decimal"
                  placeholder="0.05"
                />
              </label>
              <label className="text-xs text-gray-400">
                Denied tools (comma-separated)
                <input
                  className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 font-mono"
                  value={denyDraft}
                  onChange={(e) => setDenyDraft(e.target.value)}
                  placeholder="terminal, risky/server"
                />
              </label>
              <label className="text-xs text-gray-400">
                Allowed tools (empty = no allow restriction)
                <input
                  className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 font-mono"
                  value={allowDraft}
                  onChange={(e) => setAllowDraft(e.target.value)}
                  placeholder="filesystem/read"
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-2 mt-3">
              <button
                className="rounded bg-indigo-500/30 px-3 py-2 text-xs text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
                disabled={busy !== null}
                onClick={() =>
                  void save(
                    {
                      tools_deny: denyDraft
                        .split(",")
                        .map((t) => t.trim())
                        .filter(Boolean),
                      tools_allow: allowDraft
                        .split(",")
                        .map((t) => t.trim())
                        .filter(Boolean),
                    },
                    "tools"
                  )
                }
              >
                {busy === "tools" ? "Saving…" : "Save tool rules"}
              </button>
              <button
                className="rounded bg-indigo-500/30 px-3 py-2 text-xs text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
                disabled={busy !== null}
                onClick={() =>
                  void save(
                    {
                      max_cost_per_call_usd: capDraft === null || capDraft === "" ? null : Number(capDraft),
                    },
                    "cap"
                  )
                }
              >
                {busy === "cap" ? "Saving…" : "Save cost cap"}
              </button>
            </div>

            <div className="mt-4 rounded border border-white/15 bg-black/30 p-3">
              <p className="text-xs uppercase tracking-wider text-gray-400 mb-2">
                Custom redaction patterns ({Object.keys(policy.custom_redactions).length})
              </p>
              {Object.entries(policy.custom_redactions).length === 0 ? (
                <p className="text-xs text-gray-500">none configured</p>
              ) : (
                <div className="space-y-1 mb-2">
                  {Object.entries(policy.custom_redactions).map(([name, pattern]) => (
                    <p key={name} className="text-xs font-mono text-gray-300">
                      <span className="text-sky-300">{name}</span>: {pattern}
                    </p>
                  ))}
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-end">
                <input
                  className="rounded bg-black/40 border border-white/15 px-3 py-2 text-xs text-gray-100"
                  value={rxName}
                  onChange={(e) => setRxName(e.target.value)}
                  placeholder="pattern name"
                />
                <input
                  className="rounded bg-black/40 border border-white/15 px-3 py-2 text-xs text-gray-100 font-mono"
                  value={rxPattern}
                  onChange={(e) => setRxPattern(e.target.value)}
                  placeholder="regex, e.g. \\bProject\\s+X\\b"
                />
                <button
                  className="rounded bg-indigo-500/30 px-3 py-2 text-xs text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
                  disabled={busy !== null || !rxName || !rxPattern}
                  onClick={() => {
                    const next = { ...policy.custom_redactions, [rxName]: rxPattern };
                    void save({ custom_redactions: next }, "regex");
                    setRxName("");
                    setRxPattern("");
                  }}
                >
                  {busy === "regex" ? "Saving…" : "Add pattern"}
                </button>
              </div>
            </div>
          </section>

          {/* ── Live inspector ──────────────────────────────────────── */}
          <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
              Live inspector (dry run against the real policy)
            </h2>
            <textarea
              className="w-full h-28 rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 font-mono focus:border-indigo-400 outline-none"
              value={inspectInput}
              onChange={(e) => setInspectInput(e.target.value)}
            />
            <div className="flex gap-2 mt-2">
              <button
                className="rounded bg-indigo-500/30 px-3 py-2 text-xs text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
                disabled={busy !== null}
                onClick={() => void runInspect()}
              >
                {busy === "inspect" ? "Inspecting…" : "Inspect"}
              </button>
              <button
                className="rounded bg-white/10 px-3 py-2 text-xs text-gray-300 hover:bg-white/20 disabled:opacity-40"
                disabled={busy !== null}
                onClick={() => void runRedact()}
              >
                {busy === "redact" ? "Redacting…" : "Redact"}
              </button>
            </div>
            {inspectReport && (
              <div className="mt-3 space-y-2">
                <p className="text-xs text-gray-300">
                  {inspectReport.replacements === 0
                    ? "nothing matched — 0 replacements (measured)"
                    : `${inspectReport.replacements} replacement(s): ${Object.entries(
                        inspectReport.by_class
                      )
                        .map(([k, v]) => `${k} × ${v}`)
                        .join(", ")}`}
                </p>
                {redacted !== null && (
                  <pre className="overflow-x-auto rounded bg-black/40 p-2 text-xs text-gray-300 whitespace-pre-wrap">
                    {redacted}
                  </pre>
                )}
              </div>
            )}
          </section>

          {/* ── Verdict checkers ────────────────────────────────────── */}
          <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
              Verdict checks (tool rules &amp; air-gap)
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-xs text-gray-400 block">
                  Tool name
                  <input
                    className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 font-mono"
                    value={toolCheck}
                    onChange={(e) => setToolCheck(e.target.value)}
                    placeholder="mcpserver/terminal"
                  />
                </label>
                <button
                  className="rounded bg-indigo-500/30 px-3 py-2 text-xs text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
                  disabled={busy !== null || !toolCheck}
                  onClick={() => void runToolCheck()}
                >
                  {busy === "toolcheck" ? "Checking…" : "Check tool"}
                </button>
                {toolVerdict && <Verdict v={toolVerdict} />}
              </div>
              <div className="space-y-2">
                <label className="text-xs text-gray-400 block">
                  Endpoint URL
                  <input
                    className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 font-mono"
                    value={urlCheck}
                    onChange={(e) => setUrlCheck(e.target.value)}
                    placeholder="http://api.openai.com/v1"
                  />
                </label>
                <button
                  className="rounded bg-indigo-500/30 px-3 py-2 text-xs text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
                  disabled={busy !== null || !urlCheck}
                  onClick={() => void runUrlCheck()}
                >
                  {busy === "urlcheck" ? "Checking…" : "Check URL"}
                </button>
                {urlVerdict && <Verdict v={urlVerdict} />}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Toggle({
  label,
  desc,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  desc: string;
  checked: boolean;
  disabled: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-3 rounded border border-white/10 bg-black/30 p-3 cursor-pointer">
      <input
        type="checkbox"
        className="mt-1"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <span className="block text-sm text-gray-200">{label}</span>
        <span className="block text-xs text-gray-500">{desc}</span>
      </span>
    </label>
  );
}

function Verdict({ v }: { v: EgressVerdict }) {
  return (
    <p
      className={`rounded border px-3 py-2 text-xs font-mono break-all ${
        v.allowed
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
          : "border-red-500/30 bg-red-500/10 text-red-200"
      }`}
    >
      {v.allowed ? "ALLOWED" : "REFUSED"} — {v.reason}
    </p>
  );
}
