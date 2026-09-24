"""Agent cgroups — per-agent resource control groups enforced on the bus.

The container world uses cgroups to give every process a hard slice of the
machine. Agents consume a different machine: tokens, wall clock, tool calls,
and concurrent LLM slots. This module gives every agent the same hard-slice
discipline, measured and enforced on the event bus:

* quotas per agent: token budget, wall-clock budget, tool-call cap, and a
  cap on concurrent LLM slots;
* usage accounting from REAL events published on the bus (cost.recorded,
  mcp.tool_invoked) plus an explicit operator/integration accounting API;
* mid-flight control: freeze (pause the clock, refuse admission), resume,
  and kill (terminal) — the same verbs a process supervisor has;
* an append-only measurement ledger per agent so every number shown is a
  number that was actually measured, when it was measured.

Honesty rules: usage is only what real events / real calls reported; a
frozen or killed agent is refused admission with the exact reason; nothing
is estimated ahead of time and no state is fabricated.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("cgroups.agent_cgroups")

DEFAULT_CGROUPS_DIR = "~/.agentic_os/data/cgroups"

STATE_RUNNING = "running"
STATE_FROZEN = "frozen"
STATE_KILLED = "killed"

# Bus topics carrying usage payloads; routing is by envelope topic, so we
# subscribe on the system topic and match the envelope TYPE inside the handler.
USAGE_EVENT_TYPES = ("cost.recorded", "mcp.tool_invoked")
BUS_TOPIC = "system"


class CgroupError(ValueError):
    """Operator-facing cgroup error (mapped to HTTP 400/404)."""


class AdmissionRefused(CgroupError):
    """Admission refused because of cgroup state or an exhausted quota."""


@dataclass
class AgentQuota:
    """Hard resource slice for one agent. None = no limit on that axis."""

    token_budget: int | None = None
    wall_clock_s: float | None = None
    tool_call_cap: int | None = None
    max_concurrent_llm: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class AgentCgroup:
    """Measured state of one agent's control group."""

    agent_id: str
    state: str = STATE_RUNNING
    quota: AgentQuota = field(default_factory=AgentQuota)
    tokens_used: int = 0
    tool_calls: int = 0
    llm_slots_active: int = 0
    activated_at: float | None = None  # first admission (monotonic clock)
    frozen_at: float | None = None
    frozen_total_s: float = 0.0  # accumulated frozen time (paused clock)
    killed_reason: str = ""
    exceeded_dimension: str = ""

    def wall_clock_s(self, now: float) -> float:
        """Measured wall clock EXCLUDING frozen intervals (freeze pauses it)."""
        if self.activated_at is None:
            return 0.0
        end = self.frozen_at if (self.state == STATE_FROZEN and self.frozen_at) else now
        return max(0.0, end - self.activated_at - self.frozen_total_s)

    def to_dict(self, now: float) -> dict[str, Any]:
        d = asdict(self)
        d.pop("quota", None)
        d["quota"] = self.quota.to_dict()
        d["wall_clock_s"] = round(self.wall_clock_s(now), 3)
        d.pop("activated_at", None)
        d.pop("frozen_at", None)
        return d


class AgentCgroupManager:
    """Registry of per-agent control groups with bus-level accounting."""

    def __init__(self, data_dir: str = "", bus: Any = None) -> None:
        base = Path(data_dir or os.path.expanduser(DEFAULT_CGROUPS_DIR))
        base.mkdir(parents=True, exist_ok=True)
        self._dir = base
        self._bus = bus
        self._groups: dict[str, AgentCgroup] = {}
        self._ledgers: dict[str, list[dict[str, Any]]] = {}
        self._bg_tasks: set[asyncio.Task] = set()
        self._load_ledgers()

    # ── persistence (append-only measurement ledger) ─────────────────────

    def _ledger_path(self, agent_id: str) -> Path:
        safe = agent_id.replace("/", "_").replace("\\", "_") or "unknown"
        return self._dir / f"{safe}.jsonl"

    def _load_ledgers(self) -> None:
        for p in self._dir.glob("*.jsonl"):
            rows: list[dict[str, Any]] = []
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            continue
            except Exception:
                continue
            self._ledgers[p.stem] = rows

    def _append(self, agent_id: str, kind: str, **fields: Any) -> None:
        entry = {"ts": time.time(), "kind": kind, **fields}
        self._ledgers.setdefault(agent_id, []).append(entry)
        try:
            with self._ledger_path(agent_id).open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            log.debug("cgroup ledger append failed", exc_info=True)

    def ledger(self, agent_id: str, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._ledgers.get(agent_id, [])
        return rows[-limit:]

    # ── quota management ─────────────────────────────────────────────────

    def set_quota(self, agent_id: str, quota: AgentQuota) -> dict[str, Any]:
        if not agent_id.strip():
            raise CgroupError("agent_id is required")
        group = self._groups.get(agent_id)
        if group is None:
            group = AgentCgroup(agent_id=agent_id)
            self._groups[agent_id] = group
        if group.state == STATE_KILLED:
            raise CgroupError(f"agent {agent_id!r} is killed; quotas cannot be set")
        group.quota = quota
        self._append(agent_id, "quota_set", quota=quota.to_dict())
        self._publish("cgroup.quota_set", {"agent_id": agent_id, "quota": quota.to_dict()})
        return self.status(agent_id)

    def clear_quota(self, agent_id: str) -> dict[str, Any]:
        group = self._groups.get(agent_id)
        if group is None:
            raise CgroupError(f"no control group exists for agent {agent_id!r}")
        group.quota = AgentQuota()
        self._append(agent_id, "quota_cleared")
        return self.status(agent_id)

    # ── admission & accounting ───────────────────────────────────────────

    def _group(self, agent_id: str) -> AgentCgroup:
        group = self._groups.get(agent_id)
        if group is None:
            # No control group configured: nothing to enforce. Honest no-op.
            group = AgentCgroup(agent_id=agent_id)
            self._groups[agent_id] = group
        return group

    def admit(self, agent_id: str, llm_slot: bool = False) -> dict[str, Any]:
        """Check admission against state + every quota axis. Raises AdmissionRefused."""
        group = self._group(agent_id)
        if group.state == STATE_KILLED:
            raise AdmissionRefused(
                f"agent {agent_id!r} is killed by its control group: {group.killed_reason}"
            )
        if group.state == STATE_FROZEN:
            raise AdmissionRefused(f"agent {agent_id!r} is frozen by its control group")
        now = time.monotonic()
        if group.activated_at is None:
            group.activated_at = now
            self._append(agent_id, "activated")
        q = group.quota
        if q.token_budget is not None and group.tokens_used >= q.token_budget:
            self._exceeded(agent_id, "token_budget")
            raise AdmissionRefused(
                f"token budget exhausted: {group.tokens_used}/{q.token_budget} tokens used"
            )
        if q.wall_clock_s is not None and group.wall_clock_s(now) >= q.wall_clock_s:
            self._exceeded(agent_id, "wall_clock_s")
            raise AdmissionRefused(
                f"wall-clock budget exhausted: {group.wall_clock_s(now):.1f}/"
                f"{q.wall_clock_s:.1f}s used"
            )
        if q.tool_call_cap is not None and group.tool_calls >= q.tool_call_cap:
            self._exceeded(agent_id, "tool_call_cap")
            raise AdmissionRefused(
                f"tool-call cap reached: {group.tool_calls}/{q.tool_call_cap} calls"
            )
        if llm_slot:
            if q.max_concurrent_llm is not None and group.llm_slots_active >= q.max_concurrent_llm:
                self._exceeded(agent_id, "max_concurrent_llm")
                raise AdmissionRefused(
                    f"concurrent LLM slots exhausted: "
                    f"{group.llm_slots_active}/{q.max_concurrent_llm} active"
                )
            group.llm_slots_active += 1
            self._append(agent_id, "llm_slot_acquired", active=group.llm_slots_active)
        return self.status(agent_id)

    def record_tokens(self, agent_id: str, tokens: int) -> dict[str, Any]:
        tokens = int(tokens)
        if tokens < 0:
            raise CgroupError("tokens must be >= 0")
        group = self._group(agent_id)
        group.tokens_used += tokens
        self._append(agent_id, "tokens", tokens=tokens, total=group.tokens_used)
        q = group.quota
        if (
            q.token_budget is not None
            and group.tokens_used >= q.token_budget
            and group.state == STATE_RUNNING
        ):
            self._exceeded(agent_id, "token_budget")
        return self.status(agent_id)

    def record_tool_call(self, agent_id: str) -> dict[str, Any]:
        group = self._group(agent_id)
        group.tool_calls += 1
        self._append(agent_id, "tool_call", total=group.tool_calls)
        q = group.quota
        if (
            q.tool_call_cap is not None
            and group.tool_calls >= q.tool_call_cap
            and group.state == STATE_RUNNING
        ):
            self._exceeded(agent_id, "tool_call_cap")
        return self.status(agent_id)

    def release_llm_slot(self, agent_id: str) -> dict[str, Any]:
        group = self._group(agent_id)
        if group.llm_slots_active > 0:
            group.llm_slots_active -= 1
            self._append(agent_id, "llm_slot_released", active=group.llm_slots_active)
        return self.status(agent_id)

    def _exceeded(self, agent_id: str, dimension: str) -> None:
        group = self._group(agent_id)
        group.exceeded_dimension = dimension
        self._append(agent_id, "exceeded", dimension=dimension)
        self._publish(
            "cgroup.exceeded",
            {"agent_id": agent_id, "dimension": dimension, "status": group.state},
        )

    # ── mid-flight control: freeze / resume / kill ───────────────────────

    def freeze(self, agent_id: str) -> dict[str, Any]:
        group = self._group(agent_id)
        if group.state == STATE_KILLED:
            raise CgroupError(f"agent {agent_id!r} is already killed")
        if group.state == STATE_FROZEN:
            return self.status(agent_id)
        group.state = STATE_FROZEN
        group.frozen_at = time.monotonic()
        self._append(agent_id, "frozen")
        self._publish("cgroup.frozen", {"agent_id": agent_id})
        return self.status(agent_id)

    def resume(self, agent_id: str) -> dict[str, Any]:
        group = self._group(agent_id)
        if group.state == STATE_KILLED:
            raise CgroupError("a killed control group cannot be resumed")
        if group.state != STATE_FROZEN:
            return self.status(agent_id)
        now = time.monotonic()
        if group.frozen_at is not None:
            group.frozen_total_s += now - group.frozen_at
            group.frozen_at = None
        group.state = STATE_RUNNING
        self._append(agent_id, "resumed", frozen_total_s=round(group.frozen_total_s, 3))
        self._publish("cgroup.resumed", {"agent_id": agent_id})
        return self.status(agent_id)

    def kill(self, agent_id: str, reason: str = "") -> dict[str, Any]:
        group = self._group(agent_id)
        if group.state == STATE_FROZEN and group.frozen_at is not None:
            # settle the clock before the terminal transition
            group.frozen_total_s += time.monotonic() - group.frozen_at
            group.frozen_at = None
        group.state = STATE_KILLED
        group.killed_reason = str(reason)
        self._append(agent_id, "killed", reason=str(reason))
        self._publish("cgroup.killed", {"agent_id": agent_id, "reason": str(reason)})
        return self.status(agent_id)

    # ── status ───────────────────────────────────────────────────────────

    def status(self, agent_id: str) -> dict[str, Any]:
        group = self._groups.get(agent_id)
        if group is None:
            raise CgroupError(f"no control group exists for agent {agent_id!r}")
        return group.to_dict(time.monotonic())

    def status_all(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        return [g.to_dict(now) for g in self._groups.values()]

    # ── bus integration ──────────────────────────────────────────────────

    async def attach_bus(self, bus: Any) -> list[str]:
        """Subscribe to the system topic; usage events are matched by type."""
        self._bus = bus
        subs: list[str] = []
        try:
            sub = await bus.subscribe(BUS_TOPIC, self._on_bus_event)
            subs.append(sub)
        except Exception:
            log.debug("cgroup bus subscribe failed", exc_info=True)
        return subs

    async def _on_bus_event(self, envelope: Any) -> None:
        """Account real usage events published on the bus."""
        try:
            etype = str(getattr(envelope, "type", ""))
            if etype not in USAGE_EVENT_TYPES:
                return
            payload = getattr(envelope, "payload", None) or {}
            agent_id = str(
                payload.get("agent_id")
                or payload.get("agent")
                or getattr(envelope, "source", "")
                or ""
            )
            if not agent_id:
                return
            if etype == "mcp.tool_invoked":
                self.record_tool_call(agent_id)
                return
            tokens = 0
            if payload.get("total_tokens") or payload.get("tokens"):
                tokens = int(payload.get("total_tokens") or payload.get("tokens") or 0)
            elif payload.get("tokens_in") or payload.get("tokens_out"):
                tokens = int(payload.get("tokens_in") or 0) + int(payload.get("tokens_out") or 0)
            if tokens:
                self.record_tokens(agent_id, tokens)
        except Exception:
            log.debug("cgroup bus accounting failed", exc_info=True)

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        try:
            from agentic_os.domain.events import EventEnvelope

            envelope = EventEnvelope(
                type=event_type,
                source="cgroups.agent_cgroups",
                topic="system",
                payload=payload,
            )
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (sync context): skip bus publish honestly.
            log.debug("cgroup publish skipped: no running event loop")
            return
        except Exception:
            log.debug("cgroup event publish failed", exc_info=True)
            return
        task = loop.create_task(self._apublish(envelope))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _apublish(self, envelope: Any) -> None:
        try:
            await self._bus.publish(envelope)
        except Exception:
            log.debug("cgroup bus publish failed", exc_info=True)


# Process singleton wired lazily by the API layer with the live bus.
agent_cgroup_manager: AgentCgroupManager | None = None
_cgroup_lock = asyncio.Lock()


async def get_agent_cgroup_manager(bus: Any = None) -> AgentCgroupManager:
    global agent_cgroup_manager
    async with _cgroup_lock:
        if agent_cgroup_manager is None:
            manager = AgentCgroupManager(bus=bus)
            if bus is not None:
                await manager.attach_bus(bus)
            agent_cgroup_manager = manager
        return agent_cgroup_manager
