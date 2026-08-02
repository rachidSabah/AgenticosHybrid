"""Orchestration configuration — profiles and runtime knobs."""

from dataclasses import dataclass, field
from typing import Any

from agentic_os.domain.orchestration import OrchestrationProfile, SwarmTopology


@dataclass
class OrchestrationConfiguration:
    """Runtime configuration for the orchestration subsystem.

    Controls profiles, synchronization, communication, and telemetry limits,
    plus all new swarm engine subsystems (planner, scheduler, supervisor,
    retry, checkpoint, validation, etc.).
    """

    profiles: dict[str, OrchestrationProfile] = field(default_factory=dict)
    default_profile: str = "default"
    enabled: bool = True
    agent_sync_interval_seconds: float = 30.0
    communication_history_max: int = 1000
    telemetry_max_entries: int = 500
    default_quorum: float = 0.51
    default_topology: str = "mesh"

    # ── Planner ──
    planner_enabled: bool = True
    planner_default_max_parallel: int = 5
    planner_default_strategy: str = "rule-based"

    # ── Scheduler ──
    scheduler_enabled: bool = True
    scheduler_default_timeout_seconds: float = 60.0
    scheduler_max_concurrent_tasks: int = 10

    # ── Supervisor ──
    supervisor_enabled: bool = True
    supervisor_monitor_interval_seconds: float = 5.0
    supervisor_hung_task_timeout_seconds: float = 120.0
    supervisor_max_retries: int = 3

    # ── Retry ──
    retry_enabled: bool = True
    retry_default_policy: dict[str, Any] = field(
        default_factory=lambda: {
            "max_retries": 3,
            "base_delay_seconds": 1.0,
            "backoff_multiplier": 2.0,
            "max_delay_seconds": 60.0,
            "jitter": True,
            "retry_on_error": True,
            "retry_on_timeout": True,
        }
    )

    # ── Checkpoint ──
    checkpoint_enabled: bool = True
    checkpoint_interval_tasks: int = 5  # Save checkpoint every N completed tasks

    # ── Validation ──
    validation_enabled: bool = True
    validation_strict_mode: bool = False

    # ── Merging ──
    merge_default_strategy: str = "consensus"

    # ── Metrics ──
    metrics_enabled: bool = True
    metrics_max_timeline_entries: int = 1000

    # ── Cost ──
    cost_tracking_enabled: bool = True
    cost_default_currency: str = "USD"

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
