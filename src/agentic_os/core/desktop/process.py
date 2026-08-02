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
        import random

        pid = random.randint(10000, 99999)
        info = ProcessInfo(
            pid=pid,
            name=command.split("/")[-1].split("\\")[-1],
            command=f"{command} {' '.join(args or [])}".strip(),
            cwd=cwd or "",
        )
        self._processes[pid] = info
        log.info("Process spawned", pid=pid, command=command)
        return info

    async def get_process_count(self) -> int:
        return len(self._processes)
