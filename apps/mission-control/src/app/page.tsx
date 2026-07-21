"use client";

import { useContext, Suspense, lazy, type ReactNode } from "react";
import { ReactFlowProvider } from "reactflow";
import { ActiveViewCtx } from "@/lib/active-view";
import { ErrorBoundary } from "@/components/error-boundary";
import { ViewSkeleton, ViewSkeletonMinimal } from "@/components/view-skeleton";

const MissionOverview = lazy(() =>
  import("@/views/mission-overview").then((m) => ({ default: m.MissionOverview }))
);
const AIBrain = lazy(() =>
  import("@/views/ai-brain").then((m) => ({ default: m.default }))
);
const AgentConstellation = lazy(() =>
  import("@/views/agent-constellation").then((m) => ({ default: m.AgentConstellation }))
);
const ExecutionGraph = lazy(() =>
  import("@/views/execution-graph").then((m) => ({ default: m.ExecutionGraph }))
);
const WorkflowStudio = lazy(() =>
  import("@/views/workflow-studio").then((m) => ({ default: m.WorkflowStudio }))
);
const PipelineBuilder = lazy(() =>
  import("@/views/pipeline-builder").then((m) => ({ default: m.PipelineBuilder }))
);
const ProviderControlCenter = lazy(() =>
  import("@/views/provider-control-center").then((m) => ({ default: m.ProviderControlCenter }))
);
const MemoryExplorer = lazy(() =>
  import("@/views/memory-explorer").then((m) => ({ default: m.MemoryExplorer }))
);
const PluginMarketplace = lazy(() =>
  import("@/views/plugin-marketplace").then((m) => ({ default: m.PluginMarketplace }))
);
const McpManager = lazy(() =>
  import("@/views/mcp-manager").then((m) => ({ default: m.McpManager }))
);
const WorkspaceExplorer = lazy(() =>
  import("@/views/workspace-explorer").then((m) => ({ default: m.WorkspaceExplorer }))
);
const TaskTimeline = lazy(() =>
  import("@/views/task-timeline").then((m) => ({ default: m.TaskTimeline }))
);
const SystemMonitor = lazy(() =>
  import("@/views/system-monitor").then((m) => ({ default: m.SystemMonitor }))
);
const DiscoveryDashboard = lazy(() =>
  import("@/views/discovery-dashboard").then((m) => ({ default: m.DiscoveryDashboard }))
);
const SelfHealingPanel = lazy(() =>
  import("@/views/self-healing").then((m) => ({ default: m.SelfHealingPanel }))
);
const SwarmDashboard = lazy(() =>
  import("@/views/swarm-dashboard").then((m) => ({ default: m.SwarmDashboard }))
);
const MissionOrchestrator = lazy(() =>
  import("@/views/mission-orchestrator").then((m) => ({ default: m.MissionOrchestrator }))
);

// Desktop views (Phase 4, M6)
const DesktopOverview = lazy(() =>
  import("@/views/desktop-overview").then((m) => ({ default: m.default }))
);
const DesktopRuntimes = lazy(() =>
  import("@/views/desktop-runtimes").then((m) => ({ default: m.default }))
);
const DesktopUpdates = lazy(() =>
  import("@/views/desktop-updates").then((m) => ({ default: m.default }))
);
const DesktopDiagnostics = lazy(() =>
  import("@/views/desktop-diagnostics").then((m) => ({ default: m.default }))
);
const DesktopOffline = lazy(() =>
  import("@/views/desktop-offline").then((m) => ({ default: m.default }))
);
const DesktopSettings = lazy(() =>
  import("@/views/desktop-settings").then((m) => ({ default: m.default }))
);

const VIEWS: Record<string, () => ReactNode> = {
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
};

export default function Page() {
  const { active } = useContext(ActiveViewCtx);
  const View = VIEWS[active] ?? VIEWS.overview;
  return <View />;
}