"""Cost ledger — measured spend, per-agent/model/task aggregation, forecasts.

The cockpit shows money the way it actually happened:

* **Recording** — the ledger subscribes to the bus and records real
  cost-bearing events (``orchestration.cost_recorded``,
  ``cost.recorded``), plus an explicit operator/integration endpoint.
  Every entry keeps its true timestamp, the producer's cost value, and
  whatever dimensions the producer supplied (agent, plan/task, model).
  Dimensions a producer did not supply stay empty — they are never
  inferred.
* **Aggregation** — totals and breakdowns per agent, per plan/task, per
  model, and per day, computed from recorded entries only. No entries
  means NO DATA, not a zero-dollar lie... a zero total with zero entries
  is shown as "no cost data recorded".
* **Burn rate & forecast** — burn rate is measured over a real window of
  recorded entries; the forecast is that measured rate projected forward
  linearly. The UI labels it as a projection of measured history, which
  is exactly what it is.
* **Budget alerts** — an operator budget with alert thresholds; crossing
  a threshold (measured) publishes ``cost.budget.alert`` on the bus and
  records the alert. Resetting the budget resets alerts.

All entries persist to an append-only JSONL ledger.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("costs.ledger")

DEFAULT_COSTS_DIR = "~/.agentic_os/data/costs"

# Event types the ledger records (matched by envelope type on the system topic).
COST_EVENT_TYPES = ("cost.recorded", "orchestration.cost_recorded")
BUS_TOPIC = "system"

DEFAULT_ALERT_THRESHOLDS = (0.5, 0.8, 1.0)


class CostLedgerError(ValueError):
    """Operator-facing cost ledger error (mapped to HTTP 400/404)."""


def _now() -> float:
    return time.time()


def _day_of(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")


class CostLedger:
    """Append-only measured cost ledger with aggregation and alerts."""

    def __init__(self, data_dir: str = "", bus: Any = None) -> None:
        base = Path(data_dir or os.path.expanduser(DEFAULT_COSTS_DIR))
        base.mkdir(parents=True, exist_ok=True)
        self._dir = base
        self._ledger_path = base / "cost-ledger.jsonl"
        self._state_path = base / "budget.json"
        self._entries: list[dict[str, Any]] = []
        self._alerts: list[dict[str, Any]] = []
        self._budget: dict[str, Any] = {"total_usd": None, "crossed": []}
        self._bus = bus
        self._bg_tasks: set[asyncio.Task] = set()
        self._load()

    # ── persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._ledger_path.exists():
            try:
                for line in self._ledger_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        self._entries.append(json.loads(line))
                    except Exception:
                        continue
            except Exception:
                log.debug("cost ledger load failed", exc_info=True)
        if self._state_path.exists():
            try:
                d = json.loads(self._state_path.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    self._budget = {
                        "total_usd": d.get("total_usd"),
                        "crossed": list(d.get("crossed", [])),
                    }
                    self._alerts = list(d.get("alerts", []))
            except Exception:
                log.debug("budget state load failed", exc_info=True)

    def _persist_entry(self, entry: dict[str, Any]) -> None:
        try:
            with self._ledger_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            log.debug("cost ledger append failed", exc_info=True)

    def _persist_state(self) -> None:
        try:
            self._state_path.write_text(
                json.dumps(
                    {
                        "total_usd": self._budget.get("total_usd"),
                        "crossed": self._budget.get("crossed", []),
                        "alerts": self._alerts[-100:],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            log.debug("budget state save failed", exc_info=True)

    # ── recording ────────────────────────────────────────────────────────

    def record(
        self,
        cost_usd: float,
        agent_id: str = "",
        plan_id: str = "",
        task_id: str = "",
        model: str = "",
        source: str = "operator",
        ts: float | None = None,
    ) -> dict[str, Any]:
        cost = float(cost_usd)
        if cost < 0:
            raise CostLedgerError("cost must be >= 0")
        entry = {
            "ts": ts if ts is not None else _now(),
            "cost_usd": cost,
            "agent_id": str(agent_id or ""),
            "plan_id": str(plan_id or ""),
            "task_id": str(task_id or ""),
            "model": str(model or ""),
            "source": str(source),
            "day": _day_of(ts if ts is not None else _now()),
        }
        self._entries.append(entry)
        self._persist_entry(entry)
        self._check_alerts()
        return entry

    async def attach_bus(self, bus: Any) -> list[str]:
        """Subscribe to the system topic; cost events are matched by type."""
        self._bus = bus
        subs: list[str] = []
        try:
            subs.append(await bus.subscribe(BUS_TOPIC, self._on_bus_event))
        except Exception:
            log.debug("cost ledger bus subscribe failed", exc_info=True)
        return subs

    async def _on_bus_event(self, envelope: Any) -> None:
        try:
            etype = str(getattr(envelope, "type", ""))
            if etype not in COST_EVENT_TYPES:
                return
            payload = getattr(envelope, "payload", None) or {}
            cost = payload.get("cost")
            if cost is None:
                cost = payload.get("cost_usd")
            if cost is None:
                return  # a cost event without a cost value records nothing
            self.record(
                cost_usd=float(cost),
                agent_id=str(payload.get("agent_id", "")),
                plan_id=str(payload.get("plan_id", "")),
                task_id=str(payload.get("task_id", "")),
                model=str(payload.get("model", "")),
                source=str(getattr(envelope, "source", "")) or etype,
            )
        except Exception:
            log.debug("cost ledger bus accounting failed", exc_info=True)

    # ── aggregation ──────────────────────────────────────────────────────

    def _in_window(self, entry: dict[str, Any], window_s: float | None, now: float) -> bool:
        if window_s is None:
            return True
        return float(entry.get("ts", 0)) >= now - window_s

    def summary(self, window_hours: float | None = None) -> dict[str, Any]:
        now = _now()
        window_s = window_hours * 3600 if window_hours else None
        rows = [e for e in self._entries if self._in_window(e, window_s, now)]
        if not rows:
            return {
                "has_data": False,
                "window_hours": window_hours,
                "entries": 0,
                "total_usd": None,
                "by_agent": [],
                "by_plan": [],
                "by_model": [],
                "by_day": [],
                "budget": self.budget_status(rows),
                "alerts": self._alerts[-20:],
            }
        total = sum(float(e.get("cost_usd", 0.0)) for e in rows)

        def _breakdown(key: str) -> list[dict[str, Any]]:
            agg: dict[str, float] = {}
            for e in rows:
                k = str(e.get(key, "") or "")
                if not k:
                    continue
                agg[k] = agg.get(k, 0.0) + float(e.get("cost_usd", 0.0))
            return [
                {"key": k, "cost_usd": round(v, 6)}
                for k, v in sorted(agg.items(), key=lambda kv: -kv[1])
            ]

        by_day: dict[str, float] = {}
        for e in rows:
            d = str(e.get("day", ""))
            by_day[d] = by_day.get(d, 0.0) + float(e.get("cost_usd", 0.0))

        burn = self._burn_rate(rows, now)
        forecast = self._forecast(burn)
        return {
            "has_data": True,
            "window_hours": window_hours,
            "entries": len(rows),
            "total_usd": round(total, 6),
            "by_agent": _breakdown("agent_id"),
            "by_plan": _breakdown("plan_id"),
            "by_model": _breakdown("model"),
            "by_day": [{"day": d, "cost_usd": round(v, 6)} for d, v in sorted(by_day.items())],
            "burn_rate_usd_per_hour": burn,
            "forecast": forecast,
            "budget": self.budget_status(rows),
            "alerts": self._alerts[-20:],
        }

    def _burn_rate(self, rows: list[dict[str, Any]], now: float) -> dict[str, Any] | None:
        """Measured spend rate per hour over the recorded window."""
        if not rows:
            return None
        ts_list = sorted(float(e.get("ts", 0)) for e in rows)
        span_s = max(now - ts_list[0], 60.0)  # at least one minute of span
        total = sum(float(e.get("cost_usd", 0.0)) for e in rows)
        return {
            "usd_per_hour": round(total / (span_s / 3600.0), 6),
            "window_span_hours": round(span_s / 3600.0, 4),
            "entries_measured": len(rows),
        }

    def _forecast(self, burn: dict[str, Any] | None) -> dict[str, Any] | None:
        """Linear projection of the measured burn rate. Labeled honestly."""
        if burn is None:
            return None
        rate = float(burn.get("usd_per_hour", 0.0))
        return {
            "method": "linear projection of measured burn rate",
            "next_24h_usd": round(rate * 24.0, 6),
            "next_7d_usd": round(rate * 24.0 * 7.0, 6),
        }

    def ledger_rows(self, limit: int = 200) -> list[dict[str, Any]]:
        return self._entries[-limit:]

    # ── budget & alerts ──────────────────────────────────────────────────

    def set_budget(self, total_usd: float | None) -> dict[str, Any]:
        if total_usd is not None and float(total_usd) < 0:
            raise CostLedgerError("budget must be >= 0")
        self._budget = {
            "total_usd": float(total_usd) if total_usd is not None else None,
            "crossed": [],
        }
        self._persist_state()
        return {"total_usd": self._budget.get("total_usd")}

    def budget_status(self, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if rows is None:
            now = _now()
            rows = [e for e in self._entries if self._in_window(e, None, now)]
        spent = sum(float(e.get("cost_usd", 0.0)) for e in rows)
        budget = self._budget.get("total_usd")
        if budget is None:
            return {
                "budget_usd": None,
                "spent_usd": round(spent, 6),
                "remaining_usd": None,
                "used_ratio": None,
                "note": "no budget set",
            }
        remaining = float(budget) - spent
        ratio = spent / float(budget) if float(budget) > 0 else None
        return {
            "budget_usd": float(budget),
            "spent_usd": round(spent, 6),
            "remaining_usd": round(remaining, 6),
            "used_ratio": round(ratio, 4) if ratio is not None else None,
            "crossed_thresholds": list(self._budget.get("crossed", [])),
        }

    def _check_alerts(self) -> None:
        budget = self._budget.get("total_usd")
        if budget is None or float(budget) <= 0:
            return
        spent = sum(float(e.get("cost_usd", 0.0)) for e in self._entries)
        ratio = spent / float(budget)
        for threshold in DEFAULT_ALERT_THRESHOLDS:
            if ratio >= threshold and threshold not in self._budget.get("crossed", []):
                self._budget.setdefault("crossed", []).append(threshold)
                alert = {
                    "ts": _now(),
                    "threshold": threshold,
                    "spent_usd": round(spent, 6),
                    "budget_usd": float(budget),
                    "used_ratio": round(ratio, 4),
                }
                self._alerts.append(alert)
                self._persist_state()
                self._publish("cost.budget.alert", alert)

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        try:
            from agentic_os.domain.events import EventEnvelope

            envelope = EventEnvelope(
                type=event_type,
                source="costs.ledger",
                topic="system",
                payload=payload,
            )
            loop = asyncio.get_running_loop()
        except RuntimeError:
            log.debug("cost publish skipped: no running event loop")
            return
        except Exception:
            log.debug("cost event publish failed", exc_info=True)
            return
        task = loop.create_task(self._apublish(envelope))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _apublish(self, envelope: Any) -> None:
        try:
            await self._bus.publish(envelope)
        except Exception:
            log.debug("cost bus publish failed", exc_info=True)


# Process singleton wired lazily by the API layer with the live bus.
cost_ledger: CostLedger | None = None
_cost_lock = asyncio.Lock()


async def get_cost_ledger(bus: Any = None) -> CostLedger:
    global cost_ledger
    async with _cost_lock:
        if cost_ledger is None:
            ledger = CostLedger(bus=bus)
            if bus is not None:
                await ledger.attach_bus(bus)
            cost_ledger = ledger
        return cost_ledger
