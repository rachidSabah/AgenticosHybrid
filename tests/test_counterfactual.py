"""Counterfactual fork debugging — journal-level forks, real replay, real diff.

No mocks: every test uses a real PersistenceLayer writing to tmp_path and a
real LocalBus with a live subscriber for replay assertions.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agentic_os.adapters.bus.local import LocalBus
from agentic_os.core.persistent.domain import EventJournalEntry
from agentic_os.core.persistent.snapshot_engine import PersistenceLayer
from agentic_os.core.swarm.counterfactual import (
    CounterfactualEngine,
    CounterfactualError,
)


def _entry(cid: str, etype: str, i: int, payload: dict | None = None) -> EventJournalEntry:
    return EventJournalEntry(
        event_type=etype,
        source="test",
        topic="system",
        payload=payload if payload is not None else {"seq": i},
        correlation_id=cid,
        session_id="sess-1",
        timestamp=f"2026-01-01T00:00:0{i}:00+00:00",
    )


@pytest.fixture
async def persistence(tmp_path: Path) -> PersistenceLayer:
    layer = PersistenceLayer(data_dir=str(tmp_path / "data"))
    for i in range(5):
        await layer.append_journal(_entry("run-alpha", "tool.result", i))
    await layer.append_journal(
        _entry("run-alpha", "mission.completed", 5, {"result": "ok", "tokens": 42})
    )
    return layer


@pytest.fixture
def bus() -> LocalBus:
    return LocalBus()


@pytest.fixture
def engine(persistence: PersistenceLayer, bus: LocalBus) -> CounterfactualEngine:
    return CounterfactualEngine(persistence=persistence, bus=bus)


# ── list_runs ────────────────────────────────────────────────────────────────


async def test_list_runs_groups_by_correlation_id(engine: CounterfactualEngine):
    runs = await engine.list_runs()
    assert len(runs) == 1
    run = runs[0]
    assert run["correlation_id"] == "run-alpha"
    assert run["event_count"] == 6
    assert run["event_types"] == ["tool.result", "mission.completed"]
    assert run["span_ms"] == 5000  # 00:00:00 -> 00:00:05
    assert run["forked"] is False


async def test_list_runs_marks_forks(engine: CounterfactualEngine):
    await engine.fork("run-alpha", fork_at=3)
    runs = await engine.list_runs()
    assert any(r["correlation_id"].startswith("fork-") and r["forked"] for r in runs)


# ── fork ─────────────────────────────────────────────────────────────────────


async def test_fork_records_prefix_only_and_lineage(engine: CounterfactualEngine):
    record = await engine.fork(
        "run-alpha",
        fork_at=3,
        mutations=[{"op": "replace_field", "index": 1, "field_path": "seq", "value": 999}],
    )
    assert record["status"] == "recorded"
    assert record["lineage"]["retained_prefix"] == 3
    assert record["lineage"]["mutations"][0]["value"] == 999
    fork_id = record["fork_id"]

    events = await engine._load_stream(fork_id)
    assert len(events) == 3
    assert events[1]["payload"]["seq"] == 999
    assert events[1]["payload"]["fork_lineage"]["source"] == "run-alpha"
    assert events[1]["payload"]["fork_source_event_id"]
    # All fork events carry the fork lineage marker.
    assert all("fork_lineage" in e["payload"] for e in events)


async def test_fork_suffix_is_never_copied(engine: CounterfactualEngine):
    record = await engine.fork("run-alpha", fork_at=2)
    events = await engine._load_stream(record["fork_id"])
    assert all(e["event_type"] != "mission.completed" for e in events)


async def test_fork_drop_event_stable_original_indexing(engine: CounterfactualEngine):
    record = await engine.fork(
        "run-alpha",
        fork_at=4,
        mutations=[
            {"op": "drop_event", "index": 1},
            {"op": "replace_field", "index": 2, "field_path": "seq", "value": "x"},
        ],
    )
    events = await engine._load_stream(record["fork_id"])
    assert len(events) == 3
    # Indexes are ORIGINAL stream indexes: drop event 1, then mutate event 2
    # (the one with seq=2) — retained order is [0, 2, 3], mutated to [0, "x", 3].
    assert [e["payload"]["seq"] for e in events] == [0, "x", 3]
    lineage = record["lineage"]["mutations"]
    assert lineage[0]["op"] == "drop_event"
    assert lineage[1]["index"] == 2  # original index preserved verbatim


async def test_fork_mutation_on_dropped_index_raises(engine: CounterfactualEngine):
    with pytest.raises(CounterfactualError) as exc:
        await engine.fork(
            "run-alpha",
            fork_at=4,
            mutations=[
                {"op": "drop_event", "index": 1},
                {"op": "replace_field", "index": 1, "field_path": "seq", "value": 0},
            ],
        )
    assert "not part of the retained prefix" in str(exc.value)


async def test_fork_replace_payload_wholesale(engine: CounterfactualEngine):
    record = await engine.fork(
        "run-alpha",
        fork_at=1,
        mutations=[{"op": "replace_payload", "index": 0, "payload": {"note": "fresh"}}],
    )
    events = await engine._load_stream(record["fork_id"])
    assert events[0]["payload"]["note"] == "fresh"
    assert events[0]["payload"]["fork_lineage"]["source"] == "run-alpha"


async def test_fork_unknown_source_raises_honest(engine: CounterfactualEngine):
    with pytest.raises(CounterfactualError) as exc:
        await engine.fork("does-not-exist", fork_at=0)
    assert "no recorded events" in str(exc.value)


async def test_fork_out_of_bounds_fork_at_raises(engine: CounterfactualEngine):
    with pytest.raises(CounterfactualError) as exc:
        await engine.fork("run-alpha", fork_at=99)
    assert "fork_at" in str(exc.value)


async def test_fork_mutation_index_outside_prefix_raises(engine: CounterfactualEngine):
    with pytest.raises(CounterfactualError) as exc:
        await engine.fork("run-alpha", fork_at=2, mutations=[{"op": "drop_event", "index": 3}])
    assert "prefix" in str(exc.value)


async def test_fork_unknown_op_raises(engine: CounterfactualEngine):
    with pytest.raises(CounterfactualError):
        await engine.fork("run-alpha", fork_at=1, mutations=[{"op": "voodoo", "index": 0}])


# ── replay (real bus, real subscriber) ──────────────────────────────────────


async def test_fork_replay_publishes_through_real_bus(engine: CounterfactualEngine, bus: LocalBus):
    received: list[str] = []
    await bus.subscribe("system", lambda e: received.append(e.type) or asyncio.sleep(0))
    await bus.start()
    try:
        record = await engine.fork("run-alpha", fork_at=4, replay=True)
        assert record["replayed"] == 4
        await asyncio.sleep(0.2)  # let the bus queue drain
        assert len(received) == 4
        assert set(received) == {"tool.result"}
    finally:
        await bus.stop()


async def test_fork_without_bus_records_but_never_replays(
    persistence: PersistenceLayer,
):
    engine = CounterfactualEngine(persistence=persistence, bus=None)
    record = await engine.fork("run-alpha", fork_at=2, replay=True)
    assert record["replayed"] == 0
    assert record["status"] == "recorded"


# ── diff ─────────────────────────────────────────────────────────────────────


async def test_diff_identical_streams_all_matched(engine: CounterfactualEngine):
    d = await engine.diff("run-alpha", "run-alpha")
    assert d["summary"]["matched"] == 6
    assert d["summary"]["changed"] == 0
    assert d["a"]["event_count"] == d["b"]["event_count"]


async def test_diff_detects_mutated_event_and_fields(engine: CounterfactualEngine):
    await engine.fork("run-alpha", fork_at=6)
    fork_id = (await engine.fork("run-alpha", fork_at=6))["fork_id"]  # second fork
    # Mutate one event of a fresh fork with a different payload.
    rec = await engine.fork(
        "run-alpha",
        fork_at=6,
        mutations=[{"op": "replace_field", "index": 2, "field_path": "seq", "value": "changed"}],
    )
    d = await engine.diff("run-alpha", rec["fork_id"])
    # fork lineage payload differs on EVERY event (fork_lineage added), but
    # the summary must still be exact — count changed events honestly.
    assert d["summary"]["changed"] >= 1
    idxs = [c["index"] for c in d["changed"]]
    assert 2 in idxs
    changed_at_2 = next(c for c in d["changed"] if c["index"] == 2)
    assert "seq" in changed_at_2["differing_fields"]
    assert changed_at_2["payload_a"]["seq"] == 2
    assert changed_at_2["payload_b"]["seq"] == "changed"
    _ = fork_id  # both forks exist in the journal


async def test_diff_reports_only_in_lengths(engine: CounterfactualEngine):
    rec = await engine.fork("run-alpha", fork_at=2)
    d = await engine.diff("run-alpha", rec["fork_id"])
    assert d["a"]["event_count"] == 6
    assert d["b"]["event_count"] == 2
    assert d["summary"]["only_in_a"] == 4
    assert d["summary"]["only_in_b"] == 0
    assert d["only_in_a"][0]["event_type"] == "tool.result"


async def test_diff_unknown_ids_raise(engine: CounterfactualEngine):
    with pytest.raises(CounterfactualError):
        await engine.diff("ghost-a", "run-alpha")
    with pytest.raises(CounterfactualError):
        await engine.diff("run-alpha", "ghost-b")


async def test_diff_span_delta_measured_not_guessed(engine: CounterfactualEngine):
    d = await engine.diff("run-alpha", "run-alpha")
    assert d["a"]["span_ms"] == 5000
    assert d["summary"]["span_delta_ms"] == 0


# ── API surface ──────────────────────────────────────────────────────────────


@pytest.fixture
def api_client(tmp_path: Path):
    """TestClient against the real app; journal pointed at tmp_path."""
    from fastapi.testclient import TestClient

    from agentic_os.api.app import create_app
    from agentic_os.core.persistent.persistent_controller import PersistentController
    from agentic_os.kernel import Kernel

    layer = PersistenceLayer(data_dir=str(tmp_path / "pdata"))
    kernel = Kernel()
    platform = kernel.platform()
    platform.persistent_controller = PersistentController(
        bus=platform.bus, data_dir=str(tmp_path / "pdata")
    )
    app = create_app(platform)
    return TestClient(app), layer


def test_api_runs_empty_journal_is_honest(api_client):
    client, _layer = api_client
    r = client.get("/api/counterfactual/runs")
    assert r.status_code == 200
    body = r.json()
    assert "runs" in body
    assert isinstance(body["runs"], list)
    assert body["runs"] == []


def test_api_fork_requires_source(api_client):
    client, _layer = api_client
    r = client.post("/api/counterfactual/fork", json={"fork_at": 1})
    assert r.status_code == 400


def test_api_fork_unknown_source_404(api_client):
    client, _layer = api_client
    r = client.post(
        "/api/counterfactual/fork", json={"source_correlation_id": "ghost", "fork_at": 0}
    )
    assert r.status_code == 404
    assert "no recorded events" in r.json()["detail"]


def test_api_fork_full_cycle(api_client):
    import asyncio as _asyncio

    client, layer = api_client
    _asyncio.run(layer.append_journal(_entry("api-run", "tool.result", 0)))

    r = client.post(
        "/api/counterfactual/fork",
        json={"source_correlation_id": "api-run", "fork_at": 1},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fork_id"].startswith("fork-")
    assert body["lineage"]["retained_prefix"] == 1

    d = client.get("/api/counterfactual/diff", params={"a": "api-run", "b": body["fork_id"]})
    assert d.status_code == 200
    diff = d.json()
    assert diff["b"]["event_count"] == 1

    forks = client.get("/api/counterfactual/forks")
    assert forks.status_code == 200
    assert any(f["fork_id"] == body["fork_id"] for f in forks.json()["forks"])


def test_api_diff_missing_params_400(api_client):
    client, _layer = api_client
    r = client.get("/api/counterfactual/diff", params={"a": "x"})
    assert r.status_code == 400


def test_journal_roundtrip_preserves_correlation(tmp_path: Path):
    layer = PersistenceLayer(data_dir=str(tmp_path / "j"))
    entry = _entry("cid-x", "tool.result", 0, {"a": 1})
    asyncio.run(layer.append_journal(entry))
    rows = asyncio.run(layer.read_journal(limit=10))
    assert any(r.get("correlation_id") == "cid-x" for r in rows)
    raw = json.dumps(rows[0]["payload"])
    assert json.loads(raw) == {"a": 1}
