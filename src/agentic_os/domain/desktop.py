"""
Desktop Runtime Domain Models

Domain layer for Phase 4 Milestone 6 — Desktop Runtime Foundation.
Pure Python, no external dependencies.

Every desktop runtime concept — windows, workspaces, layouts, menus,
notifications, diagnostics — lives here as a pure domain type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Enums ──


class DesktopRuntimeStatus(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class WindowState(StrEnum):
    NORMAL = "normal"
    MINIMIZED = "minimized"
    MAXIMIZED = "maximized"
    FULLSCREEN = "fullscreen"
    HIDDEN = "hidden"
    CLOSED = "closed"


class WindowPosition(StrEnum):
    CENTER = "center"
    CUSTOM = "custom"
    CASCADE = "cascade"
    TILED = "tiled"


class PanelPosition(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"
    CENTER = "center"


class PanelState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    MINIMIZED = "minimized"
    FLOATING = "floating"
    DOCKED = "docked"


class DockingZone(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"
    CENTER = "center"
    TAB = "tab"
    SPLIT = "split"


class MenuType(StrEnum):
    APP = "app"
    FILE = "file"
    EDIT = "edit"
    VIEW = "view"
    WINDOW = "window"
    HELP = "help"
    CUSTOM = "custom"


class MenuItemType(StrEnum):
    ACTION = "action"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    SEPARATOR = "separator"
    SUBMENU = "submenu"


class NotificationLevel(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationAction(StrEnum):
    CREATED = "created"
    CLICKED = "clicked"
    DISMISSED = "dismissed"
    TIMED_OUT = "timed_out"


class ThemeMode(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    CLOSED = "closed"


class LayoutOrientation(StrEnum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    GRID = "grid"
    CUSTOM = "custom"


class DialogType(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CONFIRM = "confirm"
    OPEN_FILE = "open_file"
    SAVE_FILE = "save_file"
    FOLDER_SELECT = "folder_select"


class DesktopEventType(StrEnum):
    STARTED = "desktop.started"
    STOPPED = "desktop.stopped"
    READY = "desktop.ready"
    WORKSPACE_CREATED = "desktop.workspace.created"
    WORKSPACE_LOADED = "desktop.workspace.loaded"
    LAYOUT_CHANGED = "desktop.layout.changed"
    WINDOW_OPENED = "desktop.window.opened"
    WINDOW_CLOSED = "desktop.window.closed"
    PERFORMANCE_UPDATED = "desktop.performance.updated"
    DIAGNOSTICS_UPDATED = "desktop.diagnostics.updated"
    NOTIFICATION_CREATED = "desktop.notification.created"
    NOTIFICATION_CLICKED = "desktop.notification.clicked"
    THEME_CHANGED = "desktop.theme.changed"
    WORKSPACE_SWITCHED = "desktop.workspace.switched"
    MENU_ACTION = "desktop.menu.action"
    CONFIG_CHANGED = "desktop.config.changed"
    INSTALLED = "desktop.installed"
    UPDATED = "desktop.updated"
    UPDATE_AVAILABLE = "desktop.update.available"
    UPDATE_STARTED = "desktop.update.started"
    UPDATE_COMPLETED = "desktop.update.completed"
    UPDATE_FAILED = "desktop.update.failed"
    ROLLBACK_STARTED = "desktop.rollback.started"
    ROLLBACK_COMPLETED = "desktop.rollback.completed"
    RUNTIME_DISCOVERED = "desktop.runtime.discovered"
    RUNTIME_UPDATED = "desktop.runtime.updated"
    RUNTIME_REMOVED = "desktop.runtime.removed"
    OFFLINE_ENABLED = "desktop.offline.enabled"
    OFFLINE_DISABLED = "desktop.offline.disabled"
    BACKUP_CREATED = "desktop.backup.created"
    RESTORE_COMPLETED = "desktop.restore.completed"
    FIRST_RUN_COMPLETED = "desktop.first_run.completed"
    INSTALLER_PROGRESS = "desktop.installer.progress"
    HARDENING_STARTED = "desktop.hardening.started"
    HARDENING_COMPLETED = "desktop.hardening.completed"
    HARDENING_FAILED = "desktop.hardening.failed"
    INTEGRITY_CHECK_PASSED = "desktop.integrity.passed"
    INTEGRITY_CHECK_FAILED = "desktop.integrity.failed"
    RECOVERY_STARTED = "desktop.recovery.started"
    RECOVERY_COMPLETED = "desktop.recovery.completed"
    RECOVERY_FAILED = "desktop.recovery.failed"
    MEMORY_LEAK_DETECTED = "desktop.memory_leak.detected"
    THREAD_ANOMALY_DETECTED = "desktop.thread_anomaly.detected"
    CLEANUP_STARTED = "desktop.cleanup.started"
    CLEANUP_COMPLETED = "desktop.cleanup.completed"
    GRACEFUL_SHUTDOWN = "desktop.graceful_shutdown"
    RECOVERY_MODE_ENTERED = "desktop.recovery_mode.entered"
    RECOVERY_MODE_EXITED = "desktop.recovery_mode.exited"


class UpdateChannel(StrEnum):
    STABLE = "stable"
    BETA = "beta"
    NIGHTLY = "nightly"


class UpdateStatus(StrEnum):
    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    READY = "ready"
    INSTALLING = "installing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class InstallerType(StrEnum):
    MSI = "msi"
    EXE = "exe"
    PORTABLE_ZIP = "portable_zip"
    APPIMAGE = "appimage"
    DEB = "deb"
    RPM = "rpm"
    DMG = "dmg"
    PKG = "pkg"


class RuntimeType(StrEnum):
    PYTHON = "python"
    GIT = "git"
    DOCKER = "docker"
    NODE = "node"
    CLAUDE_CODE = "claude_code"
    OPENCODE = "opencode"
    GEMINI_CLI = "gemini_cli"
    CODEX_CLI = "codex_cli"
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    LLAMA_CPP = "llama.cpp"
    OPENAI_LOCAL = "openai_local"
    MCP_SERVER = "mcp_server"
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    REDIS = "redis"
    UNKNOWN = "unknown"
    CUSTOM = "custom"


class OfflineState(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    RECONNECTING = "reconnecting"
    SYNCHRONIZING = "synchronizing"


class BackupState(StrEnum):
    CREATING = "creating"
    COMPLETED = "completed"
    FAILED = "failed"
    RESTORING = "restoring"
    RESTORED = "restored"
    RESTORE_FAILED = "restore_failed"


class BackupScope(StrEnum):
    FULL = "full"
    CONFIG = "config"
    WORKSPACES = "workspaces"
    DATABASE = "database"
    MEMORY = "memory"
    CUSTOM = "custom"


class FirstRunStep(StrEnum):
    WELCOME = "welcome"
    WORKSPACE = "workspace"
    CONFIG = "config"
    RUNTIME_DISCOVERY = "runtime_discovery"
    PROVIDER = "provider"
    PLUGIN = "plugin"
    DATABASE = "database"
    HEALTH = "health"
    COMPLETE = "complete"


# ── Runtime Discovery Models ──


@dataclass
class RuntimeInfo:
    runtime_type: RuntimeType = RuntimeType.UNKNOWN
    name: str = ""
    version: str = ""
    path: str = ""
    executable: str = ""
    capabilities: list[str] = field(default_factory=list)
    detected_at: datetime = field(default_factory=_utcnow)
    verified: bool = False
    source: str = "auto"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_type": self.runtime_type.value,
            "name": self.name,
            "version": self.version,
            "path": self.path,
            "executable": self.executable,
            "capabilities": self.capabilities,
            "detected_at": self.detected_at.isoformat(),
            "verified": self.verified,
            "source": self.source,
            "metadata": self.metadata,
        }


# ── Update Models ──


def _coerce_enum(enum_cls: type[StrEnum], value: Any, default: StrEnum) -> StrEnum:
    """Coerce *value* to *enum_cls*, tolerating raw strings from JSON bodies.

    The update API builds manifests straight from frontend JSON, where enum
    fields arrive as plain strings (e.g. ``channel="stable"``). Convert them
    (case-insensitively) so ``.value`` access in ``to_dict()`` and install
    flows never raises ``AttributeError``; fall back to *default* for values
    that match no member.
    """
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        for candidate in (value, value.lower()):
            try:
                return enum_cls(candidate)
            except ValueError:
                continue
    return default


@dataclass
class ReleaseInfo:
    version: str = ""
    tag: str = ""
    url: str = ""
    published_at: datetime | None = None
    release_notes: str = ""
    assets: list[dict[str, Any]] = field(default_factory=list)
    prerelease: bool = False
    channel: UpdateChannel = UpdateChannel.STABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "tag": self.tag,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "release_notes": self.release_notes,
            "assets": self.assets,
            "prerelease": self.prerelease,
            "channel": self.channel.value,
        }


@dataclass
class UpdateManifest:
    version: str = ""
    download_url: str = ""
    checksum_sha256: str = ""
    signature: str = ""
    size_bytes: int = 0
    release_date: str = ""
    min_version: str = ""
    changelog: list[str] = field(default_factory=list)
    mandatory: bool = False
    channel: UpdateChannel = UpdateChannel.STABLE
    installer_type: InstallerType = InstallerType.EXE
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # API constructs this straight from frontend JSON — coerce enum fields.
        self.channel = _coerce_enum(UpdateChannel, self.channel, UpdateChannel.STABLE)
        self.installer_type = _coerce_enum(InstallerType, self.installer_type, InstallerType.EXE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "download_url": self.download_url,
            "checksum_sha256": self.checksum_sha256,
            "signature": self.signature,
            "size_bytes": self.size_bytes,
            "release_date": self.release_date,
            "min_version": self.min_version,
            "changelog": self.changelog,
            "mandatory": self.mandatory,
            "channel": self.channel.value,
            "installer_type": self.installer_type.value,
            "metadata": self.metadata,
        }


@dataclass
class DeltaUpdate:
    from_version: str = ""
    to_version: str = ""
    patch_url: str = ""
    checksum_sha256: str = ""
    signature: str = ""
    size_bytes: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "patch_url": self.patch_url,
            "checksum_sha256": self.checksum_sha256,
            "signature": self.signature,
            "size_bytes": self.size_bytes,
            "metadata": self.metadata,
        }


@dataclass
class UpdateResult:
    success: bool = False
    previous_version: str = ""
    new_version: str = ""
    installed_at: datetime = field(default_factory=_utcnow)
    duration_seconds: float = 0.0
    error: str | None = None
    rolled_back: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "previous_version": self.previous_version,
            "new_version": self.new_version,
            "installed_at": self.installed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "rolled_back": self.rolled_back,
            "metadata": self.metadata,
        }


@dataclass
class UpdateHistoryRecord:
    id: str = field(default_factory=lambda: uuid4().hex)
    from_version: str = ""
    to_version: str = ""
    channel: UpdateChannel = UpdateChannel.STABLE
    status: UpdateStatus = UpdateStatus.COMPLETED
    installed_at: datetime = field(default_factory=_utcnow)
    duration_seconds: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Records may be built from untyped data (API bodies, persisted JSON) —
        # coerce so to_dict() never crashes on a raw string.
        self.channel = _coerce_enum(UpdateChannel, self.channel, UpdateChannel.STABLE)
        self.status = _coerce_enum(UpdateStatus, self.status, UpdateStatus.COMPLETED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "channel": self.channel.value,
            "status": self.status.value,
            "installed_at": self.installed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "metadata": self.metadata,
        }


# ── Installer Models ──


@dataclass
class InstallerConfig:
    installer_type: InstallerType = InstallerType.EXE
    output_dir: str = ""
    app_name: str = "AgenticOS"
    app_version: str = "0.9.5"
    publisher: str = "AgenticOS"
    description: str = "Agentic Operating System"
    icon_path: str = ""
    start_menu_folder: str = "AgenticOS"
    desktop_shortcut: bool = True
    start_menu_shortcut: bool = True
    auto_start: bool = False
    file_associations: list[dict[str, Any]] = field(default_factory=list)
    include_portable_runtime: bool = False
    sign: bool = True
    certificate_path: str = ""
    timestamp_server: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "installer_type": self.installer_type.value,
            "output_dir": self.output_dir,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "publisher": self.publisher,
            "description": self.description,
            "icon_path": self.icon_path,
            "start_menu_folder": self.start_menu_folder,
            "desktop_shortcut": self.desktop_shortcut,
            "start_menu_shortcut": self.start_menu_shortcut,
            "auto_start": self.auto_start,
            "file_associations": self.file_associations,
            "include_portable_runtime": self.include_portable_runtime,
            "sign": self.sign,
            "certificate_path": self.certificate_path,
            "timestamp_server": self.timestamp_server,
            "metadata": self.metadata,
        }


@dataclass
class InstallerResult:
    success: bool = False
    installer_path: str = ""
    installer_type: InstallerType = InstallerType.EXE
    size_bytes: int = 0
    checksum_sha256: str = ""
    duration_seconds: float = 0.0
    error: str | None = None
    output: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "installer_path": self.installer_path,
            "installer_type": self.installer_type.value,
            "size_bytes": self.size_bytes,
            "checksum_sha256": self.checksum_sha256,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "output": self.output,
            "metadata": self.metadata,
        }


# ── Platform Integration Models ──


@dataclass
class ShortcutInfo:
    name: str = "AgenticOS"
    target_path: str = ""
    arguments: str = ""
    icon_path: str = ""
    working_dir: str = ""
    description: str = ""
    locations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target_path": self.target_path,
            "arguments": self.arguments,
            "icon_path": self.icon_path,
            "working_dir": self.working_dir,
            "description": self.description,
            "locations": self.locations,
            "metadata": self.metadata,
        }


@dataclass
class FileAssociation:
    extension: str = ""
    prog_id: str = "AgenticOS"
    description: str = ""
    icon_path: str = ""
    command: str = ""
    content_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "extension": self.extension,
            "prog_id": self.prog_id,
            "description": self.description,
            "icon_path": self.icon_path,
            "command": self.command,
            "content_type": self.content_type,
            "metadata": self.metadata,
        }


# ── Offline Models ──


@dataclass
class OfflineConfig:
    enabled: bool = True
    cache_dir: str = ""
    max_cache_size_mb: int = 1024
    sync_interval_seconds: int = 300
    auth_token_cache: bool = True
    queue_offline_events: bool = True
    auto_sync_on_connect: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "cache_dir": self.cache_dir,
            "max_cache_size_mb": self.max_cache_size_mb,
            "sync_interval_seconds": self.sync_interval_seconds,
            "auth_token_cache": self.auth_token_cache,
            "queue_offline_events": self.queue_offline_events,
            "auto_sync_on_connect": self.auto_sync_on_connect,
            "metadata": self.metadata,
        }


@dataclass
class OfflineEvent:
    id: str = field(default_factory=lambda: uuid4().hex)
    event_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    queued_at: datetime = field(default_factory=_utcnow)
    synced: bool = False
    synced_at: datetime | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "payload": self.payload,
            "queued_at": self.queued_at.isoformat(),
            "synced": self.synced,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
            "error": self.error,
        }


# ── Backup / Restore Models ──


@dataclass
class BackupConfig:
    scope: BackupScope = BackupScope.FULL
    output_path: str = ""
    compress: bool = True
    encrypt: bool = False
    encryption_key: str = ""
    include_logs: bool = True
    include_cache: bool = False
    max_backups: int = 10
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "output_path": self.output_path,
            "compress": self.compress,
            "encrypt": self.encrypt,
            "include_logs": self.include_logs,
            "include_cache": self.include_cache,
            "max_backups": self.max_backups,
            "metadata": self.metadata,
        }


@dataclass
class BackupResult:
    success: bool = False
    backup_path: str = ""
    size_bytes: int = 0
    scope: BackupScope = BackupScope.FULL
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    file_count: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "backup_path": self.backup_path,
            "size_bytes": self.size_bytes,
            "scope": self.scope.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "file_count": self.file_count,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class RestoreConfig:
    backup_path: str = ""
    scope: BackupScope = BackupScope.FULL
    overwrite: bool = False
    verify_before: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backup_path": self.backup_path,
            "scope": self.scope.value,
            "overwrite": self.overwrite,
            "verify_before": self.verify_before,
            "metadata": self.metadata,
        }


@dataclass
class FirstRunState:
    completed: bool = False
    current_step: FirstRunStep = FirstRunStep.WELCOME
    workspace_created: bool = False
    config_saved: bool = False
    runtimes_discovered: bool = False
    provider_configured: bool = False
    plugins_initialized: bool = False
    database_initialized: bool = False
    health_verified: bool = False
    completed_at: datetime | None = None
    skipped_steps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "completed": self.completed,
            "current_step": self.current_step.value,
            "workspace_created": self.workspace_created,
            "config_saved": self.config_saved,
            "runtimes_discovered": self.runtimes_discovered,
            "provider_configured": self.provider_configured,
            "plugins_initialized": self.plugins_initialized,
            "database_initialized": self.database_initialized,
            "health_verified": self.health_verified,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "skipped_steps": self.skipped_steps,
            "metadata": self.metadata,
        }


@dataclass
class RuntimeDiscoveryResult:
    total_discovered: int = 0
    runtimes: list[RuntimeInfo] = field(default_factory=list)
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_discovered": self.total_discovered,
            "runtimes": [r.to_dict() for r in self.runtimes],
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
        }


@dataclass
class WindowConfig:
    title: str = "AgenticOS"
    url: str = ""
    width: int = 1280
    height: int = 800
    min_width: int = 800
    min_height: int = 600
    x: int | None = None
    y: int | None = None
    state: WindowState = WindowState.NORMAL
    resizable: bool = True
    maximizable: bool = True
    minimizable: bool = True
    closable: bool = True
    decorations: bool = True
    always_on_top: bool = False
    fullscreen: bool = False
    transparent: bool = False
    center: bool = True
    label: str = "main"


@dataclass
class WindowInfo:
    id: str = field(default_factory=lambda: uuid4().hex)
    label: str = ""
    title: str = ""
    url: str = ""
    width: int = 1280
    height: int = 800
    x: int | None = None
    y: int | None = None
    state: WindowState = WindowState.NORMAL
    focused: bool = False
    created_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "title": self.title,
            "url": self.url,
            "width": self.width,
            "height": self.height,
            "x": self.x,
            "y": self.y,
            "state": self.state.value,
            "focused": self.focused,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


# ── Workspace Models ──


@dataclass
class TabInfo:
    id: str = field(default_factory=lambda: uuid4().hex)
    title: str = ""
    url: str = ""
    icon: str | None = None
    active: bool = False
    closable: bool = True
    pinned: bool = False
    order: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "icon": self.icon,
            "active": self.active,
            "closable": self.closable,
            "pinned": self.pinned,
            "order": self.order,
            "metadata": self.metadata,
        }


@dataclass
class PanelConfig:
    id: str = field(default_factory=lambda: uuid4().hex)
    title: str = ""
    position: PanelPosition = PanelPosition.LEFT
    state: PanelState = PanelState.OPEN
    width: int = 300
    height: int = 300
    min_width: int = 150
    min_height: int = 100
    resizable: bool = True
    collapsible: bool = True
    order: int = 0
    content_url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "position": self.position.value,
            "state": self.state.value,
            "width": self.width,
            "height": self.height,
            "min_width": self.min_width,
            "min_height": self.min_height,
            "resizable": self.resizable,
            "collapsible": self.collapsible,
            "order": self.order,
            "content_url": self.content_url,
            "metadata": self.metadata,
        }


@dataclass
class WorkspaceLayout:
    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    orientation: LayoutOrientation = LayoutOrientation.HORIZONTAL
    panels: list[PanelConfig] = field(default_factory=list)
    active_tab_id: str | None = None
    split_ratio: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "orientation": self.orientation.value,
            "panels": [p.to_dict() for p in self.panels],
            "active_tab_id": self.active_tab_id,
            "split_ratio": self.split_ratio,
            "metadata": self.metadata,
        }


@dataclass
class Workspace:
    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = "Default"
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE
    layout: WorkspaceLayout = field(default_factory=WorkspaceLayout)
    tabs: list[TabInfo] = field(default_factory=list)
    is_dirty: bool = False
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "layout": self.layout.to_dict() if self.layout else None,
            "tabs": [t.to_dict() for t in self.tabs],
            "is_dirty": self.is_dirty,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


# ── Menu Models ──


@dataclass
class MenuItem:
    id: str = field(default_factory=lambda: uuid4().hex)
    label: str = ""
    item_type: MenuItemType = MenuItemType.ACTION
    shortcut: str | None = None
    icon: str | None = None
    enabled: bool = True
    checked: bool = False
    action: str | None = None
    children: list[MenuItem] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "item_type": self.item_type.value,
            "shortcut": self.shortcut,
            "icon": self.icon,
            "enabled": self.enabled,
            "checked": self.checked,
            "action": self.action,
            "children": [c.to_dict() for c in self.children],
            "metadata": self.metadata,
        }


@dataclass
class MenuConfig:
    id: str = field(default_factory=lambda: uuid4().hex)
    menu_type: MenuType = MenuType.APP
    label: str = ""
    items: list[MenuItem] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "menu_type": self.menu_type.value,
            "label": self.label,
            "items": [i.to_dict() for i in self.items],
            "metadata": self.metadata,
        }


# ── Notification Models ──


@dataclass
class DesktopNotification:
    id: str = field(default_factory=lambda: uuid4().hex)
    title: str = ""
    message: str = ""
    level: NotificationLevel = NotificationLevel.INFO
    action: NotificationAction = NotificationAction.CREATED
    source: str = "system"
    duration_seconds: float = 5.0
    persistent: bool = False
    icon: str | None = None
    action_url: str | None = None
    created_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "level": self.level.value,
            "action": self.action.value,
            "source": self.source,
            "duration_seconds": self.duration_seconds,
            "persistent": self.persistent,
            "icon": self.icon,
            "action_url": self.action_url,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


# ── Dialog Models ──


@dataclass
class DialogConfig:
    dialog_type: DialogType = DialogType.INFO
    title: str = ""
    message: str = ""
    default_path: str | None = None
    filters: list[dict[str, Any]] = field(default_factory=list)
    multiple: bool = False
    directory: bool = False
    confirm_label: str = "OK"
    cancel_label: str = "Cancel"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dialog_type": self.dialog_type.value,
            "title": self.title,
            "message": self.message,
            "default_path": self.default_path,
            "filters": self.filters,
            "multiple": self.multiple,
            "directory": self.directory,
            "confirm_label": self.confirm_label,
            "cancel_label": self.cancel_label,
            "metadata": self.metadata,
        }


@dataclass
class DialogResult:
    accepted: bool = False
    selected_paths: list[str] = field(default_factory=list)
    selected_text: str = ""
    confirmed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "selected_paths": self.selected_paths,
            "selected_text": self.selected_text,
            "confirmed": self.confirmed,
            "metadata": self.metadata,
        }


# ── Desktop Performance & Diagnostics ──


@dataclass
class DesktopPerformanceMetrics:
    cpu_usage_percent: float = 0.0
    memory_usage_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    gpu_name: str = ""
    gpu_memory_mb: float = 0.0
    disk_usage_percent: float = 0.0
    disk_free_gb: float = 0.0
    disk_total_gb: float = 0.0
    workspace_storage_used_mb: float = 0.0
    workspace_storage_total_mb: float = 0.0
    cache_size_mb: float = 0.0
    process_count: int = 0
    window_count: int = 0
    uptime_seconds: float = 0.0
    sampled_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_usage_percent": self.cpu_usage_percent,
            "memory_usage_percent": self.memory_usage_percent,
            "memory_used_mb": self.memory_used_mb,
            "memory_total_mb": self.memory_total_mb,
            "gpu_name": self.gpu_name,
            "gpu_memory_mb": self.gpu_memory_mb,
            "disk_usage_percent": self.disk_usage_percent,
            "disk_free_gb": self.disk_free_gb,
            "disk_total_gb": self.disk_total_gb,
            "workspace_storage_used_mb": self.workspace_storage_used_mb,
            "workspace_storage_total_mb": self.workspace_storage_total_mb,
            "cache_size_mb": self.cache_size_mb,
            "process_count": self.process_count,
            "window_count": self.window_count,
            "uptime_seconds": self.uptime_seconds,
            "sampled_at": self.sampled_at.isoformat(),
        }


@dataclass
class DesktopDiagnosticsInfo:
    os_name: str = ""
    os_version: str = ""
    os_arch: str = ""
    hostname: str = ""
    python_version: str = ""
    app_version: str = ""
    tauri_version: str = ""
    backend_version: str = ""
    node_version: str = ""
    npm_version: str = ""
    rust_version: str = ""
    cargo_version: str = ""
    display_resolution: str = ""
    display_count: int = 1
    language: str = "en-US"
    timezone: str = "UTC"
    locale: str = "en-US"
    sampled_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "os_name": self.os_name,
            "os_version": self.os_version,
            "os_arch": self.os_arch,
            "hostname": self.hostname,
            "python_version": self.python_version,
            "app_version": self.app_version,
            "tauri_version": self.tauri_version,
            "backend_version": self.backend_version,
            "node_version": self.node_version,
            "npm_version": self.npm_version,
            "rust_version": self.rust_version,
            "cargo_version": self.cargo_version,
            "display_resolution": self.display_resolution,
            "display_count": self.display_count,
            "language": self.language,
            "timezone": self.timezone,
            "locale": self.locale,
            "sampled_at": self.sampled_at.isoformat(),
        }


# ── Configuration Models ──


@dataclass
class DesktopConfig:
    theme: ThemeMode = ThemeMode.SYSTEM
    language: str = "en-US"
    auto_start: bool = False
    minimize_to_tray: bool = True
    confirm_on_close: bool = True
    enable_notifications: bool = True
    enable_global_search: bool = True
    enable_command_palette: bool = True
    enable_keyboard_shortcuts: bool = True
    enable_auto_save: bool = True
    auto_save_interval_seconds: int = 30
    workspace_dir: str = ""
    cache_dir: str = ""
    log_dir: str = ""
    session_timeout_minutes: int = 1440
    max_recent_workspaces: int = 10
    check_updates: bool = True
    telemetry_enabled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        theme_val = self.theme.value if isinstance(self.theme, ThemeMode) else str(self.theme)
        return {
            "theme": theme_val,
            "language": self.language,
            "auto_start": self.auto_start,
            "minimize_to_tray": self.minimize_to_tray,
            "confirm_on_close": self.confirm_on_close,
            "enable_notifications": self.enable_notifications,
            "enable_global_search": self.enable_global_search,
            "enable_command_palette": self.enable_command_palette,
            "enable_keyboard_shortcuts": self.enable_keyboard_shortcuts,
            "enable_auto_save": self.enable_auto_save,
            "auto_save_interval_seconds": self.auto_save_interval_seconds,
            "workspace_dir": self.workspace_dir,
            "cache_dir": self.cache_dir,
            "log_dir": self.log_dir,
            "session_timeout_minutes": self.session_timeout_minutes,
            "max_recent_workspaces": self.max_recent_workspaces,
            "check_updates": self.check_updates,
            "telemetry_enabled": self.telemetry_enabled,
            "metadata": self.metadata,
        }


# ── Keyboard Shortcut ──


@dataclass
class KeyboardShortcut:
    id: str = field(default_factory=lambda: uuid4().hex)
    key: str = ""
    modifiers: list[str] = field(default_factory=list)
    action: str = ""
    label: str = ""
    enabled: bool = True
    global_shortcut: bool = False
    category: str = "general"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "modifiers": self.modifiers,
            "action": self.action,
            "label": self.label,
            "enabled": self.enabled,
            "global_shortcut": self.global_shortcut,
            "category": self.category,
            "metadata": self.metadata,
        }


# ── Local Database Models ──


@dataclass
class DatabaseInfo:
    path: str = ""
    size_mb: float = 0.0
    table_count: int = 0
    migration_count: int = 0
    last_migration: str = ""
    status: str = "connected"
    error: str | None = None
    sampled_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_mb": self.size_mb,
            "table_count": self.table_count,
            "migration_count": self.migration_count,
            "last_migration": self.last_migration,
            "status": self.status,
            "error": self.error,
            "sampled_at": self.sampled_at.isoformat(),
        }


@dataclass
class MigrationRecord:
    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    applied_at: datetime = field(default_factory=_utcnow)
    checksum: str = ""
    success: bool = True
    duration_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "applied_at": self.applied_at.isoformat(),
            "checksum": self.checksum,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


# ── Clipboard ──


@dataclass
class ClipboardContent:
    text: str | None = None
    html: str | None = None
    image_path: str | None = None
    file_paths: list[str] = field(default_factory=list)
    content_type: str = "text"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "html": self.html,
            "image_path": self.image_path,
            "file_paths": self.file_paths,
            "content_type": self.content_type,
        }


# ── Local Database Types (SQLite-based persistence) ──


@dataclass
class WorkspaceMetadata:
    workspace_id: str = ""
    key: str = ""
    value: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class SessionRecord:
    id: str = field(default_factory=lambda: uuid4().hex)
    session_type: str = "app"
    started_at: datetime = field(default_factory=_utcnow)
    ended_at: datetime | None = None
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_type": self.session_type,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }


# ── Drag & Drop ──


@dataclass
class DragDropPayload:
    file_paths: list[str] = field(default_factory=list)
    text: str | None = None
    urls: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_paths": self.file_paths,
            "text": self.text,
            "urls": self.urls,
            "data": self.data,
        }


# ── Terminal ──


@dataclass
class TerminalConfig:
    id: str = field(default_factory=lambda: uuid4().hex)
    title: str = "Terminal"
    command: str = ""
    cwd: str | None = None
    rows: int = 24
    cols: int = 80
    shell_path: str = ""
    env: dict[str, str] = field(default_factory=dict)
    auto_start: bool = True
    close_on_exit: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "command": self.command,
            "cwd": self.cwd,
            "rows": self.rows,
            "cols": self.cols,
            "shell_path": self.shell_path,
            "env": self.env,
            "auto_start": self.auto_start,
            "close_on_exit": self.close_on_exit,
        }


@dataclass
class TerminalInfo:
    id: str = ""
    title: str = ""
    pid: int = 0
    running: bool = False
    exit_code: int | None = None
    started_at: datetime | None = None
    config: TerminalConfig = field(default_factory=TerminalConfig)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "pid": self.pid,
            "running": self.running,
            "exit_code": self.exit_code,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "config": self.config.to_dict(),
        }


# ── Process ──


@dataclass
class ProcessInfo:
    pid: int = 0
    name: str = ""
    command: str = ""
    cwd: str = ""
    status: str = "running"
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    started_at: datetime = field(default_factory=_utcnow)
    children: list[ProcessInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "command": self.command,
            "cwd": self.cwd,
            "status": self.status,
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "started_at": self.started_at.isoformat(),
            "children": [c.to_dict() for c in self.children],
        }


# ── Command Palette ──


@dataclass
class CommandPaletteItem:
    id: str = field(default_factory=lambda: uuid4().hex)
    label: str = ""
    description: str = ""
    action: str = ""
    category: str = "general"
    shortcut: str | None = None
    icon: str | None = None
    enabled: bool = True
    order: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "action": self.action,
            "category": self.category,
            "shortcut": self.shortcut,
            "icon": self.icon,
            "enabled": self.enabled,
            "order": self.order,
        }


# ── Global Search ──


@dataclass
class SearchResult:
    id: str = ""
    title: str = ""
    description: str = ""
    category: str = ""
    url: str = ""
    score: float = 0.0
    icon: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "url": self.url,
            "score": self.score,
            "icon": self.icon,
        }


# ── Desktop Runtime State ──


@dataclass
class DesktopRuntimeState:
    status: DesktopRuntimeStatus = DesktopRuntimeStatus.STOPPED
    windows: list[WindowInfo] = field(default_factory=list)
    active_workspace_id: str = ""
    workspaces: list[Workspace] = field(default_factory=list)
    performance: DesktopPerformanceMetrics = field(default_factory=DesktopPerformanceMetrics)
    diagnostics: DesktopDiagnosticsInfo = field(default_factory=DesktopDiagnosticsInfo)
    config: DesktopConfig = field(default_factory=DesktopConfig)
    database: DatabaseInfo | None = None
    theme: ThemeMode = ThemeMode.SYSTEM
    started_at: datetime | None = None
    uptime_seconds: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "windows": [w.to_dict() for w in self.windows],
            "active_workspace_id": self.active_workspace_id,
            "workspaces": [w.to_dict() for w in self.workspaces],
            "performance": self.performance.to_dict(),
            "diagnostics": self.diagnostics.to_dict(),
            "config": self.config.to_dict(),
            "database": self.database.to_dict() if self.database else None,
            "theme": self.theme.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "uptime_seconds": self.uptime_seconds,
            "error": self.error,
        }


# ── Desktop Events ──


@dataclass
class DesktopEvent:
    event_type: DesktopEventType = DesktopEventType.READY
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "desktop"
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "payload": self.payload,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
        }


# ── Production Hardening Models ──


class IntegrityStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ShutdownStepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ServiceHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HardeningConfig:
    validate_on_startup: bool = True
    integrity_check_interval_seconds: int = 300
    enable_memory_leak_detection: bool = True
    enable_thread_monitoring: bool = True
    enable_resource_cleanup: bool = True
    enable_auto_repair: bool = True
    enable_recovery_mode: bool = True
    startup_profiling: bool = True
    memory_leak_threshold_mb: int = 50
    thread_count_threshold: int = 200
    max_startup_time_seconds: int = 30
    graceful_shutdown_timeout_seconds: int = 30
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validate_on_startup": self.validate_on_startup,
            "integrity_check_interval_seconds": self.integrity_check_interval_seconds,
            "enable_memory_leak_detection": self.enable_memory_leak_detection,
            "enable_thread_monitoring": self.enable_thread_monitoring,
            "enable_resource_cleanup": self.enable_resource_cleanup,
            "enable_auto_repair": self.enable_auto_repair,
            "enable_recovery_mode": self.enable_recovery_mode,
            "startup_profiling": self.startup_profiling,
            "memory_leak_threshold_mb": self.memory_leak_threshold_mb,
            "thread_count_threshold": self.thread_count_threshold,
            "max_startup_time_seconds": self.max_startup_time_seconds,
            "graceful_shutdown_timeout_seconds": self.graceful_shutdown_timeout_seconds,
            "metadata": self.metadata,
        }


@dataclass
class StartupValidationResult:
    success: bool = False
    started_at: datetime = field(default_factory=_utcnow)
    duration_seconds: float = 0.0
    checks: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "started_at": self.started_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "metadata": self.metadata,
        }


@dataclass
class IntegrityCheckResult:
    status: IntegrityStatus = IntegrityStatus.UNKNOWN
    checked_at: datetime = field(default_factory=_utcnow)
    duration_seconds: float = 0.0
    checks: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "checked_at": self.checked_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "metadata": self.metadata,
        }


@dataclass
class MemoryLeakReport:
    detected: bool = False
    detected_at: datetime = field(default_factory=_utcnow)
    current_memory_mb: float = 0.0
    baseline_memory_mb: float = 0.0
    growth_rate_mb_per_minute: float = 0.0
    suspicious_allocations: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "detected_at": self.detected_at.isoformat(),
            "current_memory_mb": self.current_memory_mb,
            "baseline_memory_mb": self.baseline_memory_mb,
            "growth_rate_mb_per_minute": self.growth_rate_mb_per_minute,
            "suspicious_allocations": self.suspicious_allocations,
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }


@dataclass
class ThreadReport:
    total_threads: int = 0
    active_threads: int = 0
    blocked_threads: int = 0
    deadlocked_threads: int = 0
    threshold_exceeded: bool = False
    threshold: int = 200
    sampled_at: datetime = field(default_factory=_utcnow)
    threads: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_threads": self.total_threads,
            "active_threads": self.active_threads,
            "blocked_threads": self.blocked_threads,
            "deadlocked_threads": self.deadlocked_threads,
            "threshold_exceeded": self.threshold_exceeded,
            "threshold": self.threshold,
            "sampled_at": self.sampled_at.isoformat(),
            "threads": self.threads,
            "metadata": self.metadata,
        }


@dataclass
class RecoveryModeConfig:
    enabled: bool = True
    auto_recover: bool = True
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    preserve_workspaces: bool = True
    clear_cache_on_recovery: bool = False
    notify_user: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "auto_recover": self.auto_recover,
            "max_retries": self.max_retries,
            "retry_delay_seconds": self.retry_delay_seconds,
            "preserve_workspaces": self.preserve_workspaces,
            "clear_cache_on_recovery": self.clear_cache_on_recovery,
            "notify_user": self.notify_user,
            "metadata": self.metadata,
        }


@dataclass
class CleanupResult:
    success: bool = False
    started_at: datetime = field(default_factory=_utcnow)
    duration_seconds: float = 0.0
    items_cleaned: int = 0
    space_freed_mb: float = 0.0
    actions: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "started_at": self.started_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "items_cleaned": self.items_cleaned,
            "space_freed_mb": self.space_freed_mb,
            "actions": self.actions,
            "errors": self.errors,
            "metadata": self.metadata,
        }


@dataclass
class SelfDiagnosticsReport:
    status: IntegrityStatus = IntegrityStatus.UNKNOWN
    generated_at: datetime = field(default_factory=_utcnow)
    services: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "generated_at": self.generated_at.isoformat(),
            "services": self.services,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }


@dataclass
class ResourceUsageSummary:
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    thread_count: int = 0
    open_handles: int = 0
    network_connections: int = 0
    disk_io_bytes_per_sec: float = 0.0
    sampled_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "thread_count": self.thread_count,
            "open_handles": self.open_handles,
            "network_connections": self.network_connections,
            "disk_io_bytes_per_sec": self.disk_io_bytes_per_sec,
            "sampled_at": self.sampled_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class RepairAction:
    action: str = ""
    target: str = ""
    status: str = "pending"
    duration_seconds: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class RepairResult:
    success: bool = False
    repaired: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    actions: list[RepairAction] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "repaired": self.repaired,
            "failed": self.failed,
            "actions": [a.to_dict() for a in self.actions],
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class ShutdownPlan:
    initiated_at: datetime = field(default_factory=_utcnow)
    timeout_seconds: int = 30
    force: bool = False
    save_workspaces: bool = True
    steps: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "initiated_at": self.initiated_at.isoformat(),
            "timeout_seconds": self.timeout_seconds,
            "force": self.force,
            "save_workspaces": self.save_workspaces,
            "steps": self.steps,
            "metadata": self.metadata,
        }


__all__ = [
    "DesktopRuntimeStatus",
    "WindowState",
    "WindowPosition",
    "PanelPosition",
    "PanelState",
    "DockingZone",
    "MenuType",
    "MenuItemType",
    "NotificationLevel",
    "NotificationAction",
    "ThemeMode",
    "WorkspaceStatus",
    "LayoutOrientation",
    "DialogType",
    "DesktopEventType",
    "WindowConfig",
    "WindowInfo",
    "TabInfo",
    "PanelConfig",
    "WorkspaceLayout",
    "Workspace",
    "MenuItem",
    "MenuConfig",
    "DesktopNotification",
    "DialogConfig",
    "DialogResult",
    "DesktopPerformanceMetrics",
    "DesktopDiagnosticsInfo",
    "DesktopConfig",
    "KeyboardShortcut",
    "DatabaseInfo",
    "MigrationRecord",
    "ClipboardContent",
    "WorkspaceMetadata",
    "SessionRecord",
    "DragDropPayload",
    "TerminalConfig",
    "TerminalInfo",
    "ProcessInfo",
    "CommandPaletteItem",
    "SearchResult",
    "DesktopRuntimeState",
    "DesktopEvent",
    "DesktopEventType",
    "UpdateChannel",
    "UpdateStatus",
    "InstallerType",
    "RuntimeType",
    "OfflineState",
    "BackupState",
    "BackupScope",
    "FirstRunStep",
    "RuntimeInfo",
    "ReleaseInfo",
    "UpdateManifest",
    "DeltaUpdate",
    "UpdateResult",
    "UpdateHistoryRecord",
    "InstallerConfig",
    "InstallerResult",
    "ShortcutInfo",
    "FileAssociation",
    "OfflineConfig",
    "OfflineEvent",
    "BackupConfig",
    "BackupResult",
    "RestoreConfig",
    "FirstRunState",
    "RuntimeDiscoveryResult",
    "HardeningConfig",
    "StartupValidationResult",
    "IntegrityCheckResult",
    "IntegrityStatus",
    "SelfDiagnosticsReport",
    "MemoryLeakReport",
    "ThreadReport",
    "RecoveryModeConfig",
    "CleanupResult",
    "ShutdownPlan",
    "ShutdownStepStatus",
    "ResourceUsageSummary",
    "ServiceHealthStatus",
    "RepairAction",
    "RepairResult",
]
