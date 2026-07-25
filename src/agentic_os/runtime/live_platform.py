"""Dynamic proxy over Kernel.

Never stores runtime objects.

Always resolves them lazily.
"""

from __future__ import annotations

from typing import Any

from agentic_os.kernel import Kernel


class LivePlatform:
    """Dynamic proxy over Kernel.

    Every property access resolves the current Kernel attribute at call time,
    ensuring FastAPI routes always see the live runtime state even when
    subsystems initialize after application construction.

    This solves the stale-platform-snapshot bug where API routes captured
    a Platform dataclass before _start_subsystems() populated brain_registry
    and other late-binding subsystems.
    """

    def __init__(self, kernel: Kernel) -> None:
        self._kernel = kernel

    # ── Core subsystems ──────────────────────────────────────────────────

    @property
    def bus(self):
        return self._kernel.bus

    @property
    def registry(self):
        return self._kernel.registry

    @property
    def providers(self):
        return self._kernel.providers

    @property
    def orchestrator(self):
        return self._kernel.orchestrator

    @property
    def scheduler(self):
        return self._kernel.scheduler

    @property
    def health(self):
        return self._kernel.health

    @property
    def recovery(self):
        return self._kernel.recovery

    @property
    def dashboard(self):
        return self._kernel.dashboard

    # ── Provider management ──────────────────────────────────────────────

    @property
    def provider_mgr(self):
        return self._kernel.provider_mgr

    @property
    def model_mgr(self):
        return self._kernel.model_mgr

    @property
    def vault(self):
        return self._kernel.vault

    @property
    def provider_health(self):
        return self._kernel.provider_health

    @property
    def cost(self):
        return self._kernel.cost

    @property
    def rate(self):
        return self._kernel.rate

    @property
    def router(self):
        return self._kernel.router

    @property
    def secret_store(self):
        return self._kernel.secret_store

    # ── Memory / Capability / Security ───────────────────────────────────

    @property
    def memory(self):
        return self._kernel.memory

    @property
    def capability(self):
        return self._kernel.capability

    @property
    def security(self):
        return self._kernel.security

    # ── Workflow / Pipeline ──────────────────────────────────────────────

    @property
    def workflow(self):
        return self._kernel.workflow

    @property
    def pipeline(self):
        return self._kernel.pipeline

    # ── Runtime / Discovery / Installer ──────────────────────────────────

    @property
    def runtime(self):
        return self._kernel.runtime

    @property
    def discovery_framework(self):
        return self._kernel.discovery_framework

    @property
    def installer_intelligence(self):
        return self._kernel.installer_intelligence

    # ── Orchestration / MCP / Desktop / Learning ─────────────────────────

    @property
    def orchestration(self):
        return self._kernel.orchestration

    @property
    def mcp(self):
        return self._kernel.mcp

    @property
    def mcp_ws(self):
        return self._kernel.mcp_ws

    @property
    def desktop(self):
        return self._kernel.desktop

    @property
    def learning(self):
        return self._kernel.learning

    # ── Mission / Local Discovery ────────────────────────────────────────

    @property
    def mission_planner(self):
        return self._kernel.mission_planner

    @property
    def local_discovery(self):
        return self._kernel.local_discovery

    # ── Brain Registry & Constellation (Phase 6.2) ───────────────────────

    @property
    def brain_registry(self):
        return self._kernel.brain_registry

    @property
    def brain_manager(self):
        return self._kernel.brain_manager

    @property
    def brain_catalog(self):
        return self._kernel.brain_catalog

    @property
    def brain_graph(self):
        return self._kernel.brain_graph

    @property
    def brain_stats(self):
        return self._kernel.brain_stats

    @property
    def brain_health(self):
        return self._kernel.brain_health

    @property
    def brain_discovery_bridge(self):
        return self._kernel.brain_discovery_bridge

    @property
    def brain_runtime_bridge(self):
        return self._kernel.brain_runtime_bridge

    # ── Runtime registries (alternate names) ─────────────────────────────

    @property
    def provider_registry(self):
        """Alias for ``.providers`` — matches spec naming."""
        return self._kernel.providers

    @property
    def capability_registry(self):
        """Alias for ``.capability`` — matches spec naming."""
        return self._kernel.capability

    @property
    def aggregation_engine(self):
        """Alias — routes that expect ``aggregation_engine`` resolve dynamically."""
        return self._kernel.recovery

    @property
    def executor(self):
        """Alias — routes that expect ``executor`` resolve dynamically."""
        return self._kernel.orchestrator

    @property
    def event_bus(self):
        """Alias — routes that expect ``event_bus`` resolve dynamically."""
        return self._kernel.bus

    # ── Fallback for unknown attributes ──────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        """Resolve unknown attributes from the Kernel as a final fallback.

        This ensures forward-compatibility: if a new subsystem is added to
        Kernel but not yet exposed via an explicit property, routes can still
        access it through the dynamic proxy.
        """
        return getattr(self._kernel, name)
