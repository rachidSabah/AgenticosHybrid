"""Rollback Manager — manages version rollbacks."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from agentic_os.domain.desktop import UpdateResult
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.rollback")


class RollbackManager:
    """Manages application version rollbacks."""

    def __init__(self) -> None:
        self._versions: list[str] = ["0.9.5"]
        self._current_index = 0

    async def rollback(self, target_version: str | None = None) -> UpdateResult:
        if not await self.can_rollback():
            return UpdateResult(success=False, error="No versions available for rollback")

        if target_version is None and self._current_index < len(self._versions) - 1:
            target_version = self._versions[self._current_index + 1]
        elif target_version not in self._versions:
            return UpdateResult(success=False, error=f"Version not found: {target_version}")

        result = UpdateResult(
            success=True,
            previous_version=self._versions[self._current_index],
            new_version=target_version,
            installed_at=datetime.now(UTC),
            rolled_back=True,
        )

        self._current_index = self._versions.index(target_version)
        log.info(
            "Rollback completed",
            from_version=result.previous_version,
            to_version=result.new_version,
        )
        return result

    async def get_available_versions(self) -> Sequence[str]:
        return self._versions

    async def can_rollback(self) -> bool:
        return len(self._versions) > 1 and self._current_index < len(self._versions) - 1
