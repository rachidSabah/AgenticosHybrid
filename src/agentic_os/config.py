"""Application configuration via pydantic-settings.

All knobs are environment-driven (12-factor). Defaults let the system boot on
the in-process bus with the mock provider — zero infrastructure.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bus_type: str = "local"  # local | redis | nats
    redis_url: str = "redis://localhost:6379/0"
    nats_url: str = "nats://localhost:4222"

    http_host: str = "127.0.0.1"
    http_port: int = 8000
    log_level: str = "INFO"
    api_key: str = ""

    provider_default: str = "mock"  # mock | claude_code | <registered>
    routing_policy: str = "latency"  # latency | cost | round_robin
    claude_code_bin: str = "claude"
    anthropic_api_key: str = ""
    hermes_config: str = ""

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

    # MCP Runtime Foundation (Phase 4, M3)
    mcp_enabled: bool = True
    mcp_default_transport: str = "stdio"  # stdio | sse | streamable_http
    mcp_default_timeout_seconds: int = 30
    mcp_health_check_interval_seconds: int = 30
    mcp_health_check_timeout_seconds: int = 10
    mcp_session_timeout_minutes: int = 60
    mcp_max_retries: int = 5
    mcp_auto_reconnect: bool = True
    mcp_auto_restart: bool = True
    mcp_discovery_enabled: bool = True
    mcp_max_servers: int = 50
    mcp_enforce_sandbox: bool = True

    # Learning & Optimization Engine (Phase 5)
    learning_enabled: bool = True

    # Desktop Runtime Foundation (Phase 4, M6)
    desktop_enabled: bool = True
    desktop_workspace_dir: str = ""
    desktop_cache_dir: str = ""
    desktop_log_dir: str = ""
    desktop_db_path: str = ""
    desktop_auto_start: bool = False
    desktop_minimize_to_tray: bool = True

    # Desktop Runtime Operational Layer (Phase 4, M6 Part 2)
    desktop_update_enabled: bool = True
    desktop_update_channel: str = "stable"
    desktop_offline_enabled: bool = True
    desktop_backup_enabled: bool = True
    desktop_runtime_discovery_enabled: bool = True
    desktop_installer_enabled: bool = True
    desktop_check_updates_on_start: bool = True
    desktop_auto_download_updates: bool = False
    desktop_auto_install_updates: bool = False
    desktop_backup_interval_hours: int = 24
    desktop_max_backups: int = 10
    desktop_runtime_discovery_interval_seconds: int = 3600

    # Production Hardening (Phase 4, M6 Part 3)
    desktop_validate_on_startup: bool = True
    desktop_enable_memory_leak_detection: bool = True
    desktop_enable_thread_monitoring: bool = True
    desktop_enable_auto_repair: bool = True
    desktop_enable_recovery_mode: bool = True
    desktop_memory_leak_threshold_mb: int = 50
    desktop_thread_count_threshold: int = 200
    desktop_graceful_shutdown_timeout_seconds: int = 30


settings = Settings()
