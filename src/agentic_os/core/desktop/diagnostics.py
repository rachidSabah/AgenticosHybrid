"""Desktop Diagnostics Manager — system diagnostics and health checks."""

from __future__ import annotations

from typing import Any

from agentic_os.domain.desktop import DesktopDiagnosticsInfo, DesktopPerformanceMetrics
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.diagnostics")


class DesktopDiagnosticsManager:
    """In-memory diagnostics. Reports system information when Tauri is available."""

    def __init__(self) -> None:
        self._diagnostics = DesktopDiagnosticsInfo(
            os_name="unknown",
            os_version="0.0.0",
            os_arch="x86_64",
            backend_version="0.9.2",
        )
        self._performance = DesktopPerformanceMetrics()

    async def get_diagnostics(self) -> DesktopDiagnosticsInfo:
        return self._diagnostics

    async def get_performance(self) -> DesktopPerformanceMetrics:
        return self._performance

    async def update_performance(self, metrics: DesktopPerformanceMetrics) -> None:
        self._performance = metrics

    async def run_diagnostics(self) -> dict[str, Any]:
        return {
            "diagnostics": self._diagnostics.to_dict(),
            "performance": self._performance.to_dict(),
            "status": "healthy",
        }

    async def check_health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "desktop_runtime": "running",
            "diagnostics": self._diagnostics.to_dict(),
        }
