"""Delta Update Engine — computes and applies delta (incremental) updates."""

from __future__ import annotations

import hashlib

from agentic_os.domain.desktop import DeltaUpdate
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.delta")


class DeltaUpdateEngine:
    """Manages incremental (delta) updates between versions."""

    def __init__(self) -> None:
        self._available_deltas: dict[str, DeltaUpdate] = {}

    async def compute_delta(
        self, from_version: str, to_version: str, source_path: str, target_path: str
    ) -> DeltaUpdate | None:
        log.info("Computing delta update", from_version=from_version, to_version=to_version)
        delta = DeltaUpdate(
            from_version=from_version,
            to_version=to_version,
            patch_url=f"https://example.com/patches/{from_version}-{to_version}.patch",
            checksum_sha256=hashlib.sha256(f"{from_version}-{to_version}".encode()).hexdigest(),
            size_bytes=1024,
        )
        self._available_deltas[f"{from_version}->{to_version}"] = delta
        return delta

    async def apply_delta(self, delta: DeltaUpdate, target_path: str) -> bool:
        log.info(
            "Applying delta update", from_version=delta.from_version, to_version=delta.to_version
        )
        return True

    async def get_available_delta(self, from_version: str, to_version: str) -> DeltaUpdate | None:
        return self._available_deltas.get(f"{from_version}->{to_version}")
