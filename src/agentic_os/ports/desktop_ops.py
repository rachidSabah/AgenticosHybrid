"""
Desktop Operational Port Interfaces

Phase 4 M6 Part 2 ports for installer, updates, runtime discovery,
offline mode, and backup/restore.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from agentic_os.domain.desktop import (
    BackupConfig,
    BackupResult,
    FirstRunState,
    InstallerConfig,
    InstallerResult,
    InstallerType,
    OfflineConfig,
    OfflineState,
    ReleaseInfo,
    RestoreConfig,
    RuntimeDiscoveryResult,
    RuntimeInfo,
    RuntimeType,
    UpdateChannel,
    UpdateHistoryRecord,
    UpdateManifest,
    UpdateResult,
    UpdateStatus,
)


@runtime_checkable
class DesktopInstallerPort(Protocol):
    """Installer generation and execution interface."""

    async def generate_installer(self, config: InstallerConfig) -> InstallerResult: ...
    async def generate_all(self, config: InstallerConfig) -> Sequence[InstallerResult]: ...
    async def validate_installer(self, path: str) -> dict[str, Any]: ...
    async def get_supported_types(self) -> Sequence[InstallerType]: ...
    async def get_installer_info(self, path: str) -> dict[str, Any]: ...


@runtime_checkable
class DesktopUpdatePort(Protocol):
    """Auto-update interface."""

    async def check_for_updates(
        self, channel: UpdateChannel = UpdateChannel.STABLE
    ) -> Sequence[ReleaseInfo]: ...
    async def download_update(self, manifest: UpdateManifest) -> bool: ...
    async def install_update(self, manifest: UpdateManifest) -> UpdateResult: ...
    async def get_update_status(self) -> UpdateStatus: ...
    async def get_update_history(self, limit: int = 50) -> Sequence[UpdateHistoryRecord]: ...
    async def get_pending_update(self) -> UpdateManifest | None: ...


@runtime_checkable
class DesktopUpdateChannelPort(Protocol):
    """Update channel management interface."""

    async def get_channels(self) -> Sequence[UpdateChannel]: ...
    async def set_channel(self, channel: UpdateChannel) -> None: ...
    async def get_current_channel(self) -> UpdateChannel: ...


@runtime_checkable
class DesktopRollbackPort(Protocol):
    """Rollback interface."""

    async def rollback(self, target_version: str | None = None) -> UpdateResult: ...
    async def get_available_versions(self) -> Sequence[str]: ...
    async def can_rollback(self) -> bool: ...


@runtime_checkable
class RuntimeDiscoveryPort(Protocol):
    """Runtime discovery interface."""

    async def discover_runtimes(self) -> RuntimeDiscoveryResult: ...
    async def get_discovered_runtimes(self) -> Sequence[RuntimeInfo]: ...
    async def get_runtime(self, runtime_type: RuntimeType) -> RuntimeInfo | None: ...
    async def verify_runtime(self, runtime_type: RuntimeType) -> bool: ...
    async def refresh_runtime(self, runtime_type: RuntimeType) -> RuntimeInfo | None: ...


@runtime_checkable
class OfflineRuntimePort(Protocol):
    """Offline mode interface."""

    async def enable_offline_mode(self) -> None: ...
    async def disable_offline_mode(self) -> None: ...
    async def get_offline_state(self) -> OfflineState: ...
    async def get_offline_config(self) -> OfflineConfig: ...
    async def update_offline_config(self, config: OfflineConfig) -> OfflineConfig: ...
    async def get_queued_events(self) -> Sequence[dict[str, Any]]: ...
    async def sync_queued_events(self) -> int: ...


@runtime_checkable
class BackupPort(Protocol):
    """Backup interface."""

    async def create_backup(self, config: BackupConfig) -> BackupResult: ...
    async def list_backups(self) -> Sequence[BackupResult]: ...
    async def get_backup_info(self, backup_path: str) -> BackupResult | None: ...
    async def delete_backup(self, backup_path: str) -> bool: ...


@runtime_checkable
class RestorePort(Protocol):
    """Restore interface."""

    async def restore(self, config: RestoreConfig) -> BackupResult: ...
    async def verify_backup(self, backup_path: str) -> bool: ...
    async def get_available_restore_points(self) -> Sequence[str]: ...


@runtime_checkable
class FirstRunPort(Protocol):
    """First run wizard interface."""

    async def get_state(self) -> FirstRunState: ...
    async def is_completed(self) -> bool: ...
    async def run_step(self, step: str) -> dict[str, Any]: ...
    async def skip_step(self, step: str) -> None: ...
    async def complete(self) -> None: ...
    async def reset(self) -> None: ...


__all__ = [
    "DesktopInstallerPort",
    "DesktopUpdatePort",
    "DesktopUpdateChannelPort",
    "DesktopRollbackPort",
    "RuntimeDiscoveryPort",
    "OfflineRuntimePort",
    "BackupPort",
    "RestorePort",
    "FirstRunPort",
]
