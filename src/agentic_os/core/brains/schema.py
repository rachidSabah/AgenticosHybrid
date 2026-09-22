"""Canonical agent schema — the single runtime state contract.

Every UI surface (AI Agent Binding, AI Brain, Agent Constellation, Prompt
Center, Mission Control, ...) consumes these types and nothing else.

Design rules (from the dynamic-discovery spec):
* An agent appears only if a real executable was discovered AND probed.
* Absence is valid data: unknown values are ``None``/"UNKNOWN", never guessed.
* Capabilities and version carry explicit provenance.
* Health is measured, never assumed — ``health_score`` is None until probed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ── Statuses (spec §5) ──────────────────────────────────────────────────────

STATUS_NOT_FOUND = "not_found"
STATUS_DISCOVERED = "discovered"
STATUS_VALIDATING = "validating"
STATUS_BOUND = "bound"
STATUS_HEALTHY = "healthy"
STATUS_DEGRADED = "degraded"
STATUS_UNAVAILABLE = "unavailable"
STATUS_FAILED = "failed"
STATUS_RETIRED = "retired"

#: Statuses that mean "show this as an active agent".
ACTIVE_STATUSES = frozenset({STATUS_BOUND, STATUS_HEALTHY, STATUS_DEGRADED})

# ── Classification (spec §4) ────────────────────────────────────────────────

KIND_AI_AGENT_CLI = "ai-agent-cli"
KIND_AI_RUNTIME = "ai-runtime"
KIND_DEV_RUNTIME = "developer-runtime"
KIND_VCS = "vcs"
KIND_PACKAGE_MANAGER = "package-manager"
KIND_SYSTEM_UTILITY = "system-utility"
KIND_UNKNOWN = "unknown"

#: Kinds that are NOT AI agents. Surfaced separately as "Runtimes".
NON_AGENT_KINDS = frozenset(
    {KIND_DEV_RUNTIME, KIND_VCS, KIND_PACKAGE_MANAGER, KIND_SYSTEM_UTILITY, KIND_UNKNOWN}
)

UNKNOWN = "UNKNOWN"
NOT_DETECTED = "NOT DETECTED"


@dataclass
class Capability:
    """A capability with provenance (spec §7).

    ``source`` is how we learned it; ``confidence`` is how sure we are.
    """

    capability: str
    source: str  # e.g. "runtime_probe", "help_text", "inferred"
    confidence: str  # "verified" | "inferred" | "unknown"


@dataclass
class ProbeResult:
    """Outcome of a single probe step."""

    name: str
    ok: bool
    detail: str = ""
    evidence: str = ""


@dataclass
class DiscoveredAgent:
    """Normalized agent record (spec §18).

    Every field defaults to "unknown". Nothing is invented.
    """

    id: str
    name: str
    kind: str = KIND_UNKNOWN
    executable_path: str = ""
    command: str = ""

    version: str | None = None
    version_source: str | None = None  # e.g. "--version"

    status: str = STATUS_DISCOVERED
    capabilities: list[Capability] = field(default_factory=list)

    discovered_at: str = field(default_factory=_now)
    validated_at: str | None = None

    # Real measurements. None until actually measured — never 0/fabricated.
    health_score: float | None = None
    latency_ms: float | None = None
    throughput: float | None = None
    session_count: int | None = None
    heartbeat: str | None = None

    probes: list[ProbeResult] = field(default_factory=list)
    error: str | None = None

    def is_active(self) -> bool:
        """Active means: real AI agent AND a status that passed validation.

        Checking status alone would let a healthy *runtime* (git/node/python)
        masquerade as an active agent, so kind is enforced too (§4).
        """
        return self.is_agent() and self.status in ACTIVE_STATUSES

    def is_agent(self) -> bool:
        return self.kind not in NON_AGENT_KINDS

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["is_active"] = self.is_active()
        d["is_agent"] = self.is_agent()
        return d


@dataclass
class DiscoverySnapshot:
    """Immutable result of one discovery pass."""

    scanned_at: str = field(default_factory=_now)
    platform: str = ""
    agents: list[DiscoveredAgent] = field(default_factory=list)
    candidates_seen: int = 0
    errors: list[str] = field(default_factory=list)

    def active_agents(self) -> list[DiscoveredAgent]:
        return [a for a in self.agents if a.is_active() and a.is_agent()]

    def runtimes(self) -> list[DiscoveredAgent]:
        """Non-agent tooling (git/node/python) — shown separately."""
        return [a for a in self.agents if not a.is_agent()]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned_at": self.scanned_at,
            "platform": self.platform,
            "candidates_seen": self.candidates_seen,
            "agents": [a.to_dict() for a in self.agents],
            "active_agents": [a.to_dict() for a in self.active_agents()],
            "runtimes": [a.to_dict() for a in self.runtimes()],
            "counts": {
                "discovered": len(self.agents),
                "active": len(self.active_agents()),
                "runtimes": len(self.runtimes()),
            },
            "errors": self.errors,
        }
