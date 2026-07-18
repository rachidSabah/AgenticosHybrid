"""Orchestration configuration — profiles and runtime knobs."""

from dataclasses import dataclass, field

from agentic_os.domain.orchestration import OrchestrationProfile, SwarmTopology


@dataclass
class OrchestrationConfiguration:
    """Runtime configuration for the orchestration subsystem.

    Controls profiles, synchronization, communication, and telemetry limits.
    """

    profiles: dict[str, OrchestrationProfile] = field(default_factory=dict)
    default_profile: str = "default"
    enabled: bool = True
    agent_sync_interval_seconds: float = 30.0
    communication_history_max: int = 1000
    telemetry_max_entries: int = 500
    default_quorum: float = 0.51
    default_topology: str = "mesh"

    def get_profile(self, name: str | None = None) -> OrchestrationProfile:
        """Get a named profile, or return the default."""
        return self.profiles.get(name or self.default_profile, self._default_profile())

    def add_profile(self, profile: OrchestrationProfile) -> None:
        """Register a profile."""
        self.profiles[profile.name] = profile

    def remove_profile(self, name: str) -> bool:
        """Remove a profile by name."""
        if name == self.default_profile:
            return False
        return self.profiles.pop(name, None) is not None

    def _default_profile(self) -> OrchestrationProfile:
        return OrchestrationProfile(
            name="default",
            description="Default orchestration profile — mesh topology, balanced settings",
            default_topology=SwarmTopology.MESH,
            max_agents_per_swarm=10,
            subtask_timeout_seconds=60.0,
            auto_discover_agents=True,
        )
