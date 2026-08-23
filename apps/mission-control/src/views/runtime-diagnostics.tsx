"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { clsx } from "clsx";
import {
  Activity,
  Server,
  Brain,
  Search,
  Zap,
  Globe,
  Settings,
  Shield,
  ActivitySquare,
  Network,
  Cpu,
  Database,
  RefreshCw,
  Download,
  Terminal,
  FileJson,
  PlayCircle,
  Clock,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Play,
  BarChart,
  HardDrive,
  ListFilter
} from "lucide-react";
import {
  Panel,
  Stat,
  Badge,
  StatusDot,
  Empty,
  LoadingScreen
} from "@/components/ui/primitives";
import * as api from "@/lib/diagnostics-api";

// -----------------------------------------------------------------------------
// MAIN VIEW COMPONENT
// -----------------------------------------------------------------------------

export function RuntimeDiagnostics() {
  const [activeTab, setActiveTab] = useState(1);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [sseConnected, setSseConnected] = useState(false);
  const [globalSearch, setGlobalSearch] = useState("");
  
  useEffect(() => {
    const cleanup = api.fetchDiagnosticsSSE(
      (data) => {
        setSseConnected(true);
        // We could dispatch events to a context or store, but for now just show connection status
      },
      (err) => {
        setSseConnected(false);
      }
    );
    return cleanup;
  }, []);

  const tabs = [
    { id: 1, name: "Runtime Overview", icon: Server },
    { id: 2, name: "Runtime Discovery", icon: Search },
    { id: 3, name: "Brain Registry", icon: Brain },
    { id: 4, name: "Agent Registry", icon: Globe },
    { id: 5, name: "Capability Registry", icon: Zap },
    { id: 6, name: "Discovery Pipeline", icon: Network },
    { id: 7, name: "EventBus Inspector", icon: ActivitySquare },
    { id: 8, name: "SSE Inspector", icon: Activity },
    { id: 9, name: "API Monitor", icon: Terminal },
    { id: 10, name: "Provider Runtime", icon: Server },
    { id: 11, name: "MCP Monitor", icon: Network },
    { id: 12, name: "Queue Inspector", icon: Database },
    { id: 13, name: "Thread/Task Monitor", icon: Cpu },
    { id: 14, name: "Resource Monitor", icon: HardDrive },
    { id: 15, name: "Event Timeline", icon: Clock },
    { id: 16, name: "Logs", icon: FileJson },
    { id: 17, name: "Health Dashboard", icon: Shield },
    { id: 18, name: "Configuration", icon: Settings },
    { id: 19, name: "Diagnostics Report", icon: Download },
    { id: 20, name: "Self Test", icon: PlayCircle },
  ];

  return (
    <div className="flex h-full flex-col bg-background/50 text-text">
      {/* HEADER */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border/60 bg-surface/30 px-6 backdrop-blur-md">
        <div className="flex items-center gap-4">
          <Activity className="h-5 w-5 text-accent" />
          <h1 className="text-lg font-semibold tracking-tight">Mission Control Runtime Diagnostics</h1>
          <div className="flex items-center gap-2 ml-4 px-3 py-1 bg-surface/50 rounded-full border border-border/60">
            <StatusDot status={sseConnected ? "healthy" : "down"} pulse={sseConnected} />
            <span className="text-xs font-medium text-muted">{sseConnected ? "SSE Connected" : "SSE Disconnected"}</span>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder="Global search..."
              value={globalSearch}
              onChange={(e) => setGlobalSearch(e.target.value)}
              className="h-8 w-64 rounded-md border border-border/60 bg-surface/40 pl-9 pr-3 text-sm text-text placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={clsx(
              "flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
              autoRefresh 
                ? "border-accent/40 bg-accent/10 text-accent" 
                : "border-border/60 bg-surface/40 text-muted hover:bg-surface/60"
            )}
          >
            <RefreshCw className={clsx("h-3.5 w-3.5", autoRefresh && "animate-spin")} />
            {autoRefresh ? "Auto-Refresh ON" : "Auto-Refresh OFF"}
          </button>
        </div>
      </header>

      {/* BODY */}
      <div className="flex flex-1 overflow-hidden">
        {/* SIDEBAR TABS */}
        <aside className="w-64 shrink-0 border-r border-border/60 bg-surface/20 overflow-y-auto">
          <nav className="flex flex-col gap-1 p-3">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={clsx(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                    isActive
                      ? "bg-accent/15 text-accent"
                      : "text-muted hover:bg-surface/60 hover:text-text"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="truncate">{tab.name}</span>
                </button>
              );
            })}
          </nav>
        </aside>

        {/* CONTENT */}
        <main className="flex-1 overflow-y-auto bg-background p-6">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.15 }}
              className="h-full"
            >
              <TabContent 
                tabId={activeTab} 
                autoRefresh={autoRefresh} 
                globalSearch={globalSearch} 
              />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------------
// TAB ROUTER
// -----------------------------------------------------------------------------

function TabContent({ tabId, autoRefresh, globalSearch }: { tabId: number; autoRefresh: boolean; globalSearch: string }) {
  switch (tabId) {
    case 1: return <TabRuntimeOverview autoRefresh={autoRefresh} />;
    case 2: return <TabRuntimeDiscovery autoRefresh={autoRefresh} search={globalSearch} />;
    case 3: return <TabBrainRegistry autoRefresh={autoRefresh} search={globalSearch} />;
    case 4: return <TabAgentRegistry autoRefresh={autoRefresh} search={globalSearch} />;
    case 5: return <TabCapabilityRegistry autoRefresh={autoRefresh} search={globalSearch} />;
    case 6: return <TabDiscoveryPipeline autoRefresh={autoRefresh} />;
    case 7: return <TabEventBusInspector autoRefresh={autoRefresh} search={globalSearch} />;
    case 8: return <TabSSEInspector autoRefresh={autoRefresh} search={globalSearch} />;
    case 9: return <TabAPIMonitor autoRefresh={autoRefresh} search={globalSearch} />;
    case 10: return <TabProviderRuntime autoRefresh={autoRefresh} search={globalSearch} />;
    case 11: return <TabMCPMonitor autoRefresh={autoRefresh} search={globalSearch} />;
    case 12: return <TabQueueInspector autoRefresh={autoRefresh} />;
    case 13: return <TabThreadMonitor autoRefresh={autoRefresh} search={globalSearch} />;
    case 14: return <TabResourceMonitor autoRefresh={autoRefresh} />;
    case 15: return <TabEventTimeline autoRefresh={autoRefresh} search={globalSearch} />;
    case 16: return <TabLogs autoRefresh={autoRefresh} search={globalSearch} />;
    case 17: return <TabHealthDashboard autoRefresh={autoRefresh} />;
    case 18: return <TabConfiguration autoRefresh={autoRefresh} />;
    case 19: return <TabDiagnosticsReport />;
    case 20: return <TabSelfTest />;
    default: return <Empty title="Not Implemented" hint="This tab is under construction." />;
  }
}

// -----------------------------------------------------------------------------
// HOOKS
// -----------------------------------------------------------------------------

function useDiagnosticsData<T>(
  fetcher: () => Promise<T>,
  autoRefresh: boolean,
  intervalMs = 30000
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());

  const refresh = useCallback(async () => {
    try {
      // Don't show loading on background refresh
      const result = await fetcher();
      setData(result);
      setError(null);
      setLastRefreshed(new Date());
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(refresh, intervalMs);
    return () => clearInterval(timer);
  }, [autoRefresh, intervalMs, refresh]);

  return { data, loading, error, refresh, lastRefreshed };
}

// Helper formatters
function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** i).toFixed(1)} ${units[i]}`;
}

function formatUptime(seconds: number): string {
  if (!seconds) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

// -----------------------------------------------------------------------------
// TABS IMPLEMENTATION
// -----------------------------------------------------------------------------

function TabRuntimeOverview({ autoRefresh }: { autoRefresh: boolean }) {
  const { data, loading, error, refresh } = useDiagnosticsData(api.fetchRuntime, autoRefresh);

  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  if (!data) return null;

  const healthyServices = Object.values(data.platform_services ?? {}).filter(Boolean).length;
  const totalServices = Object.keys(data.platform_services ?? {}).length;
  const healthScore = totalServices > 0 ? Math.round((healthyServices / totalServices) * 100) : 0;

  return (
    <Panel 
      title="Runtime Overview" 
      actions={
        <button onClick={refresh} className="p-1.5 hover:bg-surface/50 rounded-md"><RefreshCw className="w-4 h-4 text-muted" /></button>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Stat label="Hostname" value={data.hostname} />
        <Stat label="OS" value={`${data.os} ${data.os_version ?? ""}`} />
        <Stat label="Uptime" value={formatUptime(data.uptime_seconds)} />
        <Stat label="Health Score" value={`${healthScore}%`} tone={healthScore > 90 ? "ok" : healthScore > 70 ? "warn" : "danger"} />
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="glass rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-3">Versions & Runtimes</h3>
          <div className="space-y-2">
            <div className="flex justify-between border-b border-border/40 pb-2"><span className="text-muted text-sm">System Version</span><span className="text-sm font-mono">{data.version}</span></div>
            <div className="flex justify-between border-b border-border/40 pb-2"><span className="text-muted text-sm">Python</span><span className="text-sm font-mono">{data.python_version}</span></div>
            <div className="flex justify-between border-b border-border/40 pb-2"><span className="text-muted text-sm">Environment</span><span className="text-sm font-mono">{data.environment}</span></div>
            <div className="flex justify-between border-b border-border/40 pb-2"><span className="text-muted text-sm">Workspace</span><span className="text-sm font-mono truncate max-w-[200px]">{data.workspace}</span></div>
          </div>
        </div>
        <div className="glass rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-3">Hardware & Build</h3>
          <div className="space-y-2">
            <div className="flex justify-between border-b border-border/40 pb-2"><span className="text-muted text-sm">CPU Cores</span><span className="text-sm font-mono">{data.cpu_count} ({data.cpu_percent}%)</span></div>
            <div className="flex justify-between border-b border-border/40 pb-2"><span className="text-muted text-sm">Total RAM</span><span className="text-sm font-mono">{formatBytes(data.ram_total)}</span></div>
            <div className="flex justify-between border-b border-border/40 pb-2"><span className="text-muted text-sm">RAM Used</span><span className="text-sm font-mono">{formatBytes(data.ram_used)} ({data.ram_percent}%)</span></div>
            <div className="flex justify-between border-b border-border/40 pb-2"><span className="text-muted text-sm">Git Branch / Commit</span><span className="text-sm font-mono">{data.git_branch ?? "—"} ({data.git_commit?.substring(0, 7) ?? "—"})</span></div>
          </div>
        </div>
      </div>
      
      <div className="mt-4">
        <h3 className="text-sm font-semibold mb-3">Platform Services ({healthyServices}/{totalServices} operational)</h3>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(data.platform_services ?? {}).map(([name, ok]) => (
            <span key={name} className={clsx(
              "px-2 py-0.5 rounded-full border text-[10px] font-medium",
              ok ? "bg-ok/10 border-ok/30 text-ok" : "bg-danger/10 border-danger/30 text-danger"
            )}>
              {name}
            </span>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function TabRuntimeDiscovery({ autoRefresh, search }: { autoRefresh: boolean; search: string }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchDiscovery, autoRefresh);
  
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  const tools = (data?.providers || []).filter(t => t.name.toLowerCase().includes(search.toLowerCase()) || t.type.toLowerCase().includes(search.toLowerCase()));

  return (
    <Panel title="Discovered Runtimes & Tools">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Stat label="Total Discovered" value={data?.total_discovered ?? 0} />
        <Stat label="Running" value={data?.total_running ?? 0} tone="ok" />
        <Stat label="Healthy" value={data?.total_healthy ?? 0} tone="ok" />
      </div>
      <div className="border border-border/60 rounded-xl overflow-hidden">
        <table className="w-full text-sm text-left block overflow-x-auto">
          <thead className="bg-surface/40 text-muted uppercase text-[11px] font-semibold">
            <tr>
              <th className="px-4 py-3">Tool Name</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Vendor</th>
              <th className="px-4 py-3">Version</th>
              <th className="px-4 py-3">PID</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {tools.map((t, i) => (
              <tr key={i} className="hover:bg-surface/20">
                <td className="px-4 py-3 font-medium flex items-center gap-2">
                  <StatusDot status={t.health === "healthy" || t.health === "ok" ? "healthy" : t.running ? "running" : "down"} pulse={t.running} /> {t.name}
                </td>
                <td className="px-4 py-3 text-muted">{t.type}</td>
                <td className="px-4 py-3 text-muted">{t.vendor}</td>
                <td className="px-4 py-3 font-mono">{t.version || 'N/A'}</td>
                <td className="px-4 py-3 font-mono">{t.pid ?? '-'}</td>
                <td className="px-4 py-3">
                  <Badge tone={t.running ? "ok" : t.installed ? "info" : "default"}>
                    {t.status}
                  </Badge>
                </td>
              </tr>
            ))}
            {tools.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-muted">No tools found matching criteria.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function TabBrainRegistry({ autoRefresh, search }: { autoRefresh: boolean; search: string }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchBrains, autoRefresh);
  
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  const brains = data?.brains.filter(b => b.display_name.toLowerCase().includes(search.toLowerCase()) || b.id.toLowerCase().includes(search.toLowerCase())) || [];

  return (
    <Panel title="Brain Registry">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <Stat label="Total Brains" value={data?.total_count ?? 0} />
        <Stat label="Healthy (≥80)" value={data?.healthy_count ?? 0} tone="ok" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {brains.map((brain) => (
          <div key={brain.id} className="glass rounded-xl p-4 border border-border/40">
            <div className="flex justify-between items-start mb-4">
              <div className="flex items-center gap-2">
                <Brain className="h-5 w-5 text-accent" />
                <h3 className="font-semibold text-lg">{brain.display_name}</h3>
              </div>
              <Badge tone={brain.health >= 80 ? "ok" : "warn"}>{brain.status}</Badge>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-y-2 text-sm mb-4">
              <div className="text-muted">Runtime</div>
              <div className="font-medium text-right">{brain.runtime}</div>
              <div className="text-muted">Health</div>
              <div className="font-medium text-right">{brain.health}%</div>
              <div className="text-muted">Memory Usage</div>
              <div className="font-medium text-right">{brain.memory_mb} MB</div>
              <div className="text-muted">CPU Load</div>
              <div className="font-medium text-right">{brain.cpu_percent}%</div>
              <div className="text-muted">Active Tasks</div>
              <div className="font-medium text-right">{brain.task_count}</div>
              <div className="text-muted">Latency</div>
              <div className="font-medium text-right">{brain.latency}ms</div>
            </div>
            
            <div className="pt-3 border-t border-border/40">
              <div className="text-xs text-muted mb-2">Capabilities</div>
              <div className="flex flex-wrap gap-1">
                {brain.capabilities.map(cap => (
                  <span key={cap} className="px-2 py-0.5 bg-surface/50 text-[10px] rounded border border-border/60">{cap}</span>
                ))}
              </div>
            </div>
          </div>
        ))}
        {brains.length === 0 && <div className="col-span-full"><Empty title="No brains found" /></div>}
      </div>
    </Panel>
  );
}

function TabAgentRegistry({ autoRefresh, search }: { autoRefresh: boolean; search: string }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchAgents, autoRefresh);
  
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  const agents = data?.agents.filter(a => a.id.toLowerCase().includes(search.toLowerCase()) || (a.mission || "").toLowerCase().includes(search.toLowerCase())) || [];

  return (
    <Panel title="Agent Registry">
      <div className="border border-border/60 rounded-xl overflow-hidden">
        <table className="w-full text-sm text-left block overflow-x-auto">
          <thead className="bg-surface/40 text-muted uppercase text-[11px] font-semibold">
            <tr>
              <th className="px-4 py-3">Agent ID</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Current Mission</th>
              <th className="px-4 py-3">Provider</th>
              <th className="px-4 py-3 text-right">Tasks</th>
              <th className="px-4 py-3 text-right">Latency</th>
              <th className="px-4 py-3 text-right">Fails/Retries</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {agents.map((a, i) => (
              <tr key={i} className="hover:bg-surface/20">
                <td className="px-4 py-3 font-medium text-accent">{a.id}</td>
                <td className="px-4 py-3">
                  <Badge tone={a.status === "active" || a.status === "healthy" ? "ok" : a.status === "idle" ? "info" : "warn"}>
                    {a.status}
                  </Badge>
                </td>
                <td className="px-4 py-3 text-muted truncate max-w-xs">{a.mission || "—"}</td>
                <td className="px-4 py-3 text-muted">{a.provider}</td>
                <td className="px-4 py-3 text-right font-mono">{a.task_count}</td>
                <td className="px-4 py-3 text-right font-mono">{a.latency_ms}ms</td>
                <td className="px-4 py-3 text-right font-mono text-danger">{a.failures}/{a.retries}</td>
              </tr>
            ))}
            {agents.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-muted">No agents found.</td></tr>}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function TabCapabilityRegistry({ autoRefresh, search }: { autoRefresh: boolean; search: string }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchCapabilities, autoRefresh);
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  const caps = data?.capabilities.filter(c => (c.name || "").toLowerCase().includes(search.toLowerCase()) || (c.provider || "").toLowerCase().includes(search.toLowerCase())) || [];

  return (
    <Panel title="Capability Registry">
      <div className="border border-border/60 rounded-xl overflow-hidden">
        <table className="w-full text-sm text-left block overflow-x-auto">
          <thead className="bg-surface/40 text-muted uppercase text-[11px] font-semibold">
            <tr>
              <th className="px-4 py-3">Capability</th>
              <th className="px-4 py-3">Provider</th>
              <th className="px-4 py-3">Bound Brain</th>
              <th className="px-4 py-3">Priority</th>
              <th className="px-4 py-3">Consumers</th>
              <th className="px-4 py-3">Health</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {caps.map((c, i) => (
              <tr key={i} className="hover:bg-surface/20">
                <td className="px-4 py-3 font-mono text-accent">{c.name}</td>
                <td className="px-4 py-3 text-muted">{c.provider}</td>
                <td className="px-4 py-3 text-muted">{c.brain || '-'}</td>
                <td className="px-4 py-3 font-mono">{c.priority}</td>
                <td className="px-4 py-3 font-mono">{c.consumers}</td>
                <td className="px-4 py-3">
                  <StatusDot status={c.healthy ? "healthy" : "failed"} />
                </td>
              </tr>
            ))}
            {caps.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-muted">No capabilities registered.</td></tr>}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function TabDiscoveryPipeline({ autoRefresh }: { autoRefresh: boolean }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchDiscovery, autoRefresh);
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  const providers = data?.providers ?? [];
  const installed = providers.filter(p => p.installed).length;
  const running = providers.filter(p => p.running).length;

  return (
    <Panel title="Discovery Pipeline Status">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Stat label="Discovered" value={providers.length} />
        <Stat label="Installed" value={installed} />
        <Stat label="Running" value={running} tone="ok" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {providers.map((p, i) => (
          <div key={i} className="glass rounded-xl p-4 border border-border/40">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-semibold">{p.name}</span>
              <Badge tone={p.running ? "ok" : p.installed ? "info" : "default"}>{p.running ? "Running" : p.installed ? "Installed" : "Missing"}</Badge>
            </div>
            <div className="text-xs text-muted">
              {p.version || "unknown version"} · {p.registration_state ?? "discovered"}
              {p.pid ? ` · PID ${p.pid}` : ""}
            </div>
          </div>
        ))}
        {providers.length === 0 && <div className="col-span-full"><Empty title="No providers discovered" hint="Run discovery to scan for runtimes." /></div>}
      </div>
    </Panel>
  );
}

function TabEventBusInspector({ autoRefresh, search }: { autoRefresh: boolean; search: string }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchEventBus, autoRefresh);
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  const topics = data?.topics.filter(t => t.topic.toLowerCase().includes(search.toLowerCase())) || [];

  return (
    <Panel title="EventBus Topics">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Stat label="Total Topics" value={data?.total_topics ?? 0} />
        <Stat label="Total Messages" value={data?.total_messages ?? 0} />
        <Stat label="Bus Type" value={data?.bus_type ?? "unknown"} />
      </div>
      <div className="border border-border/60 rounded-xl overflow-hidden">
        <table className="w-full text-sm text-left block overflow-x-auto">
          <thead className="bg-surface/40 text-muted uppercase text-[11px] font-semibold">
            <tr>
              <th className="px-4 py-3">Topic Name</th>
              <th className="px-4 py-3 text-right">Subscribers</th>
              <th className="px-4 py-3 text-right">Msgs/sec</th>
              <th className="px-4 py-3 text-right">Dropped</th>
              <th className="px-4 py-3 text-right">Errors</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {topics.map((t, i) => (
              <tr key={i} className="hover:bg-surface/20">
                <td className="px-4 py-3 font-mono text-accent">{t.topic}</td>
                <td className="px-4 py-3 text-right font-mono">{t.subscriber_count}</td>
                <td className="px-4 py-3 text-right font-mono">{t.messages_per_sec.toFixed(2)}</td>
                <td className="px-4 py-3 text-right font-mono">{t.dropped}</td>
                <td className="px-4 py-3 text-right font-mono text-danger">{t.errors}</td>
              </tr>
            ))}
            {topics.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted">No topics found.</td></tr>}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function TabSSEInspector({ autoRefresh, search }: { autoRefresh: boolean; search: string }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchSSE, autoRefresh);
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  const q = search.toLowerCase();
  const clients = (data?.clients ?? []).filter(c =>
    ((c.client_id ?? "") as string).toLowerCase().includes(q) ||
    ((c.heartbeat ?? "") as string).toLowerCase().includes(q)
  );

  return (
    <Panel title="SSE Connected Clients">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Stat label="Total Clients" value={data?.clients.length || 0} />
      </div>
      <div className="border border-border/60 rounded-xl overflow-hidden">
        <table className="w-full text-sm text-left block overflow-x-auto">
          <thead className="bg-surface/40 text-muted uppercase text-[11px] font-semibold">
            <tr>
              <th className="px-4 py-3">Client ID</th>
              <th className="px-4 py-3">Connected At</th>
              <th className="px-4 py-3 text-right">Reconnects</th>
              <th className="px-4 py-3 text-right">Msgs/sec</th>
              <th className="px-4 py-3 text-right">Dropped</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {clients.map((c, i) => (
              <tr key={i} className="hover:bg-surface/20">
                <td className="px-4 py-3 font-mono text-muted">{c.client_id}</td>
                <td className="px-4 py-3 text-muted">{c.connected_at || "—"}</td>
                <td className="px-4 py-3 text-right font-mono">{c.reconnects}</td>
                <td className="px-4 py-3 text-right font-mono">{c.messages_per_sec.toFixed(2)}</td>
                <td className="px-4 py-3 text-right font-mono">{c.dropped_frames}</td>
              </tr>
            ))}
            {clients.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted">No connected clients.</td></tr>}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function TabAPIMonitor({ autoRefresh, search }: { autoRefresh: boolean; search: string }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchAPIs, autoRefresh);
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  const apis = data?.endpoints.filter(e => e.path.toLowerCase().includes(search.toLowerCase())) || [];

  return (
    <Panel title="API Monitor (Control Plane)">
      <div className="border border-border/60 rounded-xl overflow-hidden">
        <table className="w-full text-sm text-left block overflow-x-auto">
          <thead className="bg-surface/40 text-muted uppercase text-[11px] font-semibold">
            <tr>
              <th className="px-4 py-3">Method</th>
              <th className="px-4 py-3">Endpoint Path</th>
              <th className="px-4 py-3 text-right">Avg Latency (ms)</th>
              <th className="px-4 py-3 text-right">Total Calls</th>
              <th className="px-4 py-3 text-right">Errors</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {apis.map((a, i) => (
              <tr key={i} className="hover:bg-surface/20">
                <td className="px-4 py-3 font-mono">
                  <Badge tone={a.method === "GET" ? "info" : a.method === "POST" ? "ok" : "warn"}>{a.method}</Badge>
                </td>
                <td className="px-4 py-3 font-mono text-accent">{a.path}</td>
                <td className="px-4 py-3 text-right font-mono">{a.latency.toFixed(2)}</td>
                <td className="px-4 py-3 text-right font-mono">{a.calls.toLocaleString()}</td>
                <td className="px-4 py-3 text-right font-mono text-danger">{a.errors}</td>
              </tr>
            ))}
            {apis.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted">No API telemetry recorded.</td></tr>}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function TabProviderRuntime({ autoRefresh, search }: { autoRefresh: boolean; search: string }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchProviders, autoRefresh);
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  const providers = data?.providers.filter(p => p.name.toLowerCase().includes(search.toLowerCase())) || [];

  return (
    <Panel title="Provider Runtime State">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {providers.map((p, i) => (
          <div key={i} className="glass rounded-xl p-4 border border-border/40">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-semibold">{p.name}</h3>
              <StatusDot status={p.health >= 80 ? "healthy" : p.health >= 50 ? "degraded" : "down"} />
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-muted">Status</span><Badge>{p.status}</Badge></div>
              <div className="flex justify-between"><span className="text-muted">Health</span><span className="font-mono text-xs">{p.health}%</span></div>
              <div className="flex justify-between"><span className="text-muted">Latency</span><span className="font-mono text-xs">{p.latency_ms}ms</span></div>
              <div className="flex justify-between"><span className="text-muted">Brain ID</span><span className="font-mono text-xs truncate max-w-[120px]">{p.brain_id}</span></div>
              <div className="flex justify-between"><span className="text-muted">Bound</span><span className={clsx("font-mono text-xs", p.bound ? "text-ok" : "text-danger")}>{p.bound ? "YES" : "NO"}</span></div>
            </div>
          </div>
        ))}
        {providers.length === 0 && <div className="col-span-full"><Empty title="No providers registered" /></div>}
      </div>
    </Panel>
  );
}

function TabMCPMonitor({ autoRefresh, search }: { autoRefresh: boolean; search: string }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchMCP, autoRefresh);
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  const servers = data?.servers.filter(s => s.name.toLowerCase().includes(search.toLowerCase())) || [];

  return (
    <Panel title="Model Context Protocol (MCP) Servers">
      <div className="border border-border/60 rounded-xl overflow-hidden">
        <table className="w-full text-sm text-left block overflow-x-auto">
          <thead className="bg-surface/40 text-muted uppercase text-[11px] font-semibold">
            <tr>
              <th className="px-4 py-3">Server Name</th>
              <th className="px-4 py-3">Connection</th>
              <th className="px-4 py-3">Ping (ms)</th>
              <th className="px-4 py-3">Capabilities</th>
              <th className="px-4 py-3 text-right">Errors</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {servers.map((s, i) => (
              <tr key={i} className="hover:bg-surface/20">
                <td className="px-4 py-3 font-semibold">{s.name}</td>
                <td className="px-4 py-3">
                  <Badge tone={s.connected ? "ok" : "danger"}>{s.connected ? "Connected" : "Disconnected"}</Badge>
                </td>
                <td className="px-4 py-3 font-mono">{s.ping}ms</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {s.capabilities.map(c => <span key={c} className="px-1.5 py-0.5 bg-surface/60 rounded text-[10px]">{c}</span>)}
                  </div>
                </td>
                <td className="px-4 py-3 text-right font-mono text-danger">{s.errors}</td>
              </tr>
            ))}
            {servers.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted">No MCP servers registered.</td></tr>}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function TabQueueInspector({ autoRefresh }: { autoRefresh: boolean }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchQueues, autoRefresh);
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  return (
    <Panel title="Internal Message Queues">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {data?.queues.map((q, i) => {
          const percent = Math.min(100, q.depth * 5);
          return (
            <div key={i} className="glass rounded-xl p-4 border border-border/40">
              <div className="flex justify-between items-center mb-2">
                <h3 className="font-mono text-sm">{q.name}</h3>
                <span className="text-xs font-mono">depth {q.depth}</span>
              </div>
              <div className="h-2 bg-surface/60 rounded-full overflow-hidden">
                <div 
                  className={clsx("h-full rounded-full transition-all duration-500", percent > 80 ? "bg-danger" : percent > 50 ? "bg-warn" : "bg-ok")} 
                  style={{ width: `${percent}%` }}
                />
              </div>
            </div>
          );
        })}
        {(data?.queues?.length ?? 0) === 0 && <Empty title="No queues" hint="Scheduler and orchestrator queues are empty." />}
      </div>
    </Panel>
  );
}

function TabThreadMonitor({ autoRefresh, search }: { autoRefresh: boolean; search: string }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchThreads, autoRefresh);
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  const q = search.toLowerCase();
  const tasks = (data?.tasks ?? []).filter(t =>
    ((t.name ?? "") as string).toLowerCase().includes(q) ||
    ((t.coroutine ?? "") as string).toLowerCase().includes(q)
  );

  return (
    <Panel title="Asyncio Task Monitor">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Stat label="Total Tasks" value={data?.total_count ?? 0} />
        <Stat label="Running" value={data?.running_count ?? 0} tone="ok" />
        <Stat label="Cancelled" value={data?.cancelled_count ?? 0} tone="warn" />
      </div>
      <div className="border border-border/60 rounded-xl overflow-hidden">
        <table className="w-full text-sm text-left block overflow-x-auto">
          <thead className="bg-surface/40 text-muted uppercase text-[11px] font-semibold">
            <tr>
              <th className="px-4 py-3">Task Name</th>
              <th className="px-4 py-3">Coroutine</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Duration</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {tasks.map((t, i) => (
              <tr key={i} className="hover:bg-surface/20">
                <td className="px-4 py-3 font-mono text-muted">{t.name}</td>
                <td className="px-4 py-3 font-mono text-accent break-all">{t.coroutine || "—"}</td>
                <td className="px-4 py-3">
                  <Badge tone={t.status === "running" ? "ok" : t.status === "pending" ? "warn" : "default"}>{t.status}</Badge>
                </td>
                <td className="px-4 py-3 text-right font-mono">{t.duration_seconds.toFixed(1)}s</td>
              </tr>
            ))}
            {(data?.tasks?.length ?? 0) === 0 && <tr><td colSpan={4} className="px-4 py-8 text-center text-muted">No tasks tracked.</td></tr>}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function TabResourceMonitor({ autoRefresh }: { autoRefresh: boolean }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchResources, autoRefresh);
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  if (!data) return null;

  const cpu = data.cpu_percent ?? 0;
  const ramPct = data.ram_percent ?? 0;
  const diskPct = data.disk_percent ?? 0;

  return (
    <Panel title="System Resources">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Stat label="CPU Usage" value={`${cpu.toFixed(1)}%`} tone={cpu > 80 ? "danger" : "ok"} />
        <Stat label="Memory Usage" value={`${ramPct.toFixed(1)}%`} delta={`${formatBytes(data.ram_used ?? 0)} / ${formatBytes(data.ram_total ?? 0)}`} tone={ramPct > 80 ? "danger" : "ok"} />
        <Stat label="Disk Usage" value={`${diskPct.toFixed(1)}%`} delta={`${formatBytes(data.disk_used ?? 0)} / ${formatBytes(data.disk_total ?? 0)}`} />
        <Stat label="Process Memory" value={`${data.process_rss_mb ?? 0} MB`} tone="accent" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Network Sent" value={formatBytes(data.net_bytes_sent ?? 0)} />
        <Stat label="Network Received" value={formatBytes(data.net_bytes_recv ?? 0)} />
        <Stat label="Threads" value={data.thread_count ?? 0} />
        <Stat label="Open Files" value={data.open_files_count ?? 0} />
      </div>
    </Panel>
  );
}

function TabEventTimeline({ autoRefresh, search }: { autoRefresh: boolean; search: string }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchLogs, autoRefresh);
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  const events = data?.logs.filter(l => l.message.toLowerCase().includes(search.toLowerCase())) || [];

  return (
    <Panel title="Event Timeline">
      <div className="space-y-4">
        {events.map((e, i) => (
          <div key={i} className="flex gap-4 p-3 glass rounded-lg border border-border/40">
            <div className="text-xs text-muted font-mono whitespace-nowrap mt-0.5">{e.timestamp}</div>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <Badge tone="default">{e.subsystem}</Badge>
                <Badge tone={e.level === "ERROR" ? "danger" : e.level === "WARNING" ? "warn" : "info"}>{e.level}</Badge>
              </div>
              <div className="text-sm font-mono text-text/90">{e.message}</div>
            </div>
          </div>
        ))}
        {events.length === 0 && <Empty title="No events found" hint="No structured logs captured yet." />}
      </div>
    </Panel>
  );
}

function TabLogs({ autoRefresh, search }: { autoRefresh: boolean; search: string }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchLogs, autoRefresh);
  const [levelFilter, setLevelFilter] = useState("ALL");
  
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  
  let logs = data?.logs || [];
  if (levelFilter !== "ALL") logs = logs.filter(l => l.level === levelFilter);
  if (search) logs = logs.filter(l => l.message.toLowerCase().includes(search.toLowerCase()) || l.subsystem.toLowerCase().includes(search.toLowerCase()));

  return (
    <Panel 
      title="Structured Logs" 
      actions={
        <div className="flex items-center gap-2">
          <ListFilter className="w-4 h-4 text-muted" />
          <select 
            value={levelFilter} 
            onChange={e => setLevelFilter(e.target.value)}
            className="bg-surface/50 border border-border/60 rounded text-sm px-2 py-1 text-text outline-none"
          >
            <option value="ALL">All Levels</option>
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
        </div>
      }
    >
      <div className="border border-border/60 rounded-xl overflow-hidden font-mono text-xs">
        <table className="w-full text-left block overflow-x-auto">
          <thead className="bg-surface/40 text-muted uppercase">
            <tr>
              <th className="px-3 py-2 w-48">Timestamp</th>
              <th className="px-3 py-2 w-24">Level</th>
              <th className="px-3 py-2 w-32">Subsystem</th>
              <th className="px-3 py-2">Message</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {logs.map((l, i) => (
              <tr key={i} className="hover:bg-surface/20">
                <td className="px-3 py-2 text-muted whitespace-nowrap">{l.timestamp}</td>
                <td className="px-3 py-2">
                  <span className={clsx(
                    l.level === "ERROR" ? "text-danger" : l.level === "WARNING" ? "text-warn" : l.level === "INFO" ? "text-info" : "text-muted"
                  )}>
                    {l.level}
                  </span>
                </td>
                <td className="px-3 py-2 text-accent/80">{l.subsystem}</td>
                <td className="px-3 py-2 break-all">{l.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {logs.length === 0 && <div className="p-8 text-center text-muted">No logs found matching filters.</div>}
      </div>
    </Panel>
  );
}

function TabHealthDashboard({ autoRefresh }: { autoRefresh: boolean }) {
  const { data, loading, error } = useDiagnosticsData(api.fetchHealth, autoRefresh);
  
  if (loading && !data) return <LoadingScreen />;
  if (error) return <Empty title="Error fetching data" hint={error.message} />;
  if (!data) return null;

  const meta = data._meta;
  const subsystems = Object.entries(data).filter(([k]) => k !== "_meta");
  const overall = meta?.health_score ?? 0;

  return (
    <Panel title="Subsystem Health Grid">
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="inline-flex items-center gap-3 px-4 py-2 glass rounded-lg border border-border/40">
          <span className="text-sm font-semibold text-muted">Health Score:</span>
          <Badge tone={overall > 90 ? "ok" : overall > 70 ? "warn" : "danger"}>{overall}%</Badge>
        </div>
        <div className="text-xs text-faint">
          {meta?.healthy_count ?? 0}/{meta?.total_subsystems ?? 0} subsystems operational · checked {meta?.checked_at ? new Date(meta.checked_at).toLocaleTimeString() : "—"}
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {subsystems.map(([name, stat]) => {
          const s = stat as api.DiagnosticsHealthSubsystem;
          return (
            <div key={name} className="glass rounded-xl p-4 border border-border/40">
              <div className="flex justify-between items-center mb-3">
                <h3 className="font-semibold text-sm capitalize">{name.replace(/_/g, " ")}</h3>
                <StatusDot status={s.healthy ? "healthy" : "down"} pulse={s.healthy} />
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="text-muted">Status</div>
                <div className="text-right font-mono">{s.status}</div>
                <div className="text-muted">Latency</div>
                <div className="text-right font-mono">{s.latency_ms}ms</div>
                <div className="text-muted">Errors</div>
                <div className="text-right font-mono text-danger">{s.errors}</div>
                <div className="text-muted">Warnings</div>
                <div className="text-right font-mono text-warn">{s.warnings}</div>
                <div className="text-muted">Restarts</div>
                <div className="text-right font-mono">{s.restart_count}</div>
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function TabConfiguration({ autoRefresh }: { autoRefresh: boolean }) {
  return (
    <Panel title="Example Configuration (static reference — not fetched live)">
      <div className="glass rounded-xl p-4 overflow-auto border border-border/40">
        <p className="mb-2 text-[10px] text-faint">
          Illustrative shape only. The running backend does not expose a config
          endpoint, so this is a static sample — not your live configuration.
        </p>
        <pre className="text-xs font-mono text-accent/90">
{`{
  "runtime": {
    "mode": "hybrid",
    "debug": false,
    "logLevel": "INFO",
    "telemetryEnabled": true
  },
  "network": {
    "controlPlanePort": 8000,
    "dataPlanePort": 8001,
    "corsOrigins": ["http://localhost:3000", "tauri://localhost"]
  },
  "providers": {
    "openai": {
      "enabled": true,
      "apiKey": "sk-***...***",
      "defaultModel": "<your-openai-model>"
    },
    "anthropic": {
      "enabled": true,
      "apiKey": "sk-ant-***...***",
      "defaultModel": "<your-anthropic-model>"
    }
  },
  "storage": {
    "vectorDb": "chroma",
    "chromaUrl": "http://localhost:8002",
    "localStoragePath": "~/.agenticos/data"
  },
  "discovery": {
    "autoScanPaths": ["/usr/local/bin", "~/.cargo/bin", "~/go/bin"],
    "refreshIntervalSecs": 300
  }
}`}
        </pre>
      </div>
    </Panel>
  );
}

function TabDiagnosticsReport() {
  return (
    <Panel title="Generate Diagnostics Report">
      <div className="max-w-2xl">
        <p className="text-sm text-muted mb-6">
          Generate a complete snapshot of the system&apos;s current state, including logs, metrics, active tasks, and configuration. 
          This archive is suitable for support tickets and offline analysis.
        </p>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <button className="flex flex-col items-center justify-center p-6 glass rounded-xl border border-border/40 hover:bg-surface/40 transition-colors">
            <FileJson className="w-8 h-8 text-accent mb-3" />
            <span className="text-sm font-semibold">JSON Export</span>
            <span className="text-xs text-muted mt-1">Raw structured data</span>
          </button>
          
          <button className="flex flex-col items-center justify-center p-6 glass rounded-xl border border-border/40 hover:bg-surface/40 transition-colors">
            <FileJson className="w-8 h-8 text-info mb-3" />
            <span className="text-sm font-semibold">Markdown Export</span>
            <span className="text-xs text-muted mt-1">Human readable summary</span>
          </button>

          <button className="flex flex-col items-center justify-center p-6 glass rounded-xl border border-border/40 hover:bg-surface/40 transition-colors">
            <Download className="w-8 h-8 text-ok mb-3" />
            <span className="text-sm font-semibold">Full Archive (.zip)</span>
            <span className="text-xs text-muted mt-1">Logs, DBs, configs</span>
          </button>
        </div>
      </div>
    </Panel>
  );
}

function TabSelfTest() {
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<api.DiagnosticsSelfTestResult | null>(null);

  const runTest = async () => {
    setRunning(true);
    setResults(null);
    try {
      const res = await api.runSelfTest();
      setResults(res);
    } catch (e) {
      console.error(e);
      setResults(null);
    } finally {
      setRunning(false);
    }
  };

  return (
    <Panel title="System Self Test">
      <div className="mb-6">
        <button
          onClick={runTest}
          disabled={running}
          className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent/90 text-accent-foreground rounded-md font-medium text-sm disabled:opacity-50 transition-colors"
        >
          {running ? <RefreshCw className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
          {running ? "Running Diagnostics..." : "Run Self Test Sequence"}
        </button>
      </div>

      {running && (
        <div className="p-12 flex flex-col items-center justify-center">
          <div className="w-10 h-10 border-4 border-accent border-t-transparent rounded-full animate-spin mb-4" />
          <div className="text-sm font-medium animate-pulse text-muted">Running comprehensive checks...</div>
        </div>
      )}

      {!running && results && (
        <div className="border border-border/60 rounded-xl overflow-hidden">
          <table className="w-full text-sm text-left block overflow-x-auto">
            <thead className="bg-surface/40 text-muted uppercase text-[11px] font-semibold">
              <tr>
                <th className="px-4 py-3 w-12">Result</th>
                <th className="px-4 py-3 w-1/3">Test Name</th>
                <th className="px-4 py-3">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {results.results.map((r, i) => (
                <tr key={i} className="hover:bg-surface/20">
                  <td className="px-4 py-3">
                    {r.status === "PASS" ? <CheckCircle className="w-5 h-5 text-ok" /> : 
                     r.status === "WARNING" ? <AlertTriangle className="w-5 h-5 text-warn" /> : 
                     <XCircle className="w-5 h-5 text-danger" />}
                  </td>
                  <td className="px-4 py-3 font-semibold">{r.name}</td>
                  <td className="px-4 py-3 text-muted">{r.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      
      {!running && !results && (
        <Empty title="Ready to run diagnostics" hint="Click the button above to start the self-test sequence." />
      )}
    </Panel>
  );
}
