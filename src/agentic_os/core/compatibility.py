"""Compatibility Layer — Bridges v2.0 Kernel Container to v1.0 Kernel API.

Ensures complete backward compatibility during migration so that all existing
code continues to work unmodified.

Two operating modes:
  - CONTAINER mode (default): Container resolves all services
  - LEGACY mode (AGENTIC_OS_USE_CONTAINER=0): Pure v1.0 Kernel, no Container
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from agentic_os.core.container import Container
from agentic_os.core.lifecycle import LifecycleManager

log = logging.getLogger("agentic_os.compatibility")

_USE_CONTAINER = os.environ.get("AGENTIC_OS_USE_CONTAINER", "1") == "1"


class _PlatformStub:
    """Minimal Platform-compatible data class for Container mode.
    Replaced by the real Platform import once services are migrated.
    """

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


# Mapping of old Platform field names → Container interface types
PLATFORM_FIELD_MAP: dict[str, type] = {
    # Populated as services migrate: "field_name": InterfaceType
}

# Mapping of old Kernel attr names → LifecycleManager service IDs
KNOWN_SERVICE_IDS: dict[str, str] = {
    # Populated as services migrate: "attr_name": "service_id"
}


class CompatibilityKernelProxy:
    """Wraps the v2.0 Container + LifecycleManager to expose the v1.0 Kernel API."""

    def __init__(
        self,
        container: Container | None = None,
        lifecycle: LifecycleManager | None = None,
        old_kernel: Any = None,
    ) -> None:
        self._container = container
        self._lifecycle = lifecycle
        self._old_kernel = old_kernel
        self._use_container = _USE_CONTAINER
        self._resolve_cache: dict[str, Any] = {}
        self._legacy_usage: dict[str, int] = {}
        self._platform: Any = None
        self._platform_generated_at: datetime | None = None

        if not container and not old_kernel:
            raise ValueError("Either container or old_kernel must be provided")

        if not self._use_container:
            log.info("CompatibilityKernelProxy: LEGACY MODE (AGENTIC_OS_USE_CONTAINER=0)")

    def __getattr__(self, name: str) -> Any:
        """Fallback attribute access — tries Container, then old Kernel."""
        if name in self._resolve_cache:
            return self._resolve_cache[name]

        if self._lifecycle and name in KNOWN_SERVICE_IDS:
            service_id = KNOWN_SERVICE_IDS[name]
            record = self._lifecycle.get_service(service_id)
            if record and record.instance:
                self._resolve_cache[name] = record.instance
                return record.instance

        if name in PLATFORM_FIELD_MAP:
            interface = PLATFORM_FIELD_MAP[name]
            if self._container and self._use_container:
                try:
                    instance = self._container.resolve(interface)
                    self._resolve_cache[name] = instance
                    return instance
                except Exception:
                    pass

        if self._old_kernel and self._use_container:
            self._legacy_usage[name] = self._legacy_usage.get(name, 0) + 1
            val = getattr(self._old_kernel, name, None)
            if val is not None:
                return val

        raise AttributeError(f"'{self.__class__.__name__}' has no attribute '{name}'")

    def generate_platform(self, **overrides: Any) -> Any:
        """Auto-generate a Platform-compatible object from Container registrations."""
        if not self._use_container or not self._container:
            return self._old_kernel.platform() if self._old_kernel else _PlatformStub()

        data: dict[str, Any] = {}
        for field_name, interface in PLATFORM_FIELD_MAP.items():
            try:
                data[field_name] = self._container.resolve(interface)
            except Exception:
                if self._old_kernel:
                    val = getattr(self._old_kernel, field_name, None)
                    if val is not None:
                        data[field_name] = val
        data.update(overrides)

        try:
            self._platform = _PlatformStub(**data)
        except Exception:
            if self._old_kernel:
                self._platform = self._old_kernel.platform()
        self._platform_generated_at = datetime.now(UTC)
        return self._platform

    async def start(self) -> None:
        """Pre-resolve all Container singletons into cache."""
        if self._container and self._use_container:
            log.info("CompatibilityKernelProxy: resolving all singletons")
            for reg in self._container.list_registrations():
                try:
                    inst = self._container.resolve(reg.interface, name=reg.name)
                    self._resolve_cache[reg.key] = inst
                except Exception:
                    pass

    async def stop(self) -> None:
        self._resolve_cache.clear()

    def get_deprecation_report(self) -> dict[str, Any]:
        return {
            "legacy_attributes_used": dict(self._legacy_usage),
            "container_resolved_services": len(self._resolve_cache),
            "platform_generated_at": (
                self._platform_generated_at.isoformat() if self._platform_generated_at else None
            ),
            "use_container": self._use_container,
            "has_container": self._container is not None,
            "has_old_kernel": self._old_kernel is not None,
        }

    def get_service(self, attr_name: str) -> Any:
        return getattr(self, attr_name)

    def register_legacy_bridge(self, attr_name: str, interface: type, service_id: str) -> None:
        PLATFORM_FIELD_MAP[attr_name] = interface
        KNOWN_SERVICE_IDS[attr_name] = service_id

    def health(self) -> dict[str, Any]:
        return {
            "mode": "container" if self._use_container and self._container else "legacy",
            "use_container": self._use_container,
            "container_available": self._container is not None,
            "old_kernel_available": self._old_kernel is not None,
            "cache_size": len(self._resolve_cache),
            "legacy_usage_count": sum(self._legacy_usage.values()),
        }


def should_use_container() -> bool:
    return _USE_CONTAINER


def set_use_container(value: bool) -> None:
    global _USE_CONTAINER  # noqa: PLW0603
    _USE_CONTAINER = value
    os.environ["AGENTIC_OS_USE_CONTAINER"] = "1" if value else "0"
