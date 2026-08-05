"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Panel, Badge, StatusDot, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { CapabilityInfo, ProviderInfo, MCPServerDetail } from "@/lib/types";

// ── Featured plugin catalog (curated, backed by MCP install capability) ──
interface PluginEntry {
  name: string;
  vendor: string;
  description: string;
  type: "provider" | "mcp" | "capability";
  icon: string;
  color: string;
  installable: boolean;
}

const FEATURED: PluginEntry[] = [
  { name: "Claude", vendor: "Anthropic", description: "Advanced reasoning & coding", type: "provider", icon: "◆", color: "#d980ff", installable: false },
  { name: "Hermes", vendor: "Nous Research", description: "Multi-agent orchestration", type: "provider", icon: "◇", color: "#6366f1", installable: false },
  { name: "OpenCode", vendor: "OpenAI", description: "Agentic coding CLI", type: "provider", icon: "○", color: "#22c55e", installable: false },
  { name: "Gemini CLI", vendor: "Google", description: "Gemini-powered coding agent", type: "provider", icon: "◇", color: "#38bdf8", installable: false },
  { name: "GitHub", vendor: "Microsoft", description: "Repository & CI/CD integration", type: "mcp", icon: "⌂", color: "#f0f6fc", installable: true },
  { name: "Docker", vendor: "Docker Inc", description: "Container management", type: "mcp", icon: "⎔", color: "#2496ed", installable: true },
  { name: "Kubernetes", vendor: "CNCF", description: "K8s cluster management", type: "mcp", icon: "◉", color: "#326ce5", installable: true },
  { name: "Slack", vendor: "Salesforce", description: "Team messaging & alerts", type: "mcp", icon: "☰", color: "#4a154b", installable: true },
  { name: "Notion", vendor: "Notion Labs", description: "Docs & wikis API", type: "mcp", icon: "□", color: "#000000", installable: true },
  { name: "Jira", vendor: "Atlassian", description: "Issue & project tracking", type: "mcp", icon: "▲", color: "#0052cc", installable: true },
  { name: "Linear", vendor: "Linear", description: "Issue tracking & roadmaps", type: "mcp", icon: "△", color: "#5e6ad2", installable: true },
  { name: "PostgreSQL", vendor: "PostgreSQL", description: "Relational database", type: "mcp", icon: "▽", color: "#336791", installable: true },
  { name: "SQLite", vendor: "SQLite", description: "Embedded database proxy", type: "mcp", icon: "◈", color: "#003b57", installable: true },
  { name: "Redis", vendor: "Redis Ltd", description: "Cache & message broker", type: "mcp", icon: "◆", color: "#dc382d", installable: true },
  { name: "Browser Automation", vendor: "Playwright", description: "Headless browser control", type: "mcp", icon: "⊕", color: "#45ba4b", installable: true },
  { name: "OCR Engine", vendor: "Tesseract", description: "Image & PDF text extraction", type: "mcp", icon: "⊡", color: "#eab308", installable: true },
  { name: "Vector DB", vendor: "Qdrant", description: "Semantic vector search", type: "capability", icon: "⊛", color: "#ea580c", installable: true },
  { name: "Local LLM", vendor: "Ollama", description: "On-device model inference", type: "capability", icon: "⎈", color: "#10b981", installable: true },
];

// ── Main Component ──
export function PluginMarketplace() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [caps, setCaps] = useState<CapabilityInfo[]>([]);
  const [mcps, setMcps] = useState<MCPServerDetail[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [installing, setInstalling] = useState<string | null>(null);

  useEffect(() => {
    api.providers()
      .then((list) => {
        // Dedupe by normalized name: the backend registry can emit the same
        // runtime under multiple aliases ("Claude Code" / "claude_code"),
        // which would collide as React keys in the map below.
        const seen = new Set<string>();
        const unique: ProviderInfo[] = [];
        for (const p of list) {
          const slug = (p.name ?? "").toLowerCase().replace(/\s+/g, "-");
          if (!slug || seen.has(slug)) continue;
          seen.add(slug);
          unique.push(p);
        }
        setProviders(unique);
      })
      .catch((err) => { console.error("providers API error:", err); setError(String(err)); });
    api.capabilities()
      .then(setCaps)
      .catch((err) => { console.error("capabilities API error:", err); setError(String(err)); });
    api.mcpServers("", true)
      .then(setMcps)
      .catch(() => { /* MCP servers may not be available */ });
  }, []);

  const installedProviders = new Set(providers.map((p) => p.name.toLowerCase()));
  const installedMcps = new Set(mcps.map((m) => m.config.name?.toLowerCase()));
  const installedCaps = new Set(caps.map((c) => c.name.toLowerCase()));

  const handleInstall = async (plugin: PluginEntry) => {
    setInstalling(plugin.name);
    try {
      // Attempt to register an MCP server for the plugin
      await api.registerMcpServer({
        name: plugin.name,
        transport: "stdio",
        command: plugin.name.toLowerCase().replace(/\s+/g, "-"),
        enabled: true,
        auto_discover: true,
      });
      // Refresh MCP list
      const updated = await api.mcpServers("", true);
      setMcps(updated);
    } catch (e) {
      console.error(`Failed to install ${plugin.name}:`, e);
    } finally {
      setInstalling(null);
    }
  };

  const isInstalled = (plugin: PluginEntry): boolean => {
    const key = plugin.name.toLowerCase();
    if (plugin.type === "provider") return installedProviders.has(key);
    if (plugin.type === "mcp") return installedMcps.has(key);
    if (plugin.type === "capability") return installedCaps.has(key);
    return false;
  };

  return (
    <div className="grid h-full gap-4 p-4"
      style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(320px, 100%), 1fr))" }}
    >
      {/* Header */}
      <div className="col-span-12 flex items-center gap-4 rounded-2xl border border-border/50 bg-surface/30 px-5 py-3">
        <span className="text-sm font-bold tracking-[0.15em] uppercase">Plugin Marketplace</span>
        <span className="h-4 w-px bg-border/40" />
        <span className="text-[11px] text-faint">
          {providers.length} providers · {mcps.length} MCP servers · {caps.length} capabilities
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5 text-[10px] text-ok">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-ok animate-pulse" />
          LIVE
        </span>
      </div>

      {/* Installed Providers */}
      <Panel title="Provider Plugins" subtitle={`${providers.length} loaded adapters`} className="">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {providers.map((p) => (
            <div key={p.name} className="rounded-xl border border-border/60 px-3 py-2.5 flex items-center gap-2.5">
              <StatusDot status="healthy" />
              <div className="min-w-0 flex-1">
                <div className="text-xs font-medium">{p.name}</div>
                <div className="text-[10px] text-faint/70 flex items-center gap-1.5">
                  <Badge tone="info">{p.kind}</Badge>
                  <span>{p.supports_streaming ? "stream" : ""}</span>
                  {p.supports_tools && <span>tools</span>}
                </div>
              </div>
            </div>
          ))}
          {providers.length === 0 && <div className="col-span-2"><Empty title="No provider plugins loaded" /></div>}
        </div>
      </Panel>

      {/* Installed MCP Servers */}
      <Panel title="MCP Servers" subtitle={`${mcps.length} registered`} className="">
        {mcps.length > 0 ? (
          <div className="space-y-1.5">
            {mcps.map((m) => (
              <div key={m.config.id || m.config.name} className="flex items-center gap-2.5 rounded-xl border border-border/60 px-3 py-2">
                <StatusDot status={m.health === "healthy" ? "healthy" : m.health === "degraded" ? "degraded" : "unknown"} />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium">{m.config.name}</div>
                  <div className="text-[10px] text-faint/70">{m.config.transport} · {m.tools?.length || 0} tools</div>
                </div>
                <span className="text-[9px] text-faint/50 tabular-nums">
                  {m.last_health_check ? new Date(m.last_health_check).toLocaleTimeString() : "—"}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <Empty title="No MCP servers registered" hint="Install plugins below to populate this list." />
        )}
      </Panel>

      {/* Featured Plugin Catalog */}
      <Panel title="Plugin Catalog" subtitle={`${FEATURED.length} available`} className="col-span-12">
        <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2.5 h-full overflow-y-auto">
          {FEATURED.map((plugin, i) => {
            const installed = isInstalled(plugin);
            return (
              <motion.div
                key={plugin.name}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.02 }}
                className={`relative rounded-xl border px-3 py-2.5 transition-all ${
                  installed ? "border-ok/40 bg-ok/5" : "border-border/60 bg-surface/10 hover:border-accent/40"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-base shrink-0" style={{ color: plugin.color }}>{plugin.icon}</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium truncate">{plugin.name}</div>
                    <div className="text-[9px] text-faint/60 truncate">{plugin.vendor}</div>
                  </div>
                  {installed && <Badge tone="ok">✓</Badge>}
                </div>
                <p className="mt-1 text-[10px] text-faint/80 line-clamp-2">{plugin.description}</p>
                <div className="mt-1.5 flex items-center gap-1.5">
                  <Badge tone={plugin.type === "provider" ? "info" : plugin.type === "mcp" ? "default" : "accent"}>
                    {plugin.type}
                  </Badge>
                  {installed ? (
                    <span className="text-[9px] text-ok/70">installed</span>
                  ) : plugin.installable ? (
                    <button
                      onClick={() => handleInstall(plugin)}
                      disabled={installing === plugin.name}
                      className="ml-auto rounded bg-accent/20 px-2 py-0.5 text-[9px] text-accent hover:bg-accent/30 transition-colors disabled:opacity-50"
                    >
                      {installing === plugin.name ? "..." : "Install"}
                    </button>
                  ) : null}
                </div>
              </motion.div>
            );
          })}
        </div>
      </Panel>

      {/* Capability Catalog */}
      <Panel title="Capability Catalog" subtitle={`${caps.length} registered`} className="col-span-12">
        <div className="flex flex-wrap gap-2 h-full overflow-y-auto">
          {caps.map((c) => (
            <div key={c.name} className="flex items-center gap-1.5 rounded-lg border border-border/50 px-2.5 py-1.5">
              <StatusDot status={c.requires_approval ? "degraded" : "healthy"} />
              <span className="text-xs font-medium">{c.name}</span>
              {c.requires_approval && <span className="inline-flex items-center gap-1.5 text-[9px]"><Badge tone="warn">approval</Badge></span>}
              {c.description && (
                <span className="text-[10px] text-faint/60 hidden md:inline">{c.description}</span>
              )}
            </div>
          ))}
          {caps.length === 0 && <Empty title="No capabilities registered" />}
        </div>
      </Panel>

      {error && (
        <div className="col-span-12 text-xs text-danger/80 bg-danger/5 rounded-lg px-3 py-2">
          API error: {error}
        </div>
      )}
    </div>
  );
}
