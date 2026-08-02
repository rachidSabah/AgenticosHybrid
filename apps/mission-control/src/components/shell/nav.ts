import {
  Brain,
  Orbit,
  Activity,
  GitBranch,
  Workflow,
  Database,
  Server,
  Boxes,
  Plug,
  Network,
  FolderTree,
  History,
  Settings,
  Gauge,
  Search,
  Globe,
  Monitor,
  MonitorDot,
  Wifi,
  RefreshCw,
  Shield,
  Terminal,
  MessageSquarePlus,
  Zap,
  Sparkles,
  Cloud,
  GitPullRequestArrow,
} from "lucide-react";

export interface NavItem {
  id: string;
  label: string;
  hint: string;
  icon: typeof Brain;
  group: "core" | "build" | "observe" | "desktop";
}

export const NAV: NavItem[] = [
  { id: "binding", label: "AI Agent Binding", hint: "A", icon: Server, group: "core" },
  { id: "overview", label: "Mission Overview", hint: "O", icon: Activity, group: "core" },
  { id: "brain", label: "AI Brain", hint: "B", icon: Brain, group: "core" },
  { id: "prompt-center", label: "Prompt Center", hint: "P", icon: MessageSquarePlus, group: "core" },
  { id: "constellation", label: "Agent Constellation", hint: "C", icon: Orbit, group: "core" },
  { id: "execution", label: "Execution Graph", hint: "E", icon: GitBranch, group: "core" },
  { id: "workflow", label: "Workflow Studio", hint: "W", icon: Workflow, group: "build" },
  { id: "pipeline", label: "Pipeline Builder", hint: "P", icon: Network, group: "build" },
  { id: "providers", label: "Provider Control Center", hint: "R", icon: Server, group: "observe" },
  { id: "memory", label: "Memory Explorer", hint: "M", icon: Database, group: "observe" },
  { id: "plugins", label: "Plugin Marketplace", hint: "U", icon: Boxes, group: "observe" },
  { id: "mcp", label: "MCP Manager", hint: "N", icon: Plug, group: "observe" },
  { id: "workspace", label: "Workspace Explorer", hint: "S", icon: FolderTree, group: "observe" },
  { id: "timeline", label: "Task Timeline", hint: "T", icon: History, group: "observe" },
  { id: "monitor", label: "System Monitor", hint: "Y", icon: Gauge, group: "observe" },
  { id: "runtime-diagnostics", label: "Diagnostics", hint: "X", icon: Activity, group: "observe" },
  { id: "discovery", label: "Discovery", hint: "D", icon: Search, group: "observe" },
  { id: "healing", label: "Self-Healing", hint: "H", icon: Shield, group: "observe" },
  { id: "swarm", label: "Swarm Orchestration", hint: "S", icon: Globe, group: "core" },
  { id: "missions", label: "Mission Orchestrator", hint: "M", icon: GitBranch, group: "core" },
  // Desktop views (Phase 4, M6)
  { id: "desktop-overview", label: "Desktop Overview", hint: "1", icon: Monitor, group: "desktop" },
  { id: "desktop-runtimes", label: "Desktop Runtimes", hint: "2", icon: MonitorDot, group: "desktop" },
  { id: "desktop-updates", label: "Desktop Updates", hint: "3", icon: RefreshCw, group: "desktop" },
  { id: "desktop-diagnostics", label: "Desktop Diagnostics", hint: "4", icon: Shield, group: "desktop" },
  { id: "desktop-offline", label: "Offline Mode", hint: "5", icon: Wifi, group: "desktop" },
  { id: "desktop-settings", label: "Desktop Settings", hint: "6", icon: Settings, group: "desktop" },
  { id: "omniroute", label: "OmniRoute", hint: "R", icon: Network, group: "core" },
  { id: "gateway", label: "API Gateway", hint: "G", icon: Zap, group: "core" },
  { id: "governance", label: "AI Governance", hint: "V", icon: Shield, group: "observe" },
  { id: "agent-memory", label: "Agent Memory Manager", hint: "Y", icon: Database, group: "observe" },
  { id: "collaboration", label: "Live Collaboration", hint: "L", icon: Orbit, group: "build" },
  { id: "disaster-recovery", label: "Backup & Recovery", hint: "K", icon: RefreshCw, group: "desktop" },
  // Phase 6.3 — Universal Runtime Control
  { id: "runtime", label: "Runtime Dashboard", hint: "7", icon: Terminal, group: "desktop" },
  // Phase 15 — Autonomous Agent Ecosystem
  { id: "ecosystem", label: "Ecosystem", hint: "E", icon: Sparkles, group: "core" },
  // Phase 16 — Distributed Runtime Federation
  { id: "cluster", label: "Cluster Federation", hint: "F", icon: Cloud, group: "core" },
  // Phase 17 — Autonomous Agent Evolution
  { id: "evolution", label: "Evolution", hint: "V", icon: GitPullRequestArrow, group: "core" },
];

export const NAV_GROUPS: { id: NavItem["group"]; label: string }[] = [
  { id: "core", label: "Command" },
  { id: "build", label: "Compose" },
  { id: "observe", label: "Inspect" },
  { id: "desktop", label: "Desktop" },
];


