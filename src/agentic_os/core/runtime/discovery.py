"""
Discovery Engine

Orchestrates all discovery providers to find available execution engines.
Supports multiple discovery methods with deduplication and confidence scoring.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("runtime.discovery")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class DiscoveryResult:
    """Result from a single discovery provider."""

    registration: EngineRegistration
    provider_name: str
    provider_type: str
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.registration.name,
            "engine_type": self.registration.engine_type.value,
            "provider_name": self.provider_name,
            "provider_type": self.provider_type,
            "confidence": self.confidence,
            "endpoint": self.registration.endpoint,
        }


@dataclass
class DiscoveryEngine:
    """
    Orchestrates all discovery providers.

    Features:
    - Multiple provider support (PATH, WSL, Docker, config)
    - Deduplication (same engine from different providers)
    - Confidence scoring
    - Configurable enable/disable per provider
    - Optional continuous watching
    """

    _providers: dict[str, DiscoveryProvider] = field(default_factory=dict)

    def add_provider(self, provider: DiscoveryProvider) -> None:
        """Register a discovery provider."""
        name = provider.get_provider_name()
        self._providers[name] = provider
        log.info("Discovery provider added", name=name, type=provider.get_provider_type())

    def remove_provider(self, name: str) -> bool:
        """Remove a discovery provider by name."""
        if name in self._providers:
            del self._providers[name]
            return True
        return False

    def list_providers(self) -> list[dict[str, str]]:
        """List registered discovery providers."""
        return [
            {"name": name, "type": p.get_provider_type()} for name, p in self._providers.items()
        ]

    async def discover_all(self) -> list[DiscoveryResult]:
        """
        Run all discovery providers and return deduplicated results.

        Deduplication: if the same engine name appears from multiple providers,
        the result with the highest confidence wins. The provider with higher
        confidence supercedes the lower.
        """
        results: list[DiscoveryResult] = []

        for name, provider in self._providers.items():
            try:
                registrations = await provider.discover()
                for reg in registrations:
                    # Calculate confidence based on provider type priority
                    confidence = self._get_provider_confidence(provider.get_provider_type())
                    results.append(
                        DiscoveryResult(
                            registration=reg,
                            provider_name=name,
                            provider_type=provider.get_provider_type(),
                            confidence=confidence,
                        )
                    )
            except Exception as exc:
                log.warning("Discovery provider failed", provider=name, error=str(exc))

        # Deduplicate by engine name — keep highest confidence
        return self._deduplicate(results)

    async def discover_by_type(self, provider_type: str) -> list[DiscoveryResult]:
        """Run discovery providers matching a specific type."""
        results: list[DiscoveryResult] = []

        for name, provider in self._providers.items():
            if provider.get_provider_type() != provider_type:
                continue
            try:
                registrations = await provider.discover()
                for reg in registrations:
                    confidence = self._get_provider_confidence(provider_type)
                    results.append(
                        DiscoveryResult(
                            registration=reg,
                            provider_name=name,
                            provider_type=provider_type,
                            confidence=confidence,
                        )
                    )
            except Exception as exc:
                log.warning("Discovery provider failed", provider=name, error=str(exc))

        return self._deduplicate(results)

    async def watch(self, interval_seconds: float = 60.0) -> AsyncIterator[list[DiscoveryResult]]:
        """
        Continuously watch for engines with periodic discovery scans.

        Usage:
            async for results in discovery_engine.watch(30.0):
                for result in results:
                    print(f"Found: {result.registration.name}")
        """
        while True:
            results = await self.discover_all()
            yield results
            await asyncio.sleep(interval_seconds)

    def _deduplicate(self, results: list[DiscoveryResult]) -> list[DiscoveryResult]:
        """Deduplicate results by engine name, keeping highest confidence."""
        best: dict[str, DiscoveryResult] = {}

        for result in results:
            name = result.registration.name
            if name not in best or result.confidence > best[name].confidence:
                # Merge provider info if same name but different provider
                if name in best:
                    existing = best[name]
                    merged_metadata = {
                        **existing.registration.metadata,
                        **result.registration.metadata,
                        "providers": [
                            existing.provider_name,
                            result.provider_name,
                        ],
                    }
                    merged_reg = EngineRegistration(
                        name=existing.registration.name,
                        engine_type=existing.registration.engine_type,
                        endpoint=existing.registration.endpoint or result.registration.endpoint,
                        transport=existing.registration.transport,
                        capabilities=list(
                            set(
                                existing.registration.capabilities
                                + result.registration.capabilities
                            )
                        ),
                        description=existing.registration.description
                        or result.registration.description,
                        version=existing.registration.version,
                        metadata=merged_metadata,
                    )
                    best[name] = DiscoveryResult(
                        registration=merged_reg,
                        provider_name=existing.provider_name,
                        provider_type=existing.provider_type,
                        confidence=max(existing.confidence, result.confidence),
                    )
                else:
                    # Ensure metadata has providers list
                    reg = result.registration
                    meta = dict(reg.metadata)
                    meta.setdefault("providers", [result.provider_name])
                    merged_reg = EngineRegistration(
                        name=reg.name,
                        engine_type=reg.engine_type,
                        endpoint=reg.endpoint,
                        transport=reg.transport,
                        capabilities=list(reg.capabilities),
                        description=reg.description,
                        version=reg.version,
                        tags=list(reg.tags),
                        metadata=meta,
                    )
                    best[name] = DiscoveryResult(
                        registration=merged_reg,
                        provider_name=result.provider_name,
                        provider_type=result.provider_type,
                        confidence=result.confidence,
                    )

        return list(best.values())

    def _get_provider_confidence(self, provider_type: str) -> float:
        """Return the base confidence level for a provider type.

        Priority (higher = more trusted):
        - CONFIGURATION: 1.0 (explicitly configured)
        - PATH: 0.8 (found on system PATH)
        - REGISTRY: 0.7 (found in registry)
        - VSCODE/JETBRAINS: 0.6 (IDE integration)
        - WSL: 0.5 (found in WSL)
        - DOCKER: 0.4 (found in Docker)
        - MANUAL: 0.3 (manually specified)
        - default: 0.5
        """
        confidence_map: dict[str, float] = {
            "configuration": 1.0,
            "path": 0.8,
            "registry": 0.7,
            "vscode": 0.6,
            "jetbrains": 0.6,
            "wsl": 0.5,
            "docker": 0.4,
            "manual": 0.3,
        }
        return confidence_map.get(provider_type.lower(), 0.5)
