"""Domain entities for the Provider Management System.

Pure data (Pydantic v2). No behavior, no I/O. These are the shared vocabulary
between the provider ports, the kernel, and the API layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ProviderHealthStatus(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class ProviderConfig(BaseModel):
    """User-supplied configuration for a provider (from the management UI/API).

    Holds the connection details needed to instantiate a provider adapter.
    Secrets (api_key) are never returned by read endpoints.
    """

    name: str
    kind: str  # mock | claude_code | openai_compatible | ...
    base_url: str = ""
    default_model: str = ""
    api_key_ref: str = ""  # key into the ApiKeyVault
    enabled: bool = True
    rate_limit: int = 0  # 0 = unlimited
    notes: str = ""


class ProviderHealthRecord(BaseModel):
    provider: str
    status: ProviderHealthStatus = ProviderHealthStatus.UNKNOWN
    latency_ms: float = 0.0
    last_checked: datetime = Field(default_factory=_utcnow)
    error: str | None = None


class CostRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    provider: str
    model: str
    task_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    at: datetime = Field(default_factory=_utcnow)


class BenchmarkResult(BaseModel):
    provider: str
    model: str
    latency_ms: float
    success: bool
    score: float = 0.0
    error: str | None = None
    at: datetime = Field(default_factory=_utcnow)
