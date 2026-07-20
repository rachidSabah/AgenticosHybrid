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


# ── Window Models ──


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
        return {
            "theme": self.theme.value,
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
]
