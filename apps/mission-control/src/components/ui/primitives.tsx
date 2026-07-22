"use client";

import { clsx } from "clsx";
import type { ReactNode } from "react";

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
  contentClassName,
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}) {
  return (
    <section className={clsx("panel flex min-h-0 flex-col", className)}>
      {(title || actions) && (
        <header className="flex items-center gap-3 border-b border-border/60 px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="truncate text-sm font-semibold tracking-tight">{title}</h2>}
            {subtitle && <p className="truncate text-[11px] text-faint">{subtitle}</p>}
          </div>
          {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={clsx("min-h-0 flex-1 overflow-auto p-4", contentClassName)}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  delta,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  delta?: string;
  tone?: "default" | "ok" | "warn" | "danger" | "accent";
}) {
  const toneClass = {
    default: "text-text",
    ok: "text-ok",
    warn: "text-warn",
    danger: "text-danger",
    accent: "text-accent",
  }[tone];
  return (
    <div className="glass rounded-xl px-3.5 py-3">
      <div className="text-[11px] uppercase tracking-wide text-faint">{label}</div>
      <div className={clsx("mt-1 text-xl font-semibold tabular-nums", toneClass)}>{value}</div>
      {delta && <div className="mt-0.5 text-[11px] text-faint">{delta}</div>}
    </div>
  );
}

const STATUS_COLOR: Record<string, string> = {
  healthy: "bg-ok",
  ok: "bg-ok",
  running: "bg-accent",
  completed: "bg-ok",
  idle: "bg-faint",
  degraded: "bg-warn",
  down: "bg-danger",
  unknown: "bg-faint",
  failed: "bg-danger",
  recovered: "bg-warn",
  pending: "bg-warn",
};

export function StatusDot({ status, pulse }: { status: string; pulse?: boolean }) {
  const color = STATUS_COLOR[status] ?? "bg-faint";
  return (
    <span className="relative inline-flex h-2.5 w-2.5">
      {pulse && (
        <span className={clsx("absolute inline-flex h-full w-full rounded-full opacity-60 animate-pulse-ring", color)} />
      )}
      <span className={clsx("relative inline-flex h-2.5 w-2.5 rounded-full", color)} />
    </span>
  );
}

export function Badge({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "ok" | "warn" | "danger" | "accent" | "info";
}) {
  const map = {
    default: "bg-surface/60 text-muted",
    ok: "bg-ok/12 text-ok",
    warn: "bg-warn/12 text-warn",
    danger: "bg-danger/12 text-danger",
    accent: "bg-accent/12 text-accent",
    info: "bg-info/12 text-info",
  }[tone];
  return <span className={clsx("pill", map)}>{children}</span>;
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="grid h-full place-items-center text-center">
      <div className="max-w-xs">
        <div className="text-sm font-medium text-muted">{title}</div>
        {hint && <div className="mt-1 text-xs text-faint">{hint}</div>}
      </div>
    </div>
  );
}

export function LoadingScreen() {
  return (
    <div className="grid h-full min-h-[200px] place-items-center">
      <div className="flex items-center gap-3 text-sm text-faint">
        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        Loading…
      </div>
    </div>
  );
}
