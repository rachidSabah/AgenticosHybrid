"use client";

import { useContext, Suspense, lazy, type ReactNode } from "react";
import { ActiveViewCtx } from "@/lib/active-view";
import { ErrorBoundary, withErrorBoundary } from "@/components/error-boundary";
import { ViewSkeleton, ViewSkeletonMinimal } from "@/components/view-skeleton";

const MissionOverview = lazy(() =>
  import("@/views/mission-overview").then((m) => ({ default: m.MissionOverview }))
);
const AIBrain = lazy(() =>
  import("@/views/ai-brain").then((m) => ({ default: m.AIBrain }))
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
    <ErrorBoundary viewName="Agent Constellation" fallback={<ViewSkeletonMinimal title="Agent Constellation" />}>
      <Suspense fallback={<ViewSkeletonMinimal title="Agent Constellation" />}>
        <AgentConstellation />
      </Suspense>
    </ErrorBoundary>
  ),
  execution: () => (
    <ErrorBoundary viewName="Execution Graph" fallback={<ViewSkeletonMinimal title="Execution Graph" />}>
      <Suspense fallback={<ViewSkeletonMinimal title="Execution Graph" />}>
        <ExecutionGraph />
      </Suspense>
    </ErrorBoundary>
  ),
  workflow: () => (
    <ErrorBoundary viewName="Workflow Studio" fallback={<ViewSkeleton title="Workflow Studio" />}>
      <Suspense fallback={<ViewSkeleton title="Workflow Studio" />}>
        <WorkflowStudio />
      </Suspense>
    </ErrorBoundary>
  ),
  pipeline: () => (
    <ErrorBoundary viewName="Pipeline Builder" fallback={<ViewSkeleton title="Pipeline Builder" />}>
      <Suspense fallback={<ViewSkeleton title="Pipeline Builder" />}>
        <PipelineBuilder />
      </Suspense>
    </ErrorBoundary>
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
};

export default function Page() {
  const active = useContext(ActiveViewCtx) || "overview";
  const View = VIEWS[active] ?? VIEWS.overview;
  return <View />;
}