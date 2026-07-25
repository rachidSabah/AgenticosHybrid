"use client";

import { useContext, Suspense, lazy, type ReactNode } from "react";
import { ReactFlowProvider } from "reactflow";
import { ActiveViewCtx } from "@/lib/active-view";
import { ErrorBoundary } from "@/components/error-boundary";
import { ViewSkeleton, ViewSkeletonMinimal } from "@/components/view-skeleton";

function lazyWithRetry<T extends React.ComponentType<any>>(
  factory: () => Promise<{ default: T }>
) {
  return lazy(async () => {
    try {
      return await factory();
    } catch {
      await new Promise((r) => setTimeout(r, 400));
      return await factory();
    }
  });
}

const MissionOverview = lazyWithRetry(() =>
  import("@/views/mission-overview").then((m) => ({ default: m.MissionOverview }))
);
const AIBrain = lazyWithRetry(() =>
  import("@/views/ai-brain").then((m) => ({ default: m.AIBrain }))
);
const AgentConstellation = lazyWithRetry(() =>
  import("@/views/agent-constellation").then((m) => ({ default: m.AgentConstellation }))
);
const ExecutionGraph = lazyWithRetry(() =>
  import("@/views/execution-graph").then((m) => ({ default: m.ExecutionGraph }))
);
const WorkflowStudio = lazyWithRetry(() =>
  import("@/views/workflow-studio").then((m) => ({ default: m.WorkflowStudio }))
);
const PipelineBuilder = lazyWithRetry(() =>
  import("@/views/pipeline-builder").then((m) => ({ default: m.PipelineBuilder }))
);
const ProviderControlCenter = lazyWithRetry(() =>
  import("@/views/provider-control-center").then((m) => ({ default: m.ProviderControlCenter }))
);
const MemoryExplorer = lazyWithRetry(() =>
  import("@/views/memory-explorer").then((m) => ({ default: m.MemoryExplorer }))
);
const PluginMarketplace = lazyWithRetry(() =>
  import("@/views/plugin-marketplace").then((m) => ({ default: m.PluginMarketplace }))
);
const McpManager = lazyWithRetry(() =>
  import("@/views/mcp-manager").then((m) => ({ default: m.McpManager }))
);
const WorkspaceExplorer = lazyWithRetry(() =>
  import("@/views/workspace-explorer").then((m) => ({ default: m.WorkspaceExplorer }))
);
const TaskTimeline = lazyWithRetry(() =>
  import("@/views/task-timeline").then((m) => ({ default: m.TaskTimeline }))
);
const SystemMonitor = lazyWithRetry(() =>
  import("@/views/system-monitor").then((m) => ({ default: m.SystemMonitor }))
);
const DiscoveryDashboard = lazyWithRetry(() =>
  import("@/views/discovery-dashboard").then((m) => ({ default: m.DiscoveryDashboard }))
);
const SelfHealingPanel = lazyWithRetry(() =>
  import("@/views/self-healing").then((m) => ({ default: m.SelfHealingPanel }))
);
const SwarmDashboard = lazyWithRetry(() =>
  import("@/views/swarm-dashboard").then((m) => ({ default: m.SwarmDashboard }))
);
const MissionOrchestrator = lazyWithRetry(() =>
  import("@/views/mission-orchestrator").then((m) => ({ default: m.MissionOrchestrator }))
);
const PromptCenter = lazyWithRetry(() =>
  import("@/views/prompt-center").then((m) => ({ default: m.PromptCenter }))
);

// Desktop views (Phase 4, M6)
const DesktopOverview = lazyWithRetry(() =>
  import("@/views/desktop-overview").then((m) => ({ default: m.default }))
);
const DesktopRuntimes = lazyWithRetry(() =>
  import("@/views/desktop-runtimes").then((m) => ({ default: m.default }))
);
const DesktopUpdates = lazyWithRetry(() =>
  import("@/views/desktop-updates").then((m) => ({ default: m.default }))
);
const DesktopDiagnostics = lazyWithRetry(() =>
  import("@/views/desktop-diagnostics").then((m) => ({ default: m.default }))
);
const DesktopOffline = lazyWithRetry(() =>
  import("@/views/desktop-offline").then((m) => ({ default: m.default }))
);
const DesktopSettings = lazyWithRetry(() =>
  import("@/views/desktop-settings").then((m) => ({ default: m.default }))
);
const GatewayDashboard = lazyWithRetry(() =>
  import("@/views/gateway-dashboard").then((m) => ({ default: m.GatewayDashboard }))
);

const LocalAgents = lazyWithRetry(() =>
  import("@/views/local-agents").then((m) => ({ default: m.LocalAgents }))
);

const OmniRouteDashboard = lazyWithRetry(() =>
  import("@/views/omniroute-dashboard").then((m) => ({ default: m.OmniRouteDashboard }))
);

const AgentBindingCenter = lazyWithRetry(() =>
  import("@/views/agent-binding-center").then((m) => ({ default: m.AgentBindingCenter }))
);

const GovernanceCenter = lazyWithRetry(() =>
  import("@/views/governance-center").then((m) => ({ default: m.GovernanceCenter }))
);
const AgentMemoryManager = lazyWithRetry(() =>
  import("@/views/agent-memory-manager").then((m) => ({ default: m.AgentMemoryManager }))
);
const LiveCollaboration = lazyWithRetry(() =>
  import("@/views/live-collaboration").then((m) => ({ default: m.LiveCollaboration }))
);
const DisasterRecovery = lazyWithRetry(() =>
  import("@/views/disaster-recovery").then((m) => ({ default: m.DisasterRecovery }))
);

const VIEWS: Record<string, () => ReactNode> = {
  governance: () => (
    <ErrorBoundary viewName="AI Governance Center" fallback={<ViewSkeleton title="AI Governance Center" />}>
      <Suspense fallback={<ViewSkeleton title="AI Governance Center" />}>
        <GovernanceCenter />
      </Suspense>
    </ErrorBoundary>
  ),
  "agent-memory": () => (
    <ErrorBoundary viewName="Agent Memory Manager" fallback={<ViewSkeleton title="Agent Memory Manager" />}>
      <Suspense fallback={<ViewSkeleton title="Agent Memory Manager" />}>
        <AgentMemoryManager />
      </Suspense>
    </ErrorBoundary>
  ),
  collaboration: () => (
    <ErrorBoundary viewName="Live Collaboration" fallback={<ViewSkeleton title="Live Collaboration" />}>
      <Suspense fallback={<ViewSkeleton title="Live Collaboration" />}>
        <LiveCollaboration />
      </Suspense>
    </ErrorBoundary>
  ),
  "disaster-recovery": () => (
    <ErrorBoundary viewName="Backup & Recovery" fallback={<ViewSkeleton title="Backup & Recovery" />}>
      <Suspense fallback={<ViewSkeleton title="Backup & Recovery" />}>
        <DisasterRecovery />
      </Suspense>
    </ErrorBoundary>
  ),
  omniroute: () => (
    <ErrorBoundary viewName="OmniRoute AI Subsystem" fallback={<ViewSkeleton title="OmniRoute AI Subsystem" />}>
      <Suspense fallback={<ViewSkeleton title="OmniRoute AI Subsystem" />}>
        <OmniRouteDashboard />
      </Suspense>
    </ErrorBoundary>
  ),
  binding: () => (
    <ErrorBoundary viewName="AI Agent Binding Center" fallback={<ViewSkeleton title="AI Agent Binding Center" />}>
      <Suspense fallback={<ViewSkeleton title="AI Agent Binding Center" />}>
        <AgentBindingCenter />
      </Suspense>
    </ErrorBoundary>
  ),
  overview: () => (
    <ErrorBoundary viewName="Mission Overview" fallback={<ViewSkeleton title="Mission Overview" />}>
      <Suspense fallback={<ViewSkeleton title="Mission Overview" />}>
        <MissionOverview />
      </Suspense>
    </ErrorBoundary>
  ),
  brain: () => (
    <ErrorBoundary viewName="AI Brain" fallback={<ViewSkeleton title="AI Brain" />}>
      <Suspense fallback={<ViewSkeleton title="AI Brain" />}>
        <AIBrain />
      </Suspense>
    </ErrorBoundary>
  ),
  constellation: () => (
    <ReactFlowProvider>
      <ErrorBoundary viewName="Agent Constellation" fallback={<ViewSkeletonMinimal title="Agent Constellation" />}>
        <Suspense fallback={<ViewSkeletonMinimal title="Agent Constellation" />}>
          <AgentConstellation />
        </Suspense>
      </ErrorBoundary>
    </ReactFlowProvider>
  ),
  execution: () => (
    <ReactFlowProvider>
      <ErrorBoundary viewName="Execution Graph" fallback={<ViewSkeletonMinimal title="Execution Graph" />}>
        <Suspense fallback={<ViewSkeletonMinimal title="Execution Graph" />}>
          <ExecutionGraph />
        </Suspense>
      </ErrorBoundary>
    </ReactFlowProvider>
  ),
  workflow: () => (
    <ReactFlowProvider>
      <ErrorBoundary viewName="Workflow Studio" fallback={<ViewSkeleton title="Workflow Studio" />}>
        <Suspense fallback={<ViewSkeleton title="Workflow Studio" />}>
          <WorkflowStudio />
        </Suspense>
      </ErrorBoundary>
    </ReactFlowProvider>
  ),
  pipeline: () => (
    <ReactFlowProvider>
      <ErrorBoundary viewName="Pipeline Builder" fallback={<ViewSkeleton title="Pipeline Builder" />}>
        <Suspense fallback={<ViewSkeleton title="Pipeline Builder" />}>
          <PipelineBuilder />
        </Suspense>
      </ErrorBoundary>
    </ReactFlowProvider>
  ),
  providers: () => (
    <ErrorBoundary viewName="Provider Control Center" fallback={<ViewSkeleton title="Provider Control Center" />}>
      <Suspense fallback={<ViewSkeleton title="Provider Control Center" />}>
        <ProviderControlCenter />
      </Suspense>
    </ErrorBoundary>
  ),
  memory: () => (
    <ErrorBoundary viewName="Memory Explorer" fallback={<ViewSkeleton title="Memory Explorer" />}>
      <Suspense fallback={<ViewSkeleton title="Memory Explorer" />}>
        <MemoryExplorer />
      </Suspense>
    </ErrorBoundary>
  ),
  plugins: () => (
    <ErrorBoundary viewName="Plugin Marketplace" fallback={<ViewSkeleton title="Plugin Marketplace" />}>
      <Suspense fallback={<ViewSkeleton title="Plugin Marketplace" />}>
        <PluginMarketplace />
      </Suspense>
    </ErrorBoundary>
  ),
  mcp: () => (
    <ErrorBoundary viewName="MCP Manager" fallback={<ViewSkeleton title="MCP Manager" />}>
      <Suspense fallback={<ViewSkeleton title="MCP Manager" />}>
        <McpManager />
      </Suspense>
    </ErrorBoundary>
  ),
  workspace: () => (
    <ErrorBoundary viewName="Workspace Explorer" fallback={<ViewSkeleton title="Workspace Explorer" />}>
      <Suspense fallback={<ViewSkeleton title="Workspace Explorer" />}>
        <WorkspaceExplorer />
      </Suspense>
    </ErrorBoundary>
  ),
  timeline: () => (
    <ErrorBoundary viewName="Task Timeline" fallback={<ViewSkeleton title="Task Timeline" />}>
      <Suspense fallback={<ViewSkeleton title="Task Timeline" />}>
        <TaskTimeline />
      </Suspense>
    </ErrorBoundary>
  ),
  monitor: () => (
    <ErrorBoundary viewName="System Monitor" fallback={<ViewSkeleton title="System Monitor" />}>
      <Suspense fallback={<ViewSkeleton title="System Monitor" />}>
        <SystemMonitor />
      </Suspense>
    </ErrorBoundary>
  ),
  discovery: () => (
    <ErrorBoundary viewName="Discovery" fallback={<ViewSkeleton title="Discovery" />}>
      <Suspense fallback={<ViewSkeleton title="Discovery" />}>
        <DiscoveryDashboard />
      </Suspense>
    </ErrorBoundary>
  ),
  healing: () => (
    <ErrorBoundary viewName="Self-Healing" fallback={<ViewSkeleton title="Self-Healing" />}>
      <Suspense fallback={<ViewSkeleton title="Self-Healing" />}>
        <SelfHealingPanel />
      </Suspense>
    </ErrorBoundary>
  ),
  swarm: () => (
    <ErrorBoundary viewName="Swarm Orchestration" fallback={<ViewSkeleton title="Swarm Orchestration" />}>
      <Suspense fallback={<ViewSkeleton title="Swarm Orchestration" />}>
        <SwarmDashboard />
      </Suspense>
    </ErrorBoundary>
  ),
  missions: () => (
    <ErrorBoundary viewName="Mission Orchestrator" fallback={<ViewSkeleton title="Mission Orchestrator" />}>
      <Suspense fallback={<ViewSkeleton title="Mission Orchestrator" />}>
        <MissionOrchestrator />
      </Suspense>
    </ErrorBoundary>
  ),
  "prompt-center": () => (
    <ErrorBoundary viewName="Prompt Center" fallback={<ViewSkeleton title="Prompt Center" />}>
      <Suspense fallback={<ViewSkeleton title="Prompt Center" />}>
        <PromptCenter />
      </Suspense>
    </ErrorBoundary>
  ),
  // Desktop views (Phase 4, M6)
  "desktop-overview": () => (
    <ErrorBoundary viewName="Desktop Overview" fallback={<ViewSkeleton title="Desktop Overview" />}>
      <Suspense fallback={<ViewSkeleton title="Desktop Overview" />}>
        <DesktopOverview />
      </Suspense>
    </ErrorBoundary>
  ),
  "desktop-runtimes": () => (
    <ErrorBoundary viewName="Desktop Runtimes" fallback={<ViewSkeleton title="Desktop Runtimes" />}>
      <Suspense fallback={<ViewSkeleton title="Desktop Runtimes" />}>
        <DesktopRuntimes />
      </Suspense>
    </ErrorBoundary>
  ),
  "desktop-updates": () => (
    <ErrorBoundary viewName="Desktop Updates" fallback={<ViewSkeleton title="Desktop Updates" />}>
      <Suspense fallback={<ViewSkeleton title="Desktop Updates" />}>
        <DesktopUpdates />
      </Suspense>
    </ErrorBoundary>
  ),
  "desktop-diagnostics": () => (
    <ErrorBoundary viewName="Desktop Diagnostics" fallback={<ViewSkeleton title="Desktop Diagnostics" />}>
      <Suspense fallback={<ViewSkeleton title="Desktop Diagnostics" />}>
        <DesktopDiagnostics />
      </Suspense>
    </ErrorBoundary>
  ),
  "desktop-offline": () => (
    <ErrorBoundary viewName="Offline Mode" fallback={<ViewSkeleton title="Offline Mode" />}>
      <Suspense fallback={<ViewSkeleton title="Offline Mode" />}>
        <DesktopOffline />
      </Suspense>
    </ErrorBoundary>
  ),
  "desktop-settings": () => (
    <ErrorBoundary viewName="Desktop Settings" fallback={<ViewSkeleton title="Desktop Settings" />}>
      <Suspense fallback={<ViewSkeleton title="Desktop Settings" />}>
        <DesktopSettings />
      </Suspense>
    </ErrorBoundary>
  ),
  "gateway": () => (
    <ErrorBoundary viewName="API Gateway" fallback={<ViewSkeleton title="API Gateway" />}>
      <Suspense fallback={<ViewSkeleton title="API Gateway" />}>
        <GatewayDashboard />
      </Suspense>
    </ErrorBoundary>
  ),
  "local-agents": () => (
    <ErrorBoundary viewName="Local Agents" fallback={<ViewSkeleton title="Local Agents" />}>
      <Suspense fallback={<ViewSkeleton title="Local Agents" />}>
        <LocalAgents />
      </Suspense>
    </ErrorBoundary>
  ),
};

export default function Page() {
  const { active } = useContext(ActiveViewCtx);
  const View = VIEWS[active] ?? VIEWS.overview;
  return <View />;
}