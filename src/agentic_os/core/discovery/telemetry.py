"""Discovery telemetry — tracks scan history and aggregates metrics."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from agentic_os.domain.discovery import DiscoveryTelemetryEntry


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class DiscoveryTelemetry:
    """Tracks discovery run history and aggregates scan metrics.

    Each call to start_scan() creates a new entry.  Call complete_scan()
    when the scan finishes to populate duration and result counts.
    """

    _history: list[DiscoveryTelemetryEntry] = field(default_factory=list)
    max_entries: int = 1000

    # ── Scan lifecycle ──

    def start_scan(self, profile_name: str = "default") -> str:
        """Record the start of a discovery scan. Returns the entry id."""
        entry = DiscoveryTelemetryEntry(profile_name=profile_name)
        self._history.append(entry)
        self._trim()
        return entry.id

    def complete_scan(
        self, entry_id: str, **updates: int | tuple[str, ...]
    ) -> DiscoveryTelemetryEntry | None:
        """Mark a scan as completed with final counts. Returns the updated entry."""
        for i, entry in enumerate(self._history):
            if entry.id == entry_id:
                updated = entry.with_completed(**updates)
                self._history[i] = updated
                return updated
        return None

    # ── Query ──

    def get_history(self, limit: int = 50) -> list[dict]:
        """Return the most recent scan entries as dicts."""
        sorted_entries = sorted(self._history, key=lambda e: e.started_at, reverse=True)
        return [e.to_dict() for e in sorted_entries[:limit]]

    def get_entry(self, entry_id: str) -> DiscoveryTelemetryEntry | None:
        """Get a single telemetry entry by id."""
        for entry in self._history:
            if entry.id == entry_id:
                return entry
        return None

    def get_stats(self) -> dict:
        """Aggregated discovery statistics across all history."""
        completed = [e for e in self._history if e.completed_at is not None]
        if not completed:
            return {
                "total_scans": 0,
                "total_engines_found": 0,
                "total_engines_registered": 0,
                "avg_duration_ms": 0.0,
                "total_failures": 0,
                "failure_rate": 0.0,
            }

        total_found = sum(e.engines_found for e in completed)
        total_registered = sum(e.engines_registered for e in completed)
        total_failures = sum(e.providers_failed for e in completed)
        durations = [e.duration_ms for e in completed if e.completed_at]
        avg_duration = sum(durations) / len(durations) if durations else 0.0
        failure_rate = total_failures / max(sum(e.providers_run for e in completed), 1)

        return {
            "total_scans": len(completed),
            "total_engines_found": total_found,
            "total_engines_registered": total_registered,
            "avg_duration_ms": round(avg_duration, 2),
            "total_failures": total_failures,
            "failure_rate": round(failure_rate, 4),
        }

    def get_recent_errors(self, limit: int = 10) -> list[str]:
        """Return the most recent error strings from scans."""
        errors: list[str] = []
        for entry in reversed(self._history):
            if entry.errors:
                errors.extend(entry.errors)
                if len(errors) >= limit:
                    break
        return errors[:limit]

    # ── Maintenance ──

    def clear(self) -> int:
        """Clear all telemetry history. Returns count removed."""
        count = len(self._history)
        self._history.clear()
        return count

    def _trim(self) -> None:
        """Remove oldest entries if over max_entries."""
        while len(self._history) > self.max_entries:
            self._history.pop(0)
