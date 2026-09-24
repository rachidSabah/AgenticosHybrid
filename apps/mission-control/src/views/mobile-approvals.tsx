"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type ApprovalAuditEntry, type ApprovalRequest } from "@/lib/api";

/**
 * Mobile Approvals — dangerous operations pause until a human decides.
 *
 * Two honest delivery channels, both leaving the decision to the operator:
 * a Telegram push with one-time /approve and /reject tokens, and a locally
 * rendered QR code pointing at THIS machine's decision page (same network,
 * no cloud relay). The one-time token is shown exactly once, at creation.
 */

const fmtIn = (expiresAt: number) => {
  const s = Math.max(0, Math.round(expiresAt - Date.now() / 1000));
  return `${s}s`;
};

export function MobileApprovals() {
  const [pending, setPending] = useState<ApprovalRequest[] | null>(null);
  const [history, setHistory] = useState<ApprovalRequest[]>([]);
  const [audit, setAudit] = useState<ApprovalAuditEntry[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // create form
  const [op, setOp] = useState("");
  const [detail, setDetail] = useState("");
  const [risk, setRisk] = useState("");
  const [ttl, setTtl] = useState("300");
  const [lastToken, setLastToken] = useState<{ id: string; token: string } | null>(null);

  // QR panel
  const [qrFor, setQrFor] = useState<string | null>(null);
  const [qrSvg, setQrSvg] = useState<string>("");
  const [lanBase, setLanBase] = useState("");

  const load = useCallback(async () => {
    try {
      const [listRes, auditRes] = await Promise.all([
        api.approvals(),
        api.approvalAudit(30),
      ]);
      setPending(listRes.pending ?? []);
      setHistory(listRes.history ?? []);
      setAudit(auditRes.entries ?? []);
    } catch (e) {
      setPending([]);
      setHistory([]);
      setAudit([]);
      setNotice(`Approval service unavailable: ${String(e)}`);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async () => {
    setBusy("create");
    setNotice(null);
    try {
      const ttlNum = Number.parseInt(ttl, 10);
      const req = await api.approvalCreate({
        operation: op,
        detail,
        risk,
        ttl_s: Number.isFinite(ttlNum) && ttlNum > 0 ? ttlNum : undefined,
      });
      setLastToken({ id: req.request_id, token: req.token ?? "" });
      setOp("");
      setDetail("");
      setRisk("");
      await load();
    } catch (e) {
      setNotice(`Not created: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const decide = async (requestId: string, approved: boolean) => {
    setBusy(`decide-${requestId}`);
    setNotice(null);
    try {
      await api.approvalDecide(requestId, approved);
      await load();
    } catch (e) {
      setNotice(`Decision refused: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const pushTelegram = async (requestId: string) => {
    setBusy(`push-${requestId}`);
    setNotice(null);
    try {
      const res = await api.approvalTelegramPush(requestId);
      setNotice(
        `Pushed to ${res.pushed_to.length} chat(s)${
          res.not_pushed.length ? `; ${res.not_pushed.length} failed` : ""
        }.`
      );
    } catch (e) {
      setNotice(`Push failed: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const showQr = async (requestId: string) => {
    setBusy(`qr-${requestId}`);
    setNotice(null);
    setQrSvg("");
    try {
      const base =
        lanBase.trim() ||
        `${window.location.protocol}//${window.location.hostname}:8000`;
      const res = await api.approvalQr(requestId, base);
      setQrSvg(res.svg);
      setQrFor(requestId);
    } catch (e) {
      setNotice(`QR failed: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#05060a] text-gray-200 p-6 space-y-6">
      <header className="border-b border-white/10 pb-4">
        <h1 className="text-xl font-bold text-white">Mobile Approvals</h1>
        <p className="text-sm text-gray-400 mt-1">
          Dangerous operations pause here until a human decides. Two channels,
          both operated by you: a Telegram push with one-time{" "}
          <code className="text-gray-300">/approve</code> /{" "}
          <code className="text-gray-300">/reject</code> tokens, and a QR code
          rendered locally that opens this machine&apos;s decision page on your
          phone (same network — no cloud relay). Tokens expire; expiry is a
          refusal, never a silent yes.
        </p>
      </header>

      {notice && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm text-amber-200 font-mono break-all">
          {notice}
        </div>
      )}

      {/* ── Pending ───────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
          Pending decisions
        </h2>
        {pending === null ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : pending.length === 0 ? (
          <p className="text-sm text-gray-500">
            NO DATA — nothing is waiting for a human right now. Requests appear
            here the moment an enforcement point or you create one.
          </p>
        ) : (
          <div className="space-y-3">
            {pending.map((r) => (
              <div key={r.request_id} className="rounded border border-white/15 bg-black/30 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm text-gray-100">
                      {r.operation}{" "}
                      <span className="text-xs font-mono text-gray-500">
                        {r.request_id}
                      </span>
                    </p>
                    {r.detail && (
                      <p className="text-xs text-gray-400 mt-0.5">{r.detail}</p>
                    )}
                    <p className="text-xs text-gray-500 mt-0.5">
                      {r.risk && <>risk: {r.risk} · </>}
                      expires in {fmtIn(r.expires_at)}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="rounded bg-emerald-500/20 px-2 py-1 text-xs text-emerald-300 hover:bg-emerald-500/30 disabled:opacity-40"
                      disabled={busy !== null}
                      onClick={() => void decide(r.request_id, true)}
                    >
                      approve
                    </button>
                    <button
                      className="rounded bg-red-500/20 px-2 py-1 text-xs text-red-300 hover:bg-red-500/30 disabled:opacity-40"
                      disabled={busy !== null}
                      onClick={() => void decide(r.request_id, false)}
                    >
                      reject
                    </button>
                    <button
                      className="rounded bg-sky-500/20 px-2 py-1 text-xs text-sky-300 hover:bg-sky-500/30 disabled:opacity-40"
                      disabled={busy !== null}
                      onClick={() => void pushTelegram(r.request_id)}
                    >
                      {busy === `push-${r.request_id}` ? "pushing…" : "push via Telegram"}
                    </button>
                    <button
                      className="rounded bg-white/10 px-2 py-1 text-xs text-gray-300 hover:bg-white/20 disabled:opacity-40"
                      disabled={busy !== null}
                      onClick={() => void showQr(r.request_id)}
                    >
                      {busy === `qr-${r.request_id}` ? "rendering…" : "show QR"}
                    </button>
                  </div>
                </div>
                {qrFor === r.request_id && qrSvg && (
                  <div className="mt-3 flex items-start gap-4">
                    <div
                      className="rounded bg-white p-2 w-44"
                      dangerouslySetInnerHTML={{ __html: qrSvg }}
                    />
                    <p className="text-xs text-gray-500 max-w-sm">
                      Scan with your phone on the same network. The QR opens this
                      machine&apos;s decision page — the link carries the one-time
                      decision token and is never shown again after this request
                      expires.
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        <label className="block text-xs text-gray-400 mt-3 max-w-md">
          LAN base URL for QR links (optional; defaults to this host with port 8000)
          <input
            className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100 font-mono"
            value={lanBase}
            onChange={(e) => setLanBase(e.target.value)}
            placeholder="http://192.168.1.10:8000"
          />
        </label>
      </section>

      {/* ── Create ────────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-1">
          Create a pending approval
        </h2>
        <p className="text-xs text-gray-500 mb-3">
          Enforcement points create these automatically; you can also raise one
          by hand. The one-time decision token is shown exactly once after
          creation — copy it before you close the page.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
          <label className="text-xs text-gray-400">
            Operation
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100"
              value={op}
              onChange={(e) => setOp(e.target.value)}
              placeholder="delete production database"
            />
          </label>
          <label className="text-xs text-gray-400">
            Risk note
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100"
              value={risk}
              onChange={(e) => setRisk(e.target.value)}
              placeholder="irreversible"
            />
          </label>
          <label className="text-xs text-gray-400 md:col-span-2">
            Detail
            <input
              className="mt-1 w-full rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100"
              value={detail}
              onChange={(e) => setDetail(e.target.value)}
              placeholder="DROP TABLE users on prod cluster"
            />
          </label>
          <label className="text-xs text-gray-400">
            TTL (seconds)
            <input
              className="mt-1 w-40 rounded bg-black/40 border border-white/15 px-3 py-2 text-sm text-gray-100"
              value={ttl}
              onChange={(e) => setTtl(e.target.value)}
              inputMode="numeric"
            />
          </label>
        </div>
        <button
          className="rounded bg-indigo-500/30 px-4 py-2 text-sm text-indigo-200 hover:bg-indigo-500/40 disabled:opacity-40"
          disabled={busy !== null || !op.trim()}
          onClick={() => void create()}
        >
          {busy === "create" ? "Creating…" : "Create approval"}
        </button>
        {lastToken && (
          <div className="mt-3 rounded border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-xs text-amber-200 font-mono">
            one-time token for {lastToken.id}: {lastToken.token} — shown only
            this once
          </div>
        )}
      </section>

      {/* ── History + audit ──────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
            Recent requests
          </h2>
          {history.length === 0 ? (
            <p className="text-xs text-gray-500">NO DATA — no approval requests yet.</p>
          ) : (
            <div className="space-y-1">
              {history.map((r) => (
                <p key={r.request_id} className="text-xs font-mono text-gray-400">
                  <span
                    className={
                      r.state === "approved"
                        ? "text-emerald-300"
                        : r.state === "rejected"
                          ? "text-red-300"
                          : r.state === "expired"
                            ? "text-gray-500"
                            : "text-amber-300"
                    }
                  >
                    {r.state}
                  </span>{" "}
                  {r.operation}{" "}
                  {r.decided_by ? `by ${r.decided_by} via ${r.decision_via}` : ""}
                </p>
              ))}
            </div>
          )}
        </section>
        <section className="rounded-lg border border-white/10 bg-[rgba(8,10,16,0.85)] p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-300 mb-3">
            Audit trail (append-only)
          </h2>
          {audit.length === 0 ? (
            <p className="text-xs text-gray-500">NO DATA — no approval transitions yet.</p>
          ) : (
            <div className="space-y-1">
              {audit
                .slice()
                .reverse()
                .map((e, i) => (
                  <p key={`${e.ts}-${i}`} className="text-xs font-mono text-gray-400">
                    {new Date(e.ts * 1000).toISOString()} — {e.action}{" "}
                    <span className="text-gray-300">{e.request_id}</span> {e.operation}
                    {e.by ? ` by ${e.by}` : ""}
                    {e.via ? ` via ${e.via}` : ""}
                  </p>
                ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
