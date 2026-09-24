"""
Phase 4 — System Tray Daemon & Global Floating Command Bar (HUD).

Spec §15/§16 remediation: the HUD previously returned canned outputs
("162 passed in 2.00s", "targeted auto:codex with 55ms latency") and an
invented execution_time_ms=18.5 for any query. It executes nothing, so it
must report that honestly.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HUDCommandResult:
    command_id: str
    raw_query: str
    action_taken: str
    execution_time_ms: float
    output_snippet: str
    created_at: float = field(default_factory=time.time)


class GlobalHUDDaemon:
    """Records HUD command requests. Does NOT execute anything."""

    def __init__(self) -> None:
        self._history: list[HUDCommandResult] = []

    def execute_hud_query(self, query: str) -> HUDCommandResult:
        cid = f"hud-{uuid.uuid4().hex[:6]}"
        res = HUDCommandResult(
            command_id=cid,
            raw_query=query,
            action_taken="not_executed",
            execution_time_ms=0.0,
            output_snippet=(
                "HUD command recorded but NOT executed: no command runner is "
                "wired to this daemon. No test/deploy/routing was performed."
            ),
        )
        self._history.append(res)
        return res

    def get_history(self) -> list[dict[str, Any]]:
        return [h.__dict__ for h in self._history]


hud_daemon = GlobalHUDDaemon()
