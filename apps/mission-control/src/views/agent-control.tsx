"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type CgroupGroup,
  type PackageInfo,
  type PackageJournalEntry,
} from "@/lib/api";

/**
 * Agent Cgroups & Packages — hard resource slices per agent and a real
 * signed-package lifecycle.
 *
 * Honesty rules: usage numbers come only from real accounting (bus events or
 * explicit consume calls); a quota axis with no limit shows "no limit"; the
 * package journal shows only what actually happened; verification failures
 * name the exact file.
 */

const fmtNum = (v: number | null | undefined, suffix = "") =>
  v === null || v === undefined ? "no limit" : `${v}${suffix}`;

export function AgentControl() {
  const [groups, setGroups] = useState<CgroupGroup[] | null>(null);
  const [installed, setInstalled] = useState<PackageInfo[]>([]);
  const [journal, setJournal] = useState<PackageJournalEntry[]>([]);
  const [keyId, setKeyId] = useState("");
  const [signingNote, setSigningNote] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // quota editor
  const [quotaAgent, setQuotaAgent] = useState("");
  const [qTokens, setQTokens] = useState("");
  const [qWall, setQWall] = useState("");
  const [qTools, setQTools] = useState("");
  const [qSlots, setQSlots] = useState("");

  // package forms
  const [pkSource, setPkSource] = useState("");
  const [pkName, setPkName] = useState("");
  const [pkVersion, setPkVersion] = useState("");
  const [pkPath, setPkPath] = useState("");
  const [rbName, setRbName] = useState("");
  const [lastPackInfo, setLastPackInfo] = useState<string | null>(null);
  const [lastVerify, setLastVerify] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [cg, pk] = await Promise.all([api.cgroups(), api.packages()]);
      setGroups(cg.groups ?? []);
      setInstalled(pk.installed ?? []);
      setJournal(pk.journal ?? []);
      setKeyId(pk.key_id ?? "");
      setSigningNote(pk.signing_note ?? "");
    } catch (e) {
      setGroups([]);
      setInstalled([]);
      setJournal([]);
      setNotice(`Control plane unavailable: ${String(e)}`);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const setQuota = async () => {
    if (!quotaAgent.trim()) {
      setNotice("Pick an agent id — a quota without an agent enforces nothing.");
      return;
    }
    setBusy("quota");
    setNotice(null);
    try {
      await api.cgroupsSetQuota({
        agent_id: quotaAgent.trim(),
        token_budget: qTokens ? Number(qTokens) : null,
        wall_clock_s: qWall ? Number(qWall) : null,
        tool_call_cap: qTools ? Number(qTools) : null,
        max_concurrent_llm: qSlots ? Number(qSlots) : null,
      });
      setQTokens("");
      setQWall("");
      setQTools("");
      setQSlots("");
      await load();
    } catch (e) {
      setNotice(`Quota not applied: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const control = async (verb: "freeze" | "resume" | "kill", agentId: string) => {
    setBusy(`${verb}-${agentId}`);
    setNotice(null);
    try {
      await api.cgroupsControl(verb, { agent_id: agentId });
      await load();
    } catch (e) {
      setNotice(`${verb} refused: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const pack = async () => {
    setBusy("pack");
    setNotice(null);
    setLastPackInfo(null);
    try {
      const info = await api.packPack({
        source_dir: pkSource,
        name: pkName,
        version: pkVersion,
      });
      setLastPackInfo(
        `packed ${info.package}@${info.version} -> ${info.path} (${info.files} file(s), signed, key ${info.key_id})`
      );
      setPkPath(info.path);
      await load();
    } catch (e) {
      setNotice(`Pack failed: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const verify = async () => {
    setBusy("verify");
    setNotice(null);
    setLastVerify(null);
    try {
      const v = await api.packVerify({ path: pkPath });
      setLastVerify(
        v.ok
          ? `VERIFIED: ${v.name}@${v.version} — signature ok, ${v.files_checked} file(s) checked`
          : `FAILED: ${v.problems.join("; ")}`
      );
    } catch (e) {
      setLastVerify(`Verification error: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const pkgAction = async (verb: "install" | "upgrade" | "rollback") => {
    setBusy(verb);
    setNotice(null);
    try {
      const res =
        verb === "install"
          ? await api.packInstall({ path: pkPath })
          : verb === "upgrade"
            ? await api.packUpgrade({ path: pkPath })
            : await api.packRollback({ name: rbName });
      setNotice(`${verb} OK: ${JSON.stringify(res)}`.slice(0, 240));
      await load();
    } catch (e) {
      setNotice(`${verb} refused: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#05060a] text-gray-200 p-6 space-y-6">
      <header className="border-b border-white/10 pb-4">
        <h1 className="text-xl font-bold text-white">Agent Cgroups &amp; Packages</h1>
        <p className="text-sm text-gray-400 mt-1">
          Hard resource slices per agent — tokens, wall clock, tool calls, concurrent
          LLM slots — accounted from real bus events, with mid-flight freeze, resume,
          and kill. Plus a signed-package lifecycle: pack, verify, install, upgrade,
          and rollback that replays the previous version&apos;s checkpoint with hash
          verification.
        </p>
      </header>

      {notice && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm text-amber-200 font-mono break-all">
          {notice}
        </div>
      )}

      {/* ── Control groups ────────────────────────────────────────────── */}
      <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
          Control groups (measured usage)
        </h2>
        {groups === null ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : groups.length === 0 ? (
          <p className="text-sm text-gray-500">
            NO DATA — no control groups yet. Apply a quota below; groups appear as
            soon as a quota is set or usage is recorded.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b border-white/10">
                  <th className="py-2 pr-3">Agent</th>
                  <th className="py-2 pr-3">State</th>
                  <th className="py-2 pr-3">Tokens (used / budget)</th>
                  <th className="py-2 pr-3">Wall clock</th>
                  <th className="py-2 pr-3">Tool calls (used / cap)</th>
                  <th className="py-2 pr-3">LLM slots (active / max)</th>
                  <th className="py-2 pr-3">Control</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((g) => (
                  <tr key={g.agent_id} className="border-b border-white/5">
                    <td className="py-2 pr-3 font-mono text-xs text-gray-200">
                      {g.agent_id}
                      {g.exceeded_dimension && (
                        <p className="text-xs text-red-300">exceeded: {g.exceeded_dimension}</p>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      <span
                        className={
                          g.state === "running"
                            ? "text-emerald-300"
                            : g.state === "frozen"
                              ? "text-amber-300"
                              : "text-red-300"
                        }
                      >
                        {g.state}
                      </span>
                      {g.killed_reason && (
                        <p className="text-xs text-gray-500">{g.killed_reason}</p>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-xs">
                      {g.tokens_used} / {fmtNum(g.quota.token_budget)}
                    </td>
                    <td className="py-2 pr-3 text-xs">
                      {g.wall_clock_s}s /{" "}
                      {g.quota.wall_clock_s === null ? "no limit" : `${g.quota.wall_clock_s}s`}
                    </td>
                    <td className="py-2 pr-3 text-xs">
                      {g.tool_calls} / {fmtNum(g.quota.tool_call_cap)}
                    </td>
                    <td className="py-2 pr-3 text-xs">
                      {g.llm_slots_active} / {fmtNum(g.quota.max_concurrent_llm)}
                    </td>
                    <td className="py-2 pr-3 space-x-1">
                      <button
                        className="rounded bg-amber-500/20 px-2 py-1 text-xs text-amber-300 hover:bg-amber-500/30 disabled:opacity-40"
                        disabled={busy !== null || g.state === "killed"}
                        onClick={() => void control("freeze", g.agent_id)}
                      >
                        freeze
                      </button>
                      <button
                        className="rounded bg-emerald-500/20 px-2 py-1 text-xs text-emerald-300 hover:bg-emerald-500/30 disabled:opacity-40"
                        disabled={busy !== null || g.state === "killed"}
                        onClick={() => void control("resume", g.agent_id)}
                      >
                        resume
                      </button>
                      <button
                        className="rounded bg-red-500/20 px-2 py-1 text-xs text-red-300 hover:bg-red-500/30 disabled:opacity-40"
                        disabled={busy !== null || g.state === "killed"}
                        onClick={() => void control("kill", g.agent_id)}
                      >
                        kill
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-4 rounded border border-white/15 bg-black/30 p-4 space-y-3">
          <p className="text-xs uppercase tracking-wider text-gray-400">
            Apply a quota (leave a field empty for no limit on that axis)
          </p>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            <label className="text-xs text-gray-400">
              Agent id
              <input
                className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 focus:border-indigo-400 outline-none font-mono"
                value={quotaAgent}
                onChange={(e) => setQuotaAgent(e.target.value)}
                placeholder="agent:claude"
              />
            </label>
            <label className="text-xs text-gray-400">
              Token budget
              <input
                className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100"
                value={qTokens}
                onChange={(e) => setQTokens(e.target.value)}
                inputMode="numeric"
                placeholder="100000"
              />
            </label>
            <label className="text-xs text-gray-400">
              Wall clock (s)
              <input
                className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100"
                value={qWall}
                onChange={(e) => setQWall(e.target.value)}
                inputMode="decimal"
                placeholder="3600"
              />
            </label>
            <label className="text-xs text-gray-400">
              Tool-call cap
              <input
                className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100"
                value={qTools}
                onChange={(e) => setQTools(e.target.value)}
                inputMode="numeric"
                placeholder="50"
              />
            </label>
            <label className="text-xs text-gray-400">
              Max concurrent LLM slots
              <input
                className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100"
                value={qSlots}
                onChange={(e) => setQSlots(e.target.value)}
                inputMode="numeric"
                placeholder="2"
              />
            </label>
          </div>
          <button
            className="rounded bg-indigo-500/30 px-4 py-2 text-sm text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
            disabled={busy !== null}
            onClick={() => void setQuota()}
          >
            {busy === "quota" ? "Applying…" : "Apply quota"}
          </button>
        </div>
      </section>

      {/* ── Packages ──────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-1">
          Agent packages (.agent)
        </h2>
        <p className="text-xs text-gray-500 mb-3">{signingNote}</p>
        {keyId && <p className="text-xs text-gray-400 mb-3 font-mono">signing key id: {keyId}</p>}

        {installed.length === 0 ? (
          <p className="text-sm text-gray-500 mb-3">
            NO DATA — nothing installed yet. Pack a package from a directory, verify
            it, then install; every install records a checkpoint the rollback can
            replay.
          </p>
        ) : (
          <div className="overflow-x-auto mb-3">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b border-white/10">
                  <th className="py-2 pr-3">Package</th>
                  <th className="py-2 pr-3">Current</th>
                  <th className="py-2 pr-3">All versions</th>
                  <th className="py-2 pr-3">Entrypoint</th>
                  <th className="py-2 pr-3">Capabilities</th>
                  <th className="py-2 pr-3"></th>
                </tr>
              </thead>
              <tbody>
                {installed.map((p) => (
                  <tr key={p.name} className="border-b border-white/5">
                    <td className="py-2 pr-3 text-gray-100">{p.name}</td>
                    <td className="py-2 pr-3 text-emerald-300">{p.current}</td>
                    <td className="py-2 pr-3 text-xs text-gray-400">{p.versions.join(", ")}</td>
                    <td className="py-2 pr-3 text-xs font-mono text-gray-400">
                      {p.entrypoint || "—"}
                    </td>
                    <td className="py-2 pr-3 text-xs text-gray-400">
                      {p.capabilities.length === 0 ? "—" : p.capabilities.join(", ")}
                    </td>
                    <td className="py-2 pr-3">
                      <button
                        className="rounded bg-amber-500/20 px-2 py-1 text-xs text-amber-300 hover:bg-amber-500/30 disabled:opacity-40"
                        disabled={busy !== null}
                        onClick={() => {
                          setRbName(p.name);
                          void pkgAction("rollback");
                        }}
                      >
                        rollback
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="rounded border border-white/15 bg-black/30 p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="text-xs text-gray-400">
              Source directory (to pack)
              <input
                className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 font-mono"
                value={pkSource}
                onChange={(e) => setPkSource(e.target.value)}
                placeholder="/path/to/agent-src"
              />
            </label>
            <label className="text-xs text-gray-400">
              Package name
              <input
                className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100"
                value={pkName}
                onChange={(e) => setPkName(e.target.value)}
                placeholder="my-agent"
              />
            </label>
            <label className="text-xs text-gray-400">
              Version
              <input
                className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100"
                value={pkVersion}
                onChange={(e) => setPkVersion(e.target.value)}
                placeholder="1.0.0"
              />
            </label>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
            <label className="text-xs text-gray-400 md:col-span-2">
              Package file path (.agent)
              <input
                className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 font-mono"
                value={pkPath}
                onChange={(e) => setPkPath(e.target.value)}
                placeholder="/path/to/package.agent"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded bg-indigo-500/30 px-3 py-2 text-xs text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
                disabled={busy !== null}
                onClick={() => void pack()}
              >
                {busy === "pack" ? "Packing…" : "Pack"}
              </button>
              <button
                className="rounded bg-white/10 px-3 py-2 text-xs text-gray-300 hover:bg-white/20 disabled:opacity-40"
                disabled={busy !== null || !pkPath}
                onClick={() => void verify()}
              >
                {busy === "verify" ? "Verifying…" : "Verify"}
              </button>
              <button
                className="rounded bg-emerald-500/20 px-3 py-2 text-xs text-emerald-300 hover:bg-emerald-500/30 disabled:opacity-40"
                disabled={busy !== null || !pkPath}
                onClick={() => void pkgAction("install")}
              >
                {busy === "install" ? "Installing…" : "Install"}
              </button>
              <button
                className="rounded bg-sky-500/20 px-3 py-2 text-xs text-sky-300 hover:bg-sky-500/30 disabled:opacity-40"
                disabled={busy !== null || !pkPath}
                onClick={() => void pkgAction("upgrade")}
              >
                {busy === "upgrade" ? "Upgrading…" : "Upgrade"}
              </button>
            </div>
          </div>
          {lastPackInfo && (
            <p className="text-xs text-emerald-200 font-mono break-all">{lastPackInfo}</p>
          )}
          {lastVerify && (
            <p className="text-xs text-gray-200 font-mono break-all">{lastVerify}</p>
          )}
        </div>
      </section>

      {/* ── Package journal ───────────────────────────────────────────── */}
      <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
          Package journal (append-only, real events)
        </h2>
        {journal.length === 0 ? (
          <p className="text-sm text-gray-500">
            NO DATA — no package actions recorded yet. Pack / install / upgrade /
            rollback events land here as they happen.
          </p>
        ) : (
          <div className="space-y-1">
            {journal.map((e) => (
              <p key={e.id} className="text-xs font-mono text-gray-400">
                <span className="text-gray-500">
                  {new Date(e.ts * 1000).toISOString()}
                </span>{" "}
                <span className="text-indigo-300">{e.action}</span> {e.name}
                {e.version ? `@${e.version}` : ""}
                {e.files ? ` (${e.files} file(s))` : ""}
              </p>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
