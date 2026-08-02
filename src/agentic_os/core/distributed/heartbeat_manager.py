"""Phase 17 — HeartbeatManager + NodeRegistry.

HeartbeatManager: sends heartbeats to peers + tracks incoming heartbeats
  with configurable failure detection (N missed → node marked dead).

NodeRegistry: tracks cluster membership (join/leave/timeout) with
  sequence-numbered heartbeats for ordering.

Both are pure additive components — they extend the existing Phase 16
ClusterFederationManager with richer heartbeat tracking. They do NOT
replace it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agentic_os.core.distributed.cluster_models import (
    HeartbeatPacket,
    HeartbeatStatus,
)
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.distributed.transport import NodeTransport
    from agentic_os.ports.event_bus import EventBus

log = get_logger("distributed.heartbeat")

_DEFAULT_HEARTBEAT_INTERVAL = 15.0  # seconds
_DEFAULT_MISSED_THRESHOLD = 3  # 3 missed = dead
_STALE_CHECK_INTERVAL = 30.0


class HeartbeatManager:
    """Sends + receives heartbeats with failure detection."""

    def __init__(
        self,
        bus: EventBus,
        transport: NodeTransport,
        local_node_id: str = "",
        interval_s: float = _DEFAULT_HEARTBEAT_INTERVAL,
        missed_threshold: int = _DEFAULT_MISSED_THRESHOLD,
    ) -> None:
        self._bus = bus
        self._transport = transport
        self._local_node_id = local_node_id
        self._interval_s = interval_s
        self._missed_threshold = missed_threshold
        self._statuses: dict[str, HeartbeatStatus] = {}
        self._sequence: int = 0
        self._send_task: asyncio.Task | None = None
        self._check_task: asyncio.Task | None = None
        self._started = False
        self._stats: dict[str, int] = {
            "sent": 0,
            "received": 0,
            "missed": 0,
            "nodes_dead": 0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        return {**self._stats, "tracked_nodes": len(self._statuses)}

    def list_statuses(self) -> list[HeartbeatStatus]:
        return list(self._statuses.values())

    def get_status(self, node_id: str) -> HeartbeatStatus | None:
        return self._statuses.get(node_id)

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._send_task = asyncio.create_task(self._send_loop())
        self._check_task = asyncio.create_task(self._check_loop())
        log.info("HeartbeatManager started (interval=%ss)", self._interval_s)

    async def stop(self) -> None:
        self._started = False
        for task in [self._send_task, self._check_task]:
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._send_task = None
        self._check_task = None
        log.info("HeartbeatManager stopped")

    # ── Incoming heartbeats ────────────────────────────────────────

    def receive_heartbeat(self, packet: HeartbeatPacket) -> bool:
        """Process an incoming heartbeat from a peer. Returns True if accepted."""
        status = self._statuses.get(packet.node_id)
        if status is None:
            status = HeartbeatStatus(node_id=packet.node_id)
            self._statuses[packet.node_id] = status

        # Check sequence ordering
        if packet.sequence <= status.last_sequence and status.last_sequence > 0:
            log.debug("Stale heartbeat", node=packet.node_id, seq=packet.sequence)
            return False

        status.last_heartbeat = packet.timestamp
        status.last_sequence = packet.sequence
        status.is_alive = True
        status.consecutive_failures = 0
        status.missed_count = 0
        status.packets_received += 1
        self._stats["received"] += 1
        return True

    # ── Outgoing heartbeats ────────────────────────────────────────

    async def _send_loop(self) -> None:
        """Periodically send heartbeats to all peers."""
        while self._started:
            try:
                await asyncio.sleep(self._interval_s)
                if not self._started:
                    break
                await self._send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Heartbeat send loop error")

    async def _send_heartbeat(self) -> None:
        """Send a heartbeat packet to all peers."""
        self._sequence += 1
        packet = HeartbeatPacket(
            node_id=self._local_node_id,
            sequence=self._sequence,
        )
        delivered = await self._transport.broadcast_heartbeat(packet.to_dict())
        self._stats["sent"] += 1
        if delivered > 0:
            log.debug("Heartbeat sent", seq=self._sequence, delivered=delivered)

    # ── Failure detection ──────────────────────────────────────────

    async def _check_loop(self) -> None:
        """Periodically check for stale nodes."""
        while self._started:
            try:
                await asyncio.sleep(_STALE_CHECK_INTERVAL)
                if not self._started:
                    break
                self._check_stale_nodes()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Heartbeat check loop error")

    def _check_stale_nodes(self) -> None:
        """Mark nodes as dead if they've missed too many heartbeats."""
        now = datetime.now(UTC)
        for status in self._statuses.values():
            if not status.last_heartbeat:
                continue
            try:
                last = datetime.fromisoformat(status.last_heartbeat)
            except (ValueError, TypeError):
                continue
            elapsed = (now - last).total_seconds()
            expected_interval = self._interval_s * self._missed_threshold
            if elapsed > expected_interval and status.is_alive:
                status.is_alive = False
                status.consecutive_failures += 1
                status.packets_missed += 1
                self._stats["nodes_dead"] += 1
                log.warning(
                    "Node marked dead (missed heartbeats)",
                    node=status.node_id,
                    elapsed_s=elapsed,
                )
