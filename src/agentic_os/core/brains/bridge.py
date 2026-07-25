"""BrainDiscoveryBridge — subscribes to local agent discovery events and
converts them into :class:`BrainRecord` instances for the registry.

Acts as the bridge between Phase 6.1 (local agent discovery) and Phase 6.2
(brain registry & constellation).  Listens for ``AGENT_DISCOVERED`` /
``AGENT_REGISTERED`` / ``AGENT_UPDATED`` / ``AGENT_REMOVED`` events from
the local discovery service, converts them to brain records, and forwards
them to the :class:`BrainRegistry`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agentic_os.domain.brains import (
    BrainRecord,
    BrainRuntime,
    BrainStatus,
    BrainType,
    BrainVendor,
)
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("brains.bridge")

# ── Tool-type → brain classification helpers ────────────────────────────────

_BUILTIN_VENDOR_MAP: dict[str, BrainVendor] = {
    "claude-code": BrainVendor.CLAUDE_CODE,
    "hermes": BrainVendor.HERMES,
    "gemini-cli": BrainVendor.GEMINI_CLI,
    "gemini": BrainVendor.GEMINI_CLI,
    "codex": BrainVendor.CODEX,
    "opencode": BrainVendor.OPENCODE,
    "aider": BrainVendor.AIDER,
    "continue": BrainVendor.CONTINUE,
    "ollama": BrainVendor.OLLAMA,
}

_TOOL_TYPE_TO_BRAIN_TYPE: dict[str, BrainType] = {
    "ollama": BrainType.LOCAL_CLI,
    "lm-studio": BrainType.LOCAL_CLI,
    "vllm": BrainType.LOCAL_CLI,
}

_LOCAL_CLI_TOOL_TYPES = {
    "claude-code",
    "hermes",
    "gemini-cli",
    "gemini",
    "codex",
    "opencode",
    "aider",
    "continue",
    "ollama",
    "lm-studio",
    "vllm",
}


class BrainDiscoveryBridge:
    """Bridge between local agent discovery (Phase 6.1) and the brain
    registry (Phase 6.2).

    Subscribes to discovery events on the event bus and converts
    ``LocalAgent`` payloads into :class:`BrainRecord` objects suitable
    for the :class:`BrainRegistry`.

    Thread-safety
    -------------
    The bridge uses ``asyncio.Lock`` when accessing shared state
    (subscription IDs).

    Lifecycle
    ---------
    ::

        bridge = BrainDiscoveryBridge()
        await bridge.start(event_bus=bus, on_brain_registered=my_callback)
        # ... system runs ...
        await bridge.stop()
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._subscriptions: list[str] = []
        self._event_bus: EventBus | None = None
        self._on_brain: Any = None
        self._started = False

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(
        self,
        event_bus: EventBus,
        on_brain_registered: Any | None = None,
    ) -> None:
        """Subscribe to local agent discovery events.

        Args:
            event_bus: The event bus to subscribe to.
            on_brain_registered: An async callback ``(BrainRecord) -> None``
                that will be called for every converted brain record.
                Typically this is ``BrainRegistry.register``.
        """
        self._event_bus = event_bus
        self._on_brain = on_brain_registered

        topics = [
            Topic.AGENT_DISCOVERED,
            Topic.AGENT_REGISTERED,
            Topic.AGENT_UPDATED,
            Topic.AGENT_REMOVED,
        ]

        for topic in topics:
            try:
                sub_id = await event_bus.subscribe(topic.value, self._handle_event)
                async with self._lock:
                    self._subscriptions.append(sub_id)
            except Exception:
                log.exception("Failed to subscribe to %s", topic.value)

        self._started = True
        log.info(
            "BrainDiscoveryBridge started (%d subscriptions)",
            len(self._subscriptions),
        )

    async def stop(self) -> None:
        """Unsubscribe from all discovery events."""
        bus = self._event_bus
        if bus is not None:
            async with self._lock:
                for sub_id in self._subscriptions:
                    try:
                        await bus.unsubscribe(sub_id)
                    except Exception:
                        log.exception("Failed to unsubscribe %s", sub_id)
                self._subscriptions.clear()
        self._started = False
        log.info("BrainDiscoveryBridge stopped")

    # ── Event handling ──────────────────────────────────────────────────────

    async def _handle_event(self, event: EventEnvelope) -> None:
        """Handle an incoming agent discovery event."""
        try:
            payload = event.payload
            if not payload or "id" not in payload:
                return

            record = self._convert(payload, event.topic)
            if record is None:
                return

            if self._on_brain is not None:
                await self._on_brain(record)

        except Exception:
            log.exception("Failed to handle discovery event")

    # ── Conversion ──────────────────────────────────────────────────────────

    def _convert(self, payload: dict[str, Any], topic: str) -> BrainRecord | None:
        """Convert a discovered-agent payload to a :class:`BrainRecord`.

        Args:
            payload: The event payload dict (typically a ``LocalAgent``
                serialised via ``to_dict()``).
            topic: The event topic string.

        Returns:
            A :class:`BrainRecord`, or ``None`` if the payload cannot
            be converted.
        """
        tool_type = payload.get("tool_type", "") or payload.get("name", "")
        if not tool_type:
            return None

        vendor = self._resolve_vendor(tool_type)
        brain_type = self._resolve_brain_type(tool_type)
        status = self._resolve_status(payload, topic)

        # Extract model list
        supported_models = tuple(payload.get("supported_models") or payload.get("models") or [])
        supported_tools = tuple(payload.get("supported_tools") or payload.get("tools") or [])
        capabilities = tuple(payload.get("capabilities") or [])
        tags = tuple(payload.get("tags") or [])

        now_iso = datetime.now(UTC).isoformat()

        return BrainRecord(
            id=payload.get("id", uuid4().hex[:12]),
            display_name=payload.get("name", payload.get("display_name", tool_type)),
            brain_type=brain_type,
            vendor=vendor,
            runtime=BrainRuntime.UNKNOWN,
            version=payload.get("version", ""),
            status=status,
            health=float(payload.get("health_score", 100.0)),
            capabilities=capabilities,
            supported_models=supported_models,
            supported_tools=supported_tools,
            memory_usage=float(payload.get("memory_mb", 0.0)),
            cpu_usage=float(payload.get("cpu_percent", 0.0)),
            latency=float(payload.get("latency_ms", 0.0)),
            workspace=payload.get("working_directory", ""),
            current_tasks=payload.get("current_tasks", 0),
            queue_depth=payload.get("queue_depth", 0),
            tags=tags,
            metadata=payload.get("metadata", {}),
            discovered_at=payload.get("discovered_at", now_iso),
            last_seen=payload.get("last_seen", now_iso),
            error_count=payload.get("error_count", 0),
            last_error=payload.get("last_error", ""),
        )

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_vendor(tool_type: str) -> BrainVendor:
        """Map a tool_type string to the most appropriate vendor."""
        return _BUILTIN_VENDOR_MAP.get(tool_type.lower(), BrainVendor.CUSTOM)

    @staticmethod
    def _resolve_brain_type(tool_type: str) -> BrainType:
        """Map a tool_type string to a brain type."""
        lower = tool_type.lower()
        if lower in _TOOL_TYPE_TO_BRAIN_TYPE:
            return _TOOL_TYPE_TO_BRAIN_TYPE[lower]
        if lower in _LOCAL_CLI_TOOL_TYPES:
            return BrainType.LOCAL_CLI
        return BrainType.CUSTOM

    @staticmethod
    def _resolve_status(payload: dict[str, Any], topic: str) -> BrainStatus:
        """Map an agent event payload and topic to a brain status."""
        # Direct status field wins
        raw_status = payload.get("status", "")
        if raw_status:
            status_map: dict[str, BrainStatus] = {
                "running": BrainStatus.CONNECTED,
                "idle": BrainStatus.IDLE,
                "busy": BrainStatus.BUSY,
                "stopped": BrainStatus.DISCONNECTED,
                "unknown": BrainStatus.DISCOVERED,
                "crashed": BrainStatus.FAILED,
                "degraded": BrainStatus.DEGRADED,
            }
            mapped = status_map.get(raw_status.lower())
            if mapped:
                return mapped

        # Fall back to topic-based status
        if topic == Topic.AGENT_REMOVED.value:
            return BrainStatus.REMOVED
        if topic == Topic.AGENT_DISCOVERED.value:
            return BrainStatus.DISCOVERED
        if topic == Topic.AGENT_REGISTERED.value:
            return BrainStatus.REGISTERED

        return BrainStatus.DISCOVERED
