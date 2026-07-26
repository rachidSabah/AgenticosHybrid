"""Tests for RuntimeSnapshotManager — immutable snapshots, TTL, diff comparison."""

import time

import pytest

from agentic_os.core.runtime.runtime import Runtime
from agentic_os.core.runtime.runtime_snapshot import RuntimeSnapshotManager


@pytest.fixture
def snap_mgr() -> RuntimeSnapshotManager:
    return RuntimeSnapshotManager(ttl=300)  # 5 min TTL


class TestRuntimeSnapshotManager:
    def test_take_snapshot(self, snap_mgr: RuntimeSnapshotManager) -> None:
        r = Runtime(name="test-rt", cpu=50.0, memory=256.0)
        sid = snap_mgr.take(r)
        assert sid is not None
        assert len(sid) > 0

    def test_get_snapshot(self, snap_mgr: RuntimeSnapshotManager) -> None:
        r = Runtime(name="get-test")
        sid = snap_mgr.take(r)
        snapshot = snap_mgr.get(sid)
        assert snapshot is not None
        assert snapshot["name"] == "get-test"
        assert "_snapshot_at" in snapshot

    def test_get_nonexistent(self, snap_mgr: RuntimeSnapshotManager) -> None:
        assert snap_mgr.get("nonexistent") is None

    def test_get_latest(self, snap_mgr: RuntimeSnapshotManager) -> None:
        r = Runtime(name="latest-test")
        snap_mgr.take(r)
        latest = snap_mgr.get_latest(r.id)
        assert latest is not None
        assert latest["name"] == "latest-test"

    def test_get_latest_no_snapshots(self, snap_mgr: RuntimeSnapshotManager) -> None:
        assert snap_mgr.get_latest("ghost") is None

    def test_get_latest_multiple_returns_newest(self, snap_mgr: RuntimeSnapshotManager) -> None:
        r = Runtime(name="multi-snap")
        snap_mgr.take(r)
        time.sleep(0.01)
        r.cpu = 99.0
        sid2 = snap_mgr.take(r)
        latest = snap_mgr.get_latest(r.id)
        assert latest is not None
        assert latest["_snapshot_at"] == snap_mgr.get(sid2)["_snapshot_at"]  # type: ignore[index]

    def test_snapshot_isolation(self, snap_mgr: RuntimeSnapshotManager) -> None:
        r = Runtime(name="isolated", cpu=50.0)
        sid = snap_mgr.take(r)
        snapshot = snap_mgr.get(sid)
        assert snapshot is not None
        r.cpu = 90.0
        assert snapshot["cpu"] == 50.0  # not affected

    def test_expired_snapshot_returns_none(self) -> None:
        mgr = RuntimeSnapshotManager(ttl=0)  # expires immediately
        r = Runtime(name="expired")
        sid = mgr.take(r)
        time.sleep(0.01)
        assert mgr.get(sid) is None

    def test_expired_not_in_latest(self) -> None:
        mgr = RuntimeSnapshotManager(ttl=0)
        r = Runtime(name="expired-latest")
        mgr.take(r)
        time.sleep(0.01)
        assert mgr.get_latest(r.id) is None

    def test_compare_no_changes(self, snap_mgr: RuntimeSnapshotManager) -> None:
        r = Runtime(name="same")
        s1 = snap_mgr.take(r)
        s2 = snap_mgr.take(r)
        snap_a = snap_mgr.get(s1)
        snap_b = snap_mgr.get(s2)
        assert snap_a is not None and snap_b is not None
        diff = snap_mgr.compare(snap_a, snap_b)
        # Only change should be _snapshot_at timestamp
        assert "changed" in diff

    def test_compare_with_changes(self, snap_mgr: RuntimeSnapshotManager) -> None:
        r = Runtime(name="changing")
        s1 = snap_mgr.take(r)
        r.cpu = 90.0
        r.memory = 512.0
        s2 = snap_mgr.take(r)
        snap_a = snap_mgr.get(s1)
        snap_b = snap_mgr.get(s2)
        assert snap_a is not None and snap_b is not None
        diff = snap_mgr.compare(snap_a, snap_b)
        assert "cpu" in diff.get("changed", {})
        assert "memory" in diff.get("changed", {})

    def test_cleanup_removes_expired(self) -> None:
        mgr = RuntimeSnapshotManager(ttl=0)
        r = Runtime(name="cleanup-test")
        mgr.take(r)
        time.sleep(0.01)
        count = mgr.cleanup()
        assert count >= 1

    def test_cleanup_no_expired(self, snap_mgr: RuntimeSnapshotManager) -> None:
        r = Runtime(name="fresh")
        snap_mgr.take(r)
        count = snap_mgr.cleanup()
        assert count == 0

    def test_multi_runtime_index(self, snap_mgr: RuntimeSnapshotManager) -> None:
        r1 = Runtime(name="rt-a")
        r2 = Runtime(name="rt-b")
        snap_mgr.take(r1)
        snap_mgr.take(r2)
        assert snap_mgr.get_latest(r1.id) is not None
        assert snap_mgr.get_latest(r2.id) is not None

    def test_compare_added_removed_keys(self, snap_mgr: RuntimeSnapshotManager) -> None:
        a = {"name": "test", "cpu": 50.0}
        b = {"name": "test", "cpu": 50.0, "memory": 256.0}
        diff = snap_mgr.compare(a, b)
        assert "memory" in diff["added"]
        assert diff["added"]["memory"] == 256.0

    def test_compare_removed_keys(self, snap_mgr: RuntimeSnapshotManager) -> None:
        a = {"name": "test", "temp": "gone"}
        b = {"name": "test"}
        diff = snap_mgr.compare(a, b)
        assert "temp" in diff["removed"]
