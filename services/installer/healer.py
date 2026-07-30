"""Self-Healing Engine — automatically repairs broken runtime bindings.

Monitors for broken paths, missing permissions, environment changes,
and corrupted configurations. Repairs without user intervention.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("installer.healer")


@dataclass
class HealAction:
    """A single healing action taken or proposed."""

    provider_id: str
    issue: str
    severity: str  # "low", "medium", "high", "critical"
    action_taken: str
    success: bool
    details: str = ""


@dataclass
class HealReport:
    """Report of all healing actions performed in a cycle."""

    actions: list[HealAction] = field(default_factory=list)
    total_issues: int = 0
    total_repaired: int = 0
    total_failed: int = 0


class SelfHealingEngine:
    """Automatic repair engine for broken runtime bindings.

    Healing priorities (by severity):
        CRITICAL: Missing executable paths, corrupt provider configs
        HIGH:     Permission errors, expired auth
        MEDIUM:   Changed install dirs, env var changes
        LOW:      Stale caches, missing optional dependencies
    """

    def __init__(self):
        self._provider_bindings: dict[str, dict[str, Any]] = {}

    def register_binding(self, provider_id: str, binding: dict[str, Any]) -> None:
        """Register a provider binding for monitoring and repair."""
        self._provider_bindings[provider_id] = binding

    def unregister_binding(self, provider_id: str) -> None:
        """Remove a provider binding from monitoring."""
        self._provider_bindings.pop(provider_id, None)

    async def heal_all(self) -> HealReport:
        """Run a full healing cycle on all registered bindings."""
        report = HealReport()
        for provider_id in list(self._provider_bindings.keys()):
            actions = await self._heal_provider(provider_id)
            report.actions.extend(actions)
        report.total_issues = len(report.actions)
        report.total_repaired = sum(1 for a in report.actions if a.success)
        report.total_failed = sum(1 for a in report.actions if not a.success)
        return report

    async def heal_provider(self, provider_id: str) -> list[HealAction]:
        """Run a healing cycle for a single provider."""
        return await self._heal_provider(provider_id)

    async def _heal_provider(self, provider_id: str) -> list[HealAction]:
        """Inspect and repair a single provider binding."""
        actions: list[HealAction] = []
        binding = self._provider_bindings.get(provider_id)
        if not binding:
            return actions

        # 1. Check executable path
        exe_path = binding.get("executable_path", "")
        if exe_path and not os.path.isfile(exe_path):
            action = await self._repair_broken_path(provider_id, exe_path, binding)
            actions.append(action)
            # If path was repaired, update binding
            if action.success and action.details:
                binding["executable_path"] = action.details

        # 2. Check permissions
        if binding.get("executable_path"):
            ep = binding["executable_path"]
            if os.path.isfile(ep) and not os.access(ep, os.X_OK):
                action = await self._repair_permissions(provider_id, ep)
                actions.append(action)

        # 3. Check environment variables
        env_vars = binding.get("env_vars", [])
        for var in env_vars:
            val = os.environ.get(var)
            expected = binding.get("expected_path", "")
            if expected and val != expected:
                action = await self._repair_env_var(provider_id, var, expected)
                actions.append(action)

        # 4. Check config file integrity
        config_path = binding.get("config_path", "")
        if config_path and os.path.isfile(config_path):
            try:
                with open(config_path, "r") as f:
                    content = f.read(1024)
                if not content.strip():
                    actions.append(HealAction(
                        provider_id=provider_id,
                        issue="Config file is empty",
                        severity="high",
                        action_taken="Config file needs regeneration",
                        success=False,
                        details=f"Empty config at {config_path}",
                    ))
            except (OSError, PermissionError) as exc:
                actions.append(HealAction(
                    provider_id=provider_id,
                    issue=f"Cannot read config: {exc}",
                    severity="high",
                    action_taken="Manual intervention required",
                    success=False,
                    details=str(exc),
                ))

        return actions

    async def _repair_broken_path(
        self, provider_id: str, old_path: str, binding: dict[str, Any]
    ) -> HealAction:
        """Try to find the executable at a new location."""
        name = os.path.basename(old_path)
        exe_names = binding.get("exe_names", [name])

        # Search PATH
        for exe_name in exe_names:
            found = shutil.which(exe_name)
            if found:
                return HealAction(
                    provider_id=provider_id,
                    issue=f"Executable path changed: {old_path}",
                    severity="critical",
                    action_taken=f"Found at new location: {found}",
                    success=True,
                    details=found,
                )

        # Search common install dirs
        install_dirs = binding.get("install_paths", [])
        for install_dir in install_dirs:
            for exe_name in exe_names:
                candidate = os.path.join(install_dir, exe_name)
                if os.path.isfile(candidate):
                    return HealAction(
                        provider_id=provider_id,
                        issue=f"Executable path changed: {old_path}",
                        severity="critical",
                        action_taken=f"Found in install dir: {candidate}",
                        success=True,
                        details=candidate,
                    )

        return HealAction(
            provider_id=provider_id,
            issue=f"Executable not found: {old_path}",
            severity="critical",
            action_taken="Could not locate executable — will retry on next cycle",
            success=False,
            details="",
        )

    async def _repair_permissions(self, provider_id: str, exe_path: str) -> HealAction:
        """Attempt to fix executable permissions."""
        try:
            current = os.stat(exe_path).st_mode
            os.chmod(exe_path, current | 0o111)  # Add execute bit
            return HealAction(
                provider_id=provider_id,
                issue=f"Missing execute permission: {exe_path}",
                severity="high",
                action_taken="Added execute permission",
                success=True,
                details=exe_path,
            )
        except (OSError, PermissionError) as exc:
            return HealAction(
                provider_id=provider_id,
                issue=f"Cannot fix permissions: {exe_path}",
                severity="high",
                action_taken=f"Failed: {exc}",
                success=False,
                details=str(exc),
            )

    async def _repair_env_var(self, provider_id: str, var: str, expected: str) -> HealAction:
        """Attempt to fix environment variable."""
        try:
            os.environ[var] = expected
            return HealAction(
                provider_id=provider_id,
                issue=f"Environment variable {var} incorrect",
                severity="medium",
                action_taken=f"Set {var}={expected}",
                success=False,  # Process-level only — not persistent
                details="Set in current process; persists until shell restart",
            )
        except Exception as exc:
            return HealAction(
                provider_id=provider_id,
                issue=f"Cannot fix env var {var}",
                severity="medium",
                action_taken=f"Failed: {exc}",
                success=False,
                details=str(exc),
            )
