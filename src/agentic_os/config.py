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


settings = Settings()
