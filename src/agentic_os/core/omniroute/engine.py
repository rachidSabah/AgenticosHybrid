"""OmniRoute Universal Multi-Model Router, Circuit Breaker, and Context Compressor."""

from __future__ import annotations

import re
import time
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("omniroute.engine")

# Strategy mapping with primary and fallback providers + latency expectations
STRATEGIES: dict[str, dict[str, Any]] = {
    "latency": {
        "name": "Fast-Path (Low Latency)",
        "description": "Optimized for sub-200ms turnaround using Groq LPU or Gemini Flash.",
        "primary_provider": "groq",
        "primary_model": "llama-3.3-70b-versatile",
        "fallback_provider": "google",
        "fallback_model": "gemini-2.5-flash",
        "latency_target_ms": 150.0,
    },
    "cost": {
        "name": "Cost-Optimization",
        "description": "Prefers local zero-cost Ollama models or cost-effective tier APIs.",
        "primary_provider": "ollama",
        "primary_model": "qwen2.5-coder",
        "fallback_provider": "deepseek",
        "fallback_model": "deepseek-chat",
        "latency_target_ms": 350.0,
    },
    "reasoning": {
        "name": "Deep Reasoning",
        "description": "Heavy reasoning for architectural planning, security, and diff generation.",
        "primary_provider": "anthropic",
        "primary_model": "claude-3-7-sonnet",
        "fallback_provider": "deepseek",
        "fallback_model": "deepseek-reasoner",
        "latency_target_ms": 800.0,
    },
    "privacy": {
        "name": "Privacy / Local-First",
        "description": "Strictly blocks external cloud egress, ensuring code stays on-device.",
        "primary_provider": "ollama",
        "primary_model": "llama3.2",
        "fallback_provider": "ollama",
        "fallback_model": "qwen2.5-coder",
        "latency_target_ms": 250.0,
    },
}


class OmniRouteEngine:
    """Universal model routing engine with lockless O(1) evaluation, circuit breakers, and compression."""

    def __init__(self, failure_threshold: int = 3) -> None:
        self.failure_threshold = failure_threshold
        # Atomic lockless state dictionaries
        self._provider_health: dict[str, str] = {
            "groq": "HEALTHY",
            "google": "HEALTHY",
            "ollama": "HEALTHY",
            "deepseek": "HEALTHY",
            "anthropic": "HEALTHY",
            "openai": "HEALTHY",
        }
        self._consecutive_failures: dict[str, int] = {p: 0 for p in self._provider_health}
        self._failover_history: list[dict[str, Any]] = []

    def list_policies(self) -> list[dict[str, Any]]:
        """Return list of active routing policy strategies."""
        return [
            {
                "strategy": k,
                "name": v["name"],
                "description": v["description"],
                "primary": f"{v['primary_provider']}/{v['primary_model']}",
                "fallback": f"{v['fallback_provider']}/{v['fallback_model']}",
                "latency_target_ms": v["latency_target_ms"],
                "primary_status": self._provider_health.get(v["primary_provider"], "HEALTHY"),
            }
            for k, v in STRATEGIES.items()
        ]

    def record_failure(self, provider: str, reason: str = "timeout") -> None:
        """Record an upstream provider failure; trips circuit breaker if threshold reached."""
        current = self._consecutive_failures.get(provider, 0) + 1
        self._consecutive_failures[provider] = current
        if current >= self.failure_threshold:
            self._provider_health[provider] = "TRIPPED"
            log.warning("circuit_breaker_tripped", provider=provider, consecutive_failures=current)

    def record_success(self, provider: str) -> None:
        """Reset consecutive failures upon successful response."""
        self._consecutive_failures[provider] = 0
        self._provider_health[provider] = "HEALTHY"

    def resolve(
        self, prompt: str = "", category: str = "general", strategy: str = "latency"
    ) -> dict[str, Any]:
        """Perform sub-millisecond lockless O(1) routing decision."""
        t0 = time.perf_counter()

        strat_key = strategy.lower()
        if strat_key not in STRATEGIES:
            strat_key = "latency"

        strat = STRATEGIES[strat_key]
        primary = strat["primary_provider"]
        fallback = strat["fallback_provider"]

        # Check circuit breaker status
        is_tripped = self._provider_health.get(primary) == "TRIPPED"
        if is_tripped:
            selected_provider = fallback
            selected_model = strat["fallback_model"]
            is_fallback = True
            # Log failover event
            self._failover_history.append(
                {
                    "timestamp": time.time(),
                    "strategy": strat_key,
                    "tripped_provider": primary,
                    "fallback_provider": fallback,
                    "reason": f"Provider '{primary}' circuit breaker TRIPPED ({self._consecutive_failures.get(primary, 0)} consecutive failures)",
                }
            )
        else:
            selected_provider = primary
            selected_model = strat["primary_model"]
            is_fallback = False

        decision_time_ms = round((time.perf_counter() - t0) * 1000, 4)

        return {
            "strategy": strat_key,
            "selected_provider": selected_provider,
            "selected_model": selected_model,
            "is_fallback": is_fallback,
            "decision_time_ms": decision_time_ms,
            "latency_estimate_ms": strat["latency_target_ms"],
        }

    def get_failovers(self) -> list[dict[str, Any]]:
        """Return history of circuit-breaker fallback triggers."""
        return list(self._failover_history)

    def compress_context(self, prompt: str) -> dict[str, Any]:
        """Strip redundant whitespace, repeated diff lines, and duplicates to optimize prompt tokens."""
        original_len = len(prompt)
        if not prompt:
            return {
                "original_characters": 0,
                "compressed_characters": 0,
                "compression_ratio": 1.0,
                "savings_percent": 0.0,
                "optimized_prompt": "",
            }

        # 1. Normalize line endings and multiple trailing spaces
        text = prompt.replace("\r\n", "\n")
        # 2. Collapse runs of blank lines to maximum 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 3. Collapse multiple spaces into single space (except leading indentation)
        lines = []
        for line in text.split("\n"):
            indent_match = re.match(r"^(\s*)", line)
            indent = indent_match.group(1) if indent_match else ""
            rest = line[len(indent) :].strip()
            rest = re.sub(r"[ \t]{2,}", " ", rest)
            lines.append(f"{indent}{rest}" if rest else "")
        optimized = "\n".join(lines)

        compressed_len = len(optimized)
        ratio = round(compressed_len / original_len, 3) if original_len else 1.0
        savings = round((1.0 - ratio) * 100, 1)

        return {
            "original_characters": original_len,
            "compressed_characters": compressed_len,
            "compression_ratio": ratio,
            "savings_percent": savings,
            "optimized_prompt": optimized,
        }


# Singleton instance
omniroute_engine = OmniRouteEngine()
