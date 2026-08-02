"""Discovery registry — manages all discovery providers and their configs."""

from dataclasses import dataclass, field

from agentic_os.domain.discovery import DiscoveryProfile, DiscoveryProviderConfig
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.execution import DiscoveryProvider, EngineRegistration

log = get_logger("discovery.registry")


class DiscoveryRegistryError(Exception):
    """Base exception for discovery registry errors."""


@dataclass
class DiscoveryRegistry:
    """Registry of all discovery providers with their configurations.

    Wraps provider instances so the DiscoveryFramework can manage them
    independently of the M1 DiscoveryEngine.
    """

    _providers: dict[str, DiscoveryProvider] = field(default_factory=dict)
    _configs: dict[str, DiscoveryProviderConfig] = field(default_factory=dict)

    # ── Provider lifecycle ──

    def register(
        self,
        name: str,
        provider: DiscoveryProvider,
        config: DiscoveryProviderConfig | None = None,
    ) -> None:
        """Register a discovery provider with optional config."""
        if name in self._providers:
            raise DiscoveryRegistryError(f"Provider already registered: {name}")
        self._providers[name] = provider
        if config is not None:
            self._configs[name] = config
        else:
            self._configs[name] = DiscoveryProviderConfig(
                name=name,
                provider_type=provider.get_provider_type(),
            )
        log.info("Discovery provider registered", name=name, type=provider.get_provider_type())

    def unregister(self, name: str) -> bool:
        """Remove a discovery provider. Returns True if removed."""
        if name in self._providers:
            del self._providers[name]
            self._configs.pop(name, None)
            log.info("Discovery provider unregistered", name=name)
            return True
        return False

    def get_provider(self, name: str) -> DiscoveryProvider | None:
        """Get a provider instance by name."""
        return self._providers.get(name)

    def get_config(self, name: str) -> DiscoveryProviderConfig | None:
        """Get the config for a named provider."""
        return self._configs.get(name)

    # ── Provider listing ──

    def list_providers(self) -> list[dict]:
        """List all registered providers with their status."""
        result: list[dict] = []
        for name, provider in self._providers.items():
            config = self._configs.get(name)
            result.append(
                {
                    "name": name,
                    "provider_type": provider.get_provider_type(),
                    "enabled": config.enabled if config else True,
                    "interval_seconds": config.interval_seconds if config else 60.0,
                    "timeout_seconds": config.timeout_seconds if config else 10.0,
                    "confidence_override": config.confidence_override if config else None,
                }
            )
        return result

    def list_enabled(self) -> list[str]:
        """Return names of all enabled providers."""
        result: list[str] = []
        for name in self._providers:
            config = self._configs.get(name)
            if config is None or config.enabled:
                result.append(name)
        return result

    def list_by_type(self, provider_type: str) -> list[str]:
        """Return names of providers matching a type."""
        return [
            name for name, p in self._providers.items() if p.get_provider_type() == provider_type
        ]

    # ── Provider configuration ──

    def configure(self, name: str, config: DiscoveryProviderConfig) -> bool:
        """Update configuration for a named provider. Returns True if updated."""
        if name not in self._providers:
            return False
        self._configs[name] = config
        return True

    def enable_provider(self, name: str) -> bool:
        """Enable a provider. Returns True if state changed."""
        if name not in self._providers:
            return False
        config = self._configs.get(name)
        if config is not None and not config.enabled:
            self._configs[name] = config.with_enabled(True)
            return True
        elif config is None:
            self._configs[name] = DiscoveryProviderConfig(name=name, provider_type="", enabled=True)
            return True
        return False

    def disable_provider(self, name: str) -> bool:
        """Disable a provider. Returns True if state changed."""
        if name not in self._providers:
            return False
        config = self._configs.get(name)
        if config is not None and config.enabled:
            self._configs[name] = config.with_enabled(False)
            return True
        elif config is None:
            self._configs[name] = DiscoveryProviderConfig(
                name=name, provider_type="", enabled=False
            )
            return True
        return False

    def is_enabled(self, name: str) -> bool:
        """Check if a provider is enabled."""
        config = self._configs.get(name)
        if config is None:
            return name in self._providers  # enabled by default
        return config.enabled

    # ── Bulk discovery ──

    async def discover_all(self) -> dict[str, list[EngineRegistration]]:
        """Run all enabled providers and return results grouped by provider name.

        This does NOT deduplicate — the M1 DiscoveryEngine handles that.
        """
        results: dict[str, list[EngineRegistration]] = {}
        for name in self.list_enabled():
            provider = self._providers.get(name)
            if provider is None:
                continue
            try:
                registrations = await provider.discover()
                results[name] = registrations
            except Exception as exc:
                log.warning("Discovery provider failed", provider=name, error=str(exc))
                results[name] = []
        return results

    async def discover_by_provider(self, name: str) -> list[EngineRegistration]:
        """Run a single named provider and return registrations."""
        provider = self._providers.get(name)
        if provider is None:
            raise DiscoveryRegistryError(f"Unknown provider: {name}")
        if not self.is_enabled(name):
            return []
        return await provider.discover()

    def get_enabled_for_profile(self, profile: DiscoveryProfile) -> list[str]:
        """Return enabled provider names that are included in a profile."""
        profile_names = {c.name for c in profile.provider_configs if c.enabled}
        return [name for name in self.list_enabled() if name in profile_names]

    def count(self) -> int:
        """Return the number of registered providers."""
        return len(self._providers)
