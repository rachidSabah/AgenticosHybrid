"""Shared pytest fixtures: a fresh in-process bus + registries per test."""

from __future__ import annotations

import pytest

from agentic_os.adapters.bus.local import LocalBus
from agentic_os.config import Settings
from agentic_os.core.orchestrator import Orchestrator
from agentic_os.core.registry import AgentRegistry, ProviderRegistry


@pytest.fixture
async def bus():
    b = LocalBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def settings():
    return Settings(bus_type="local", provider_default="mock")


@pytest.fixture
def registry():
    return AgentRegistry()


@pytest.fixture
def providers():
    return ProviderRegistry()


@pytest.fixture
async def orchestrator(bus, registry, providers, settings):
    o = Orchestrator(bus, registry, providers, settings)
    await o.start()
    return o


@pytest.fixture
async def kernel(bus, registry, providers, settings):
    """Full kernel wiring (orchestrator + health + recovery + dashboard) so
    integration tests exercise the real supervision/recovery paths."""
    from agentic_os.api.dashboard import DashboardBroadcaster
    from agentic_os.core.health import HealthMonitorImpl
    from agentic_os.core.recovery import RecoveryManagerImpl
    from agentic_os.core.scheduler import Scheduler

    sched = Scheduler()
    orch = Orchestrator(bus, registry, providers, settings)
    health = HealthMonitorImpl(bus, registry, sched, settings)
    recovery = RecoveryManagerImpl(bus, orch, settings)
    dashboard = DashboardBroadcaster(bus)
    await orch.start()
    await sched.start()
    await health.start()
    await recovery.start()
    await dashboard.start()
    yield orch
    await dashboard.stop()
    await recovery.stop()
    await health.stop()
    await sched.stop()
    await orch.stop()
