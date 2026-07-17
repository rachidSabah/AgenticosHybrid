"use client";

import { useContext, type ReactNode } from "react";
import { ActiveViewCtx } from "@/lib/active-view";
import { MissionOverview } from "@/views/mission-overview";
import { AIBrain } from "@/views/ai-brain";
import { AgentConstellation } from "@/views/agent-constellation";
import { ExecutionGraph } from "@/views/execution-graph";
import { WorkflowStudio } from "@/views/workflow-studio";
import { PipelineBuilder } from "@/views/pipeline-builder";
import { ProviderControlCenter } from "@/views/provider-control-center";
import { MemoryExplorer } from "@/views/memory-explorer";
import { PluginMarketplace } from "@/views/plugin-marketplace";
import { McpManager } from "@/views/mcp-manager";
import { WorkspaceExplorer } from "@/views/workspace-explorer";
import { TaskTimeline } from "@/views/task-timeline";
import { SystemMonitor } from "@/views/system-monitor";

const VIEWS: Record<string, () => ReactNode> = {
  overview: MissionOverview,
  brain: AIBrain,
  constellation: AgentConstellation,
  execution: ExecutionGraph,
  workflow: WorkflowStudio,
  pipeline: PipelineBuilder,
  providers: ProviderControlCenter,
  memory: MemoryExplorer,
  plugins: PluginMarketplace,
  mcp: McpManager,
  workspace: WorkspaceExplorer,
  timeline: TaskTimeline,
  monitor: SystemMonitor,
};

export default function Page() {
  const active = useContext(ActiveViewCtx) || "overview";
  const View = VIEWS[active] ?? MissionOverview;
  return <View />;
}
