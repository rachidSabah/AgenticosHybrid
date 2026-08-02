"""Phase 15 — CollaborationNetwork.

Live graph of pairwise trust + confidence between runtimes.

Updated after every mission (success or failure) using the swarm member
list. The trust score is an exponential moving average of the success
rate so recent collaborations weigh more heavily than old ones.

Used by:
  - TaskMarketplace (select best runtime by trust)
  - SwarmCoordinator team-formation (prefer high-trust pairings)
  - EvolutionEngine (recommend collaborations)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agentic_os.core.ecosystem.domain import CollaborationLink
from agentic_os.infrastructure.logging import get_logger

log = get_logger("ecosystem.collaboration_network")

# EMA factor: recent collaborations count for ~30% of the score
_EMA_ALPHA = 0.3
# Baseline trust when no history exists
_BASELINE_TRUST = 0.5


class CollaborationNetwork:
    """Directed trust graph keyed by ``(source, target)``.

    Each pair has its own CollaborationLink because trust is asymmetric:
    runtime A may trust runtime B more than B trusts A (different
    observed outcomes from each one's perspective).
    """

    def __init__(self) -> None:
        self._links: dict[tuple[str, str], CollaborationLink] = {}
        self._global_stats: dict[str, dict[str, int]] = {}
        self._updates_count = 0

    # ── Mutation ────────────────────────────────────────────────────

    def record_collaboration(
        self,
        source: str,
        target: str,
        success: bool,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CollaborationLink:
        """Record one collaboration event between two runtimes.

        Updates both directions (A→B and B→A) because collaboration is
        inherently mutual — each runtime observed the other performing.
        """
        link = self._ensure_link(source, target)
        link.successful += 1 if success else 0
        link.failed += 0 if success else 1
        link.last_collaboration = datetime.now(UTC).isoformat()
        link.last_outcome = "success" if success else "failure"

        # Update confidence (EMA)
        if confidence is not None:
            link.confidence = (_EMA_ALPHA * confidence) + ((1 - _EMA_ALPHA) * link.confidence)

        # Recompute trust score: weighted success rate + confidence
        success_rate = link.success_rate
        link.trust_score = round((success_rate * 0.6) + (link.confidence * 0.4), 4)

        # Append to history (cap at 50 entries per link)
        link.history.append(
            {
                "success": success,
                "confidence": confidence,
                "timestamp": link.last_collaboration,
                "metadata": dict(metadata or {}),
            }
        )
        if len(link.history) > 50:
            link.history = link.history[-50:]

        # Mirror direction (B → A)
        mirror = self._ensure_link(target, source)
        mirror.successful += 1 if success else 0
        mirror.failed += 0 if success else 1
        mirror.last_collaboration = link.last_collaboration
        mirror.last_outcome = link.last_outcome
        if confidence is not None:
            mirror.confidence = (_EMA_ALPHA * confidence) + ((1 - _EMA_ALPHA) * mirror.confidence)
        mirror.trust_score = round((mirror.success_rate * 0.6) + (mirror.confidence * 0.4), 4)
        mirror.history.append(
            {
                "success": success,
                "confidence": confidence,
                "timestamp": mirror.last_collaboration,
                "metadata": dict(metadata or {}),
            }
        )
        if len(mirror.history) > 50:
            mirror.history = mirror.history[-50:]

        # Update global per-runtime stats
        self._bump_global(source, success)
        self._bump_global(target, success)

        self._updates_count += 1
        return link

    def _ensure_link(self, source: str, target: str) -> CollaborationLink:
        key = (source, target)
        if key not in self._links:
            self._links[key] = CollaborationLink(
                source=source,
                target=target,
                confidence=_BASELINE_TRUST,
                trust_score=_BASELINE_TRUST,
            )
        return self._links[key]

    def _bump_global(self, runtime_id: str, success: bool) -> None:
        stats = self._global_stats.setdefault(
            runtime_id, {"successful": 0, "failed": 0, "total": 0}
        )
        stats["successful"] += 1 if success else 0
        stats["failed"] += 0 if success else 1
        stats["total"] += 1

    # ── Queries ────────────────────────────────────────────────────

    def get_link(self, source: str, target: str) -> CollaborationLink | None:
        return self._links.get((source, target))

    def trust_score(self, source: str, target: str) -> float:
        link = self._links.get((source, target))
        return link.trust_score if link else _BASELINE_TRUST

    def average_trust(self, runtime_id: str) -> float:
        """Mean trust others have in ``runtime_id`` (incoming)."""
        scores = [link.trust_score for (src, tgt), link in self._links.items() if tgt == runtime_id]
        if not scores:
            return _BASELINE_TRUST
        return sum(scores) / len(scores)

    def collaborators(self, runtime_id: str) -> list[str]:
        """All runtimes ``runtime_id`` has collaborated with."""
        return sorted({tgt for (src, tgt) in self._links if src == runtime_id})

    def top_collaborators(self, runtime_id: str, limit: int = 5) -> list[tuple[str, float]]:
        """Top-N collaborators of ``runtime_id`` by trust score (descending)."""
        pairs = [
            (tgt, link.trust_score) for (src, tgt), link in self._links.items() if src == runtime_id
        ]
        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs[:limit]

    def runtime_stats(self, runtime_id: str) -> dict[str, Any]:
        """Aggregate collaboration stats for a runtime."""
        stats = self._global_stats.get(runtime_id, {"successful": 0, "failed": 0, "total": 0})
        return {
            **stats,
            "success_rate": (stats["successful"] / stats["total"] if stats["total"] else 0.0),
            "average_trust": self.average_trust(runtime_id),
            "collaborator_count": len(self.collaborators(runtime_id)),
        }

    # ── Snapshot ───────────────────────────────────────────────────

    def list_links(self, limit: int | None = None) -> list[CollaborationLink]:
        links = list(self._links.values())
        if limit:
            links = links[-limit:]
        return links

    def stats(self) -> dict[str, Any]:
        # Each collaboration is recorded in BOTH directions (a→b and b→a),
        # so raw sums double the true event count. Divide by 2 for the
        # collaboration-level totals.
        successful = sum(link.successful for link in self._links.values()) // 2
        failed = sum(link.failed for link in self._links.values()) // 2
        avg_trust = (
            sum(link.trust_score for link in self._links.values()) / len(self._links)
            if self._links
            else 0.0
        )
        return {
            "total_links": len(self._links),
            "unique_runtimes": len(self._global_stats),
            "total_collaborations": successful + failed,
            "successful_collaborations": successful,
            "failed_collaborations": failed,
            "average_trust": round(avg_trust, 4),
            "updates_count": self._updates_count,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "links": [link.to_dict() for link in self._links.values()],
            "runtime_stats": {
                rid: {**stats, "average_trust": round(self.average_trust(rid), 4)}
                for rid, stats in self._global_stats.items()
            },
            "stats": self.stats(),
        }

    def clear(self) -> None:
        self._links.clear()
        self._global_stats.clear()
        self._updates_count += 1
