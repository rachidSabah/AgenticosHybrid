"""OmniRoute Provider Registry — production implementation.

Stores and manages provider definitions (base URLs, capabilities, cost metadata,
rate limits, health state). Publishes lifecycle events on the EventBus and
integrates with the Health Registry.

Port protocol
-------------
:class:`ProviderRegistryPort` — implemented here. Consumers depend on this
protocol, never on the concrete class directly.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.omniroute import (
    OmniRouteProvider,
    ProviderDiscoveryStatus,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("omniroute.provider_registry")


# ── Port Protocol ──


@runtime_checkable
class ProviderRegistryPort(Protocol):
    """OmniRoute provider registry — single source of truth for providers."""

    async def register(self, provider: OmniRouteProvider) -> str:
        """Register a provider. Returns the provider id."""
        ...

    async def get(self, provider_id: str) -> OmniRouteProvider | None:
        """Get a provider by id."""
        ...

    async def get_by_name(self, name: str) -> OmniRouteProvider | None:
        """Get a provider by its unique name."""
        ...

    async def update(self, provider: OmniRouteProvider) -> OmniRouteProvider | None:
        """Update an existing provider. Returns updated provider or None."""
        ...

    async def delete(self, provider_id: str) -> bool:
        """Delete a provider by id. Returns True if deleted."""
        ...

    async def list_providers(
        self,
        *,
        kind: str | None = None,
        enabled_only: bool = False,
        healthy_only: bool = False,
        capability: str | None = None,
    ) -> list[OmniRouteProvider]:
        """List providers with optional filters."""
        ...

    async def count(self) -> int:
        """Total number of registered providers."""
        ...

    # ── Health ──

    async def set_health(self, provider_id: str, healthy: bool, error: str = "") -> bool:
        """Update health status for a provider. Returns True if updated."""
        ...

    async def is_healthy(self, provider_id: str) -> bool:
        """Check if a provider is currently healthy."""
        ...

    async def list_unhealthy(self) -> list[OmniRouteProvider]:
        """List all providers that are currently unhealthy."""
        ...

    # ── Capabilities ──

    async def providers_for_capability(self, capability: str) -> list[OmniRouteProvider]:
        """Return providers that support a given capability."""
        ...

    async def set_capabilities(self, provider_id: str, capabilities: list[str]) -> bool:
        """Replace the capability set for a provider."""
        ...

    # ── Cost & Rate Limits ──

    async def set_cost_metadata(
        self,
        provider_id: str,
        *,
        cost_per_1k_input: float | None = None,
        cost_per_1k_output: float | None = None,
    ) -> bool:
        """Update cost metadata for a provider."""
        ...

    async def set_rate_limit(self, provider_id: str, rate_limit: int) -> bool:
        """Set the requests-per-minute rate limit for a provider."""
        ...

    async def consume_rate(self, provider_id: str, weight: int = 1) -> bool:
        """Consume rate-limit capacity. Returns True if within limit."""
        ...

    async def rate_limit_remaining(self, provider_id: str) -> int:
        """Return remaining rate-limit capacity."""
        ...

    # ── Lifecycle ──

    async def start(self) -> None:
        """Start the provider registry."""
        ...

    async def stop(self) -> None:
        """Stop the provider registry and release resources."""
        ...

    async def health_check(self) -> dict[str, Any]:
        """Health status of the registry itself."""
        ...


# ── In-memory rate-limit tracker ──


@dataclass
class _RateBucket:
    """Simple sliding-window rate-limit bucket."""

    limit: int = 60
    window_seconds: float = 60.0
    tokens: list[float] = field(default_factory=list)

    def consume(self, weight: int = 1) -> bool:
        now = time.monotonic()
        # Prune expired
        cutoff = now - self.window_seconds
        self.tokens = [t for t in self.tokens if t > cutoff]
        if len(self.tokens) + weight > self.limit:
            return False
        self.tokens.extend([now] * weight)
        return True

    @property
    def remaining(self) -> int:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        self.tokens = [t for t in self.tokens if t > cutoff]
        return max(0, self.limit - len(self.tokens))


# ── Concrete Implementation ──


class ProviderRegistryImpl:
    """In-memory provider registry with EventBus integration.

    Thread-safe via asyncio.Lock. Publishes lifecycle events on provider
    registration, health changes, and failures.
    """

    def __init__(
        self,
        event_bus: Any | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._lock = asyncio.Lock()
        self._providers: dict[str, OmniRouteProvider] = {}
        self._rate_buckets: dict[str, _RateBucket] = {}
        self._started = False

    # ── Lifecycle ──

    async def start(self) -> None:
        self._started = True
        log.info("ProviderRegistry started")

    async def stop(self) -> None:
        self._started = False
        self._providers.clear()
        self._rate_buckets.clear()
        log.info("ProviderRegistry stopped")

    async def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self._started else "stopped",
            "started": self._started,
            "provider_count": len(self._providers),
        }

    # ── CRUD ──

    async def register(self, provider: OmniRouteProvider) -> str:
        async with self._lock:
            provider_id = provider.id or uuid4().hex[:12]
            if provider_id in self._providers:
                log.warning("Provider %s already registered, skipping", provider_id)
                return provider_id
            stored = OmniRouteProvider(
                id=provider_id,
                name=provider.name,
                kind=provider.kind,
                base_url=provider.base_url,
                api_key_ref=provider.api_key_ref,
                enabled=provider.enabled,
                capabilities=provider.capabilities,
                models=provider.models,
                latency_ms=provider.latency_ms,
                cost_per_1k_input=provider.cost_per_1k_input,
                cost_per_1k_output=provider.cost_per_1k_output,
                context_window=provider.context_window,
                supports_streaming=provider.supports_streaming,
                supports_reasoning=provider.supports_reasoning,
                supports_vision=provider.supports_vision,
                supports_tools=provider.supports_tools,
                status=ProviderDiscoveryStatus.REGISTERED,
                priority=provider.priority,
                fallback_order=provider.fallback_order,
                rate_limit=provider.rate_limit,
                version=provider.version,
                healthy=provider.healthy,
                last_health_check=None,
                error_message="",
                metadata=dict(provider.metadata) if provider.metadata else {},
            )
            self._providers[provider_id] = stored
            if provider.rate_limit > 0:
                self._rate_buckets[provider_id] = _RateBucket(limit=provider.rate_limit)

        await self._publish(
            Topic.PROVIDER_REGISTERED,
            {
                "provider_id": provider_id,
                "name": provider.name,
                "kind": provider.kind,
            },
        )
        log.info("Provider registered: %s (%s)", provider.name, provider_id)
        return provider_id

    async def get(self, provider_id: str) -> OmniRouteProvider | None:
        async with self._lock:
            return self._providers.get(provider_id)

    async def get_by_name(self, name: str) -> OmniRouteProvider | None:
        async with self._lock:
            for p in self._providers.values():
                if p.name == name:
                    return p
            return None

    async def update(self, provider: OmniRouteProvider) -> OmniRouteProvider | None:
        async with self._lock:
            existing = self._providers.get(provider.id)
            if existing is None:
                return None
            updated = OmniRouteProvider(
                id=provider.id,
                name=provider.name or existing.name,
                kind=provider.kind or existing.kind,
                base_url=provider.base_url or existing.base_url,
                api_key_ref=provider.api_key_ref or existing.api_key_ref,
                enabled=provider.enabled,
                capabilities=provider.capabilities or existing.capabilities,
                models=provider.models or existing.models,
                latency_ms=provider.latency_ms or existing.latency_ms,
                cost_per_1k_input=provider.cost_per_1k_input or existing.cost_per_1k_input,
                cost_per_1k_output=provider.cost_per_1k_output or existing.cost_per_1k_output,
                context_window=provider.context_window or existing.context_window,
                supports_streaming=provider.supports_streaming,
                supports_reasoning=provider.supports_reasoning,
                supports_vision=provider.supports_vision,
                supports_tools=provider.supports_tools,
                status=provider.status or existing.status,
                priority=provider.priority if provider.priority != 0 else existing.priority,
                fallback_order=provider.fallback_order
                if provider.fallback_order != 0
                else existing.fallback_order,
                rate_limit=provider.rate_limit or existing.rate_limit,
                version=provider.version or existing.version,
                healthy=provider.healthy,
                last_health_check=provider.last_health_check or existing.last_health_check,
                error_message=provider.error_message or existing.error_message,
                metadata=dict(provider.metadata) if provider.metadata else dict(existing.metadata),
            )
            self._providers[provider.id] = updated
            return updated

    async def delete(self, provider_id: str) -> bool:
        async with self._lock:
            if provider_id not in self._providers:
                return False
            del self._providers[provider_id]
            self._rate_buckets.pop(provider_id, None)
        log.info("Provider deleted: %s", provider_id)
        await self._publish(
            Topic.PROVIDER_FAILED,
            {
                "provider_id": provider_id,
                "reason": "deleted",
            },
        )
        return True

    async def list_providers(
        self,
        *,
        kind: str | None = None,
        enabled_only: bool = False,
        healthy_only: bool = False,
        capability: str | None = None,
    ) -> list[OmniRouteProvider]:
        async with self._lock:
            results: list[OmniRouteProvider] = list(self._providers.values())

        if kind is not None:
            results = [p for p in results if p.kind == kind]
        if enabled_only:
            results = [p for p in results if p.enabled]
        if healthy_only:
            results = [p for p in results if p.healthy]
        if capability is not None:
            cap_lower = capability.lower()
            results = [p for p in results if any(c.lower() == cap_lower for c in p.capabilities)]
        return results

    async def count(self) -> int:
        async with self._lock:
            return len(self._providers)

    # ── Health ──

    async def set_health(self, provider_id: str, healthy: bool, error: str = "") -> bool:
        async with self._lock:
            provider = self._providers.get(provider_id)
            if provider is None:
                return False
            updated = OmniRouteProvider(
                id=provider.id,
                name=provider.name,
                kind=provider.kind,
                base_url=provider.base_url,
                api_key_ref=provider.api_key_ref,
                enabled=provider.enabled,
                capabilities=provider.capabilities,
                models=provider.models,
                latency_ms=provider.latency_ms,
                cost_per_1k_input=provider.cost_per_1k_input,
                cost_per_1k_output=provider.cost_per_1k_output,
                context_window=provider.context_window,
                supports_streaming=provider.supports_streaming,
                supports_reasoning=provider.supports_reasoning,
                supports_vision=provider.supports_vision,
                supports_tools=provider.supports_tools,
                status=ProviderDiscoveryStatus.CONNECTED
                if healthy
                else ProviderDiscoveryStatus.FAILED,
                priority=provider.priority,
                fallback_order=provider.fallback_order,
                rate_limit=provider.rate_limit,
                version=provider.version,
                healthy=healthy,
                last_health_check=datetime.now(UTC),
                error_message=error,
                metadata=dict(provider.metadata),
            )
            self._providers[provider_id] = updated

        topic = Topic.PROVIDER_HEALTH if healthy else Topic.PROVIDER_FAILED
        await self._publish(
            topic,
            {
                "provider_id": provider_id,
                "name": provider.name,
                "healthy": healthy,
                "error": error,
            },
        )
        return True

    async def is_healthy(self, provider_id: str) -> bool:
        async with self._lock:
            provider = self._providers.get(provider_id)
            return provider is not None and provider.healthy

    async def list_unhealthy(self) -> list[OmniRouteProvider]:
        async with self._lock:
            return [p for p in self._providers.values() if not p.healthy]

    # ── Capabilities ──

    async def providers_for_capability(self, capability: str) -> list[OmniRouteProvider]:
        async with self._lock:
            cap_lower = capability.lower()
            return [
                p
                for p in self._providers.values()
                if p.enabled and any(c.lower() == cap_lower for c in p.capabilities)
            ]

    async def set_capabilities(self, provider_id: str, capabilities: list[str]) -> bool:
        async with self._lock:
            provider = self._providers.get(provider_id)
            if provider is None:
                return False
            updated = OmniRouteProvider(
                id=provider.id,
                name=provider.name,
                kind=provider.kind,
                base_url=provider.base_url,
                api_key_ref=provider.api_key_ref,
                enabled=provider.enabled,
                capabilities=tuple(capabilities),
                models=provider.models,
                latency_ms=provider.latency_ms,
                cost_per_1k_input=provider.cost_per_1k_input,
                cost_per_1k_output=provider.cost_per_1k_output,
                context_window=provider.context_window,
                supports_streaming=provider.supports_streaming,
                supports_reasoning=provider.supports_reasoning,
                supports_vision=provider.supports_vision,
                supports_tools=provider.supports_tools,
                status=provider.status,
                priority=provider.priority,
                fallback_order=provider.fallback_order,
                rate_limit=provider.rate_limit,
                version=provider.version,
                healthy=provider.healthy,
                last_health_check=provider.last_health_check,
                error_message=provider.error_message,
                metadata=dict(provider.metadata),
            )
            self._providers[provider_id] = updated
            return True

    # ── Cost & Rate Limits ──

    async def set_cost_metadata(
        self,
        provider_id: str,
        *,
        cost_per_1k_input: float | None = None,
        cost_per_1k_output: float | None = None,
    ) -> bool:
        async with self._lock:
            provider = self._providers.get(provider_id)
            if provider is None:
                return False
            updated = OmniRouteProvider(
                id=provider.id,
                name=provider.name,
                kind=provider.kind,
                base_url=provider.base_url,
                api_key_ref=provider.api_key_ref,
                enabled=provider.enabled,
                capabilities=provider.capabilities,
                models=provider.models,
                latency_ms=provider.latency_ms,
                cost_per_1k_input=cost_per_1k_input
                if cost_per_1k_input is not None
                else provider.cost_per_1k_input,
                cost_per_1k_output=cost_per_1k_output
                if cost_per_1k_output is not None
                else provider.cost_per_1k_output,
                context_window=provider.context_window,
                supports_streaming=provider.supports_streaming,
                supports_reasoning=provider.supports_reasoning,
                supports_vision=provider.supports_vision,
                supports_tools=provider.supports_tools,
                status=provider.status,
                priority=provider.priority,
                fallback_order=provider.fallback_order,
                rate_limit=provider.rate_limit,
                version=provider.version,
                healthy=provider.healthy,
                last_health_check=provider.last_health_check,
                error_message=provider.error_message,
                metadata=dict(provider.metadata),
            )
            self._providers[provider_id] = updated
            return True

    async def set_rate_limit(self, provider_id: str, rate_limit: int) -> bool:
        async with self._lock:
            provider = self._providers.get(provider_id)
            if provider is None:
                return False
            updated = OmniRouteProvider(
                id=provider.id,
                name=provider.name,
                kind=provider.kind,
                base_url=provider.base_url,
                api_key_ref=provider.api_key_ref,
                enabled=provider.enabled,
                capabilities=provider.capabilities,
                models=provider.models,
                latency_ms=provider.latency_ms,
                cost_per_1k_input=provider.cost_per_1k_input,
                cost_per_1k_output=provider.cost_per_1k_output,
                context_window=provider.context_window,
                supports_streaming=provider.supports_streaming,
                supports_reasoning=provider.supports_reasoning,
                supports_vision=provider.supports_vision,
                supports_tools=provider.supports_tools,
                status=provider.status,
                priority=provider.priority,
                fallback_order=provider.fallback_order,
                rate_limit=rate_limit,
                version=provider.version,
                healthy=provider.healthy,
                last_health_check=provider.last_health_check,
                error_message=provider.error_message,
                metadata=dict(provider.metadata),
            )
            self._providers[provider_id] = updated
            self._rate_buckets[provider_id] = _RateBucket(limit=rate_limit)
            return True

    async def consume_rate(self, provider_id: str, weight: int = 1) -> bool:
        async with self._lock:
            bucket = self._rate_buckets.get(provider_id)
            if bucket is None:
                return True  # No rate limit configured
            return bucket.consume(weight)

    async def rate_limit_remaining(self, provider_id: str) -> int:
        async with self._lock:
            bucket = self._rate_buckets.get(provider_id)
            if bucket is None:
                return -1  # No limit
            return bucket.remaining

    # ── Discovery sync helper ──

    async def sync_from_discovery(
        self,
        discovered: list[dict[str, Any]],
    ) -> tuple[int, int]:
        """Upsert providers discovered by Runtime Discovery.

        Args:
            discovered: List of provider dicts from Runtime Discovery.

        Returns:
            (registered_count, updated_count)
        """
        registered = 0
        updated = 0
        for entry in discovered:
            name = entry.get("name", "")
            existing = await self.get_by_name(name)
            if existing is None:
                provider = OmniRouteProvider(
                    name=name,
                    kind=entry.get("kind", "unknown"),
                    base_url=entry.get("base_url", ""),
                    api_key_ref=entry.get("api_key_ref", ""),
                    capabilities=tuple(entry.get("capabilities", [])),
                    models=tuple(entry.get("models", [])),
                    enabled=entry.get("enabled", True),
                    rate_limit=entry.get("rate_limit", 0),
                    version=entry.get("version", ""),
                    supports_streaming=entry.get("supports_streaming", False),
                    supports_reasoning=entry.get("supports_reasoning", False),
                    supports_vision=entry.get("supports_vision", False),
                    supports_tools=entry.get("supports_tools", False),
                )
                await self.register(provider)
                registered += 1
            else:
                # Update existing
                updated_provider = OmniRouteProvider(
                    id=existing.id,
                    name=name,
                    kind=entry.get("kind", existing.kind),
                    base_url=entry.get("base_url", existing.base_url),
                    api_key_ref=entry.get("api_key_ref", existing.api_key_ref),
                    enabled=entry.get("enabled", existing.enabled),
                    capabilities=tuple(entry.get("capabilities", existing.capabilities)),
                    models=tuple(entry.get("models", existing.models)),
                    latency_ms=entry.get("latency_ms", existing.latency_ms),
                    cost_per_1k_input=entry.get("cost_per_1k_input", existing.cost_per_1k_input),
                    cost_per_1k_output=entry.get("cost_per_1k_output", existing.cost_per_1k_output),
                    context_window=entry.get("context_window", existing.context_window),
                    supports_streaming=entry.get("supports_streaming", existing.supports_streaming),
                    supports_reasoning=entry.get("supports_reasoning", existing.supports_reasoning),
                    supports_vision=entry.get("supports_vision", existing.supports_vision),
                    supports_tools=entry.get("supports_tools", existing.supports_tools),
                    status=existing.status,
                    priority=entry.get("priority", existing.priority),
                    fallback_order=entry.get("fallback_order", existing.fallback_order),
                    rate_limit=entry.get("rate_limit", existing.rate_limit),
                    version=entry.get("version", existing.version),
                    healthy=existing.healthy,
                    last_health_check=existing.last_health_check,
                    error_message=existing.error_message,
                    metadata=dict(existing.metadata),
                )
                await self.update(updated_provider)
                updated += 1
        return registered, updated

    # ── Internal helpers ──

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            envelope = EventEnvelope(
                type=topic.value,
                source="omniroute.provider_registry",
                topic=topic.value,
                payload=payload,
            )
            await self._event_bus.publish(envelope)
        except Exception:
            log.warning("Failed to publish event %s", topic.value, exc_info=True)


__all__ = [
    "ProviderRegistryPort",
    "ProviderRegistryImpl",
]
