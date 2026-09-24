"""Native Process Manager — monitors and manages system processes."""

from __future__ import annotations

from collections.abc import Sequence

from agentic_os.domain.desktop import ProcessInfo
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.process")


class NativeProcessManager:
    """In-memory process manager. Integrates with Tauri for native process operations."""

    def __init__(self) -> None:
        self._processes: dict[int, ProcessInfo] = {}

    async def list_processes(self) -> Sequence[ProcessInfo]:
        return list(self._processes.values())

    async def get_process(self, pid: int) -> ProcessInfo | None:
        return self._processes.get(pid)

    async def kill_process(self, pid: int, force: bool = False) -> bool:
        proc = self._processes.get(pid)
        if proc is None:
            return False
        proc.status = "killed" if force else "stopped"
        del self._processes[pid]
        return True

    async def spawn_process(
        self, command: str, args: list[str] | None = None, cwd: str | None = None
    ) -> ProcessInfo:
        """Spawn is NOT implemented here — refuse to fabricate a PID.

        The previous implementation returned a random PID (10000–99999)
        without creating any OS process — a fabricated execution. Real
        spawning belongs to the runtime supervisor / Tauri layer, which
        capture real PIDs.
        """
        raise NotImplementedError(
            "NativeProcessManager.spawn_process is not wired to a real OS "
            "spawn; no process was created and no PID was fabricated. Use "
            "the runtime supervisor (/api/runtimes) for real process launches."
        )

    async def get_process_count(self) -> int:
        return len(self._processes)
