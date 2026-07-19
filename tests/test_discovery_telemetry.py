"""Tests for DiscoveryTelemetry — scan lifecycle, history, and aggregated stats."""

import pytest

from agentic_os.core.discovery.telemetry import DiscoveryTelemetry


class TestDiscoveryTelemetry:
    @pytest.fixture
    def telemetry(self) -> DiscoveryTelemetry:
        return DiscoveryTelemetry()

    # ── Start / Complete scan ──

    def test_start_scan_returns_id(self, telemetry: DiscoveryTelemetry) -> None:
        entry_id = telemetry.start_scan("full")
        assert isinstance(entry_id, str)
        assert len(entry_id) > 0

    def test_start_scan_default_profile(self, telemetry: DiscoveryTelemetry) -> None:
        entry_id = telemetry.start_scan()
        assert isinstance(entry_id, str)

    def test_complete_scan_updates_entry(self, telemetry: DiscoveryTelemetry) -> None:
        entry_id = telemetry.start_scan("full")
        updated = telemetry.complete_scan(
            entry_id, providers_run=5, providers_failed=0, engines_found=3
        )
        assert updated is not None
        assert updated.id == entry_id
        assert updated.providers_run == 5
        assert updated.providers_failed == 0
        assert updated.engines_found == 3
        assert updated.completed_at is not None

    def test_complete_scan_unknown_id_returns_none(self, telemetry: DiscoveryTelemetry) -> None:
        result = telemetry.complete_scan("nonexistent", providers_run=0)
        assert result is None

    # ── History ──

    def test_get_history_returns_dicts(self, telemetry: DiscoveryTelemetry) -> None:
        telemetry.start_scan("full")
        history = telemetry.get_history()
        assert len(history) == 1
        assert isinstance(history[0], dict)
        assert "id" in history[0]
        assert "profile_name" in history[0]
        assert "started_at" in history[0]

    def test_get_history_respects_limit(self, telemetry: DiscoveryTelemetry) -> None:
        for _ in range(10):
            telemetry.start_scan("test")
        assert len(telemetry.get_history(limit=3)) == 3
        assert len(telemetry.get_history(limit=100)) == 10

    def test_get_history_empty(self, telemetry: DiscoveryTelemetry) -> None:
        assert telemetry.get_history() == []

    def test_get_history_most_recent_first(self, telemetry: DiscoveryTelemetry) -> None:
        id1 = telemetry.start_scan("first")
        id2 = telemetry.start_scan("second")
        history = telemetry.get_history()
        assert history[0]["id"] == id2
        assert history[1]["id"] == id1

    # ── get_entry ──

    def test_get_entry_by_id(self, telemetry: DiscoveryTelemetry) -> None:
        entry_id = telemetry.start_scan("test")
        entry = telemetry.get_entry(entry_id)
        assert entry is not None
        assert entry.id == entry_id

    def test_get_entry_unknown_returns_none(self, telemetry: DiscoveryTelemetry) -> None:
        assert telemetry.get_entry("nonexistent") is None

    # ── Stats ──

    def test_get_stats_empty(self, telemetry: DiscoveryTelemetry) -> None:
        stats = telemetry.get_stats()
        assert stats["total_scans"] == 0
        assert stats["total_engines_found"] == 0
        assert stats["avg_duration_ms"] == 0.0
        assert stats["failure_rate"] == 0.0

    def test_get_stats_aggregates(self, telemetry: DiscoveryTelemetry) -> None:
        id1 = telemetry.start_scan("full")
        telemetry.complete_scan(id1, providers_run=5, providers_failed=1, engines_found=3)
        id2 = telemetry.start_scan("quick")
        telemetry.complete_scan(id2, providers_run=3, providers_failed=0, engines_found=1)

        stats = telemetry.get_stats()
        assert stats["total_scans"] == 2
        assert stats["total_engines_found"] == 4
        assert stats["total_failures"] == 1
        # failure_rate = total_failures / total_providers_run
        assert stats["failure_rate"] == 1 / 8

    def test_get_stats_zero_providers_run(self, telemetry: DiscoveryTelemetry) -> None:
        """failure_rate must not divide by zero when providers_run is 0."""
        entry_id = telemetry.start_scan("test")
        telemetry.complete_scan(entry_id, providers_run=0, providers_failed=0)
        stats = telemetry.get_stats()
        assert stats["failure_rate"] == 0.0

    def test_get_stats_avg_duration(self, telemetry: DiscoveryTelemetry) -> None:
        entry_id = telemetry.start_scan("test")
        telemetry.complete_scan(entry_id, providers_run=1, engines_found=1)
        stats = telemetry.get_stats()
        assert stats["avg_duration_ms"] >= 0.0

    # ── Error tracking ──

    def test_get_recent_errors_empty(self, telemetry: DiscoveryTelemetry) -> None:
        assert telemetry.get_recent_errors() == []

    def test_get_recent_errors(self, telemetry: DiscoveryTelemetry) -> None:
        entry_id = telemetry.start_scan("full")
        telemetry.complete_scan(
            entry_id, providers_run=2, providers_failed=1, errors=("Connection refused",)
        )
        errors = telemetry.get_recent_errors()
        assert len(errors) == 1
        assert "Connection refused" in errors

    def test_get_recent_errors_respects_limit(self, telemetry: DiscoveryTelemetry) -> None:
        id1 = telemetry.start_scan("s1")
        telemetry.complete_scan(id1, errors=("err1", "err2"))
        id2 = telemetry.start_scan("s2")
        telemetry.complete_scan(id2, errors=("err3",))
        errors = telemetry.get_recent_errors(limit=2)
        assert len(errors) == 2

    # ── Max entries ──

    def test_max_entries_enforced(self, telemetry: DiscoveryTelemetry) -> None:
        telemetry.max_entries = 5
        for i in range(10):
            telemetry.start_scan(f"scan_{i}")
        assert len(telemetry._history) == 5

    # ── clear ──

    def test_clear_returns_count(self, telemetry: DiscoveryTelemetry) -> None:
        telemetry.start_scan("test")
        telemetry.start_scan("test")
        assert telemetry.clear() == 2
        assert telemetry.get_history() == []

    def test_clear_empty(self, telemetry: DiscoveryTelemetry) -> None:
        assert telemetry.clear() == 0
