"""
Phase 2 — EWMA Predictive Arbiter & Dynamic Fallback Matrix.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderMetrics:
    provider_id: str
    alpha: float = 0.2  # EWMA decay factor
    # Spec §16: no seeded latency. A provider with zero recorded requests has
    # NO measured latency — it is excluded from ranking until real telemetry
    # arrives via record_request().
    ewma_latency_ms: float = 0.0
    error_rate: float = 0.00
    requests_count: int = 0
    consecutive_failures: int = 0
    is_healthy: bool = True
    last_updated: float = field(default_factory=time.time)

    def record_request(self, latency_ms: float, success: bool) -> None:
        self.requests_count += 1
        self.last_updated = time.time()
        # Update EWMA (first sample seeds it directly, not from the zero default)
        if self.requests_count == 1:
            self.ewma_latency_ms = latency_ms
        else:
            self.ewma_latency_ms = (self.alpha * latency_ms) + (
                (1 - self.alpha) * self.ewma_latency_ms
            )
        if success:
            self.consecutive_failures = 0
            self.error_rate = (self.alpha * 0.0) + ((1 - self.alpha) * self.error_rate)
            self.is_healthy = True
        else:
            self.consecutive_failures += 1
            self.error_rate = (self.alpha * 1.0) + ((1 - self.alpha) * self.error_rate)
            if self.consecutive_failures >= 3 or self.ewma_latency_ms > 2500:
                self.is_healthy = False


class PredictiveRoutingArbiter:
    """Calculates multi-objective routing scores and handles non-breaking mid-stream failovers."""

    def __init__(self) -> None:
        # Spec §16: no fabricated seed latencies (177/774/55/156/45/95ms) and
        # no invented spend (was $2.45). Rankings contain only providers with
        # REAL recorded telemetry; spend starts at $0.00.
        self._providers: dict[str, ProviderMetrics] = {}
        self.budget_threshold_usd: float = 50.0
        self.current_spend_usd: float = 0.0

    def get_ranked_providers(self, max_latency_ms: float = 2000.0) -> list[dict[str, Any]]:
        # Providers with no recorded requests have no evidence — exclude them.
        healthy = [
            p
            for p in self._providers.values()
            if p.requests_count > 0 and p.is_healthy and p.ewma_latency_ms <= max_latency_ms
        ]
        ranked = sorted(healthy, key=lambda x: (x.error_rate * 1000) + x.ewma_latency_ms)
        return [
            {
                "provider_id": p.provider_id,
                "ewma_latency_ms": round(p.ewma_latency_ms, 1),
                "error_rate": round(p.error_rate, 3),
                "is_healthy": p.is_healthy,
                "score": round(
                    100.0 / (1.0 + (p.ewma_latency_ms / 100.0) + (p.error_rate * 50.0)), 2
                ),
            }
            for p in ranked
        ]

    def record_telemetry(
        self, provider_id: str, latency_ms: float, success: bool
    ) -> ProviderMetrics:
        if provider_id not in self._providers:
            self._providers[provider_id] = ProviderMetrics(provider_id)
        metric = self._providers[provider_id]
        metric.record_request(latency_ms, success)
        return metric


predictive_arbiter = PredictiveRoutingArbiter()
