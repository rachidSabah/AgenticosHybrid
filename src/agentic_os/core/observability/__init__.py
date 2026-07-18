"""Observability Module Exports

Provides unified access to observability implementations.
"""

from __future__ import annotations

from agentic_os.core.observability.in_memory import (
    InMemoryMetrics,
    InMemoryStructuredLogging,
    InMemoryTracing,
)
from agentic_os.core.observability.logging import (
    StructuredLogging,
    configure_logging,
    get_logging,
)
from agentic_os.core.observability.metrics import (
    PrometheusMetrics,
    configure_metrics,
    get_metrics,
)
from agentic_os.core.observability.tracing import (
    OTelTracing,
    configure_tracing,
    get_tracing,
)


# Factory functions for easy configuration
def create_observability_stack(
    mode: str = "development",  # "development", "production", "testing"
    service_name: str = "agentic-os",
    otlp_endpoint: str | None = None,
    prometheus_port: int | None = None,
) -> dict[str, object]:
    """Create a complete observability stack based on mode.

    Args:
        mode: "development" (in-memory + console), "production" (OTel), "testing" (in-memory)
        service_name: Service name for telemetry
        otlp_endpoint: OTLP endpoint for production mode
        prometheus_port: Port for Prometheus metrics endpoint

    Returns:
        Dictionary with tracing, metrics, logging implementations
    """
    if mode == "production":
        if not otlp_endpoint:
            raise ValueError("OTLP endpoint required for production mode")
        tracing = OTelTracing(service_name, otlp_endpoint)
        metrics = PrometheusMetrics()
        logging = StructuredLogging()
    elif mode == "testing":
        tracing = InMemoryTracing()
        metrics = InMemoryMetrics()
        logging = InMemoryStructuredLogging()
    else:  # development
        tracing = InMemoryTracing()
        metrics = InMemoryMetrics()
        logging = InMemoryStructuredLogging()

    return {
        "tracing": tracing,
        "metrics": metrics,
        "logging": logging,
    }


__all__ = [
    # Domain
    "OTelTracing",
    "OTelMetrics",
    "PrometheusMetrics",
    "InMemoryTracing",
    "InMemoryMetrics",
    "StructuredLogging",
    "InMemoryStructuredLogging",
    # Factory
    "create_observability_stack",
    "configure_tracing",
    "configure_metrics",
    "configure_logging",
    "get_tracing",
    "get_metrics",
    "get_logging",
]