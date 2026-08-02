"""Capability registry + agent composer.

Implements :class:`CapabilityRegistry` and :class:`AgentComposer`. Capabilities
are registered, looked up, and composed into :class:`AgentSpec` instances. The
composer derives the capability set for a task (via a simple intent→capability
mapping), then selects provider/model through the routing facade.
"""

from __future__ import annotations

from agentic_os.domain.agent import Task
from agentic_os.domain.capability import AgentSpec
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.capability import Capability
from agentic_os.ports.event_bus import EventBus

log = get_logger("capability.engine")

# Lightweight intent → required capabilities used when composing for a task.
_INTENT_MAP: dict[str, list[str]] = {
    "code": ["reasoning", "planning", "coding", "filesystem", "terminal"],
    "research": ["reasoning", "research", "browser", "memory"],
    "plan": ["reasoning", "planning"],
    "review": ["reasoning", "coding"],
    "infra": ["reasoning", "planning", "docker", "terminal", "git"],
}


class CapabilityRegistryImpl:
    def __init__(self) -> None:
        self._caps: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        self._caps[capability.name] = capability

    def get(self, name: str) -> Capability | None:
        return self._caps.get(name)

    def all(self) -> list[Capability]:
        return list(self._caps.values())

    def names(self) -> list[str]:
        return list(self._caps.keys())

    def requires_approval(self, names: list[str]) -> bool:
        return any(getattr(self._caps.get(n), "requires_approval", False) for n in names)


class AgentComposerImpl:
    def __init__(
        self, bus: EventBus | None = None, registry: CapabilityRegistryImpl | None = None
    ) -> None:
        self._bus = bus
        self._registry = registry or CapabilityRegistryImpl()

    def compose(self, name: str, capabilities: list[str], provider: str, model: str) -> AgentSpec:
        spec = AgentSpec(name=name, capabilities=capabilities, provider=provider, model=model)
        spec.requires_approval = self._registry.requires_approval(capabilities)
        return spec

    def spec_for_task(self, task: Task) -> AgentSpec:
        """Derive a capability set from the task's role/title intent."""
        intent = self._intent_for(task)
        caps = _INTENT_MAP.get(intent, ["reasoning", "planning"])
        spec = AgentSpec(name=f"agent-{intent}", capabilities=caps, provider="", model="")
        spec.requires_approval = self._registry.requires_approval(caps)
        return spec

    @staticmethod
    def _intent_for(task: Task) -> str:
        text = f"{task.role} {task.title}".lower()
        for key in ("research", "plan", "review", "infra", "code"):
            if key in text:
                return key
        return "code"


class CapabilityEngine:
    """Top-level capability subsystem: registry + composer + bus wiring."""

    def __init__(self, bus: EventBus, registry: CapabilityRegistryImpl | None = None) -> None:
        self.bus = bus
        self.registry = registry or CapabilityRegistryImpl()
        self.composer = AgentComposerImpl(bus, self.registry)

    async def start(self) -> None:
        # Seed built-in capabilities.
        for cap in _BUILTINS():
            self.registry.register(cap)
        log.info("capability.engine.started", capabilities=self.registry.names())

    async def stop(self) -> None:
        pass

    async def compose_and_emit(self, task: Task) -> AgentSpec:
        spec = self.composer.spec_for_task(task)
        await self.bus.publish(
            EventEnvelope(
                type="agent.composed",
                source="capability-engine",
                topic=Topic.AGENT_COMPOSED.value,
                payload=spec.model_dump(),
            )
        )
        return spec


def _BUILTINS() -> list[Capability]:
    from agentic_os.adapters.capability.builtins import BUILTIN_CAPABILITIES

    return BUILTIN_CAPABILITIES
