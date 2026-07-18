"""Application configuration via pydantic-settings.

All knobs are environment-driven (12-factor). Defaults let the system boot on
the in-process bus with the mock provider — zero infrastructure.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bus_type: str = "local"  # local | redis | nats
    redis_url: str = "redis://localhost:6379/0"
    nats_url: str = "nats://localhost:4222"

    http_host: str = "0.0.0.0"
    http_port: int = 8000
    log_level: str = "INFO"

    provider_default: str = "mock"  # mock | claude_code | <registered>
    routing_policy: str = "latency"  # latency | cost | round_robin
    claude_code_bin: str = "claude"
    anthropic_api_key: str = ""

    # Supervision tuning
    health_interval_seconds: float = 2.0
    heartbeat_timeout_seconds: float = 6.0
    max_attempts: int = 3

    # Runtime settings (Phase 4, M1)
    runtime_discovery_enabled: bool = True
    runtime_discovery_interval_seconds: float = 60.0
    runtime_health_interval_seconds: float = 30.0
    runtime_default_timeout_seconds: int = 60

    # Discovery & Profiling settings (Phase 4, M2)
    discovery_cache_ttl_seconds: float = 300.0
    discovery_max_cache_entries: int = 1000
    discovery_telemetry_max_entries: int = 1000
    discovery_hot_reload_enabled: bool = True
    discovery_hot_reload_interval_seconds: float = 30.0
    discovery_default_profile: str = "default"
    discovery_validation_enabled: bool = True
    discovery_profiling_enabled: bool = True

    # Multi-Agent Orchestration & Swarm Intelligence (Phase 4, M3)
    orchestration_enabled: bool = True
    orchestration_default_topology: str = "mesh"
    orchestration_default_strategy: str = "sequential"
    orchestration_max_agents_per_swarm: int = 10
    orchestration_default_timeout_seconds: int = 300
    orchestration_telemetry_max_entries: int = 1000
    orchestration_task_monitoring_interval: float = 5.0
    orchestration_leader_election_enabled: bool = True
    orchestration_consensus_quorum: float = 0.51
    orchestration_voting_enabled: bool = True
    orchestration_auto_recover: bool = True
    orchestration_default_decomposition_strategy: str = "rule-based"
    orchestration_inter_agent_timeout_seconds: int = 60


settings = Settings()
