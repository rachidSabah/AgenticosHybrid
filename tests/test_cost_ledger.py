"""Cost ledger — real bus events, measured aggregation, honest forecasts.

No fabricated costs: entries are recorded via the real manager API and via
real EventEnvelope publishes on a real LocalBus; forecasts are linear
projections of measured burn rates.
"""

from __future__ import annotations

import asyncio

import pytest

from agentic_os.adapters.bus.local import LocalBus
from agentic_os.core.costs.ledger import CostLedger, CostLedgerError


@pytest.fixture
def bus():
    return LocalBus()


@pytest.fixture
def ledger(tmp_path):
    return CostLedger(data_dir=str(tmp_path / "costs"))


def test_record_and_summary_totals(ledger):
    ledger.record(0.01, agent_id="agent:a", plan_id="plan-1", model="gpt-4o")
    ledger.record(0.02, agent_id="agent:b", plan_id="plan-1", model="claude-3")
    s = ledger.summary()
    assert s["has_data"] is True
    assert s["entries"] == 2
    assert s["total_usd"] == pytest.approx(0.03, abs=1e-9)
    agents = {r["key"]: r["cost_usd"] for r in s["by_agent"]}
    assert agents["agent:a"] == pytest.approx(0.01, abs=1e-9)
    models = {r["key"]: r["cost_usd"] for r in s["by_model"]}
    assert models["gpt-4o"] == pytest.approx(0.01, abs=1e-9)


def test_no_entries_means_no_data(ledger):
    s = ledger.summary()
    assert s["has_data"] is False
    assert s["total_usd"] is None
    assert s["entries"] == 0


def test_negative_cost_refused(ledger):
    with pytest.raises(CostLedgerError):
        ledger.record(-1.0)


def test_window_filtering(ledger):
    import time

    ledger.record(1.0, agent_id="agent:old", ts=time.time() - 10 * 3600)
    ledger.record(0.5, agent_id="agent:new")
    s_all = ledger.summary()
    assert s_all["total_usd"] == pytest.approx(1.5, abs=1e-9)
    s_recent = ledger.summary(window_hours=1)
    assert s_recent["total_usd"] == pytest.approx(0.5, abs=1e-9)


def test_burn_rate_and_forecast_are_labeled_projections(ledger):
    import time

    # 3.6 USD spread over the last hour of real entries -> ~3.6 usd/hour
    for i in range(6):
        ledger.record(0.6, agent_id="agent:a", ts=time.time() - (60 - i * 10) * 60)
    s = ledger.summary(window_hours=2)
    burn = s["burn_rate_usd_per_hour"]
    assert burn is not None
    assert burn["entries_measured"] == 6
    assert burn["usd_per_hour"] > 0
    fc = s["forecast"]
    assert fc["method"] == "linear projection of measured burn rate"
    assert fc["next_24h_usd"] == pytest.approx(burn["usd_per_hour"] * 24, rel=1e-3)


def test_budget_alerts_fire_at_thresholds_and_publish(ledger):
    seen: list[dict] = []
    ledger._publish = lambda t, p: seen.append(p)  # type: ignore[method-assign]
    ledger.set_budget(1.0)
    ledger.record(0.4)  # 40% - no alert
    assert seen == []
    ledger.record(0.4)  # 80% - 0.5 and 0.8 cross
    thresholds = [a["threshold"] for a in seen]
    assert 0.5 in thresholds
    assert 0.8 in thresholds
    ledger.record(0.4)  # 120% - 1.0 crosses
    assert 1.0 in [a["threshold"] for a in seen]
    # crossing again records nothing new
    n = len(ledger.summary()["alerts"])
    ledger.record(0.1)
    assert len(ledger.summary()["alerts"]) == n
    status = ledger.budget_status()
    assert status["used_ratio"] > 1.0
    assert status["remaining_usd"] < 0


def test_budget_reset_clears_crossed_thresholds(ledger):
    fired: list[dict] = []
    ledger._publish = lambda t, p: fired.append(p)  # type: ignore[method-assign]
    ledger.set_budget(0.5)
    ledger.record(0.6)
    assert fired
    ledger.set_budget(10.0)  # raise budget: thresholds reset
    assert ledger.budget_status()["crossed_thresholds"] == []


async def test_bus_cost_events_recorded(bus, tmp_path):
    from agentic_os.domain.events import EventEnvelope

    ledger = CostLedger(data_dir=str(tmp_path / "cg"))
    await ledger.attach_bus(bus)
    await bus.start()
    await bus.publish(
        EventEnvelope(
            type="orchestration.cost_recorded",
            source="orch.publisher",
            topic="system",
            payload={"plan_id": "plan-9", "agent_id": "agent:z", "cost": 0.123},
        )
    )
    await bus.publish(
        EventEnvelope(
            type="cost.recorded",
            source="test",
            topic="system",
            payload={"model": "gpt-4o-mini", "cost_usd": 0.004},
        )
    )
    await bus.publish(
        EventEnvelope(
            type="cost.recorded",
            source="test",
            topic="system",
            payload={"no_cost_here": True},
        )
    )
    await asyncio.sleep(0.2)
    s = ledger.summary()
    assert s["entries"] == 2
    assert s["total_usd"] == pytest.approx(0.127, abs=1e-9)
    plans = {r["key"]: r["cost_usd"] for r in s["by_plan"]}
    assert plans["plan-9"] == pytest.approx(0.123, abs=1e-9)


def test_ledger_persists_across_instances(tmp_path):
    m1 = CostLedger(data_dir=str(tmp_path / "per"))
    m1.record(0.5, agent_id="agent:x")
    m1.set_budget(2.0)
    m2 = CostLedger(data_dir=str(tmp_path / "per"))
    s = m2.summary()
    assert s["entries"] == 1
    assert s["total_usd"] == pytest.approx(0.5, abs=1e-9)
    assert m2.budget_status()["budget_usd"] == 2.0
