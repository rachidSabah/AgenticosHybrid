"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Panel,
  Badge,
  StatusDot,
  Empty,
  Stat,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { CapabilityInfo, ProviderInfo, MCPServerDetail } from "@/lib/types";
import {
  Boxes,
  Plug,
  Cpu,
  RefreshCw,
  Search,
  ShieldCheck,
  Zap,
} from "lucide-react";

interface LoadedPlugin {
  name: string;
  loaded: boolean;
  order: number;
}

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0 },
};

// ── Main Component ──
export function PluginMarketplace() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [caps, setCaps] = useState<CapabilityInfo[]>([]);
  const [mcps, setMcps] = useState<MCPServerDetail[]>([]);
  const [plugins, setPlugins] = useState<LoadedPlugin[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [prov, capList, mcpList, pluginList] = await Promise.all([
        api.providers().catch(() => [] as ProviderInfo[]),
        api.capabilities().catch(() => [] as CapabilityInfo[]),
        api.mcpServers("", true).catch(() => [] as MCPServerDetail[]),
        api.plugins().catch(() => [] as LoadedPlugin[]),
      ]);

      // Dedupe by normalized name: the backend registry can emit the same
      // runtime under multiple aliases ("Claude Code" / "claude_code"),
      // which would collide as React keys in the map below.
      const seen = new Set<string>();
      const unique: ProviderInfo[] = [];
      for (const p of prov) {
        const slug = (p.name ?? "").toLowerCase().replace(/\s+/g, "-");
        if (!slug || seen.has(slug)) continue;
        seen.add(slug);
        unique.push(p);
      }
      setProviders(unique);
      setCaps(Array.isArray(capList) ? capList : []);
      setMcps(Array.isArray(mcpList) ? mcpList : []);
      setPlugins(Array.isArray(pluginList) ? pluginList : []);
    } catch (err) {
      console.error("plugin marketplace API error:", err);
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const q = query.trim().toLowerCase();

  const filteredProviders = useMemo(
    () =>
      q
        ? providers.filter(
            (p) =>
              (p.name ?? "").toLowerCase().includes(q) ||
              (p.kind ?? "").toLowerCase().includes(q)
          )
        : providers,
    [providers, q]
  );

  const filteredMcps = useMemo(
    () =>
      q
        ? mcps.filter(
            (m) =>
              (m.config.name ?? "").toLowerCase().includes(q) ||
              (m.config.transport ?? "").toLowerCase().includes(q)
          )
        : mcps,
    [mcps, q]
  );

  const filteredPlugins = useMemo(
    () =>
      q
        ? plugins.filter((p) => (p.name ?? "").toLowerCase().includes(q))
        : plugins,
    [plugins, q]
  );

  const filteredCaps = useMemo(
    () =>
      q
        ? caps.filter(
            (c) =>
              (c.name ?? "").toLowerCase().includes(q) ||
              (c.description ?? "").toLowerCase().includes(q)
          )
        : caps,
    [caps, q]
  );

  const total = providers.length + mcps.length + plugins.length + caps.length;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background/95 p-4 space-y-3">
      {/* ── Header ── */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="relative flex flex-col gap-3 overflow-hidden rounded-2xl border border-border/50 bg-surface/40 px-5 py-4 backdrop-blur-xl sm:flex-row sm:items-center"
      >
        {/* ambient glow */}
        <div className="pointer-events-none absolute -top-16 -right-10 h-40 w-72 rounded-full bg-accent/10 blur-3xl" />
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl border border-accent/30 bg-accent/10 text-accent shadow-[0_0_24px_-6px_var(--accent)]">
            <Boxes size={18} />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-[0.18em] uppercase text-text">
              Plugin Marketplace
            </h1>
            <p className="text-[11px] text-faint">
              {providers.length} providers · {mcps.length} MCP servers ·{" "}
              {caps.length} capabilities · {plugins.length} plugins loaded
            </p>
          </div>
        </div>

        <div className="flex flex-1 flex-wrap items-center gap-2 sm:justify-end">
          {/* live search */}
          <div className="relative min-w-0 flex-1 sm:max-w-56">
            <Search
              size={13}
              className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-faint/60"
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter plugins, providers, MCP…"
              className="w-full rounded-lg border border-border/60 bg-surface/40 py-1.5 pr-3 pl-8 text-xs text-text placeholder:text-faint/50 outline-none transition focus:border-accent/60 focus:shadow-[0_0_16px_-4px_var(--accent)]"
            />
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-ok/30 bg-ok/10 px-2.5 py-1 text-[10px] text-ok">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-ok" />
            LIVE
          </span>
          <button
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border/60 px-3 py-1.5 text-xs text-faint transition hover:border-accent/40 hover:text-text disabled:opacity-50"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            {loading ? "Syncing…" : "Refresh"}
          </button>
        </div>
      </motion.div>

      {/* ── Stat strip ── */}
      <motion.div
        variants={{ show: { transition: { staggerChildren: 0.05 } } }}
        initial="hidden"
        animate="show"
        className="grid grid-cols-2 gap-3 sm:grid-cols-4"
      >
        <motion.div variants={fadeUp}>
          <Stat label="Providers" value={providers.length} tone="accent" delta="real registry" />
        </motion.div>
        <motion.div variants={fadeUp}>
          <Stat label="MCP Servers" value={mcps.length} tone="accent" delta="real health" />
        </motion.div>
        <motion.div variants={fadeUp}>
          <Stat label="Capabilities" value={caps.length} tone="accent" delta="real catalog" />
        </motion.div>
        <motion.div variants={fadeUp}>
          <Stat label="Plugins" value={plugins.length} tone="accent" delta="loaded at boot" />
        </motion.div>
      </motion.div>

      {/* ── Scrollable Content Area ── */}
      <div className="flex-1 min-h-0 overflow-y-auto space-y-3 pr-1 custom-scrollbar">
        {/* ── Installed Providers ── */}
        <motion.div
          variants={{ show: { transition: { staggerChildren: 0.04 } } }}
          initial="hidden"
          animate="show"
        >
          <Panel
            title={
              <span className="flex items-center gap-2">
                <Cpu size={13} className="text-cyan-400" /> Provider Plugins
              </span>
            }
            subtitle={`${providers.length} loaded adapters`}
            className="border border-cyan-500/15 bg-surface/30 backdrop-blur-md"
          >
            {filteredProviders.length > 0 ? (
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
                {filteredProviders.map((p) => (
                  <motion.div
                    key={p.name}
                    variants={fadeUp}
                    whileHover={{ y: -2 }}
                    className="group relative flex items-center gap-2.5 overflow-hidden rounded-xl border border-cyan-500/20 bg-surface/40 px-3 py-2.5 transition-all hover:border-cyan-500/50 hover:shadow-[0_0_15px_rgba(6,182,212,0.1)]"
                  >
                    <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-cyan-500/10 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
                    <StatusDot status="healthy" pulse />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-semibold text-text">{p.name}</div>
                      <div className="flex items-center gap-1.5 text-[10px] text-faint">
                        <Badge tone="info">{p.kind}</Badge>
                        {p.supports_streaming && <span>stream</span>}
                        {p.supports_tools && <span>tools</span>}
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            ) : (
              <Empty
                title={q ? "No providers match" : "No provider plugins loaded"}
                hint={q ? "Try a different filter." : "Backend registry returned no providers."}
              />
            )}
          </Panel>
        </motion.div>

        {/* ── MCP Servers + Loaded Plugins ── */}
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <Panel
            title={
              <span className="flex items-center gap-2">
                <Plug size={13} className="text-cyan-400" /> MCP Servers
              </span>
            }
            subtitle={`${mcps.length} registered`}
            className="border border-cyan-500/15 bg-surface/30 backdrop-blur-md"
          >
            {filteredMcps.length > 0 ? (
              <div className="space-y-1.5">
                {filteredMcps.map((m) => (
                  <motion.div
                    key={m.config.id || m.config.name}
                    whileHover={{ x: 2 }}
                    className="flex items-center gap-2.5 rounded-xl border border-cyan-500/20 bg-surface/40 px-3 py-2 transition-all hover:border-cyan-500/50"
                  >
                    <StatusDot
                      status={
                        m.health === "healthy"
                          ? "healthy"
                          : m.health === "degraded"
                            ? "degraded"
                            : "unknown"
                      }
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-semibold text-text">{m.config.name}</div>
                      <div className="text-[10px] text-faint">
                        {m.config.transport} · {m.tools?.length || 0} tools
                      </div>
                    </div>
                    <span className="shrink-0 text-[9px] font-mono text-faint tabular-nums">
                      {m.last_health_check
                        ? new Date(m.last_health_check).toLocaleTimeString()
                        : "—"}
                    </span>
                  </motion.div>
                ))}
              </div>
            ) : (
              <Empty
                title={q ? "No MCP servers match" : "No MCP servers registered"}
                hint={q ? undefined : "Install plugins below to populate this list."}
              />
            )}
          </Panel>

          <Panel
            title={
              <span className="flex items-center gap-2">
                <ShieldCheck size={13} className="text-cyan-400" /> Loaded Plugins
              </span>
            }
            subtitle={`${plugins.length} registered in backend`}
            className="border border-cyan-500/15 bg-surface/30 backdrop-blur-md"
          >
            {filteredPlugins.length > 0 ? (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {filteredPlugins.map((p) => (
                  <motion.div
                    key={p.name}
                    whileHover={{ y: -2 }}
                    className="flex items-center gap-2.5 rounded-xl border border-cyan-500/20 bg-surface/40 px-3 py-2.5 transition-all hover:border-cyan-500/50"
                  >
                    <StatusDot status={p.loaded ? "healthy" : "degraded"} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-semibold text-text">{p.name}</div>
                      <div className="text-[10px] text-faint font-mono">load order {p.order}</div>
                    </div>
                    {p.loaded && <Badge tone="ok">loaded</Badge>}
                  </motion.div>
                ))}
              </div>
            ) : (
              <Empty
                title={q ? "No plugins match" : "No plugins loaded"}
                hint={q ? undefined : "Backend /api/plugins returned an empty list."}
              />
            )}
          </Panel>
        </div>

        {/* ── Capability Catalog ── */}
        <Panel
          title={
            <span className="flex items-center gap-2">
              <Zap size={13} className="text-cyan-400" /> Capability Catalog
            </span>
          }
          subtitle={`${caps.length} registered · ${filteredCaps.length} shown`}
          className="border border-cyan-500/15 bg-surface/30 backdrop-blur-md"
        >
          {filteredCaps.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {filteredCaps.map((c) => (
                <motion.div
                  key={c.name}
                  whileHover={{ y: -2 }}
                  className="group flex items-center gap-1.5 rounded-lg border border-cyan-500/20 bg-surface/40 px-2.5 py-1.5 transition-all hover:border-cyan-500/50"
                >
                  <StatusDot status={c.requires_approval ? "degraded" : "healthy"} />
                  <span className="text-xs font-semibold text-text">{c.name}</span>
                  {c.requires_approval && (
                    <Badge tone="warn">approval</Badge>
                  )}
                  {c.description && (
                    <span className="hidden text-[10px] text-faint md:inline">
                      {c.description}
                    </span>
                  )}
                </motion.div>
              ))}
            </div>
          ) : (
            <Empty
              title={q ? "No capabilities match" : "No capabilities registered"}
              hint={q ? "Try a different filter." : undefined}
            />
          )}
        </Panel>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger/80">
          API error: {error}
        </div>
      )}
    </div>
  );
}
