"""
Phase 2 — EWMA Predictive Arbiter & Dynamic Fallback Matrix.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProviderMetrics:
    provider_id: str
    alpha: float = 0.2  # EWMA decay factor
    ewma_latency_ms: float = 120.0
    error_rate: float = 0.00
    requests_count: int = 0
    consecutive_failures: int = 0
    is_healthy: bool = True
    last_updated: float = field(default_factory=time.time)

    def record_request(self, latency_ms: float, success: bool) -> None:
        self.requests_count += 1
        self.last_updated = time.time()
        # Update EWMA
        self.ewma_latency_ms = (self.alpha * latency_ms) + ((1 - self.alpha) * self.ewma_latency_ms)
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
        self._providers: Dict[str, ProviderMetrics] = {
            "claude_code": ProviderMetrics("claude_code", ewma_latency_ms=177.0),
            "hermes": ProviderMetrics("hermes", ewma_latency_ms=774.0),
            "auto:codex": ProviderMetrics("auto:codex", ewma_latency_ms=55.0),
            "auto:agy": ProviderMetrics("auto:agy", ewma_latency_ms=156.0),
            "Codex CLI": ProviderMetrics("Codex CLI", ewma_latency_ms=45.0),
            "auto:opencode": ProviderMetrics("auto:opencode", ewma_latency_ms=95.0),
        }
        self.budget_threshold_usd: float = 50.0
        self.current_spend_usd: float = 2.45

    def get_ranked_providers(self, max_latency_ms: float = 2000.0) -> List[Dict[str, Any]]:
        healthy = [p for p in self._providers.values() if p.is_healthy and p.ewma_latency_ms <= max_latency_ms]
        ranked = sorted(healthy, key=lambda x: (x.error_rate * 1000) + x.ewma_latency_ms)
        return [
            {
                "provider_id": p.provider_id,
                "ewma_latency_ms": round(p.ewma_latency_ms, 1),
                "error_rate": round(p.error_rate, 3),
                "is_healthy": p.is_healthy,
                "score": round(100.0 / (1.0 + (p.ewma_latency_ms / 100.0) + (p.error_rate * 50.0)), 2),
            }
            for p in ranked
        ]

    def record_telemetry(self, provider_id: str, latency_ms: float, success: bool) -> ProviderMetrics:
        if provider_id not in self._providers:
            self._providers[provider_id] = ProviderMetrics(provider_id)
        metric = self._providers[provider_id]
        metric.record_request(latency_ms, success)
        return metric


predictive_arbiter = PredictiveRoutingArbiter()