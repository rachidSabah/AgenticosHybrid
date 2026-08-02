"""RuntimeBridge — bridges the desktop discovery system to the unified runtime model."""

from __future__ import annotations

from typing import Any

from agentic_os.core.runtime.runtime import (
    Runtime,
    RuntimeCapability,
    RuntimeHealth,
    RuntimeStatus,
    RuntimeType,
)
from agentic_os.core.runtime.runtime_registry import RuntimeRegistry
from agentic_os.infrastructure.logging import get_logger

log = get_logger("runtime.bridge")

# Map desktop RuntimeType values to core RuntimeType values.
# Both enums share many entries; this allows for future divergence.
_TYPE_MAP: dict[str, str] = {
    "python": "python",
    "git": "git",
    "docker": "docker",
    "node": "node",
    "claude_code": "claude_code",
    "opencode": "opencode",
    "gemini_cli": "gemini_cli",
    "codex_cli": "codex_cli",
    "ollama": "custom",
    "lm_studio": "custom",
    "llama.cpp": "custom",
    "openai_local": "custom",
    "mcp_server": "mcp_server",
    "sqlite": "custom",
    "postgresql": "custom",
    "redis": "custom",
    "unknown": "custom",
    "custom": "custom",
}


def _map_type(desktop_type: str) -> RuntimeType:
    """Map a desktop RuntimeType string to a core RuntimeType."""
    mapped = _TYPE_MAP.get(desktop_type, "custom")
    try:
        return RuntimeType(mapped)
    except ValueError:
        return RuntimeType.CUSTOM


class RuntimeBridge:
    """Bridges the desktop discovery system to the new runtime management system.

    Converts ``RuntimeInfo`` / ``RuntimeDiscoveryResult`` objects (from
    ``agentic_os.core.desktop.runtime_discovery``) into the unified
    ``Runtime`` model and auto-registers them.
    """

    def __init__(self, registry: RuntimeRegistry, bus: Any | None = None) -> None:
        self._registry = registry
        self._bus = bus
        self._last_discovery: dict[str, Any] = {}

    # ── Mapping ─────────────────────────────────────────────────────────

    def discover_to_runtime(self, discovery_info: Any) -> Runtime:
        """Convert a single discovery result into a unified Runtime.

        Accepts:
        - ``RuntimeInfo`` from ``agentic_os.domain.desktop``
        - Any dict-like object with ``runtime_type``, ``name``, ``version``,
          ``path``, ``executable``, ``capabilities`` attributes.

        Returns a new ``Runtime`` instance (not yet registered).
        """
        # Support both object-attribute and dict-like access
        if hasattr(discovery_info, "runtime_type"):
            desktop_type = (
                discovery_info.runtime_type.value
                if hasattr(discovery_info.runtime_type, "value")
                else str(discovery_info.runtime_type)
            )
            name = getattr(discovery_info, "name", "") or ""
            version = getattr(discovery_info, "version", "") or None
            binary_path = getattr(discovery_info, "path", None) or None
            executable = getattr(discovery_info, "executable", None) or None
            discovered_caps = getattr(discovery_info, "capabilities", []) or []
            source = getattr(discovery_info, "source", "auto") or "auto"
        else:
            # Dict-style access
            desktop_type = str(discovery_info.get("runtime_type", "custom"))
            name = discovery_info.get("name", "") or ""
            version = discovery_info.get("version") or None
            binary_path = discovery_info.get("path") or None
            executable = discovery_info.get("executable") or None
            discovered_caps = discovery_info.get("capabilities", []) or []
            source = discovery_info.get("source", "auto") or "auto"

        rt = _map_type(desktop_type)

        # Build capabilities
        capabilities = [
            RuntimeCapability(
                name=c if isinstance(c, str) else getattr(c, "value", str(c)),
                enabled=True,
            )
            for c in discovered_caps
        ]

        runtime = Runtime(
            name=name or rt.value,
            type=rt,
            version=version,
            binary_path=binary_path,
            executable=executable or name,
            source=source,
            status=RuntimeStatus.DISCOVERED,
            health=RuntimeHealth.UNKNOWN,
            discovered=True,
            capabilities=capabilities,
        )

        log.debug(
            "Mapped discovery to runtime",
            name=runtime.name,
            type=runtime.type.value,
            binary=binary_path,
        )
        return runtime

    # ── Sync ────────────────────────────────────────────────────────────

    async def sync_discovered(self) -> list[Runtime]:
        """Discover runtimes via the desktop discovery layer and auto-register them.

        Returns the list of newly registered Runtime objects. Already-registered
        runtimes (matched by name) are skipped.
        """
        discovered = await self._run_discovery()
        registered: list[Runtime] = []

        for info in discovered:
            name = info.name if hasattr(info, "name") else info.get("name", "")
            # Skip if already registered
            existing = await self._registry.get_by_name(name)
            if existing is not None:
                log.debug("Runtime already registered, skipping", name=name)
                continue

            runtime = self.discover_to_runtime(info)
            await self._registry.register(runtime)
            registered.append(runtime)

            log.info(
                "Discovered and registered runtime",
                name=runtime.name,
                type=runtime.type.value,
            )

        self._last_discovery = {
            "timestamp": __import__("datetime")
            .datetime.now(__import__("datetime").timezone.utc)
            .isoformat(),
            "count": len(discovered),
            "new": len(registered),
        }

        return registered

    async def get_discovery_status(self) -> dict[str, Any]:
        """Return a status snapshot of the last discovery sync."""
        total = await self._registry.count()
        active = len(await self._registry.get_active())

        return {
            "last_discovery": self._last_discovery,
            "total_registered": total,
            "active_runtimes": active,
            "bridge_available": True,
        }

    # ── Internal ────────────────────────────────────────────────────────

    async def _run_discovery(self) -> list[Any]:
        """Run discovery by importing the desktop discovery manager.

        Returns a list of ``RuntimeInfo``-compatible objects.
        """
        try:
            from agentic_os.core.desktop.runtime_discovery import (  # noqa: PLC0415
                RuntimeDiscoveryManager,
            )

            manager = RuntimeDiscoveryManager()
            result = await manager.discover_runtimes()
            runtimes: list[Any] = list(result.runtimes)
            log.info(
                "Desktop discovery completed",
                count=len(runtimes),
            )
            return runtimes
        except ImportError:
            log.warning("Desktop runtime discovery not available")
            return []
        except Exception as exc:
            log.error("Discovery failed", error=str(exc))
            return []


__all__ = [
    "RuntimeBridge",
]
