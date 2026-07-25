"use client";

import { clsx } from "clsx";

// ── Status colours ──

const STATUS_COLORS: Record<string, string> = {
  running: "bg-green-500",
  idle: "bg-yellow-400",
  busy: "bg-yellow-500",
  stopped: "bg-red-500",
  crashed: "bg-red-600",
  updating: "bg-yellow-400",
  restarting: "bg-yellow-400",
  unknown: "bg-gray-400",
};

// Pulse animation only for running/busy — alive agents
const PULSE_STATUSES = new Set(["running", "busy"]);

interface StatusDotProps {
  status: string;
  pulse?: boolean;
  label?: boolean;
  className?: string;
}

export function StatusDot({ status, pulse, label, className }: StatusDotProps) {
  const color = STATUS_COLORS[status] ?? "bg-gray-400";
  const showPulse = pulse ?? PULSE_STATUSES.has(status);

  return (
    <span className={clsx("inline-flex items-center gap-1.5", className)}>
      <span className="relative inline-flex h-2.5 w-2.5">
        {showPulse && (
          <span
            className={clsx(
              "absolute inline-flex h-full w-full animate-ping rounded-full opacity-60",
              color
            )}
          />
        )}
        <span className={clsx("relative inline-flex h-2.5 w-2.5 rounded-full", color)} />
      </span>
      {label && (
        <span className="text-[11px] capitalize text-muted">{status}</span>
      )}
    </span>
  );
}
