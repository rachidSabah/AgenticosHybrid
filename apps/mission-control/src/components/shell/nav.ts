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
  Bell,
  Command,
  Settings,
  Gauge,
} from "lucide-react";

export interface NavItem {
  id: string;
  label: string;
  hint: string;
  icon: typeof Brain;
  group: "core" | "build" | "observe";
}

export const NAV: NavItem[] = [
  { id: "overview", label: "Mission Overview", hint: "O", icon: Activity, group: "core" },
  { id: "brain", label: "AI Brain", hint: "B", icon: Brain, group: "core" },
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
];

export const NAV_GROUPS: { id: NavItem["group"]; label: string }[] = [
  { id: "core", label: "Command" },
  { id: "build", label: "Compose" },
  { id: "observe", label: "Inspect" },
];

export const ALL_ICONS = { Command, Settings, Bell };
