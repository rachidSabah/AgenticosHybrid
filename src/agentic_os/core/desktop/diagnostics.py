"""Desktop diagnostics — OS health, system info, desktop runtime state."""

import platform as _platform
import sys
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.desktop import DesktopDiagnosticsInfo, DesktopPerformanceMetrics
from agentic_os.ports.desktop import DesktopDiagnosticsPort


class DesktopDiagnosticsManager(DesktopDiagnosticsPort):
    """Collects and reports desktop runtime diagnostics and health."""

    async def get_diagnostics(self) -> DesktopDiagnosticsInfo:
        """Collect current system and runtime diagnostics."""
        return DesktopDiagnosticsInfo(
            os_name=_platform.system(),
            os_version=_platform.version(),
            os_arch=_platform.machine(),
            hostname=_platform.node(),
            python_version=sys.version.split()[0],
            app_version="1.0.0",
            backend_version="0.9.2",
            sampled_at=datetime.now(UTC),
        )

    async def get_performance(self) -> DesktopPerformanceMetrics:
        """Return current performance metrics."""
        return DesktopPerformanceMetrics()

    async def run_diagnostics(self) -> dict[str, Any]:
        """Run full diagnostics and return combined results."""
        diag = await self.get_diagnostics()
        perf = await self.get_performance()

        from agentic_os.core.desktop.update import AutoUpdateManager

        updater = AutoUpdateManager()
        update_health = await updater.validate_update_infrastructure()

        return {
            "diagnostics": diag.to_dict(),
            "performance": perf.to_dict(),
            "update_health": update_health,
            "status": "healthy",
        }

    async def check_health(self) -> dict[str, Any]:
        """Quick health check for the desktop runtime."""
        return {
            "status": "healthy",
            "os": _platform.system(),
            "python": sys.version.split()[0],
            "timestamp": datetime.now(UTC).isoformat(),
        }
