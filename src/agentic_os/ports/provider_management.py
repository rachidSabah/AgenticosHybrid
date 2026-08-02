"""Ports: Provider Management System.

Defines the interfaces for managing providers, models, secrets, health,
routing, failover, cost, rate limits, and benchmarking. All concrete behavior
lives behind these ports so the orchestrator and UI depend only on abstractions
(hexagonal architecture; ADR-0006).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from agentic_os.domain.agent import ProviderInfo
from agentic_os.ports.provider import ProviderAdapter


class ModelInfo(BaseModel):
    """Metadata for a model exposed by a provider (JSON-serializable)."""

    id: str
    provider: str
    context_window: int = 0
    input_cost_per_1k: float = 0.0
    output_cost_per_1k: float = 0.0
    capabilities: list[str] = Field(default_factory=list)


@runtime_checkable
class ProviderManager(Protocol):
    """Registry + lifecycle for provider adapters and their models."""

    def register(self, adapter: ProviderAdapter) -> None: ...

    def get(self, name: str) -> ProviderAdapter | None: ...

    def list_providers(self) -> list[ProviderInfo]: ...

    def register_model(self, model: ModelInfo) -> None: ...

    def list_models(self, provider: str | None = None) -> list[ModelInfo]: ...

    def get_model(self, provider: str, model_id: str) -> ModelInfo | None: ...


@runtime_checkable
class ModelManager(Protocol):
    """Resolves models and their economics for routing/cost decisions."""

    def models_for(self, provider: str) -> list[ModelInfo]: ...

    def cheapest(self, capability: str) -> ModelInfo | None: ...

    def by_latency(self, capability: str) -> list[ModelInfo]: ...


@runtime_checkable
class SecretStore(Protocol):
    """Secure, at-rest storage for credentials (API keys, tokens)."""

    async def put(self, key: str, value: str) -> None: ...

    async def get(self, key: str) -> str | None: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...


@runtime_checkable
class ApiKeyVault(Protocol):
    """High-level API-key management backed by a SecretStore."""

    async def store_key(self, provider: str, api_key: str) -> None: ...

    async def get_key(self, provider: str) -> str | None: ...

    async def revoke(self, provider: str) -> None: ...


@runtime_checkable
class ProviderHealthMonitor(Protocol):
    """Periodically probes provider liveness and reports status."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def status(self, provider: str) -> str: ...

    async def check_now(self, provider: str) -> bool: ...


@runtime_checkable
class RoutingPolicy(Protocol):
    """Selects a (provider, model) for a request based on strategy."""

    async def select(
        self, capability: str, candidates: list[tuple[str, str]]
    ) -> tuple[str, str] | None: ...


@runtime_checkable
class CostTracker(Protocol):
    """Records token usage and derives cost per task/provider."""

    async def record(
        self, provider: str, model: str, task_id: str, input_tokens: int, output_tokens: int
    ) -> float: ...

    def total_cost(self, provider: str | None = None) -> float: ...


@runtime_checkable
class RateLimitMonitor(Protocol):
    """Tracks remaining quota / rate budget per provider."""

    def consume(self, provider: str, weight: int = 1) -> bool: ...

    def remaining(self, provider: str) -> int: ...

    def set_limit(self, provider: str, limit: int) -> None: ...


@runtime_checkable
class FailoverPolicy(Protocol):
    """Given a failed provider, chooses the next healthy candidate."""

    async def next_provider(
        self, failed: str, capability: str, healthy: list[str]
    ) -> str | None: ...
