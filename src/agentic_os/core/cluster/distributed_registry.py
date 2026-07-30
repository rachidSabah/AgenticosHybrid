"""Phase 16 — DistributedBrainRegistry.

Extends the existing BrainRegistry with remote brain tracking. Does
NOT replace BrainRegistry — it wraps it.

Local brains remain canonical in BrainRegistry. Remote brains are
stored in this wrapper's separate dict, keyed by ``(node_id, brain_id)``.
The combined view (local + remote) is exposed via ``list_all_distributed()``.

Sync triggers:
  - Node joins → fetch its brains (in production: HTTP GET /api/brains)
  - Node leaves → remove all its brains
  - Brain discovered (on remote node) → add to remote registry
  - Brain removed (on remote node) → remove from remote registry
  - Brain updated (on remote node) → update remote entry
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_os.core.cluster.domain import RemoteBrainRecord
from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from agentic_os.core.brains.registry import BrainRegistry
    from agentic_os.core.cluster.federation import ClusterFederationManager
    from agentic_os.ports.event_bus import EventBus

log = get_logger("cluster.distributed_registry")


class DistributedBrainRegistry:
    """Wrapper around BrainRegistry that adds remote brain tracking.

    The local BrainRegistry is the single source of truth for local
    brains. This class adds a parallel registry for remote brains and
    provides a unified view via ``list_all_distributed()``.
    """

    def __init__(
        self,
        local_registry: BrainRegistry,
        federation: ClusterFederationManager | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self._local = local_registry
        self._federation = federation
        self._bus = bus
        # remote_brains keyed by f"{node_id}:{brain_id}"
        self._remote: dict[str, RemoteBrainRecord] = {}
        # Index by node_id for fast node-level purges
        self._by_node: dict[str, set[str]] = {}
        self._sync_count = 0

    # ── Dependency injection ───────────────────────────────────────

    def set_federation(self, federation: ClusterFederationManager) -> None:
        self._federation = federation

    def set_bus(self, bus: EventBus) -> None:
        self._bus = bus

    # ── Remote Brain CRUD ──────────────────────────────────────────

    async def add_remote_brain(
        self,
        brain_id: str,
        node_id: str,
        display_name: str = "",
        provider: str = "",
        host: str = "",
        capabilities: tuple[str, ...] = (),
        health: float = 100.0,
        latency: float = 0.0,
        availability: float = 1.0,
        version: str = "1.0.0",
        metadata: dict[str, Any] | None = None,
    ) -> RemoteBrainRecord:
        """Add or update a remote brain. Publishes cluster.brain.discovered."""
        key = f"{node_id}:{brain_id}"
        record = RemoteBrainRecord(
            brain_id=brain_id,
            node_id=node_id,
            display_name=display_name,
            provider=provider,
            host=host,
            capabilities=tuple(capabilities),
            health=health,
            latency=latency,
            availability=availability,
            version=version,
            metadata=dict(metadata or {}),
        )
        self._remote[key] = record
        self._by_node.setdefault(node_id, set()).add(key)
        self._sync_count += 1
        await self._publish("cluster.brain.discovered", record.to_dict())
        log.info(
            "Remote brain discovered: %s on node %s (%s)",
            brain_id,
            node_id,
            display_name,
        )
        return record

    async def remove_remote_brain(self, brain_id: str, node_id: str) -> bool:
        """Remove a remote brain. Publishes cluster.brain.removed.

        Note: parameter order is (brain_id, node_id) to match the
        intuitive "remove brain X from node Y" reading. This is
        different from add_remote_brain() which also takes brain_id
        first, then node_id.
        """
        key = f"{node_id}:{brain_id}"
        if key not in self._remote:
            return False
        record = self._remote.pop(key)
        if node_id in self._by_node:
            self._by_node[node_id].discard(key)
            if not self._by_node[node_id]:
                del self._by_node[node_id]
        self._sync_count += 1
        await self._publish("cluster.brain.removed", record.to_dict())
        log.info("Remote brain removed: %s on node %s", brain_id, node_id)
        return True

    async def remove_all_for_node(self, node_id: str) -> int:
        """Remove all remote brains for a node (used when node leaves)."""
        keys = self._by_node.pop(node_id, set())
        count = 0
        for key in keys:
            record = self._remote.pop(key, None)
            if record is not None:
                count += 1
                await self._publish("cluster.brain.removed", record.to_dict())
        if count > 0:
            self._sync_count += 1
            log.info("Removed %d remote brains for node %s", count, node_id)
        return count

    async def update_remote_brain(
        self,
        brain_id: str,
        node_id: str,
        *,
        health: float | None = None,
        latency: float | None = None,
        availability: float | None = None,
        capabilities: tuple[str, ...] | None = None,
    ) -> RemoteBrainRecord | None:
        key = f"{node_id}:{brain_id}"
        record = self._remote.get(key)
        if record is None:
            return None
        if health is not None:
            record.health = health
        if latency is not None:
            record.latency = latency
        if availability is not None:
            record.availability = availability
        if capabilities is not None:
            record.capabilities = tuple(capabilities)
        from datetime import UTC, datetime

        record.last_synced = datetime.now(UTC).isoformat()
        self._sync_count += 1
        return record

    # ── Queries ────────────────────────────────────────────────────

    def get_remote_brain(self, brain_id: str, node_id: str) -> RemoteBrainRecord | None:
        return self._remote.get(f"{node_id}:{brain_id}")

    def list_remote_brains(self, node_id: str | None = None) -> list[RemoteBrainRecord]:
        if node_id is None:
            return list(self._remote.values())
        return [r for r in self._remote.values() if r.node_id == node_id]

    async def list_all_distributed(self) -> list[dict[str, Any]]:
        """Unified view: local brains + remote brains.

        Local brains come from BrainRegistry (canonical) and are tagged
        with ``scope: "local"``. Remote brains are tagged with
        ``scope: "remote"`` and include their node_id.
        """
        local_brains = await self._local.list_all()
        unified: list[dict[str, Any]] = []
        for b in local_brains:
            d = b.to_dict()
            d["scope"] = "local"
            d["node_id"] = self._federation.local_node_id if self._federation else "local"
            unified.append(d)
        for r in self._remote.values():
            d = r.to_dict()
            d["scope"] = "remote"
            d["id"] = r.brain_id  # normalize field name
            unified.append(d)
        return unified

    def list_remote_brains_for_capability(self, capability: str) -> list[dict[str, Any]]:
        """Find all REMOTE brains that provide a capability.

        Returns a list of dicts with ``brain_id``, ``node_id``, ``scope``,
        ``health``, ``latency`` so the scheduler can score candidates.

        For local brains, callers should use the async
        ``list_all_distributed()`` method (BrainRegistry.list_all is async).
        """
        results: list[dict[str, Any]] = []
        for r in self._remote.values():
            if capability in r.capabilities:
                results.append(
                    {
                        "brain_id": r.brain_id,
                        "node_id": r.node_id,
                        "scope": "remote",
                        "display_name": r.display_name,
                        "health": r.health,
                        "latency": r.latency,
                        "availability": r.availability,
                        "provider": r.provider,
                    }
                )
        return results

    # ── Sync from federation ───────────────────────────────────────

    async def sync_from_node(
        self,
        node_id: str,
        brains_payload: list[dict[str, Any]],
    ) -> int:
        """Sync remote brains for a node from a payload (e.g. HTTP response).

        Each entry in ``brains_payload`` should look like a BrainRecord.to_dict()
        output. This method is idempotent — calling it twice with the same
        payload will update existing entries rather than duplicate them.
        """
        # Build set of incoming brain IDs for diff
        incoming_ids = {str(b.get("id") or b.get("brain_id") or "") for b in brains_payload}
        incoming_ids.discard("")
        # Remove brains no longer present
        existing_keys = set(self._by_node.get(node_id, set()))
        for key in list(existing_keys):
            record = self._remote.get(key)
            brain_id_to_remove = record.brain_id if record else ""
            if brain_id_to_remove not in incoming_ids:
                await self.remove_remote_brain(brain_id_to_remove, node_id)
        # Add/update (use update path if brain already exists to avoid
        # emitting duplicate cluster.brain.discovered events)
        for b in brains_payload:
            brain_id = str(b.get("id") or b.get("brain_id") or "")
            if not brain_id:
                continue
            key = f"{node_id}:{brain_id}"
            existing = self._remote.get(key)
            if existing is not None:
                # Update in-place — don't re-emit discovered event
                existing.display_name = str(b.get("display_name") or b.get("name") or brain_id)
                existing.provider = str(b.get("provider") or b.get("vendor") or "")
                existing.host = str(b.get("host") or "")
                existing.capabilities = tuple(b.get("capabilities") or ())
                existing.health = float(b.get("health") or 100)
                existing.latency = float(b.get("latency") or 0)
                existing.availability = float(b.get("availability") or 1.0)
                existing.version = str(b.get("version") or "1.0.0")
                existing.metadata = b.get("metadata") or {}
                from datetime import UTC, datetime

                existing.last_synced = datetime.now(UTC).isoformat()
                self._sync_count += 1
            else:
                await self.add_remote_brain(
                    brain_id=brain_id,
                    node_id=node_id,
                    display_name=str(b.get("display_name") or b.get("name") or brain_id),
                    provider=str(b.get("provider") or b.get("vendor") or ""),
                    host=str(b.get("host") or ""),
                    capabilities=tuple(b.get("capabilities") or ()),
                    health=float(b.get("health") or 100),
                    latency=float(b.get("latency") or 0),
                    availability=float(b.get("availability") or 1.0),
                    version=str(b.get("version") or "1.0.0"),
                    metadata=b.get("metadata") or {},
                )
        return len(brains_payload)

    # ── Stats ──────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        local_count = 0
        # We can't call async list_all from sync context — use the internal dict
        try:
            local_count = len(self._local._brains)  # type: ignore[attr-defined]
        except Exception:
            pass
        return {
            "local_brains": local_count,
            "remote_brains": len(self._remote),
            "total_brains": local_count + len(self._remote),
            "nodes_with_remote_brains": len(self._by_node),
            "sync_count": self._sync_count,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "remote_brains": [r.to_dict() for r in self._remote.values()],
            "stats": self.stats(),
        }

    # ── Internal ───────────────────────────────────────────────────

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type=topic,
                    source="cluster.distributed_registry",
                    topic=topic,
                    payload=payload,
                )
            )
        except Exception:
            log.exception("Failed to publish %s", topic)
