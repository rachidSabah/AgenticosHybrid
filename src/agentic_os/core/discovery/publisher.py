"""Discovery event publisher — emits discovery lifecycle events through EventBus."""

from dataclasses import dataclass

from agentic_os.domain.discovery import (
    DiscoveryTelemetryEntry,
    ProfileResult,
    ValidationResult,
)
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("discovery.publisher")


@dataclass
class DiscoveryEventPublisher:
    """Publishes discovery lifecycle events through the injected EventBus.

    Each method emits an indexed envelope with structured payload so consumers
    (Mission Control, telemetry, hot-reload handlers) can react to discovery
    state changes.
    """

    bus: EventBus

    async def scan_started(self, profile_name: str) -> None:
        """Emitted when a discovery scan begins."""
        await self._publish(
            Topic.DISCOVERY_SCAN_STARTED,
            {"profile_name": profile_name, "status": "started"},
        )

    async def scan_completed(self, entry: DiscoveryTelemetryEntry) -> None:
        """Emitted when a discovery scan completes."""
        await self._publish(
            Topic.DISCOVERY_SCAN_COMPLETED,
            {
                "scan_id": entry.id,
                "profile_name": entry.profile_name,
                "engines_found": entry.engines_found,
                "engines_registered": entry.engines_registered,
                "providers_run": entry.providers_run,
                "providers_failed": entry.providers_failed,
                "duration_ms": entry.duration_ms,
            },
        )

    async def provider_running(self, provider_name: str, provider_type: str) -> None:
        """Emitted when a discovery provider starts scanning."""
        await self._publish(
            Topic.DISCOVERY_PROVIDER_RUNNING,
            {"provider_name": provider_name, "provider_type": provider_type},
        )

    async def provider_failed(self, provider_name: str, error: str) -> None:
        """Emitted when a discovery provider fails."""
        await self._publish(
            Topic.DISCOVERY_PROVIDER_FAILED,
            {"provider_name": provider_name, "error": error},
        )

    async def engine_discovered(
        self,
        engine_name: str,
        provider_name: str,
        confidence: float,
    ) -> None:
        """Emitted when a new engine is found by a provider."""
        await self._publish(
            Topic.DISCOVERY_ENGINE_FOUND,
            {
                "engine_name": engine_name,
                "provider_name": provider_name,
                "confidence": confidence,
            },
        )

    async def engine_lost(self, engine_name: str, engine_id: str | None = None) -> None:
        """Emitted when an engine is no longer discoverable."""
        await self._publish(
            Topic.DISCOVERY_ENGINE_LOST,
            {"engine_name": engine_name, "engine_id": engine_id or ""},
        )

    async def cache_hit(self, provider_name: str, engine_name: str) -> None:
        """Emitted when a discovery result is served from cache."""
        await self._publish(
            Topic.DISCOVERY_CACHE_HIT,
            {"provider_name": provider_name, "engine_name": engine_name},
        )

    async def cache_miss(self, provider_name: str, engine_name: str) -> None:
        """Emitted when a discovery result is not in cache."""
        await self._publish(
            Topic.DISCOVERY_CACHE_MISS,
            {"provider_name": provider_name, "engine_name": engine_name},
        )

    async def profile_activated(self, profile_name: str) -> None:
        """Emitted when a discovery profile is activated."""
        await self._publish(
            Topic.DISCOVERY_PROFILE_ACTIVATED,
            {"profile_name": profile_name},
        )

    async def profile_deactivated(self, profile_name: str) -> None:
        """Emitted when a discovery profile is deactivated."""
        await self._publish(
            Topic.DISCOVERY_PROFILE_DEACTIVATED,
            {"profile_name": profile_name},
        )

    async def validation_started(self, engine_name: str) -> None:
        """Emitted when validation of a discovered engine begins."""
        await self._publish(
            Topic.VALIDATION_STARTED,
            {"engine_name": engine_name},
        )

    async def validation_passed(self, result: ValidationResult) -> None:
        """Emitted when validation passes for an engine."""
        await self._publish(
            Topic.VALIDATION_PASSED,
            {
                "engine_id": result.engine_id,
                "engine_name": result.engine_name,
                "version_detected": result.version_detected,
            },
        )

    async def validation_failed(self, result: ValidationResult) -> None:
        """Emitted when validation fails for an engine."""
        await self._publish(
            Topic.VALIDATION_FAILED,
            {
                "engine_id": result.engine_id,
                "engine_name": result.engine_name,
                "errors": list(result.errors),
            },
        )

    async def validation_skipped(self, engine_name: str, reason: str) -> None:
        """Emitted when validation is skipped for an engine."""
        await self._publish(
            Topic.VALIDATION_SKIPPED,
            {"engine_name": engine_name, "reason": reason},
        )

    async def profiling_started(self, engine_name: str) -> None:
        """Emitted when profiling of an engine begins."""
        await self._publish(
            Topic.PROFILING_STARTED,
            {"engine_name": engine_name},
        )

    async def profiling_completed(self, result: ProfileResult) -> None:
        """Emitted when profiling completes for an engine."""
        await self._publish(
            Topic.PROFILING_COMPLETED,
            {
                "engine_id": result.engine_id,
                "engine_name": result.engine_name,
                "capabilities": list(result.capabilities),
                "latency_estimate_ms": result.latency_estimate_ms,
            },
        )

    async def engine_registered(self, engine_id: str, engine_name: str) -> None:
        """Emitted when an engine is registered with the runtime manager."""
        await self._publish(
            Topic.ENGINE_REGISTERED,
            {"engine_id": engine_id, "engine_name": engine_name},
        )

    async def engine_rejected(self, engine_name: str, reason: str) -> None:
        """Emitted when an engine is rejected during validation."""
        await self._publish(
            Topic.DISCOVERY_ENGINE_REJECTED,
            {"engine_name": engine_name, "reason": reason},
        )

    async def _publish(self, topic: Topic, payload: dict) -> None:
        """Low-level publish helper with error handling."""
        try:
            await self.bus.publish(
                EventEnvelope(
                    type="event",
                    source="discovery-publisher",
                    topic=topic.value,
                    payload=payload,
                )
            )
        except Exception as exc:
            log.warning("Failed to publish discovery event", topic=topic.value, error=str(exc))
