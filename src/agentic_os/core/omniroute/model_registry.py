"""OmniRoute Model Registry — production implementation.

Stores and manages model definitions (capabilities, cost, quality, health).
Integrates with ProviderRegistry to enforce referential integrity, publishes
lifecycle events on the EventBus, and powers search/filter for the RouterEngine.

Port protocol
-------------
:class:`ModelRegistryPort` — implemented here. Consumers depend on this
protocol, never on the concrete class directly.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.omniroute import OmniRouteModel
from agentic_os.infrastructure.logging import get_logger

log = get_logger("omniroute.model_registry")


# ── Port Protocol ──


@runtime_checkable
class ModelRegistryPort(Protocol):
    """OmniRoute model registry — single source of truth for models."""

    async def register_model(self, model: OmniRouteModel) -> str:
        """Register a model. Returns the model id. Validates provider exists."""
        ...

    async def unregister_model(self, model_id: str) -> bool:
        """Unregister a model by id. Returns True if removed."""
        ...

    async def update_model(self, model: OmniRouteModel) -> OmniRouteModel | None:
        """Update an existing model. Returns updated model or None."""
        ...

    async def get_model(self, model_id: str) -> OmniRouteModel | None:
        """Get a model by id."""
        ...

    async def get_model_by_name(self, name: str) -> OmniRouteModel | None:
        """Get a model by its display name (first match)."""
        ...

    async def list_models(
        self,
        *,
        provider: str | None = None,
        family: str | None = None,
        capability: str | None = None,
        enabled_only: bool = False,
        healthy_only: bool = False,
    ) -> list[OmniRouteModel]:
        """List models with optional filters."""
        ...

    async def list_by_provider(self, provider_id: str) -> list[OmniRouteModel]:
        """List all models belonging to a provider."""
        ...

    async def list_by_capability(self, capability: str) -> list[OmniRouteModel]:
        """List models that support a given capability."""
        ...

    async def search(
        self,
        *,
        provider: str | None = None,
        family: str | None = None,
        capability: str | None = None,
        min_context: int | None = None,
        max_cost_input: float | None = None,
        max_cost_output: float | None = None,
        max_latency_ms: float | None = None,
        min_quality: float | None = None,
        enabled_only: bool = True,
        healthy_only: bool = False,
        supports_streaming: bool | None = None,
        supports_reasoning: bool | None = None,
        supports_vision: bool | None = None,
        supports_tools: bool | None = None,
        tag: str | None = None,
        modality: str | None = None,
        limit: int = 50,
    ) -> list[OmniRouteModel]:
        """Compound search with multiple filters."""
        ...

    async def best_models(
        self,
        capability: str,
        *,
        min_quality: float = 0.0,
        max_cost: float | None = None,
        max_latency: float | None = None,
        top_k: int = 5,
    ) -> list[OmniRouteModel]:
        """Return the highest-quality models for a capability within constraints."""
        ...

    async def compatible_models(
        self,
        *,
        features: set[str] | None = None,
        min_context: int = 0,
    ) -> list[OmniRouteModel]:
        """Return models compatible with a set of required features."""
        ...

    async def default_model(self, provider_id: str) -> OmniRouteModel | None:
        """Get the default model for a provider."""
        ...

    async def set_default(self, model_id: str) -> bool:
        """Set a model as the default for its provider. Returns True on success."""
        ...

    async def count(self) -> int:
        """Total number of registered models."""
        ...

    # ── Health & Lifecycle ──

    async def set_model_health(self, model_id: str, healthy: bool, error: str = "") -> bool:
        """Update health status for a model."""
        ...

    async def start(self) -> None:
        """Start the model registry."""
        ...

    async def stop(self) -> None:
        """Stop the model registry and release resources."""
        ...

    async def health_check(self) -> dict[str, Any]:
        """Health status of the registry itself."""
        ...

    async def ready(self) -> bool:
        """True if the registry is started and operational."""
        ...

    async def metadata(self) -> dict[str, Any]:
        """Service metadata for the LifecycleManager."""
        ...

    async def dependencies(self) -> list[str]:
        """Dependency names for the LifecycleManager."""
        ...

    async def capabilities(self) -> list[dict[str, Any]]:
        """Capability list for the ServiceRegistry."""
        ...

    # ── Discovery Sync ──

    async def sync_from_discovery(
        self,
        discovered: list[dict[str, Any]],
    ) -> tuple[int, int]:
        """Upsert models from Runtime Discovery. Returns (registered, updated)."""
        ...


# ── Model Query Result ──


@dataclass
class _ModelSearchResult:
    """Internal search result with scoring."""

    model: OmniRouteModel
    score: float = 0.0


# ── Concrete Implementation ──


class ModelRegistryImpl:
    """In-memory model registry with EventBus integration.

    Thread-safe via asyncio.Lock. Validates provider existence before
    registration. Publishes lifecycle events on model CRUD operations.
    """

    def __init__(
        self,
        provider_registry: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        from agentic_os.core.omniroute.provider_registry import ProviderRegistryPort

        self._provider_registry: ProviderRegistryPort | None = provider_registry
        self._event_bus = event_bus
        self._lock = asyncio.Lock()
        self._models: dict[str, OmniRouteModel] = {}
        self._defaults: dict[str, str] = {}  # provider_id -> model_id
        self._started = False
        self._start_time: float = 0.0

        # Observability counters
        self._registration_count = 0
        self._search_count = 0
        self._sync_count = 0
        self._search_duration_total = 0.0
        self._registration_duration_total = 0.0
        self._sync_duration_total = 0.0

    # ── Lifecycle ──

    async def start(self) -> None:
        self._started = True
        self._start_time = time.monotonic()
        log.info("ModelRegistry started")

    async def stop(self) -> None:
        self._started = False
        self._models.clear()
        self._defaults.clear()
        log.info("ModelRegistry stopped")

    async def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self._started else "stopped",
            "started": self._started,
            "model_count": len(self._models),
            "uptime_seconds": time.monotonic() - self._start_time if self._started else 0.0,
        }

    async def ready(self) -> bool:
        return self._started

    async def metadata(self) -> dict[str, Any]:
        return {
            "type": "ModelRegistryImpl",
            "version": "1.0.0",
            "started": self._started,
            "model_count": len(self._models),
            "provider_registry": self._provider_registry is not None,
        }

    async def dependencies(self) -> list[str]:
        return ["provider_registry"]

    async def capabilities(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "model_registry",
                "description": "Model registry (CRUD, search, discovery sync)",
            },
            {
                "name": "model_search",
                "description": "Compound model search with capability/quality/cost filters",
            },
            {"name": "sync_from_discovery", "description": "Import models from Runtime Discovery"},
        ]

    # ── Observability helpers ──

    def _metrics(self) -> dict[str, Any]:
        return {
            "registered_models": len(self._models),
            "healthy_models": sum(1 for m in self._models.values() if m.healthy),
            "disabled_models": sum(1 for m in self._models.values() if not m.enabled),
            "registration_count": self._registration_count,
            "search_count": self._search_count,
            "sync_count": self._sync_count,
            "avg_search_latency_ms": (
                (self._search_duration_total / self._search_count * 1000)
                if self._search_count > 0
                else 0.0
            ),
            "avg_registration_latency_ms": (
                (self._registration_duration_total / self._registration_count * 1000)
                if self._registration_count > 0
                else 0.0
            ),
            "avg_sync_latency_ms": (
                (self._sync_duration_total / self._sync_count * 1000)
                if self._sync_count > 0
                else 0.0
            ),
        }

    # ── Provider Validation ──

    async def _validate_provider(self, provider_id: str) -> str | None:
        """Validate that a provider exists, is enabled, and is healthy.

        Returns the provider name on success, or None (with logged warning) on failure.
        """
        if self._provider_registry is None:
            return None  # No validation available

        provider = await self._provider_registry.get(provider_id)
        if provider is None:
            log.warning("Provider %s not found — cannot register model", provider_id)
            return None
        if not provider.enabled:
            log.warning("Provider %s is disabled — cannot register model", provider_id)
            return None
        return provider.name

    # ── CRUD ──

    async def register_model(self, model: OmniRouteModel) -> str:
        start = time.monotonic()
        async with self._lock:
            model_id = model.id or uuid4().hex[:12]

            if model_id in self._models:
                log.warning("Model %s already registered, skipping", model_id)
                return model_id

            # Validate provider if provider_registry is available
            provider_name = None
            if model.provider_id and self._provider_registry is not None:
                provider_name = await self._validate_provider(model.provider_id)
                if provider_name is None:
                    raise ValueError(
                        f"Cannot register model '{model.model_id}': "
                        f"provider '{model.provider_id}' not found, disabled, or unhealthy"
                    )
            elif model.provider_id:
                # No provider registry — allow registration but log warning
                log.warning(
                    "Registering model '%s' without provider validation (no ProviderRegistry)",
                    model.model_id,
                )

            stored = OmniRouteModel(
                id=model_id,
                model_id=model.model_id,
                provider=provider_name or model.provider,
                provider_id=model.provider_id,
                display_name=model.display_name or model.model_id,
                model_family=model.model_family,
                context_window=model.context_window,
                max_output_tokens=model.max_output_tokens,
                input_cost_per_1k=model.input_cost_per_1k,
                output_cost_per_1k=model.output_cost_per_1k,
                capabilities=model.capabilities,
                supports_streaming=model.supports_streaming,
                supports_reasoning=model.supports_reasoning,
                supports_vision=model.supports_vision,
                supports_tools=model.supports_tools,
                is_default=False,
                latency_ms=model.latency_ms,
                quality_score=model.quality_score,
                throughput=model.throughput,
                tokenizer=model.tokenizer,
                healthy=model.healthy,
                enabled=model.enabled,
                tags=model.tags,
                version=model.version,
                aliases=model.aliases,
                input_modalities=model.input_modalities,
                output_modalities=model.output_modalities,
                metadata=dict(model.metadata) if model.metadata else {},
            )
            self._models[model_id] = stored
            self._registration_count += 1

        duration = time.monotonic() - start
        self._registration_duration_total += duration

        await self._publish(
            Topic.MODEL_REGISTERED,
            {
                "model_id": model_id,
                "model_name": stored.model_id,
                "provider_id": stored.provider_id,
                "provider": stored.provider,
            },
        )
        log.info("Model registered: %s/%s (%s)", stored.provider, stored.model_id, model_id)
        return model_id

    async def unregister_model(self, model_id: str) -> bool:
        async with self._lock:
            model = self._models.pop(model_id, None)
            if model is None:
                return False
            # Clear default if this was the default for its provider
            if self._defaults.get(model.provider_id) == model_id:
                self._defaults.pop(model.provider_id, None)

        await self._publish(
            Topic.MODEL_REMOVED,
            {
                "model_id": model_id,
                "model_name": model.model_id if model else "",
                "provider_id": model.provider_id if model else "",
            },
        )
        log.info("Model unregistered: %s", model_id)
        return True

    async def update_model(self, model: OmniRouteModel) -> OmniRouteModel | None:
        async with self._lock:
            existing = self._models.get(model.id)
            if existing is None:
                return None

            updated = OmniRouteModel(
                id=model.id,
                model_id=model.model_id or existing.model_id,
                provider=model.provider or existing.provider,
                provider_id=model.provider_id or existing.provider_id,
                display_name=model.display_name or existing.display_name,
                model_family=model.model_family or existing.model_family,
                context_window=model.context_window or existing.context_window,
                max_output_tokens=model.max_output_tokens or existing.max_output_tokens,
                input_cost_per_1k=model.input_cost_per_1k
                if model.input_cost_per_1k != 0.0
                else existing.input_cost_per_1k,
                output_cost_per_1k=model.output_cost_per_1k
                if model.output_cost_per_1k != 0.0
                else existing.output_cost_per_1k,
                capabilities=model.capabilities or existing.capabilities,
                supports_streaming=model.supports_streaming,
                supports_reasoning=model.supports_reasoning,
                supports_vision=model.supports_vision,
                supports_tools=model.supports_tools,
                is_default=model.is_default,
                latency_ms=model.latency_ms or existing.latency_ms,
                quality_score=model.quality_score
                if model.quality_score != 0.5
                else existing.quality_score,
                throughput=model.throughput or existing.throughput,
                tokenizer=model.tokenizer or existing.tokenizer,
                healthy=model.healthy,
                enabled=model.enabled,
                tags=model.tags or existing.tags,
                version=model.version or existing.version,
                aliases=model.aliases or existing.aliases,
                input_modalities=model.input_modalities or existing.input_modalities,
                output_modalities=model.output_modalities or existing.output_modalities,
                metadata=dict(model.metadata) if model.metadata else dict(existing.metadata),
            )
            self._models[model.id] = updated

        await self._publish(
            Topic.MODEL_UPDATED,
            {
                "model_id": model.id,
                "model_name": updated.model_id,
                "provider_id": updated.provider_id,
            },
        )
        return updated

    async def get_model(self, model_id: str) -> OmniRouteModel | None:
        async with self._lock:
            return self._models.get(model_id)

    async def get_model_by_name(self, name: str) -> OmniRouteModel | None:
        async with self._lock:
            for m in self._models.values():
                if m.display_name == name or m.model_id == name:
                    return m
                if name in m.aliases:
                    return m
            return None

    async def list_models(
        self,
        *,
        provider: str | None = None,
        family: str | None = None,
        capability: str | None = None,
        enabled_only: bool = False,
        healthy_only: bool = False,
    ) -> list[OmniRouteModel]:
        async with self._lock:
            results: list[OmniRouteModel] = list(self._models.values())

        if provider is not None:
            results = [m for m in results if m.provider_id == provider or m.provider == provider]
        if family is not None:
            results = [m for m in results if m.model_family == family]
        if capability is not None:
            cap_lower = capability.lower()
            results = [m for m in results if any(c.lower() == cap_lower for c in m.capabilities)]
        if enabled_only:
            results = [m for m in results if m.enabled]
        if healthy_only:
            results = [m for m in results if m.healthy]
        return results

    async def list_by_provider(self, provider_id: str) -> list[OmniRouteModel]:
        return await self.list_models(provider=provider_id)

    async def list_by_capability(self, capability: str) -> list[OmniRouteModel]:
        return await self.list_models(capability=capability)

    async def search(
        self,
        *,
        provider: str | None = None,
        family: str | None = None,
        capability: str | None = None,
        min_context: int | None = None,
        max_cost_input: float | None = None,
        max_cost_output: float | None = None,
        max_latency_ms: float | None = None,
        min_quality: float | None = None,
        enabled_only: bool = True,
        healthy_only: bool = False,
        supports_streaming: bool | None = None,
        supports_reasoning: bool | None = None,
        supports_vision: bool | None = None,
        supports_tools: bool | None = None,
        tag: str | None = None,
        modality: str | None = None,
        limit: int = 50,
    ) -> list[OmniRouteModel]:
        start = time.monotonic()
        self._search_count += 1

        # Start with all models, apply filters sequentially
        async with self._lock:
            results: list[OmniRouteModel] = list(self._models.values())

        if provider is not None:
            results = [m for m in results if m.provider_id == provider or m.provider == provider]
        if family is not None:
            results = [m for m in results if m.model_family == family]
        if capability is not None:
            cap_lower = capability.lower()
            results = [m for m in results if any(c.lower() == cap_lower for c in m.capabilities)]
        if min_context is not None:
            results = [m for m in results if m.context_window >= min_context]
        if max_cost_input is not None:
            results = [
                m
                for m in results
                if m.input_cost_per_1k <= max_cost_input or m.input_cost_per_1k == 0.0
            ]
        if max_cost_output is not None:
            results = [
                m
                for m in results
                if m.output_cost_per_1k <= max_cost_output or m.output_cost_per_1k == 0.0
            ]
        if max_latency_ms is not None:
            results = [m for m in results if m.latency_ms <= max_latency_ms or m.latency_ms == 0.0]
        if min_quality is not None:
            results = [m for m in results if m.quality_score >= min_quality]
        if enabled_only:
            results = [m for m in results if m.enabled]
        if healthy_only:
            results = [m for m in results if m.healthy]
        if supports_streaming is not None:
            results = [m for m in results if m.supports_streaming == supports_streaming]
        if supports_reasoning is not None:
            results = [m for m in results if m.supports_reasoning == supports_reasoning]
        if supports_vision is not None:
            results = [m for m in results if m.supports_vision == supports_vision]
        if supports_tools is not None:
            results = [m for m in results if m.supports_tools == supports_tools]
        if tag is not None:
            results = [m for m in results if tag in m.tags]
        if modality is not None:
            mod_lower = modality.lower()
            results = [
                m
                for m in results
                if mod_lower in [x.lower() for x in m.input_modalities]
                or mod_lower in [x.lower() for x in m.output_modalities]
            ]

        # Sort by quality_score descending, then latency ascending
        results.sort(key=lambda m: (-m.quality_score, m.latency_ms))
        results = results[:limit]

        duration = time.monotonic() - start
        self._search_duration_total += duration
        return results

    async def best_models(
        self,
        capability: str,
        *,
        min_quality: float = 0.0,
        max_cost: float | None = None,
        max_latency: float | None = None,
        top_k: int = 5,
    ) -> list[OmniRouteModel]:
        return await self.search(
            capability=capability,
            min_quality=min_quality,
            max_cost_input=max_cost,
            max_cost_output=max_cost,
            max_latency_ms=max_latency,
            enabled_only=True,
            healthy_only=True,
            limit=top_k,
        )

    async def compatible_models(
        self,
        *,
        features: set[str] | None = None,
        min_context: int = 0,
    ) -> list[OmniRouteModel]:
        """Return models compatible with a set of required features.

        Feature flags map to model capabilities:
          'streaming' -> supports_streaming
          'reasoning' -> supports_reasoning
          'vision'    -> supports_vision
          'tools'     -> supports_tools
        """
        features = features or set()
        results: list[OmniRouteModel]

        async with self._lock:
            results = list(self._models.values())

        results = [m for m in results if m.enabled]
        if min_context > 0:
            results = [m for m in results if m.context_window >= min_context]

        feat_lower = {f.lower() for f in features}
        if "streaming" in feat_lower:
            results = [m for m in results if m.supports_streaming]
        if "reasoning" in feat_lower:
            results = [m for m in results if m.supports_reasoning]
        if "vision" in feat_lower:
            results = [m for m in results if m.supports_vision]
        if "tools" in feat_lower:
            results = [m for m in results if m.supports_tools]

        results.sort(key=lambda m: (-m.quality_score, m.context_window))
        return results

    async def default_model(self, provider_id: str) -> OmniRouteModel | None:
        async with self._lock:
            model_id = self._defaults.get(provider_id)
            if model_id is None:
                # Fall back to first model marked is_default for this provider
                for m in self._models.values():
                    if m.provider_id == provider_id and m.is_default:
                        return m
                return None
            return self._models.get(model_id)

    async def set_default(self, model_id: str) -> bool:
        async with self._lock:
            model = self._models.get(model_id)
            if model is None:
                return False

            provider_id = model.provider_id
            old_default_id = self._defaults.get(provider_id)

            # Clear old default's is_default flag
            if old_default_id and old_default_id != model_id:
                old = self._models.get(old_default_id)
                if old:
                    self._models[old_default_id] = OmniRouteModel(
                        id=old.id,
                        model_id=old.model_id,
                        provider=old.provider,
                        provider_id=old.provider_id,
                        display_name=old.display_name,
                        model_family=old.model_family,
                        context_window=old.context_window,
                        max_output_tokens=old.max_output_tokens,
                        input_cost_per_1k=old.input_cost_per_1k,
                        output_cost_per_1k=old.output_cost_per_1k,
                        capabilities=old.capabilities,
                        supports_streaming=old.supports_streaming,
                        supports_reasoning=old.supports_reasoning,
                        supports_vision=old.supports_vision,
                        supports_tools=old.supports_tools,
                        is_default=False,
                        latency_ms=old.latency_ms,
                        quality_score=old.quality_score,
                        throughput=old.throughput,
                        tokenizer=old.tokenizer,
                        healthy=old.healthy,
                        enabled=old.enabled,
                        tags=old.tags,
                        version=old.version,
                        aliases=old.aliases,
                        input_modalities=old.input_modalities,
                        output_modalities=old.output_modalities,
                        metadata=dict(old.metadata),
                    )

            # Set new default
            self._models[model_id] = OmniRouteModel(
                id=model.id,
                model_id=model.model_id,
                provider=model.provider,
                provider_id=model.provider_id,
                display_name=model.display_name,
                model_family=model.model_family,
                context_window=model.context_window,
                max_output_tokens=model.max_output_tokens,
                input_cost_per_1k=model.input_cost_per_1k,
                output_cost_per_1k=model.output_cost_per_1k,
                capabilities=model.capabilities,
                supports_streaming=model.supports_streaming,
                supports_reasoning=model.supports_reasoning,
                supports_vision=model.supports_vision,
                supports_tools=model.supports_tools,
                is_default=True,
                latency_ms=model.latency_ms,
                quality_score=model.quality_score,
                throughput=model.throughput,
                tokenizer=model.tokenizer,
                healthy=model.healthy,
                enabled=model.enabled,
                tags=model.tags,
                version=model.version,
                aliases=model.aliases,
                input_modalities=model.input_modalities,
                output_modalities=model.output_modalities,
                metadata=dict(model.metadata),
            )
            self._defaults[provider_id] = model_id

        await self._publish(
            Topic.MODEL_DEFAULT_CHANGED,
            {
                "model_id": model_id,
                "model_name": model.model_id,
                "provider_id": provider_id,
            },
        )
        return True

    async def count(self) -> int:
        async with self._lock:
            return len(self._models)

    # ── Health ──

    async def set_model_health(self, model_id: str, healthy: bool, error: str = "") -> bool:
        async with self._lock:
            model = self._models.get(model_id)
            if model is None:
                return False
            updated = OmniRouteModel(
                id=model.id,
                model_id=model.model_id,
                provider=model.provider,
                provider_id=model.provider_id,
                display_name=model.display_name,
                model_family=model.model_family,
                context_window=model.context_window,
                max_output_tokens=model.max_output_tokens,
                input_cost_per_1k=model.input_cost_per_1k,
                output_cost_per_1k=model.output_cost_per_1k,
                capabilities=model.capabilities,
                supports_streaming=model.supports_streaming,
                supports_reasoning=model.supports_reasoning,
                supports_vision=model.supports_vision,
                supports_tools=model.supports_tools,
                is_default=model.is_default,
                latency_ms=model.latency_ms,
                quality_score=model.quality_score,
                throughput=model.throughput,
                tokenizer=model.tokenizer,
                healthy=healthy,
                enabled=model.enabled,
                tags=model.tags,
                version=model.version,
                aliases=model.aliases,
                input_modalities=model.input_modalities,
                output_modalities=model.output_modalities,
                metadata=dict(model.metadata),
            )
            self._models[model_id] = updated

        await self._publish(
            Topic.MODEL_HEALTH,
            {
                "model_id": model_id,
                "model_name": model.model_id,
                "healthy": healthy,
                "error": error,
            },
        )
        return True

    # ── Discovery Sync ──

    async def sync_from_discovery(
        self,
        discovered: list[dict[str, Any]],
    ) -> tuple[int, int]:
        start = time.monotonic()
        self._sync_count += 1
        registered = 0
        updated = 0

        for entry in discovered:
            model_id_str = entry.get("model_id", "")
            provider_id = entry.get("provider_id", "")

            # Look for existing by model_id + provider_id unique combo
            existing: OmniRouteModel | None = None
            async with self._lock:
                for m in self._models.values():
                    if m.model_id == model_id_str and m.provider_id == provider_id:
                        existing = m
                        break

            if existing is None:
                model = OmniRouteModel(
                    model_id=model_id_str,
                    provider=entry.get("provider", ""),
                    provider_id=provider_id,
                    display_name=entry.get("display_name", model_id_str),
                    model_family=entry.get("model_family", ""),
                    context_window=entry.get("context_window", 0),
                    max_output_tokens=entry.get("max_output_tokens", 4096),
                    input_cost_per_1k=entry.get("input_cost_per_1k", 0.0),
                    output_cost_per_1k=entry.get("output_cost_per_1k", 0.0),
                    capabilities=tuple(entry.get("capabilities", [])),
                    supports_streaming=entry.get("supports_streaming", False),
                    supports_reasoning=entry.get("supports_reasoning", False),
                    supports_vision=entry.get("supports_vision", False),
                    supports_tools=entry.get("supports_tools", False),
                    latency_ms=entry.get("latency_ms", 0.0),
                    quality_score=entry.get("quality_score", 0.5),
                    throughput=entry.get("throughput", 0.0),
                    tokenizer=entry.get("tokenizer", ""),
                    healthy=entry.get("healthy", False),
                    enabled=entry.get("enabled", True),
                    tags=tuple(entry.get("tags", [])),
                    version=entry.get("version", ""),
                    aliases=tuple(entry.get("aliases", [])),
                    input_modalities=tuple(entry.get("input_modalities", [])),
                    output_modalities=tuple(entry.get("output_modalities", [])),
                )
                await self.register_model(model)
                registered += 1
            else:
                # Update existing
                updated_model = OmniRouteModel(
                    id=existing.id,
                    model_id=existing.model_id,
                    provider=entry.get("provider", existing.provider),
                    provider_id=existing.provider_id,
                    display_name=entry.get("display_name", existing.display_name),
                    model_family=entry.get("model_family", existing.model_family),
                    context_window=entry.get("context_window", existing.context_window),
                    max_output_tokens=entry.get("max_output_tokens", existing.max_output_tokens),
                    input_cost_per_1k=entry.get("input_cost_per_1k", existing.input_cost_per_1k),
                    output_cost_per_1k=entry.get("output_cost_per_1k", existing.output_cost_per_1k),
                    capabilities=tuple(entry.get("capabilities", existing.capabilities)),
                    supports_streaming=entry.get("supports_streaming", existing.supports_streaming),
                    supports_reasoning=entry.get("supports_reasoning", existing.supports_reasoning),
                    supports_vision=entry.get("supports_vision", existing.supports_vision),
                    supports_tools=entry.get("supports_tools", existing.supports_tools),
                    is_default=existing.is_default,
                    latency_ms=entry.get("latency_ms", existing.latency_ms),
                    quality_score=entry.get("quality_score", existing.quality_score),
                    throughput=entry.get("throughput", existing.throughput),
                    tokenizer=entry.get("tokenizer", existing.tokenizer),
                    healthy=entry.get("healthy", existing.healthy),
                    enabled=entry.get("enabled", existing.enabled),
                    tags=tuple(entry.get("tags", existing.tags)),
                    version=entry.get("version", existing.version),
                    aliases=tuple(entry.get("aliases", existing.aliases)),
                    input_modalities=tuple(
                        entry.get("input_modalities", existing.input_modalities)
                    ),
                    output_modalities=tuple(
                        entry.get("output_modalities", existing.output_modalities)
                    ),
                    metadata=dict(entry.get("metadata", existing.metadata)),
                )
                await self.update_model(updated_model)
                updated += 1

        duration = time.monotonic() - start
        self._sync_duration_total += duration
        log.info(
            "Discovery sync complete: %d registered, %d updated in %.0fms",
            registered,
            updated,
            duration * 1000,
        )
        return registered, updated

    # ── Internal helpers ──

    async def _publish(self, topic: Topic, payload: dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            envelope = EventEnvelope(
                type=topic.value,
                source="omniroute.model_registry",
                topic=topic.value,
                payload=payload,
            )
            await self._event_bus.publish(envelope)
        except Exception:
            log.warning("Failed to publish event %s", topic.value, exc_info=True)


__all__ = [
    "ModelRegistryPort",
    "ModelRegistryImpl",
]
