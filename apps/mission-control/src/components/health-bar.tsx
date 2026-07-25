"use client";

import { clsx } from "clsx";

interface HealthBarProps {
  /** Health score from 0 to 100 */
  score: number;
  /** Show percentage label beside the bar */
  showLabel?: boolean;
  /** Optional custom class */
  className?: string;
  /** Bar height (default: h-2) */
  barHeight?: string;
}

export function HealthBar({
  score,
  showLabel = true,
  className,
  barHeight = "h-2",
}: HealthBarProps) {
  const clamped = Math.max(0, Math.min(100, score));

  // Color stops
  const color =
    clamped > 70
      ? "bg-gradient-to-r from-green-500 to-emerald-400"
      : clamped > 40
        ? "bg-gradient-to-r from-yellow-400 to-amber-400"
        : "bg-gradient-to-r from-red-500 to-rose-400";

  return (
    <div className={clsx("flex items-center gap-2", className)}>
      <div className={clsx("relative flex-1 overflow-hidden rounded-full bg-surface/40", barHeight)}>
        <div
          className={clsx("h-full rounded-full transition-all duration-500 ease-out", color)}
          style={{ width: `${clamped}%` }}
        />
      </div>
      {showLabel && (
        <span className="tabular-nums text-[11px] font-medium text-muted">
          {clamped}%
        </span>
      )}
    </div>
  );
}
