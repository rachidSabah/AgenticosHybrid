"""Desktop Runtime Manager — composition root for the desktop runtime."""

from __future__ import annotations

from datetime import UTC, datetime

from agentic_os.core.desktop.backup import BackupManager
from agentic_os.core.desktop.channel import ChannelManager
from agentic_os.core.desktop.clipboard import NativeClipboardService
from agentic_os.core.desktop.configuration import DesktopConfigurationManager
from agentic_os.core.desktop.database import LocalDatabaseManager
from agentic_os.core.desktop.delta_update import DeltaUpdateEngine
from agentic_os.core.desktop.diagnostics import DesktopDiagnosticsManager
from agentic_os.core.desktop.dragdrop import NativeDragDropService
from agentic_os.core.desktop.file_integration import NativeFileIntegration
from agentic_os.core.desktop.first_run import FirstRunWizard
from agentic_os.core.desktop.hardening import DesktopHardeningManager
from agentic_os.core.desktop.installer import DesktopInstallerManager
from agentic_os.core.desktop.logging import DesktopLogging
from agentic_os.core.desktop.menu import NativeMenuManager
from agentic_os.core.desktop.notification import NativeNotificationService
from agentic_os.core.desktop.offline import OfflineRuntimeManager
from agentic_os.core.desktop.performance import DesktopPerformanceMonitor
from agentic_os.core.desktop.portable import PortableRuntimeManager
from agentic_os.core.desktop.process import NativeProcessManager
from agentic_os.core.desktop.publisher import DesktopEventPublisher
from agentic_os.core.desktop.rollback import RollbackManager
from agentic_os.core.desktop.runtime_discovery import RuntimeDiscoveryManager
from agentic_os.core.desktop.signature import SignatureVerification
from agentic_os.core.desktop.terminal import NativeTerminalIntegration
from agentic_os.core.desktop.update import AutoUpdateManager
from agentic_os.core.desktop.window import NativeWindowManager
from agentic_os.core.desktop.windows_platform import WindowsPlatformIntegration
from agentic_os.core.desktop.workspace import WorkspaceManager
from agentic_os.domain.desktop import (
    DesktopRuntimeState,
    DesktopRuntimeStatus,
    KeyboardShortcut,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.desktop import (
    DesktopConfigurationPort,
    DesktopDatabasePort,
    DesktopDiagnosticsPort,
    DesktopEventPublisherPort,
    DesktopHardeningPort,
    DesktopLoggingPort,
    DesktopMenuPort,
    DesktopPerformancePort,
    DesktopWindowPort,
    DesktopWorkspacePort,
)
from agentic_os.ports.desktop_ops import RuntimeDiscoveryPort
from agentic_os.ports.event_bus import EventBus

log = get_logger("desktop.manager")


class DesktopRuntimeManager:
    """Composition root for the desktop runtime.

    Owns all desktop subsystems and wires them together.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._started_at: datetime | None = None
        self._status = DesktopRuntimeStatus.STOPPED

        # Subsystems (typed with port protocols for testability)
        self.window: DesktopWindowPort = NativeWindowManager()
        self.workspace: DesktopWorkspacePort = WorkspaceManager()
        self.notification = NativeNotificationService()
        self.file = NativeFileIntegration()
        self.clipboard = NativeClipboardService()
        self.terminal = NativeTerminalIntegration()
        self.process = NativeProcessManager()
        self.logging: DesktopLoggingPort = DesktopLogging()
        self.configuration: DesktopConfigurationPort = DesktopConfigurationManager()
        self.diagnostics: DesktopDiagnosticsPort = DesktopDiagnosticsManager()
        self.performance: DesktopPerformancePort = DesktopPerformanceMonitor()
        self.menu: DesktopMenuPort = NativeMenuManager()
        self.dragdrop = NativeDragDropService()
        self.database: DesktopDatabasePort = LocalDatabaseManager()
        self.publisher: DesktopEventPublisherPort = DesktopEventPublisher(bus)

        # Phase 4 M6 Part 2 subsystems
        self.runtime_discovery: RuntimeDiscoveryPort = RuntimeDiscoveryManager()
        self.update = AutoUpdateManager()
        self.installer = DesktopInstallerManager()
        self.first_run = FirstRunWizard()
        self.channel = ChannelManager()
        self.rollback = RollbackManager()
        self.portable = PortableRuntimeManager()
        self.offline = OfflineRuntimeManager()
        self.backup = BackupManager()
        self.delta_update = DeltaUpdateEngine()
        self.signature = SignatureVerification()
        self.windows_platform = WindowsPlatformIntegration()

        # Phase 4 M6 Part 3 — Production Hardening
        self.hardening: DesktopHardeningPort = DesktopHardeningManager()

        # Keyboard shortcuts
        self._shortcuts: dict[str, KeyboardShortcut] = {}
        self._default_shortcuts: list[KeyboardShortcut] = [
            KeyboardShortcut(
                key="p",
                modifiers=["CmdOrCtrl", "Shift"],
                action="view.command_palette",
                label="Command Palette",
                category="view",
            ),
            KeyboardShortcut(
                key="f",
                modifiers=["CmdOrCtrl", "Shift"],
                action="view.global_search",
                label="Global Search",
                category="view",
            ),
            KeyboardShortcut(
                key="n",
                modifiers=["CmdOrCtrl"],
                action="workspace.new",
                label="New Workspace",
                category="workspace",
            ),
            KeyboardShortcut(
                key="w",
                modifiers=["CmdOrCtrl"],
                action="window.close",
                label="Close Window",
                category="window",
            ),
            KeyboardShortcut(
                key="m",
                modifiers=["CmdOrCtrl"],
                action="window.minimize",
                label="Minimize",
                category="window",
            ),
            KeyboardShortcut(
                key="b",
                modifiers=["CmdOrCtrl"],
                action="view.toggle_sidebar",
                label="Toggle Sidebar",
                category="view",
            ),
            KeyboardShortcut(
                key="s", modifiers=["CmdOrCtrl"], action="file.save", label="Save", category="file"
            ),
            KeyboardShortcut(
                key="Tab",
                modifiers=["CmdOrCtrl"],
                action="workspace.next",
                label="Next Workspace",
                category="workspace",
            ),
        ]

    # ── Lifecycle ──

    async def start(self) -> None:
        self._status = DesktopRuntimeStatus.STARTING
        self._started_at = datetime.now(UTC)

        # Run startup validation
        if self.hardening._config.validate_on_startup:
            validation = await self.hardening.validate_startup()
            if not validation.success:
                log.warning(
                    "Startup validation failed, continuing anyway", errors=validation.errors
                )

        # Initialize database
        try:
            await self.database.initialize()
        except Exception as exc:
            log.warning("Local database initialization failed", error=str(exc))

        # Auto-discover system runtimes
        try:
            result = await self.runtime_discovery.discover_runtimes()
            log.info("Runtimes auto-discovered", count=result.total_discovered)
        except Exception as exc:
            log.warning("Runtime auto-discovery failed", error=str(exc))

        # Create default workspace if none exist
        if await self.workspace.get_workspace_count() == 0:
            ws = await self.workspace.create_workspace("Default")
            log.info("Default workspace created", workspace_id=ws.id)
            await self.publisher.publish_workspace_created(ws.id, ws.name)

        # Create default menus
        default_menus = await self.menu.get_default_menus()
        for menu in default_menus:
            await self.menu.create_menu(menu)

        # Register default keyboard shortcuts
        for shortcut in self._default_shortcuts:
            self._shortcuts[shortcut.id] = shortcut

        self._status = DesktopRuntimeStatus.RUNNING
        await self.publisher.publish_started()
        await self.publisher.publish_ready()
        log.info("Desktop runtime started")

    async def stop(self) -> None:
        self._status = DesktopRuntimeStatus.STOPPING
        await self.hardening.plan_shutdown()
        await self.hardening.cleanup_resources()
        await self.performance.stop_monitoring()
        await self.database.close()
        self._status = DesktopRuntimeStatus.STOPPED
        await self.publisher.publish_stopped()
        log.info("Desktop runtime stopped")

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    # ── State ──

    async def get_state(self) -> DesktopRuntimeState:
        uptime = 0.0
        if self._started_at:
            uptime = (datetime.now(UTC) - self._started_at).total_seconds()
        db_info = None
        try:
            db_info = await self.database.get_info()
        except Exception:
            pass

        return DesktopRuntimeState(
            status=self._status,
            windows=list(await self.window.list_windows()),
            active_workspace_id=self.workspace._active_workspace_id,
            workspaces=list(await self.workspace.list_workspaces()),
            performance=await self.performance.get_metrics(),
            diagnostics=await self.diagnostics.get_diagnostics(),
            config=await self.configuration.get_config(),
            database=db_info,
            started_at=self._started_at,
            uptime_seconds=uptime,
        )

    async def get_status(self) -> str:
        return self._status.value

    # ── Shortcuts ──

    async def list_shortcuts(self) -> list[KeyboardShortcut]:
        return list(self._shortcuts.values())

    async def register_shortcut(self, shortcut: KeyboardShortcut) -> KeyboardShortcut:
        self._shortcuts[shortcut.id] = shortcut
        return shortcut

    async def remove_shortcut(self, shortcut_id: str) -> bool:
        if shortcut_id in self._shortcuts:
            del self._shortcuts[shortcut_id]
            return True
        return False

    # ── Command Palette ──

    async def get_command_palette_items(self) -> list[dict[str, object]]:
        from agentic_os.domain.desktop import CommandPaletteItem

        items: list[CommandPaletteItem] = [
            CommandPaletteItem(
                label="New Workspace",
                description="Create a new workspace",
                action="workspace.new",
                category="workspace",
                shortcut="CmdOrCtrl+N",
            ),
            CommandPaletteItem(
                label="Switch Workspace",
                description="Switch to a different workspace",
                action="workspace.switch",
                category="workspace",
            ),
            CommandPaletteItem(
                label="Command Palette",
                description="Open the command palette",
                action="view.command_palette",
                category="view",
                shortcut="CmdOrCtrl+Shift+P",
            ),
            CommandPaletteItem(
                label="Global Search",
                description="Search across workspaces",
                action="view.global_search",
                category="view",
                shortcut="CmdOrCtrl+Shift+F",
            ),
            CommandPaletteItem(
                label="Toggle Dark Mode",
                description="Switch between light and dark themes",
                action="config.toggle_theme",
                category="configuration",
            ),
            CommandPaletteItem(
                label="Open File...",
                description="Open a file dialog",
                action="file.open",
                category="file",
                shortcut="CmdOrCtrl+O",
            ),
            CommandPaletteItem(
                label="Settings",
                description="Open desktop settings",
                action="config.open",
                category="configuration",
            ),
            CommandPaletteItem(
                label="About", description="About AgenticOS", action="help.about", category="help"
            ),
        ]
        return [i.to_dict() for i in items]

    # ── Global Search ──

    async def global_search(self, query: str) -> list[dict[str, object]]:
        from agentic_os.domain.desktop import SearchResult

        results: list[SearchResult] = []
        q = query.lower()

        # Search workspaces
        for ws in await self.workspace.list_workspaces():
            if q in ws.name.lower():
                results.append(
                    SearchResult(
                        id=ws.id,
                        title=ws.name,
                        description=f"Workspace — {len(ws.tabs)} tabs",
                        category="workspace",
                        url=f"/workspace/{ws.id}",
                        score=1.0,
                    )
                )

        # Search shortcuts
        for shortcut in self._shortcuts.values():
            if q in shortcut.label.lower() or q in shortcut.action.lower():
                results.append(
                    SearchResult(
                        id=shortcut.id,
                        title=shortcut.label,
                        description=f"Shortcut — {'+'.join(shortcut.modifiers + [shortcut.key])}",
                        category="shortcut",
                        score=0.8,
                    )
                )
        return [r.to_dict() for r in results[:20]]
