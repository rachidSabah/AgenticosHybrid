"""Desktop diagnostics — OS health, system info, desktop runtime state."""

import platform as _platform
import sys
from datetime import UTC, datetime

from agentic_os.domain.desktop import DesktopDiagnosticsInfo


class DesktopDiagnosticsManager:
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

    async def check_health(self) -> dict[str, str | bool]:
        """Quick health check for the desktop runtime."""
        return {
            "status": "healthy",
            "os": _platform.system(),
            "python": sys.version.split()[0],
            "timestamp": datetime.now(UTC).isoformat(),
        }
