"""Install Report — comprehensive discovery and installation report.

Generated after every installation, upgrade, or full discovery cycle.
Stored locally and exposed via Desktop Diagnostics API.
"""

from __future__ import annotations

import json
import os
import platform
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from services.installer.validator import ValidationReport, ValidationResult
from core.logging import get_logger

log = get_logger("installer.report")


@dataclass
class InstallReport:
    """Complete installation and discovery report."""

    # Meta
    generated_at: str = ""
    version: str = "1.0.0"
    platform: str = ""
    hostname: str = ""

    # Phase results
    installer_completed: bool = False
    dependencies_installed: bool = False
    runtime_discovery_completed: bool = False
    providers_validated: bool = False
    providers_bound: bool = False
    configuration_generated: bool = False
    backend_initialized: bool = False

    # Provider results
    detected_providers: list[dict[str, Any]] = field(default_factory=list)
    not_found_providers: list[str] = field(default_factory=list)
    validation_errors: list[dict[str, Any]] = field(default_factory=list)

    # Environment
    system_info: dict[str, str] = field(default_factory=dict)
    detected_runtimes: list[dict[str, Any]] = field(default_factory=list)

    # Binding
    bound_providers: list[dict[str, Any]] = field(default_factory=list)
    binding_errors: list[str] = field(default_factory=list)

    # Timing
    install_duration_seconds: float = 0.0
    discovery_duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert report to a JSON-serializable dictionary."""
        return {
            "generated_at": self.generated_at,
            "version": self.version,
            "platform": self.platform,
            "hostname": self.hostname,
            "phases": {
                "installer_completed": self.installer_completed,
                "dependencies_installed": self.dependencies_installed,
                "runtime_discovery_completed": self.runtime_discovery_completed,
                "providers_validated": self.providers_validated,
                "providers_bound": self.providers_bound,
                "configuration_generated": self.configuration_generated,
                "backend_initialized": self.backend_initialized,
            },
            "detected_providers": self.detected_providers,
            "not_found_providers": self.not_found_providers,
            "validation_errors": self.validation_errors,
            "system_info": self.system_info,
            "detected_runtimes": self.detected_runtimes,
            "bound_providers": self.bound_providers,
            "binding_errors": self.binding_errors,
            "timing": {
                "install_duration_seconds": self.install_duration_seconds,
                "discovery_duration_seconds": self.discovery_duration_seconds,
            },
        }

    def to_markdown(self) -> str:
        """Generate a human-readable markdown report."""
        lines = [
            "========================================",
            "  Mission Control Installation Report",
            "========================================",
            "",
            f"Generated: {self.generated_at}",
            f"Platform: {self.platform}",
            f"Hostname: {self.hostname}",
            "",
            "--- Installation Phases ---",
            f"  ✓ Installer completed:     {'YES' if self.installer_completed else 'NO'}",
            f"  ✓ Dependencies installed:  {'YES' if self.dependencies_installed else 'NO'}",
            f"  ✓ Runtime discovery:       {'YES' if self.runtime_discovery_completed else 'NO'}",
            f"  ✓ Providers validated:     {'YES' if self.providers_validated else 'NO'}",
            f"  ✓ Providers bound:         {'YES' if self.providers_bound else 'NO'}",
            f"  ✓ Configuration:           {'YES' if self.configuration_generated else 'NO'}",
            f"  ✓ Backend initialized:     {'YES' if self.backend_initialized else 'NO'}",
            "",
            "--- Detected Providers ---",
        ]

        if self.detected_providers:
            for p in self.detected_providers:
                verified = "✓" if p.get("passed") else "✗"
                lines.append(f"  {verified} {p.get('display_name', p.get('provider_id', '?'))} {p.get('version', '')}")
        else:
            lines.append("  (none)")

        if self.not_found_providers:
            lines.extend([
                "",
                "--- Not Found ---",
            ])
            for nf in self.not_found_providers:
                lines.append(f"  {nf}")

        lines.extend([
            "",
            f"--- Environment ---",
        ])
        for key, val in self.system_info.items():
            lines.append(f"  {key}: {val}")

        if self.detected_runtimes:
            lines.extend(["", "--- Runtimes Detected ---"])
            for rt in self.detected_runtimes:
                lines.append(f"  ✓ {rt.get('name', rt.get('type', '?'))}")

        lines.extend([
            "",
            "========================================",
        ])

        return "\n".join(lines)


class InstallReportGenerator:
    """Generates installation reports from discovery and validation data."""

    def __init__(self, report_path: str | None = None):
        self._report_path = report_path or self._default_path()

    def _default_path(self) -> str:
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "dist",
            "artifacts",
            "installer-report.json",
        )

    def generate_from_validation(
        self,
        validation_report: ValidationReport,
        bound_ids: list[str] | None = None,
        binding_errors: list[str] | None = None,
        duration: float = 0.0,
    ) -> InstallReport:
        """Generate a report from a validation run."""
        report = InstallReport()
        report.generated_at = datetime.now(timezone.utc).isoformat()
        report.platform = platform.platform()
        report.hostname = platform.node()

        report.installer_completed = True
        report.runtime_discovery_completed = True
        report.providers_validated = True
        report.discovery_duration_seconds = duration

        # Detected providers
        for result in validation_report.passed:
            report.detected_providers.append({
                "provider_id": result.provider_id,
                "executable_path": result.executable_path,
                "version": result.version,
                "passed": result.passed,
                "capabilities": list(result.detected_capabilities),
                "launch_time_ms": round(result.launch_time_ms, 1),
            })

        # Not found
        report.not_found_providers = validation_report.not_found

        # Validation errors
        for result in validation_report.failed:
            report.validation_errors.append({
                "provider_id": result.provider_id,
                "executable_path": result.executable_path,
                "errors": result.errors,
            })

        # Environment
        report.system_info = {
            "os": platform.system(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "node": self._check_runtime("node", "--version"),
            "npm": self._check_runtime("npm", "--version"),
            "python": self._check_runtime("python3", "--version")
                       or self._check_runtime("python", "--version"),
            "cargo": self._check_runtime("cargo", "--version"),
            "docker": self._check_runtime("docker", "--version"),
            "git": self._check_runtime("git", "--version"),
            "wsl": self._check_runtime("wsl", "--version"),
        }

        # Bound providers
        if bound_ids:
            report.providers_bound = True
            for pid in bound_ids:
                report.bound_providers.append({"provider_id": pid, "status": "bound"})

        if binding_errors:
            report.binding_errors = binding_errors

        return report

    def save(self, report: InstallReport) -> str:
        """Save the report to disk and return the path."""
        os.makedirs(os.path.dirname(self._report_path), exist_ok=True)
        with open(self._report_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        log.info("Install report saved", path=self._report_path)
        return self._report_path

    def load(self) -> InstallReport | None:
        """Load the most recent install report from disk."""
        if not os.path.isfile(self._report_path):
            return None
        try:
            with open(self._report_path, "r") as f:
                data = json.load(f)
            report = InstallReport()
            report.generated_at = data.get("generated_at", "")
            report.platform = data.get("platform", "")
            report.hostname = data.get("hostname", "")
            phases = data.get("phases", {})
            report.installer_completed = phases.get("installer_completed", False)
            report.dependencies_installed = phases.get("dependencies_installed", False)
            report.runtime_discovery_completed = phases.get("runtime_discovery_completed", False)
            report.providers_validated = phases.get("providers_validated", False)
            report.providers_bound = phases.get("providers_bound", False)
            report.configuration_generated = phases.get("configuration_generated", False)
            report.backend_initialized = phases.get("backend_initialized", False)
            report.detected_providers = data.get("detected_providers", [])
            report.not_found_providers = data.get("not_found_providers", [])
            report.validation_errors = data.get("validation_errors", [])
            report.system_info = data.get("system_info", {})
            report.detected_runtimes = data.get("detected_runtimes", [])
            report.bound_providers = data.get("bound_providers", [])
            report.binding_errors = data.get("binding_errors", [])
            timing = data.get("timing", {})
            report.discovery_duration_seconds = timing.get("discovery_duration_seconds", 0.0)
            return report
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load install report", error=str(exc))
            return None

    @staticmethod
    def _check_runtime(name: str, flag: str) -> str | None:
        """Check if a runtime is available and return its version."""
        import shutil
        import subprocess
        exe = shutil.which(name)
        if not exe:
            return None
        try:
            result = subprocess.run(
                [exe, flag], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip().split("\n")[0][:60]
            return None
        except (subprocess.TimeoutExpired, OSError):
            return None
