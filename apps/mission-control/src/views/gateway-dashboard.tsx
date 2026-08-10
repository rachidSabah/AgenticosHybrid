"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import { safeArr } from "@/lib/safe";
import {
  MessageCircle, Send, QrCode, Wifi, WifiOff, Loader2,
  CheckCircle2, XCircle, Smartphone, Bot, RefreshCw,
} from "lucide-react";

export function GatewayDashboard() {
  return (
    <div className="flex h-full w-full flex-col gap-4 overflow-auto p-4 bg-bg text-text">
      <div className="flex items-center gap-2">
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-1.5 text-amber-400">
          <MessageCircle size={16} />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-text">Messaging Gateways</h2>
          <p className="text-[10px] text-faint">Submit missions and receive results via chat apps</p>
        </div>
      </div>

      <TelegramPanel />
      <WhatsAppPanel />
    </div>
  );
}

function TelegramPanel() {
  const [status, setStatus] = useState<{ running: boolean; username: string; recent_messages: unknown[] } | null>(null);
  const [token, setToken] = useState("");
  const [allowedUsers, setAllowedUsers] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sendChatId, setSendChatId] = useState("");
  const [sendText, setSendText] = useState("");
  const events = useStore((s) => s.events);

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.telegramStatus();
      setStatus(s);
    } catch { /* offline */ }
  }, []);

  useEffect(() => {
    void loadStatus();
    const t = setInterval(loadStatus, 5000);
    return () => clearInterval(t);
  }, [loadStatus]);

  const handleConnect = async () => {
    setConnecting(true);
    setError(null);
    try {
      const users = allowedUsers
        .split(",")
        .map((n) => n.trim())
        .filter(Boolean)
        .map(Number);
      await api.telegramConnect({ bot_token: token, allowed_users: users.length ? users : undefined });
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await api.telegramDisconnect();
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleSend = async () => {
    if (!sendChatId || !sendText) return;
    try {
      await api.telegramSend({ chat_id: sendChatId, text: sendText });
      setSendText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const connected = status?.running ?? false;
  const telegramEvents = events.filter((e) => e.topic?.startsWith("gateway.telegram")).slice(0, 10);

  return (
    <div className="rounded-xl border border-border/60 bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bot size={16} className={connected ? "text-sky-400" : "text-faint/60"} />
          <span className="text-xs font-semibold text-text">Telegram Bot</span>
          {connected && status?.username && (
            <span className="font-mono text-[10px] text-sky-300">{status.username}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {connected ? (
            <>
              <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                <Wifi size={11} /> Connected
              </span>
              <button onClick={handleDisconnect} className="rounded-md border border-red-500/30 px-2 py-1 text-[10px] text-red-300 hover:bg-red-500/10">
                Disconnect
              </button>
            </>
          ) : (
            <span className="flex items-center gap-1 text-[10px] text-faint/60">
              <WifiOff size={11} /> Disconnected
            </span>
          )}
        </div>
      </div>

      {!connected && (
        <div className="mb-3 space-y-2">
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Bot token from @BotFather"
            className="w-full rounded-lg border border-border/60 bg-surface/60 px-3 py-2 text-xs text-text placeholder:text-faint outline-none focus:border-sky-500/40"
          />
          <input
            value={allowedUsers}
            onChange={(e) => setAllowedUsers(e.target.value)}
            placeholder="Allowed user IDs (comma-separated) — empty = everyone"
            className="w-full rounded-lg border border-border/60 bg-surface/60 px-3 py-2 text-xs text-text placeholder:text-faint outline-none focus:border-sky-500/40"
          />
          <button
            onClick={handleConnect}
            disabled={!token || connecting}
            className="w-full rounded-lg bg-sky-500/20 px-3 py-2 text-xs font-medium text-sky-300 hover:bg-sky-500/30 disabled:opacity-50"
          >
            {connecting ? <Loader2 size={12} className="animate-spin mx-auto" /> : "Connect Bot"}
          </button>
        </div>
      )}

      {error && <div className="mb-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-[10px] text-red-300">{error}</div>}

      {connected && (
        <div className="mb-3 flex gap-2">
          <input
            value={sendChatId}
            onChange={(e) => setSendChatId(e.target.value)}
            placeholder="Chat ID"
            className="w-24 rounded-lg border border-border/60 bg-surface/60 px-2 py-1.5 text-xs text-text placeholder:text-faint outline-none"
          />
          <input
            value={sendText}
            onChange={(e) => setSendText(e.target.value)}
            placeholder="Message text"
            className="flex-1 rounded-lg border border-border/60 bg-surface/60 px-2 py-1.5 text-xs text-text placeholder:text-faint outline-none"
          />
          <button onClick={handleSend} className="rounded-lg bg-sky-500/20 px-3 py-1.5 text-xs text-sky-300 hover:bg-sky-500/30">
            <Send size={11} />
          </button>
        </div>
      )}

      <div className="space-y-1">
        <div className="text-[9px] uppercase tracking-wider text-faint/60">Recent Activity</div>
        {safeArr(telegramEvents).length === 0 ? (
          <div className="text-[10px] text-faint/40">No activity yet</div>
        ) : (
          telegramEvents.map((e, i) => (
            <div key={i} className="flex items-center gap-2 text-[10px] text-faint/80">
              {e.topic.includes("received") ? <MessageCircle size={10} className="text-sky-400" /> : <Send size={10} className="text-emerald-400" />}
              <span className="truncate">{e.topic.replace("gateway.telegram.", "")}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function WhatsAppPanel() {
  const [status, setStatus] = useState<{ running: boolean; connection_status: string; has_qr: boolean } | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [qrError, setQrError] = useState<string | null>(null);
  const [qrNonce, setQrNonce] = useState(0);
  const [allowedNumbers, setAllowedNumbers] = useState("");
  const [sendTo, setSendTo] = useState("");
  const [sendText, setSendText] = useState("");
  const events = useStore((s) => s.events);

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.whatsappStatus();
      setStatus(s);
    } catch { /* offline */ }
  }, []);

  useEffect(() => {
    void loadStatus();
    const t = setInterval(loadStatus, 3000);
    return () => clearInterval(t);
  }, [loadStatus]);

  const handleConnect = async () => {
    setConnecting(true);
    setError(null);
    try {
      const allowed = allowedNumbers
        .split(",")
        .map((n) => n.trim())
        .filter(Boolean);
      await api.whatsappConnect({ allowed_numbers: allowed.length ? allowed : undefined });
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await api.whatsappDisconnect();
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleSend = async () => {
    if (!sendTo || !sendText) return;
    try {
      await api.whatsappSend({ to: sendTo, text: sendText });
      setSendText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const connected = status?.running && status?.connection_status === "connected";
  const scanning = !!status?.has_qr;
  const isConnecting = status?.connection_status === "connecting" || status?.connection_status === "reconnecting";
  const whatsappEvents = events.filter((e) => e.topic?.startsWith("gateway.whatsapp")).slice(0, 10);

  return (
    <div className="rounded-xl border border-border/60 bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Smartphone size={16} className={connected ? "text-emerald-400" : (scanning || isConnecting) ? "text-amber-400" : "text-faint/60"} />
          <span className="text-xs font-semibold text-text">WhatsApp</span>
          {status?.connection_status && (
            <span className="rounded bg-surface/80 px-1.5 py-0.5 text-[9px] text-faint/80 capitalize">{status.connection_status}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {connected ? (
            <>
              <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                <Wifi size={11} /> Connected
              </span>
              <button onClick={handleDisconnect} className="rounded-md border border-red-500/30 px-2 py-1 text-[10px] text-red-300 hover:bg-red-500/10">
                Disconnect
              </button>
            </>
          ) : (
            <button onClick={handleConnect} disabled={connecting} className="rounded-lg bg-emerald-500/20 px-3 py-1.5 text-xs text-emerald-300 hover:bg-emerald-500/30 disabled:opacity-50">
              {connecting ? <Loader2 size={11} className="animate-spin" /> : "Connect"}
            </button>
          )}
        </div>
      </div>

      {scanning ? (
        <div className="mb-3 flex flex-col items-center gap-2">
          <div className="text-[10px] text-faint">Scan with WhatsApp → Linked Devices → Link a Device</div>
          <div className="rounded-xl border-2 border-emerald-500/40 bg-white p-3 shadow-lg shadow-emerald-500/10">
            {/* Live pairing QR rendered by OUR backend — no external image
                service, no static/cached asset. Refreshes on every poll. */}
            <img
              src={api.whatsappQrUrl()}
              alt="WhatsApp QR Code"
              width={200}
              height={200}
              className="block"
              key={qrNonce}
              onError={() => setQrError("QR could not be rendered. Reconnect to generate a fresh code.")}
            />
          </div>
          {qrError && <div className="text-[10px] text-red-300">{qrError}</div>}
          <div className="flex items-center gap-1.5 text-[10px] text-amber-400">
            <Loader2 size={11} className="animate-spin" />
            Waiting for scan…
          </div>
        </div>
      ) : isConnecting ? (
        <div className="mb-3 flex items-center justify-center gap-2 text-[10px] text-amber-400">
          <Loader2 size={11} className="animate-spin" />
          Connecting to WhatsApp…
        </div>
      ) : null}

      {!connected && (
        <div className="mb-2 space-y-1">
          <input
            value={allowedNumbers}
            onChange={(e) => setAllowedNumbers(e.target.value)}
            placeholder="Allowed numbers (comma-separated, e.g. 15551234567) — empty = everyone"
            className="w-full rounded-lg border border-border/60 bg-surface/60 px-2 py-1.5 text-[10px] text-text placeholder:text-faint outline-none focus:border-emerald-500/40"
          />
          <div className="text-[9px] text-faint/50">Who may submit missions remotely. Leave empty to allow everyone.</div>
        </div>
      )}

      {error && <div className="mb-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-[10px] text-red-300">{error}</div>}

      {connected && (
        <div className="mb-3 flex gap-2">
          <input
            value={sendTo}
            onChange={(e) => setSendTo(e.target.value)}
            placeholder="Phone (e.g. 1234567890)"
            className="w-36 rounded-lg border border-border/60 bg-surface/60 px-2 py-1.5 text-xs text-text placeholder:text-faint outline-none"
          />
          <input
            value={sendText}
            onChange={(e) => setSendText(e.target.value)}
            placeholder="Message text"
            className="flex-1 rounded-lg border border-border/60 bg-surface/60 px-2 py-1.5 text-xs text-text placeholder:text-faint outline-none"
          />
          <button onClick={handleSend} className="rounded-lg bg-emerald-500/20 px-3 py-1.5 text-xs text-emerald-300 hover:bg-emerald-500/30">
            <Send size={11} />
          </button>
        </div>
      )}

      <div className="space-y-1">
        <div className="text-[9px] uppercase tracking-wider text-faint/60">Recent Activity</div>
        {safeArr(whatsappEvents).length === 0 ? (
          <div className="text-[10px] text-faint/40">No activity yet</div>
        ) : (
          whatsappEvents.map((e, i) => (
            <div key={i} className="flex items-center gap-2 text-[10px] text-faint/80">
              {e.topic.includes("received") ? <MessageCircle size={10} className="text-emerald-400" /> : <Send size={10} className="text-sky-400" />}
              <span className="truncate">{e.topic.replace("gateway.whatsapp.", "")}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
