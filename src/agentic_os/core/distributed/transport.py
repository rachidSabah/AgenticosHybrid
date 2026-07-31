"""Phase 17 — Transport layer for inter-node communication.

Provides an HTTP-based transport for:
  - Sending heartbeats to peer nodes
  - Dispatching tasks to remote nodes
  - Propagating events across the cluster
  - Replicating state entries

The transport uses httpx for async HTTP calls. In a real deployment,
each AgenticOS node exposes its own REST API; the transport calls the
peer node's /api/distributed/* endpoints.

For single-node deployments (no peers), all transport calls return
empty/default results — fully backward compatible.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agentic_os.infrastructure.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger("distributed.transport")

# Default timeout for inter-node HTTP calls
_DEFAULT_TIMEOUT_S = 10.0
# Max concurrent in-flight requests per peer
_MAX_CONCURRENT_PER_PEER = 10


class NodeTransport:
    """HTTP transport for inter-node communication.

    Wraps httpx.AsyncClient with connection pooling and timeout handling.
    In single-node mode (no peers configured), all methods return safe
    defaults without making any network calls.
    """

    def __init__(self, local_node_id: str = "", local_base_url: str = "") -> None:
        self._local_node_id = local_node_id
        self._local_base_url = local_base_url
        self._peers: dict[str, str] = {}  # node_id → base_url
        self._client: Any = None  # httpx.AsyncClient (lazy init)
        self._stats: dict[str, int] = {
            "requests_sent": 0,
            "requests_succeeded": 0,
            "requests_failed": 0,
            "timeouts": 0,
        }
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    @property
    def local_node_id(self) -> str:
        return self._local_node_id

    @property
    def stats(self) -> dict[str, Any]:
        return {**self._stats, "peer_count": len(self._peers)}

    # ── Peer management ────────────────────────────────────────────

    def register_peer(self, node_id: str, base_url: str) -> None:
        """Register a peer node's base URL for communication."""
        self._peers[node_id] = base_url.rstrip("/")
        self._semaphores[node_id] = asyncio.Semaphore(_MAX_CONCURRENT_PER_PEER)
        log.info("Peer registered", peer=node_id, url=base_url)

    def unregister_peer(self, node_id: str) -> None:
        self._peers.pop(node_id, None)
        self._semaphores.pop(node_id, None)
        log.info("Peer unregistered", peer=node_id)

    def get_peer_url(self, node_id: str) -> str | None:
        return self._peers.get(node_id)

    def list_peers(self) -> dict[str, str]:
        return dict(self._peers)

    # ── HTTP methods ───────────────────────────────────────────────

    async def _ensure_client(self) -> Any:
        """Lazy-init the httpx client."""
        if self._client is None:
            try:
                import httpx

                self._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(_DEFAULT_TIMEOUT_S),
                    limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
                )
            except ImportError:
                log.warning("httpx not available — transport disabled")
                return None
        return self._client

    async def send_heartbeat(
        self, peer_node_id: str, heartbeat: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Send a heartbeat packet to a peer node."""
        url = self._peers.get(peer_node_id)
        if not url:
            return None
        result = await self._post(f"{url}/api/distributed/heartbeat", heartbeat)
        if result is not None:
            return result
        return None

    async def dispatch_task(self, peer_node_id: str, task: dict[str, Any]) -> dict[str, Any] | None:
        """Dispatch a task to a remote node for execution."""
        url = self._peers.get(peer_node_id)
        if not url:
            return None
        return await self._post(f"{url}/api/distributed/tasks/dispatch", task)

    async def propagate_event(self, peer_node_id: str, event: dict[str, Any]) -> bool:
        """Propagate an event to a peer node. Returns True if acknowledged."""
        url = self._peers.get(peer_node_id)
        if not url:
            return False
        result = await self._post(f"{url}/api/distributed/events", event)
        return result is not None

    async def replicate_state(self, peer_node_id: str, entry: dict[str, Any]) -> bool:
        """Replicate a state entry to a peer node."""
        url = self._peers.get(peer_node_id)
        if not url:
            return False
        result = await self._post(f"{url}/api/distributed/replicate", entry)
        return result is not None

    async def request_vote(
        self, peer_node_id: str, vote_request: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Request a leader election vote from a peer."""
        url = self._peers.get(peer_node_id)
        if not url:
            return None
        return await self._post(f"{url}/api/distributed/vote", vote_request)

    async def broadcast_heartbeat(self, heartbeat: dict[str, Any]) -> int:
        """Broadcast a heartbeat to all peers. Returns count of successful sends."""
        if not self._peers:
            return 0
        results = await asyncio.gather(
            *[self.send_heartbeat(pid, heartbeat) for pid in self._peers],
            return_exceptions=True,
        )
        return sum(1 for r in results if r is not None)

    async def broadcast_event(self, event: dict[str, Any]) -> int:
        """Broadcast an event to all peers. Returns count of successful propagations."""
        if not self._peers:
            return 0
        results = await asyncio.gather(
            *[self.propagate_event(pid, event) for pid in self._peers],
            return_exceptions=True,
        )
        return sum(1 for r in results if r is True)

    # ── Internal ───────────────────────────────────────────────────

    async def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any] | None:
        """Make a POST request. Returns parsed JSON or None on failure."""
        client = await self._ensure_client()
        if client is None:
            return None
        self._stats["requests_sent"] += 1
        try:
            resp = await client.post(url, json=body, timeout=_DEFAULT_TIMEOUT_S)
            if resp.status_code < 300:
                self._stats["requests_succeeded"] += 1
                try:
                    return resp.json()
                except Exception:
                    return {"status": "ok"}
            else:
                self._stats["requests_failed"] += 1
                log.debug("POST failed", url=url, status=resp.status_code)
                return None
        except TimeoutError:
            self._stats["timeouts"] += 1
            return None
        except Exception:
            self._stats["requests_failed"] += 1
            return None

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
