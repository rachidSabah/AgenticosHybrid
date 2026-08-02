"""Native Terminal Integration — manages terminal emulator instances."""

from __future__ import annotations

from collections.abc import Sequence

from agentic_os.domain.desktop import TerminalConfig, TerminalInfo
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.terminal")


class NativeTerminalIntegration:
    """In-memory terminal manager. Integrates with Tauri for native terminal."""

    def __init__(self) -> None:
        self._terminals: dict[str, TerminalInfo] = {}

    async def open_terminal(self, config: TerminalConfig) -> TerminalInfo:
        info = TerminalInfo(id=config.id, title=config.title, running=True, config=config)
        self._terminals[info.id] = info
        log.info("Terminal opened", terminal_id=info.id)
        return info

    async def close_terminal(self, terminal_id: str) -> bool:
        if terminal_id in self._terminals:
            self._terminals[terminal_id].running = False
            del self._terminals[terminal_id]
            return True
        return False

    async def list_terminals(self) -> Sequence[TerminalInfo]:
        return list(self._terminals.values())

    async def get_terminal(self, terminal_id: str) -> TerminalInfo | None:
        return self._terminals.get(terminal_id)

    async def write_to_terminal(self, terminal_id: str, data: str) -> bool:
        term = self._terminals.get(terminal_id)
        if term is None or not term.running:
            return False
        log.debug("Terminal write", terminal_id=terminal_id, data_length=len(data))
        return True

    async def resize_terminal(self, terminal_id: str, rows: int, cols: int) -> bool:
        term = self._terminals.get(terminal_id)
        if term is None:
            return False
        term.config.rows = rows
        term.config.cols = cols
        return True
