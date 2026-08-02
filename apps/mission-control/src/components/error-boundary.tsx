"use client";

import { Component, ReactNode, ErrorInfo } from "react";
import { Panel, Empty } from "@/components/ui/primitives";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  viewName?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[ErrorBoundary:${this.props.viewName ?? "unknown"}]`, error, info);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <Panel
          title={`${this.props.viewName ?? "View"} unavailable`}
          subtitle="An error occurred while rendering this view"
          className="h-full"
        >
          <Empty
            title="Something went wrong"
            hint={this.state.error?.message ?? "Unknown error"}
          />
          <details className="mt-4 text-[11px] text-faint font-mono max-h-40 overflow-auto">
            <summary className="cursor-pointer mb-2">Error details</summary>
            <pre>{this.state.error?.stack}</pre>
          </details>
        </Panel>
      );
    }
    return this.props.children;
  }
}

export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  viewName: string,
): React.FC<P> {
  return function Wrapped(props: P) {
    return (
      <ErrorBoundary viewName={viewName}>
        <Component {...props} />
      </ErrorBoundary>
    );
  };
}