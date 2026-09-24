"""Counterfactual fork debugging — fork a recorded event stream at any point,
apply explicit operator-defined mutations, replay the fork through the real
event bus, and diff the two universes.

Absolute honesty rules (spec: everything measured, nothing fabricated):
* A fork is a REAL recorded event stream: it is persisted through the same
  journal as every other event and (optionally) re-dispatched through the
  real EventBus so actual subscribers react. No outcome is ever predicted,
  simulated, or synthesized here.
* Mutations are applied exactly as the operator specified, and every applied
  mutation is recorded verbatim in the fork lineage.
* diff_runs compares two recorded streams field-by-field. Deltas that cannot
  be measured (e.g. cost fields absent from payloads) are reported as None —
  never guessed.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from agentic_os.core.persistent.snapshot_engine import PersistenceLayer
from agentic_os.domain.events import EventEnvelope
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("swarm.counterfactual")

_MUTATION_OPS = ("replace_field", "drop_event", "replace_payload")
_FORK_PREFIX = "fork-"


class CounterfactualError(ValueError):
    """Operator error in fork/diff specification (mapped to HTTP 400/404)."""


def _parse_ts(value: Any) -> float:
    """Best-effort ISO-timestamp parse; unparseable values sort as 0.0."""
    if isinstance(value, (int, float)):
        return float(value)
    try:
        from datetime import datetime

        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _set_nested(payload: dict[str, Any], dotted_path: str, value: Any) -> None:
    """Set ``value`` at a dotted path inside ``payload``, creating dicts."""
    parts = [p for p in dotted_path.split(".") if p]
    if not parts:
        raise CounterfactualError("field_path must contain at least one segment")
    node: dict[str, Any] = payload
    for seg in parts[:-1]:
        nxt = node.get(seg)
        if not isinstance(nxt, dict):
            nxt = {}
            node[seg] = nxt
        node = nxt
    node[parts[-1]] = value


@dataclass
class CounterfactualEngine:
    """Fork recorded event streams and diff universes. Journal is the truth."""

    persistence: PersistenceLayer
    bus: EventBus | None = None
    _forks: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)

    # ── Recorded runs ────────────────────────────────────────────────────

    async def _load_stream(self, correlation_id: str) -> list[dict[str, Any]]:
        entries = await self.persistence.read_journal(limit=5000)
        events = [e for e in entries if e.get("correlation_id") == correlation_id]
        events.sort(key=lambda e: _parse_ts(e.get("timestamp")))
        return events

    async def list_runs(self, limit: int = 25) -> list[dict[str, Any]]:
        """Group the journal by correlation_id. Only real recorded events."""
        entries = await self.persistence.read_journal(limit=5000)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for e in entries:
            cid = str(e.get("correlation_id") or "")
            if not cid:
                continue
            grouped.setdefault(cid, []).append(e)
        runs: list[dict[str, Any]] = []
        for cid, events in grouped.items():
            events.sort(key=lambda e: _parse_ts(e.get("timestamp")))
            types: list[str] = []
            for e in events:
                t = str(e.get("event_type") or "?")
                if t not in types:
                    types.append(t)
            first = _parse_ts(events[0].get("timestamp"))
            last = _parse_ts(events[-1].get("timestamp"))
            runs.append(
                {
                    "correlation_id": cid,
                    "event_count": len(events),
                    "event_types": types,
                    "first_ts": events[0].get("timestamp"),
                    "last_ts": events[-1].get("timestamp"),
                    "span_ms": int(max(0.0, (last - first) * 1000)),
                    "forked": cid.startswith(_FORK_PREFIX),
                }
            )
        runs.sort(key=lambda r: str(r["last_ts"]), reverse=True)
        return runs[: max(1, limit)]

    # ── Fork ─────────────────────────────────────────────────────────────

    async def fork(
        self,
        source_correlation_id: str,
        fork_at: int,
        mutations: list[dict[str, Any]] | None = None,
        replay: bool = False,
    ) -> dict[str, Any]:
        events = await self._load_stream(source_correlation_id)
        if not events:
            raise CounterfactualError(
                f"no recorded events for correlation_id {source_correlation_id!r}"
            )
        if not isinstance(fork_at, int) or not (0 <= fork_at <= len(events)):
            raise CounterfactualError(
                f"fork_at must be an integer in [0, {len(events)}] "
                f"(the source stream has {len(events)} events)"
            )
        mutations = mutations or []
        for m in mutations:
            if not isinstance(m, dict) or m.get("op") not in _MUTATION_OPS:
                raise CounterfactualError(
                    f"mutation op must be one of {list(_MUTATION_OPS)}; got {m!r}"
                )
            idx = m.get("index")
            if not isinstance(idx, int) or not (0 <= idx < fork_at):
                raise CounterfactualError(
                    f"mutation index must be an integer in [0, {fork_at}) "
                    "(mutations apply to the retained prefix only)"
                )

        # The fork carries ONLY the prefix: everything after fork_at is the
        # counterfactual future that real replay must produce, never copy.
        # Mutation indexes are ALWAYS original recorded-stream indexes — they
        # stay stable even after drop_event, so operators address events the
        # way the journal shows them.
        prefix = [dict(e) for e in events[:fork_at]]
        orig = list(range(len(prefix)))  # original stream index per retained slot
        applied: list[dict[str, Any]] = []
        for m in mutations:
            op = m["op"]
            idx = m["index"]
            if idx not in orig:
                raise CounterfactualError(
                    f"mutation {op} targets original event index {idx}, which is "
                    "not part of the retained prefix (dropped or out of range)"
                )
            pos = orig.index(idx)
            if op == "drop_event":
                dropped = prefix.pop(pos)
                orig.pop(pos)
                applied.append({"op": op, "index": idx, "dropped_event_id": dropped.get("id")})
                continue
            target = prefix[pos]
            if op == "replace_field":
                path = str(m.get("field_path") or "")
                if not path:
                    raise CounterfactualError("replace_field requires field_path")
                payload = dict(target.get("payload") or {})
                _set_nested(payload, path, m.get("value"))
                target["payload"] = payload
                applied.append(
                    {
                        "op": op,
                        "index": idx,
                        "field_path": path,
                        "value": m.get("value"),
                    }
                )
            elif op == "replace_payload":
                new_payload = m.get("payload")
                if not isinstance(new_payload, dict):
                    raise CounterfactualError("replace_payload requires a payload object")
                target["payload"] = dict(new_payload)
                applied.append({"op": op, "index": idx})

        fork_id = f"{_FORK_PREFIX}{uuid.uuid4().hex[:8]}"
        lineage = {
            "source": source_correlation_id,
            "fork_at": fork_at,
            "source_event_count": len(events),
            "retained_prefix": len(prefix),
            "mutations": applied,
        }
        published = 0
        for src in prefix:
            entry = {
                "id": f"evt-{uuid.uuid4().hex[:8]}",
                "event_type": src.get("event_type") or "unknown",
                "source": "counterfactual-fork",
                "topic": src.get("topic") or "",
                "payload": {
                    **(src.get("payload") or {}),
                    "fork_lineage": lineage,
                    "fork_source_event_id": src.get("id"),
                },
                "correlation_id": fork_id,
                "session_id": src.get("session_id") or "",
                "timestamp": src.get("timestamp") or "",
            }
            await self.persistence.append_journal(_journal_entry(entry))
            if replay and self.bus is not None:
                await self.bus.publish(
                    EventEnvelope(
                        type=entry["event_type"],
                        source=entry["source"],
                        topic=entry["topic"] or "system",
                        payload=entry["payload"],
                    )
                )
                published += 1

        record = {
            "fork_id": fork_id,
            "lineage": lineage,
            "replayed": published,
            "status": "recorded",
            "created_at": time.time(),
        }
        self._forks[fork_id] = record
        log.info(
            "counterfactual fork %s of %r at %d (%d mutations, replayed=%d)",
            fork_id,
            source_correlation_id,
            fork_at,
            len(applied),
            published,
        )
        return record

    def list_forks(self) -> list[dict[str, Any]]:
        """Forks performed in this process, newest first."""
        return sorted(self._forks.values(), key=lambda r: r["created_at"], reverse=True)

    # ── Diff ─────────────────────────────────────────────────────────────

    async def diff(self, id_a: str, id_b: str) -> dict[str, Any]:
        a = await self._load_stream(id_a)
        b = await self._load_stream(id_b)
        if not a:
            raise CounterfactualError(f"no recorded events for correlation_id {id_a!r}")
        if not b:
            raise CounterfactualError(f"no recorded events for correlation_id {id_b!r}")

        matched: list[dict[str, Any]] = []
        changed: list[dict[str, Any]] = []
        only_in_a: list[dict[str, Any]] = []
        only_in_b: list[dict[str, Any]] = []
        n = max(len(a), len(b))
        for i in range(n):
            ea = a[i] if i < len(a) else None
            eb = b[i] if i < len(b) else None
            if ea is None:
                # n = max(len(a), len(b)) guarantees eb is not None here,
                # kept explicit so the type is honest for static checks.
                if eb is not None:
                    only_in_b.append(_brief(i, eb))
                continue
            if eb is None:
                only_in_a.append(_brief(i, ea))
                continue
            ta, tb = ea.get("event_type"), eb.get("event_type")
            if ta != tb:
                only_in_a.append(_brief(i, ea))
                only_in_b.append(_brief(i, eb))
                continue
            pa = ea.get("payload") or {}
            pb = eb.get("payload") or {}
            if json.dumps(pa, sort_keys=True, default=str) == json.dumps(
                pb, sort_keys=True, default=str
            ):
                matched.append({"index": i, "event_type": ta})
            else:
                keys = sorted(set(map(str, pa)) | set(map(str, pb)))
                differing = [k for k in keys if pa.get(k) != pb.get(k)]
                changed.append(
                    {
                        "index": i,
                        "event_type": ta,
                        "differing_fields": differing,
                        "payload_a": pa,
                        "payload_b": pb,
                    }
                )

        span_a = _span_ms(a)
        span_b = _span_ms(b)
        return {
            "a": {"correlation_id": id_a, "event_count": len(a), "span_ms": span_a},
            "b": {"correlation_id": id_b, "event_count": len(b), "span_ms": span_b},
            "matched": matched,
            "changed": changed,
            "only_in_a": only_in_a,
            "only_in_b": only_in_b,
            "summary": {
                "matched": len(matched),
                "changed": len(changed),
                "only_in_a": len(only_in_a),
                "only_in_b": len(only_in_b),
                "span_delta_ms": (span_b - span_a)
                if span_a is not None and span_b is not None
                else None,
            },
        }


def _brief(index: int, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": index,
        "event_type": entry.get("event_type"),
        "event_id": entry.get("id"),
        "timestamp": entry.get("timestamp"),
    }


def _span_ms(events: list[dict[str, Any]]) -> int | None:
    if not events:
        return None
    first = _parse_ts(events[0].get("timestamp"))
    last = _parse_ts(events[-1].get("timestamp"))
    if first == 0.0 and last == 0.0:
        return None
    return int(max(0.0, (last - first) * 1000))


def _journal_entry(entry: dict[str, Any]):
    """Build the journal entry object without touching the EventEnvelope wire."""
    from agentic_os.core.persistent.domain import EventJournalEntry

    return EventJournalEntry(
        id=entry["id"],
        event_type=entry["event_type"],
        source=entry["source"],
        topic=entry["topic"],
        payload=entry["payload"],
        correlation_id=entry["correlation_id"],
        session_id=entry["session_id"],
        timestamp=entry["timestamp"],
    )
