"""Tests for the Capability Engine (Subsystem 3)."""

from __future__ import annotations

import pytest

from agentic_os.adapters.capability.builtins import (
    BUILTIN_CAPABILITIES,
    CodingCapability,
)
from agentic_os.core.capability.engine import (
    AgentComposerImpl,
    CapabilityEngine,
    CapabilityRegistryImpl,
)
from agentic_os.domain.agent import Agent, Task
from agentic_os.domain.capability import AgentSpec
from agentic_os.ports.capability import CapabilityResult


@pytest.fixture
def registry():
    r = CapabilityRegistryImpl()
    for c in BUILTIN_CAPABILITIES:
        r.register(c)
    return r


async def test_builtin_capabilities_present():
    names = {c.name for c in BUILTIN_CAPABILITIES}
    for expected in {
        "reasoning",
        "coding",
        "planning",
        "research",
        "browser",
        "docker",
        "git",
        "filesystem",
        "vision",
        "memory",
        "terminal",
    }:
        assert expected in names


async def test_sensitive_capabilities_require_approval(registry):
    assert registry.get("terminal").requires_approval is True
    assert registry.get("docker").requires_approval is True
    assert registry.get("coding").requires_approval is False
    assert registry.requires_approval(["coding", "terminal"]) is True
    assert registry.requires_approval(["coding", "reasoning"]) is False


async def test_capability_execution():
    cap = CodingCapability()
    res = await cap.run(
        Agent(id="a", role="coding", provider="mock"), Task(title="x", role="coding"), {}
    )
    assert isinstance(res, CapabilityResult)
    assert res.ok is True
    assert "coding" in res.output


async def test_composer_builds_spec(registry):
    composer = AgentComposerImpl(registry=registry)
    spec = composer.compose("coder", ["coding", "terminal"], "mock", "mock-fast")
    assert isinstance(spec, AgentSpec)
    assert spec.capabilities == ["coding", "terminal"]
    assert spec.requires_approval is True  # terminal is sensitive
    plain = composer.compose("thinker", ["reasoning"], "mock", "mock-fast")
    assert plain.requires_approval is False


async def test_composer_spec_for_task_intent(registry):
    composer = AgentComposerImpl(registry=registry)
    code_spec = composer.spec_for_task(Task(title="implement feature", role="coding"))
    assert "coding" in code_spec.capabilities
    assert code_spec.requires_approval is True
    research_spec = composer.spec_for_task(Task(title="research topic", role="research"))
    assert "research" in research_spec.capabilities


async def test_capability_engine_start_and_compose():
    from agentic_os.adapters.bus.local import LocalBus

    bus = LocalBus()
    await bus.start()
    seen = []

    async def collect(e):
        seen.append(e.topic)

    await bus.subscribe("agent.composed", collect)
    engine = CapabilityEngine(bus)
    await engine.start()
    assert "reasoning" in engine.registry.names()
    spec = await engine.compose_and_emit(Task(title="write code", role="coding"))
    assert isinstance(spec, AgentSpec)
    await bus.stop()
    assert "agent.composed" in seen
