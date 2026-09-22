"""Platform discovery adapters (spec §17).

``AgentDiscoveryProvider`` is the platform-independent contract. Concrete
adapters know how to enumerate binaries and probe them on their OS.

The UI must never depend on a concrete adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from agentic_os.core.brains.schema import DiscoveredAgent


@runtime_checkable
class AgentDiscoveryProvider(Protocol):
    """Platform capability contract."""

    async def discover(self) -> list[str]:
        """Return candidate binary names available on this host."""
        ...

    async def validate(self, candidate: str) -> DiscoveredAgent:
        """Full probe: version -> identity -> capability -> health."""
        ...


class BaseAgentDiscovery(ABC):
    """Shared probe logic for all platforms.

    Subclasses implement only candidate enumeration; probing is OS-agnostic
    wherever possible (``--version``/``--help`` work across platforms).
    """

    platform_name: str = "unknown"

    @abstractmethod
    async def _enumerate_candidates(self) -> list[str]:
        """OS-specific enumeration of plausible binaries."""

    async def discover(self) -> list[str]:
        try:
            return await self._enumerate_candidates()
        except Exception:
            return []

    @abstractmethod
    async def _resolve(self, name: str) -> str | None:
        """Resolve a binary name to an absolute path (None if absent)."""

    async def resolve(self, name: str) -> str | None:
        """Public resolution — used by repair to re-find a moved executable."""
        return await self._resolve(name)

    async def validate(self, candidate: str) -> DiscoveredAgent:
        from agentic_os.core.brains.probes import run_probe_sequence

        path = await self._resolve(candidate)
        return await run_probe_sequence(candidate, path or "")

    def describe(self) -> dict[str, Any]:
        return {"platform": self.platform_name}
