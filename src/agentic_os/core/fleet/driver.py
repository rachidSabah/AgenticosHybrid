"""Cross-CLI Agent Fleet — drive every discovered agentic CLI from one place.

The discovery layer already finds installed agentic CLIs (claude, codex,
aider, goose, ...). This module makes them DRIVABLE:

* documented headless one-shot adapters for known CLIs (real command
  templates, executed without a shell);
* a generic adapter for operator-configured CLIs (explicit args prefix
  required — AgenticOS never guesses how to drive an unknown binary);
* capability declarations persisted by the operator;
* bidding that ranks brains using ONLY measured history (success rate and
  average duration of real past dispatches) — never invented scores;
* dispatch with real subprocess execution, wall-clock measurement, real
  exit codes, stdout/stderr capture, and a persisted run history.

Honesty rules: a dispatch result reports exactly what the process did.
Failures show the real stderr. Nothing is simulated.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("fleet.driver")

DEFAULT_FLEET_DIR = "~/.agentic_os/data/fleet"
_MAX_PREVIEW = 2000

# Documented headless one-shot invocation templates. {prompt} is substituted
# with the operator's prompt (never shell-interpolated: argv is passed
# directly, shell=False). A template failing on a given CLI version is
# reported honestly via the process's real stderr and exit code.
CLI_ADAPTERS: dict[str, dict[str, Any]] = {
    "claude": {"template": ["claude", "-p", "{prompt}"], "note": "claude-code headless print mode"},
    "codex": {"template": ["codex", "exec", "{prompt}"], "note": "codex exec"},
    "gemini": {"template": ["gemini", "-p", "{prompt}"], "note": "gemini cli prompt mode"},
    "qwen": {"template": ["qwen", "-p", "{prompt}"], "note": "qwen cli prompt mode"},
    "aider": {
        "template": ["aider", "--message", "{prompt}", "--yes", "--no-git", "--exit"],
        "note": "aider one-shot edit mode",
    },
    "goose": {"template": ["goose", "run", "--text", "{prompt}", "--quiet"], "note": "goose run"},
    "opencode": {"template": ["opencode", "run", "{prompt}"], "note": "opencode run"},
}


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _creation_flags() -> int:
    """CREATE_NO_WINDOW on Windows so headless dispatch never opens a shell."""
    if sys.platform == "win32":
        import subprocess

        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


class FleetError(ValueError):
    """Operator-facing fleet error (mapped to HTTP 400/404)."""


@dataclass
class FleetRunRecord:
    run_id: str = field(default_factory=lambda: f"fleet-run-{uuid.uuid4().hex[:8]}")
    agent_id: str = ""
    agent_name: str = ""
    adapter: str = ""
    prompt_preview: str = ""
    started_at: str = field(default_factory=_now_iso)
    duration_ms: int = 0
    exit_code: int | None = None
    status: str = "running"
    stdout_preview: str = ""
    stderr_preview: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class FleetManager:
    """Fleet registry, bidding, and real dispatch over discovered agent CLIs."""

    def __init__(
        self,
        data_dir: str = "",
        discovery_getter: Callable[[], list[Any]] | None = None,
        bus: Any = None,
    ) -> None:
        base = Path(data_dir or os.path.expanduser(DEFAULT_FLEET_DIR))
        base.mkdir(parents=True, exist_ok=True)
        self._store_path = base / "fleet.json"
        self._runs_path = base / "fleet-runs.jsonl"
        self._discovery_getter = discovery_getter
        self._bus = bus

    # ── operator store (capabilities / generic args) ────────────────────

    def _load_store(self) -> dict[str, Any]:
        try:
            return json.loads(self._store_path.read_text(encoding="utf-8"))
        except Exception:
            return {"capabilities": {}, "args_prefix": {}}

    def _save_store(self, store: dict[str, Any]) -> None:
        self._store_path.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")

    def set_capabilities(self, agent_id: str, capabilities: list[str]) -> dict[str, Any]:
        store = self._load_store()
        caps = sorted({str(c).strip().lower() for c in capabilities if str(c).strip()})
        store.setdefault("capabilities", {})[agent_id] = caps
        self._save_store(store)
        return {"agent_id": agent_id, "capabilities": caps}

    def set_args_prefix(self, agent_id: str, args_prefix: list[str]) -> dict[str, Any]:
        store = self._load_store()
        store.setdefault("args_prefix", {})[agent_id] = [str(a) for a in args_prefix]
        self._save_store(store)
        return {"agent_id": agent_id, "args_prefix": store["args_prefix"][agent_id]}

    # ── run history (measured) ───────────────────────────────────────────

    def _append_run(self, record: FleetRunRecord) -> None:
        with self._runs_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), default=str) + "\n")

    def _runs(self, agent_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if not self._runs_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            lines = self._runs_path.read_text(encoding="utf-8").strip().split("\n")
        except Exception:
            return []
        for line in lines:
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if agent_id and d.get("agent_id") != agent_id:
                continue
            rows.append(d)
        rows.sort(key=lambda r: str(r.get("started_at")), reverse=True)
        return rows[:limit]

    def stats_for(self, agent_id: str) -> dict[str, Any]:
        runs = self._runs(agent_id=agent_id, limit=1000)
        finished = [r for r in runs if r.get("status") in ("completed", "failed")]
        if not finished:
            return {
                "runs": len(runs),
                "succeeded": 0,
                "failed": 0,
                "success_rate": None,
                "avg_duration_ms": None,
            }
        succeeded = sum(1 for r in finished if r["status"] == "completed")
        return {
            "runs": len(runs),
            "succeeded": succeeded,
            "failed": len(finished) - succeeded,
            "success_rate": round(succeeded / len(finished), 4),
            "avg_duration_ms": int(
                sum(int(r.get("duration_ms") or 0) for r in finished) / len(finished)
            ),
        }

    # ── fleet listing ────────────────────────────────────────────────────

    def _agents(self) -> list[Any]:
        if self._discovery_getter is None:
            return []
        try:
            return list(self._discovery_getter() or [])
        except Exception:
            return []

    def fleet(self) -> list[dict[str, Any]]:
        store = self._load_store()
        out: list[dict[str, Any]] = []
        for a in self._agents():
            agent_id = getattr(a, "id", "")
            name = getattr(a, "name", "")
            is_agent = bool(getattr(a, "is_agent", lambda: False)())
            adapter = (
                name.lower()
                if name.lower() in CLI_ADAPTERS
                else ("generic" if is_agent else "none")
            )
            declared = list(getattr(a, "capabilities", []) or [])
            extra = store.get("capabilities", {}).get(agent_id, [])
            declared = sorted({str(c) for c in declared} | {str(c) for c in extra})
            if adapter in CLI_ADAPTERS:
                note = str(CLI_ADAPTERS[adapter].get("note", ""))
            elif adapter == "generic":
                note = "operator must configure an args prefix before dispatch"
            else:
                note = "no headless adapter - probe only"
            out.append(
                {
                    "agent_id": agent_id,
                    "name": name,
                    "kind": getattr(a, "kind", "unknown"),
                    "executable_path": getattr(a, "executable_path", ""),
                    "command": getattr(a, "command", ""),
                    "status": getattr(a, "status", "unknown"),
                    "is_active": is_agent and getattr(a, "status", "") in _ACTIVE_STATUSES(),
                    "adapter": adapter,
                    "adapter_note": note,
                    "declared_capabilities": declared,
                    "args_prefix": store.get("args_prefix", {}).get(agent_id, []),
                    "stats": self.stats_for(agent_id),
                }
            )
        return out

    # ── bidding (measured history only) ──────────────────────────────────

    def bid(
        self, task_description: str, required_capabilities: list[str], top: int = 5
    ) -> dict[str, Any]:
        required = {str(c).strip().lower() for c in required_capabilities if str(c).strip()}
        eligible: list[dict[str, Any]] = []
        for row in self.fleet():
            if not row["is_active"] or row["adapter"] == "none":
                continue
            caps = {str(c).lower() for c in row["declared_capabilities"]}
            if not required.issubset(caps):
                continue
            eligible.append(row)

        # Rank by measured success rate, then measured average duration.
        # Brains with no history rank last — unknown is not a score.
        def _rank(row: dict[str, Any]) -> tuple[int, float, int]:
            s = row["stats"]
            rate = s.get("success_rate")
            avg = s.get("avg_duration_ms")
            return (
                0 if rate is not None else 1,
                -(rate if rate is not None else 0.0),
                avg if avg is not None else 10**9,
            )

        eligible.sort(key=_rank)
        return {
            "task_description": task_description,
            "required_capabilities": sorted(required),
            "eligible_count": len(eligible),
            "ranking": [
                {
                    "agent_id": r["agent_id"],
                    "name": r["name"],
                    "adapter": r["adapter"],
                    "declared_capabilities": r["declared_capabilities"],
                    "stats": r["stats"],
                }
                for r in eligible[: max(1, top)]
            ],
        }

    # ── dispatch (real subprocess, shell=False) ──────────────────────────

    def _argv_for(self, agent: Any, adapter: str, prompt: str) -> list[str]:
        name = getattr(agent, "name", "").lower()
        exe = getattr(agent, "executable_path", "") or getattr(agent, "command", "")
        if adapter in CLI_ADAPTERS:
            template = list(CLI_ADAPTERS[adapter]["template"])
            argv = [exe if exe else template[0]] + template[1:]
        else:
            store = self._load_store()
            prefix = store.get("args_prefix", {}).get(getattr(agent, "id", ""))
            if prefix is None:
                raise FleetError(
                    "no headless adapter for this CLI and no operator args prefix "
                    "configured - AgenticOS will not guess how to drive it"
                )
            # An EMPTY prefix is a deliberate operator configuration (no extra
            # args, prompt as the final argument) - only an absent key refuses.
            argv = [exe if exe else name] + [str(a) for a in prefix]
        replaced = False
        out: list[str] = []
        for part in argv:
            if "{prompt}" in part:
                out.append(part.replace("{prompt}", prompt))
                replaced = True
            else:
                out.append(part)
        if not replaced:
            out.append(prompt)
        return out

    async def dispatch(self, agent_id: str, prompt: str, timeout_s: int = 120) -> dict[str, Any]:
        agents = {getattr(a, "id", ""): a for a in self._agents()}
        agent = agents.get(agent_id)
        if agent is None:
            raise FleetError(f"agent {agent_id!r} is not in the current discovery snapshot")
        name = getattr(agent, "name", "").lower()
        is_agent = bool(getattr(agent, "is_agent", lambda: False)())
        adapter = name if name in CLI_ADAPTERS else ("generic" if is_agent else "none")
        if adapter == "none":
            raise FleetError(
                "this entry has no headless adapter and is not an agent - dispatch refused"
            )
        argv = self._argv_for(agent, adapter, prompt)

        record = FleetRunRecord(
            agent_id=agent_id,
            agent_name=getattr(agent, "name", ""),
            adapter=adapter,
            prompt_preview=prompt[:_MAX_PREVIEW],
        )
        started = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=_creation_flags(),
                env={**os.environ, "NO_COLOR": "1"},
            )
            try:
                out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                record.duration_ms = int((time.monotonic() - started) * 1000)
                record.status = "timeout"
                record.error = f"no exit within {timeout_s}s - process killed"
                self._append_run(record)
                await self._publish(record)
                return record.to_dict()
            record.duration_ms = int((time.monotonic() - started) * 1000)
            record.exit_code = proc.returncode
            record.stdout_preview = (out_b or b"").decode("utf-8", "replace")[:_MAX_PREVIEW]
            record.stderr_preview = (err_b or b"").decode("utf-8", "replace")[:_MAX_PREVIEW]
            record.status = "completed" if proc.returncode == 0 else "failed"
        except FileNotFoundError as exc:
            record.duration_ms = int((time.monotonic() - started) * 1000)
            record.status = "failed"
            record.error = f"executable not found: {exc}"
        except OSError as exc:
            record.duration_ms = int((time.monotonic() - started) * 1000)
            record.status = "failed"
            record.error = f"os error: {exc}"
        self._append_run(record)
        await self._publish(record)
        return record.to_dict()

    async def _publish(self, record: FleetRunRecord) -> None:
        if self._bus is None:
            return
        try:
            from agentic_os.domain.events import EventEnvelope

            await self._bus.publish(
                EventEnvelope(
                    type="fleet.run.finished",
                    source="fleet.driver",
                    topic="system",
                    payload=record.to_dict(),
                )
            )
        except Exception:
            log.debug("fleet event publish failed", exc_info=True)

    def runs(self, agent_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return self._runs(agent_id=agent_id, limit=limit)


def _ACTIVE_STATUSES() -> frozenset[str]:
    from agentic_os.core.brains.schema import ACTIVE_STATUSES

    return ACTIVE_STATUSES


# Process singleton wired lazily with the live discovery engine.
fleet_manager: FleetManager | None = None


def get_fleet_manager() -> FleetManager:
    global fleet_manager
    if fleet_manager is None:
        from agentic_os.core.brains.discovery_engine import agent_discovery_engine

        fleet_manager = FleetManager(
            discovery_getter=agent_discovery_engine.get_all,
        )
    return fleet_manager
