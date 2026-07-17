"use client";

import { Panel, Empty } from "@/components/ui/primitives";

interface Props {
  title: string;
  subtitle?: string;
}

export function ViewSkeleton({ title, subtitle }: Props) {
  return (
    <Panel title={title} subtitle={subtitle} className="h-full">
      <div className="h-full flex items-center justify-center">
        <Empty
          title="Loading..."
          hint="Fetching live data from EventBus"
        />
      </div>
    </Panel>
  );
}

export function ViewSkeletonMinimal({ title }: { title: string }) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="animate-pulse space-y-3 w-3/4">
        <div className="h-4 bg-surface/50 rounded w-1/3" />
        <div className="h-4 bg-surface/50 rounded w-1/4" />
        <div className="h-32 bg-surface/50 rounded-xl" />
        <div className="h-32 bg-surface/50 rounded-xl" />
        <div className="h-32 bg-surface/50 rounded-xl" />
      </div>
    </div>
  );
}