"""Discovery configuration — global settings and named profiles."""

from dataclasses import dataclass, field

from agentic_os.domain.discovery import DiscoveryProfile, DiscoveryRule


@dataclass
class DiscoveryConfiguration:
    """Global and per-provider discovery configuration.

    Holds all named profiles, filtering rules, and global defaults.
    Mutated directly (not frozen) since it's a runtime configuration object.
    """

    enabled: bool = True
    default_profile: str = "default"
    cache_ttl_seconds: float = 300.0
    max_cache_entries: int = 1000
    telemetry_max_entries: int = 1000
    profiles: dict[str, DiscoveryProfile] = field(default_factory=dict)
    rules: list[DiscoveryRule] = field(default_factory=list)

    # ── Profile management ──

    def add_profile(self, profile: DiscoveryProfile) -> None:
        """Register or replace a named profile."""
        self.profiles[profile.name] = profile

    def remove_profile(self, name: str) -> bool:
        """Remove a profile by name. Returns True if removed."""
        if name in self.profiles:
            del self.profiles[name]
            return True
        return False

    def get_profile(self, name: str) -> DiscoveryProfile | None:
        """Get a profile by name, or None."""
        return self.profiles.get(name)

    def list_profiles(self) -> list[dict]:
        """List all registered profiles as dicts."""
        return [p.to_dict() for p in self.profiles.values()]

    def get_active_profiles(self) -> list[DiscoveryProfile]:
        """Return profiles that have at least one enabled provider config."""
        result: list[DiscoveryProfile] = []
        for profile in self.profiles.values():
            if any(c.enabled for c in profile.provider_configs):
                result.append(profile)
        return result

    # ── Rule management ──

    def add_rule(self, rule: DiscoveryRule) -> None:
        """Add a filtering rule."""
        self.rules.append(rule)

    def remove_rule(self, index: int) -> bool:
        """Remove a rule by index. Returns True if removed."""
        if 0 <= index < len(self.rules):
            self.rules.pop(index)
            return True
        return False

    def get_rules(self, action: str | None = None) -> list[DiscoveryRule]:
        """Get all rules, optionally filtered by action."""
        if action is None:
            return list(self.rules)
        return [r for r in self.rules if r.action == action]

    def clear_rules(self) -> None:
        """Remove all filtering rules."""
        self.rules.clear()

    def to_dict(self) -> dict:
        """Export configuration as a serializable dict."""
        return {
            "enabled": self.enabled,
            "default_profile": self.default_profile,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "max_cache_entries": self.max_cache_entries,
            "telemetry_max_entries": self.telemetry_max_entries,
            "profiles": [p.to_dict() for p in self.profiles.values()],
            "rules": [r.to_dict() for r in self.rules],
        }
