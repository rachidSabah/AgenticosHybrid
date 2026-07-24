"""Service Registry — Service metadata registration and BackgroundService base class.

The Service Registry is the Kernel's catalog of every registered service.
It tracks metadata, provides introspection, and enforces the BackgroundService
contract for periodic-task services.

Usage:
    registry = ServiceRegistry(lifecycle, container)
    registry.register(service_id="scheduler", ...)

    class MyBackgroundService(BackgroundService):
        async def run(self) -> None:
            while self._running:
                await do_work()
                await asyncio.sleep(10)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.container import Container
from agentic_os.core.lifecycle import LifecycleManager, ServiceProtocol

log = logging.getLogger("agentic_os.service_registry")


# ── Service Metadata ──


@dataclass
class ServiceMetadata:
    """Complete metadata for a registered Kernel service."""

    service_id: str
    interface: type
    implementation_type: str
    version: str = "1.0.0"
    description: str = ""
    phase: str = "infrastructure"
    dependencies: list[str] = field(default_factory=list)
    capabilities: list[dict[str, Any]] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    docs_url: str | None = None
    health_endpoint: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    config_schema: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "service_id": self.service_id,
            "interface": self.interface.__name__,
            "implementation_type": self.implementation_type,
            "version": self.version,
            "description": self.description,
            "phase": self.phase,
            "dependencies": self.dependencies,
            "capabilities": self.capabilities,
            "tags": list(self.tags),
            "registered_at": self.registered_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "docs_url": self.docs_url,
            "health_endpoint": self.health_endpoint,
            "config_schema": self.config_schema,
        }


# ── BackgroundService Base Class ──


class BackgroundService(ServiceProtocol):
    """Base class for periodic-task services.

    Provides:
    - _running flag with start/stop lifecycle
    - Logging
    - Graceful cancellation support

    Subclasses override run() to implement their periodic logic.
    """

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        self._log = logging.getLogger(f"agentic_os.bg.{self.__class__.__name__}")

    async def initialize(self) -> None:
        self._log.debug("Initialized")

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run_wrapper())
        self._log.info("Started")

    async def pause(self) -> None:
        self._running = False
        self._log.info("Paused")

    async def resume(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_wrapper())
            self._log.info("Resumed")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._log.info("Stopped")

    async def dispose(self) -> None:
        await self.stop()
        self._log.info("Disposed")

    async def health(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self._running else "stopped",
            "running": self._running,
        }

    async def heartbeat(self) -> bool:
        return self._running

    async def metadata(self) -> dict[str, Any]:
        return {
            "type": "BackgroundService",
            "class": self.__class__.__name__,
            "running": self._running,
        }

    async def _run_wrapper(self) -> None:
        try:
            await self.run()
        except asyncio.CancelledError:
            self._log.debug("Task cancelled")
        except Exception as exc:
            self._log.error("Background task failed: %s", exc, exc_info=True)
            self._running = False

    async def run(self) -> None:
        raise NotImplementedError


# ── ServiceRegistry ──


class ServiceRegistry:
    """Central registry for all Kernel services."""

    def __init__(
        self,
        lifecycle: LifecycleManager,
        container: Container,
    ) -> None:
        self._lifecycle = lifecycle
        self._container = container
        self._metadatas: dict[str, ServiceMetadata] = {}
        self._background_services: dict[str, BackgroundService] = {}

    def register(
        self,
        service_id: str,
        instance: ServiceProtocol,
        interface: type | None = None,
        version: str = "1.0.0",
        description: str = "",
        phase: str = "infrastructure",
        dependencies: list[str] | None = None,
        capabilities: list[dict[str, Any]] | None = None,
        tags: set[str] | None = None,
        docs_url: str | None = None,
        config_schema: dict[str, Any] | None = None,
    ) -> ServiceMetadata:
        meta = ServiceMetadata(
            service_id=service_id,
            interface=interface or type(instance),
            implementation_type=instance.__class__.__name__,
            version=version,
            description=description,
            phase=phase,
            dependencies=dependencies or [],
            capabilities=capabilities or [],
            tags=tags or set(),
            docs_url=docs_url,
            config_schema=config_schema,
        )
        self._metadatas[service_id] = meta

        if isinstance(instance, BackgroundService):
            self._background_services[service_id] = instance

        log.info("Service registered: %s (%s v%s)", service_id, meta.implementation_type, version)
        return meta

    def unregister(self, service_id: str) -> None:
        self._metadatas.pop(service_id, None)
        self._background_services.pop(service_id, None)
        log.info("Service unregistered: %s", service_id)

    def get(self, service_id: str) -> ServiceMetadata | None:
        return self._metadatas.get(service_id)

    def list_services(
        self,
        phase: str | None = None,
        tag: str | None = None,
    ) -> list[ServiceMetadata]:
        results = list(self._metadatas.values())
        if phase:
            results = [r for r in results if r.phase == phase]
        if tag:
            results = [r for r in results if tag in r.tags]
        return results

    def find_by_capability(self, capability: str) -> list[ServiceMetadata]:
        return [
            r
            for r in self._metadatas.values()
            if any(
                cap.get("name") == capability or capability in cap.get("capabilities", [])
                for cap in r.capabilities
            )
        ]

    def find_by_interface(self, interface: type) -> list[ServiceMetadata]:
        return [r for r in self._metadatas.values() if r.interface is interface]

    def get_background_service(self, service_id: str) -> BackgroundService | None:
        return self._background_services.get(service_id)

    def list_background_services(self) -> dict[str, BackgroundService]:
        return dict(self._background_services)

    async def start_all_background(self) -> None:
        for sid, bg in self._background_services.items():
            try:
                await bg.start()
                log.info("Background service started: %s", sid)
            except Exception as exc:
                log.error("Background service '%s' failed to start: %s", sid, exc)

    async def stop_all_background(self) -> None:
        for sid, bg in self._background_services.items():
            try:
                await bg.stop()
            except Exception as exc:
                log.error("Background service '%s' failed to stop: %s", sid, exc)

    def count_by_phase(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self._metadatas.values():
            counts[r.phase] = counts.get(r.phase, 0) + 1
        return counts

    def dependency_matrix(self) -> dict[str, list[str]]:
        matrix: dict[str, list[str]] = {}
        for sid, r in self._metadatas.items():
            matrix[sid] = list(r.dependencies)
        return matrix

    @property
    def total_services(self) -> int:
        return len(self._metadatas)

    @property
    def total_background(self) -> int:
        return len(self._background_services)
