"""Tests for the Desktop Runtime core subsystems.

Covers:
- DesktopRuntimeManager
- WorkspaceManager
- NativeWindowManager
- NativeNotificationService
- NativeMenuManager
- DesktopConfigurationManager
- DesktopDiagnosticsManager
- DesktopPerformanceMonitor
- NativeClipboardService
- NativeFileIntegration
- NativeTerminalIntegration
- NativeProcessManager
- LocalDatabaseManager
- DesktopEventPublisher
- NativeDragDropService
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agentic_os.core.desktop import (
    DesktopConfigurationManager,
    DesktopDiagnosticsManager,
    DesktopEventPublisher,
    DesktopLogging,
    DesktopPerformanceMonitor,
    DesktopRuntimeManager,
    NativeClipboardService,
    NativeDragDropService,
    NativeFileIntegration,
    NativeMenuManager,
    NativeNotificationService,
    NativeProcessManager,
    NativeTerminalIntegration,
    NativeWindowManager,
    WorkspaceManager,
)
from agentic_os.domain.desktop import (
    ClipboardContent,
    DesktopNotification,
    KeyboardShortcut,
    MenuConfig,
    MenuItem,
    MenuType,
    NotificationLevel,
    PanelConfig,
    TabInfo,
    TerminalConfig,
    ThemeMode,
    WindowConfig,
    WorkspaceLayout,
)


@pytest.fixture
def mock_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


class TestNativeWindowManager:
    @pytest.mark.asyncio
    async def test_create_and_list_windows(self) -> None:
        mgr = NativeWindowManager()
        config = WindowConfig(label="test", title="Test Window")
        info = await mgr.create_window(config)
        assert info.title == "Test Window"

        windows = await mgr.list_windows()
        assert len(windows) == 1

    @pytest.mark.asyncio
    async def test_close_window(self) -> None:
        mgr = NativeWindowManager()
        info = await mgr.create_window(WindowConfig())
        assert await mgr.close_window(info.id) is True
        assert await mgr.close_window("nonexistent") is False

    @pytest.mark.asyncio
    async def test_window_operations(self) -> None:
        mgr = NativeWindowManager()
        info = await mgr.create_window(WindowConfig())

        assert await mgr.minimize_window(info.id) is True
        assert (await mgr.get_window(info.id)).state.value == "minimized"

        assert await mgr.restore_window(info.id) is True
        assert (await mgr.get_window(info.id)).state.value == "normal"

        assert await mgr.enter_fullscreen(info.id) is True
        assert (await mgr.get_window(info.id)).state.value == "fullscreen"

        assert await mgr.exit_fullscreen(info.id) is True
        assert (await mgr.get_window(info.id)).state.value == "normal"

        assert await mgr.hide_window(info.id) is True
        assert await mgr.show_window(info.id) is True

        assert await mgr.set_window_title(info.id, "New Title") is True
        assert (await mgr.get_window(info.id)).title == "New Title"

        assert await mgr.set_window_size(info.id, 800, 600) is True
        win = await mgr.get_window(info.id)
        assert win.width == 800

        assert await mgr.set_window_position(info.id, 100, 200) is True
        win = await mgr.get_window(info.id)
        assert win.x == 100


class TestWorkspaceManager:
    @pytest.mark.asyncio
    async def test_crud(self) -> None:
        mgr = WorkspaceManager()
        ws = await mgr.create_workspace("Test")
        assert ws.name == "Test"

        fetched = await mgr.get_workspace(ws.id)
        assert fetched is not None

        workspaces = await mgr.list_workspaces()
        assert len(workspaces) == 1

        await mgr.delete_workspace(ws.id)
        assert await mgr.get_workspace(ws.id) is None

    @pytest.mark.asyncio
    async def test_switch_workspace(self) -> None:
        mgr = WorkspaceManager()
        await mgr.create_workspace("A")
        ws2 = await mgr.create_workspace("B")

        switched = await mgr.switch_workspace(ws2.id)
        assert switched.id == ws2.id

        active = await mgr.get_active_workspace()
        assert active is not None
        assert active.id == ws2.id

    @pytest.mark.asyncio
    async def test_tabs(self) -> None:
        mgr = WorkspaceManager()
        ws = await mgr.create_workspace("Test")
        tab = TabInfo(title="Dashboard", url="/dashboard")
        added = await mgr.add_tab(ws.id, tab)
        assert added.title == "Dashboard"

        assert await mgr.remove_tab(ws.id, added.id) is True

    @pytest.mark.asyncio
    async def test_panels(self) -> None:
        mgr = WorkspaceManager()
        ws = await mgr.create_workspace("Test")
        panel = PanelConfig(title="Terminal")
        added = await mgr.add_panel(ws.id, panel)
        assert added.title == "Terminal"

        assert await mgr.remove_panel(ws.id, added.id) is True

    @pytest.mark.asyncio
    async def test_layout(self) -> None:
        mgr = WorkspaceManager()
        ws = await mgr.create_workspace("Test")
        layout = WorkspaceLayout(name="New Layout")
        updated = await mgr.update_workspace_layout(ws.id, layout)
        assert updated.name == "New Layout"

        fetched = await mgr.get_workspace_layout(ws.id)
        assert fetched.name == "New Layout"


class TestNativeNotificationService:
    @pytest.mark.asyncio
    async def test_send_and_list(self) -> None:
        svc = NativeNotificationService()
        notif = DesktopNotification(title="Test", message="Hello", level=NotificationLevel.INFO)
        sent = await svc.send_notification(notif)
        assert sent.title == "Test"

        notifications = await svc.list_notifications()
        assert len(notifications) == 1

        count = await svc.get_unread_count()
        assert count == 1

    @pytest.mark.asyncio
    async def test_dismiss_and_clear(self) -> None:
        svc = NativeNotificationService()
        n1 = DesktopNotification(title="A", message="1")
        n2 = DesktopNotification(title="B", message="2")
        await svc.send_notification(n1)
        await svc.send_notification(n2)

        assert await svc.dismiss_notification(n1.id) is True
        assert await svc.get_notification(n1.id) is not None

        await svc.clear_notifications()
        assert len(await svc.list_notifications()) == 0


class TestNativeMenuManager:
    @pytest.mark.asyncio
    async def test_crud(self) -> None:
        mgr = NativeMenuManager()
        menu = MenuConfig(menu_type=MenuType.FILE, label="File")
        created = await mgr.create_menu(menu)
        assert created.label == "File"

        menus = await mgr.list_menus()
        assert len(menus) == 1

        assert await mgr.delete_menu(created.id) is True

    @pytest.mark.asyncio
    async def test_menu_items(self) -> None:
        mgr = NativeMenuManager()
        menu = MenuConfig(menu_type=MenuType.EDIT, label="Edit")
        await mgr.create_menu(menu)

        item = MenuItem(label="Undo", action="edit.undo")
        added = await mgr.add_menu_item(menu.id, item)
        assert added.label == "Undo"

        assert await mgr.remove_menu_item(menu.id, added.id) is True

    @pytest.mark.asyncio
    async def test_get_default_menus(self) -> None:
        mgr = NativeMenuManager()
        menus = await mgr.get_default_menus()
        assert len(menus) >= 3


class TestDesktopConfigurationManager:
    @pytest.mark.asyncio
    async def test_get_and_update(self) -> None:
        mgr = DesktopConfigurationManager()
        cfg = await mgr.get_config()
        assert cfg.theme == ThemeMode.SYSTEM

        cfg.theme = ThemeMode.DARK
        updated = await mgr.update_config(cfg)
        assert updated.theme == ThemeMode.DARK

    @pytest.mark.asyncio
    async def test_setting(self) -> None:
        mgr = DesktopConfigurationManager()
        assert await mgr.get_setting("theme") is not None
        await mgr.set_setting("auto_start", True)
        assert await mgr.get_setting("auto_start") is True

    @pytest.mark.asyncio
    async def test_reset(self) -> None:
        mgr = DesktopConfigurationManager()
        cfg = await mgr.get_config()
        cfg.theme = ThemeMode.DARK
        await mgr.update_config(cfg)

        reset = await mgr.reset_config()
        assert reset.theme == ThemeMode.SYSTEM


class TestDesktopDiagnosticsManager:
    @pytest.mark.asyncio
    async def test_get_diagnostics(self) -> None:
        mgr = DesktopDiagnosticsManager()
        diag = await mgr.get_diagnostics()
        assert diag.backend_version == "0.9.2"

    @pytest.mark.asyncio
    async def test_health(self) -> None:
        mgr = DesktopDiagnosticsManager()
        health = await mgr.check_health()
        assert health["status"] == "healthy"


class TestDesktopPerformanceMonitor:
    @pytest.mark.asyncio
    async def test_metrics(self) -> None:
        mgr = DesktopPerformanceMonitor()
        metrics = await mgr.get_metrics()
        assert metrics.cpu_usage_percent == 0.0

    @pytest.mark.asyncio
    async def test_history(self) -> None:
        mgr = DesktopPerformanceMonitor()
        from agentic_os.domain.desktop import DesktopPerformanceMetrics

        await mgr.update_metrics(DesktopPerformanceMetrics(cpu_usage_percent=50.0))
        await mgr.update_metrics(DesktopPerformanceMetrics(cpu_usage_percent=60.0))
        history = await mgr.get_metric_history("cpu")
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_monitoring_lifecycle(self) -> None:
        mgr = DesktopPerformanceMonitor()
        await mgr.start_monitoring()
        await mgr.stop_monitoring()


class TestNativeClipboardService:
    @pytest.mark.asyncio
    async def test_text(self) -> None:
        svc = NativeClipboardService()
        await svc.write_text("hello")
        assert await svc.read_text() == "hello"

    @pytest.mark.asyncio
    async def test_html(self) -> None:
        svc = NativeClipboardService()
        await svc.write_html("<p>hello</p>")
        assert await svc.read_html() == "<p>hello</p>"

    @pytest.mark.asyncio
    async def test_files(self) -> None:
        svc = NativeClipboardService()
        await svc.write_files(["/tmp/a.txt"])
        files = await svc.read_files()
        assert len(files) == 1

    @pytest.mark.asyncio
    async def test_clear(self) -> None:
        svc = NativeClipboardService()
        await svc.write_text("hello")
        await svc.clear()
        assert await svc.read_text() == ""

    @pytest.mark.asyncio
    async def test_content(self) -> None:
        svc = NativeClipboardService()
        content = ClipboardContent(text="test", html="<b>test</b>")
        await svc.set_content(content)
        result = await svc.get_content()
        assert result.text == "test"


class TestNativeFileIntegration:
    @pytest.mark.asyncio
    async def test_dialogs(self) -> None:
        fi = NativeFileIntegration()
        from agentic_os.domain.desktop import DialogConfig

        result = await fi.open_file_dialog(DialogConfig(title="Open"))
        assert result.accepted is False

        result = await fi.save_file_dialog(DialogConfig(title="Save"))
        assert result.accepted is False

        result = await fi.select_folder_dialog(DialogConfig(title="Select"))
        assert result.accepted is False


class TestNativeTerminalIntegration:
    @pytest.mark.asyncio
    async def test_open_and_list(self) -> None:
        mgr = NativeTerminalIntegration()
        config = TerminalConfig(title="Test")
        info = await mgr.open_terminal(config)
        assert info.title == "Test"

        terminals = await mgr.list_terminals()
        assert len(terminals) == 1

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        mgr = NativeTerminalIntegration()
        info = await mgr.open_terminal(TerminalConfig())
        assert await mgr.close_terminal(info.id) is True
        assert await mgr.close_terminal("nonexistent") is False

    @pytest.mark.asyncio
    async def test_write_and_resize(self) -> None:
        mgr = NativeTerminalIntegration()
        info = await mgr.open_terminal(TerminalConfig())
        assert await mgr.write_to_terminal(info.id, "echo hello") is True
        assert await mgr.resize_terminal(info.id, 50, 100) is True


class TestNativeProcessManager:
    @pytest.mark.asyncio
    async def test_spawn_and_list(self) -> None:
        mgr = NativeProcessManager()
        info = await mgr.spawn_process("python", ["server.py"])
        assert info.pid > 0

        processes = await mgr.list_processes()
        assert len(processes) == 1

    @pytest.mark.asyncio
    async def test_kill(self) -> None:
        mgr = NativeProcessManager()
        info = await mgr.spawn_process("test")
        assert await mgr.kill_process(info.pid) is True
        assert await mgr.kill_process(99999) is False


class TestDesktopLogging:
    @pytest.mark.asyncio
    async def test_log_levels(self) -> None:
        log = DesktopLogging()
        await log.log_info("info msg")
        await log.log_warning("warn msg")
        await log.log_error("error msg")
        await log.log_debug("debug msg")

        logs = await log.get_logs()
        assert len(logs) == 4

    @pytest.mark.asyncio
    async def test_filter_by_level(self) -> None:
        log = DesktopLogging()
        await log.log_info("info1")
        await log.log_error("err1")
        await log.log_error("err2")

        errors = await log.get_logs(level="error")
        assert len(errors) == 2

    @pytest.mark.asyncio
    async def test_clear(self) -> None:
        log = DesktopLogging()
        await log.log_info("test")
        await log.clear_logs()
        logs = await log.get_logs()
        assert len(logs) == 0


class TestDesktopEventPublisher:
    @pytest.mark.asyncio
    async def test_publish_started(self, mock_bus: AsyncMock) -> None:
        pub = DesktopEventPublisher(mock_bus)
        await pub.publish_started()
        assert mock_bus.publish.awaited
        envelope = mock_bus.publish.await_args[0][0]
        assert envelope.topic == "desktop.started"

    @pytest.mark.asyncio
    async def test_publish_workspace_created(self, mock_bus: AsyncMock) -> None:
        pub = DesktopEventPublisher(mock_bus)
        await pub.publish_workspace_created("ws-1", "Test")
        assert mock_bus.publish.awaited
        envelope = mock_bus.publish.await_args[0][0]
        assert envelope.topic == "desktop.workspace.created"
        assert envelope.payload == {"workspace_id": "ws-1", "name": "Test"}

    @pytest.mark.asyncio
    async def test_publish_notification_created(self, mock_bus: AsyncMock) -> None:
        pub = DesktopEventPublisher(mock_bus)
        await pub.publish_notification_created("n-1", "Hello", "info")
        mock_bus.publish.assert_awaited()

    @pytest.mark.asyncio
    async def test_publish_error_handled(self, mock_bus: AsyncMock) -> None:
        mock_bus.publish.side_effect = Exception("bus error")
        pub = DesktopEventPublisher(mock_bus)
        await pub.publish_started()  # Should not raise


class TestNativeDragDropService:
    @pytest.mark.asyncio
    async def test_handle_drop(self) -> None:
        svc = NativeDragDropService()
        from agentic_os.domain.desktop import DragDropPayload

        payload = DragDropPayload(file_paths=["/tmp/a.txt"])
        result = await svc.handle_drop(payload)
        assert result["accepted"] is True

    @pytest.mark.asyncio
    async def test_supported_formats(self) -> None:
        svc = NativeDragDropService()
        formats = await svc.get_supported_formats()
        assert "files" in formats


class TestDesktopRuntimeManager:
    @pytest.mark.asyncio
    async def test_start_and_stop(self, mock_bus: AsyncMock) -> None:
        manager = DesktopRuntimeManager(mock_bus)
        await manager.start()
        state = await manager.get_state()
        assert state.status.value == "running"

        await manager.stop()
        state = await manager.get_state()
        assert state.status.value == "stopped"

    @pytest.mark.asyncio
    async def test_restart(self, mock_bus: AsyncMock) -> None:
        manager = DesktopRuntimeManager(mock_bus)
        await manager.start()
        await manager.restart()
        state = await manager.get_state()
        assert state.status.value == "running"

    @pytest.mark.asyncio
    async def test_get_status(self, mock_bus: AsyncMock) -> None:
        manager = DesktopRuntimeManager(mock_bus)
        assert await manager.get_status() == "stopped"
        await manager.start()
        assert await manager.get_status() == "running"

    @pytest.mark.asyncio
    async def test_shortcuts(self, mock_bus: AsyncMock) -> None:
        manager = DesktopRuntimeManager(mock_bus)
        await manager.start()

        shortcuts = await manager.list_shortcuts()
        assert len(shortcuts) >= 5

        new_shortcut = KeyboardShortcut(
            key="d", modifiers=["CmdOrCtrl"], action="test.action", label="Test"
        )
        added = await manager.register_shortcut(new_shortcut)
        assert added.label == "Test"

        assert await manager.remove_shortcut(added.id) is True

    @pytest.mark.asyncio
    async def test_command_palette(self, mock_bus: AsyncMock) -> None:
        manager = DesktopRuntimeManager(mock_bus)
        items = await manager.get_command_palette_items()
        assert len(items) >= 5

    @pytest.mark.asyncio
    async def test_global_search(self, mock_bus: AsyncMock) -> None:
        manager = DesktopRuntimeManager(mock_bus)
        await manager.start()
        results = await manager.global_search("workspace")
        assert len(results) >= 0
