"""Tests for the Desktop Runtime Foundation domain models."""

from agentic_os.domain.desktop import (
    ClipboardContent,
    DesktopConfig,
    DesktopDiagnosticsInfo,
    DesktopEvent,
    DesktopEventType,
    DesktopNotification,
    DesktopPerformanceMetrics,
    DesktopRuntimeState,
    DesktopRuntimeStatus,
    DialogConfig,
    DialogResult,
    DragDropPayload,
    KeyboardShortcut,
    MenuConfig,
    MenuItem,
    MenuItemType,
    MenuType,
    NotificationLevel,
    PanelConfig,
    PanelPosition,
    PanelState,
    ProcessInfo,
    TabInfo,
    TerminalConfig,
    TerminalInfo,
    ThemeMode,
    WindowConfig,
    WindowInfo,
    WindowState,
    Workspace,
    WorkspaceLayout,
    WorkspaceStatus,
)


class TestWindowConfig:
    def test_defaults(self) -> None:
        cfg = WindowConfig()
        assert cfg.width == 1280
        assert cfg.height == 800
        assert cfg.state == WindowState.NORMAL
        assert cfg.center is True

    def test_to_dict(self) -> None:
        win = WindowInfo(label="main", title="Test", width=1024, height=768)
        d = win.to_dict()
        assert d["label"] == "main"
        assert d["width"] == 1024


class TestWorkspace:
    def test_defaults(self) -> None:
        ws = Workspace()
        assert ws.name == "Default"
        assert ws.status == WorkspaceStatus.ACTIVE
        assert len(ws.tabs) == 0

    def test_to_dict(self) -> None:
        ws = Workspace(name="Dev", status=WorkspaceStatus.ACTIVE)
        d = ws.to_dict()
        assert d["name"] == "Dev"


class TestPanelConfig:
    def test_defaults(self) -> None:
        panel = PanelConfig()
        assert panel.position == PanelPosition.LEFT
        assert panel.state == PanelState.OPEN
        assert panel.width == 300


class TestMenuConfig:
    def test_to_dict(self) -> None:
        item = MenuItem(label="Save", action="file.save", shortcut="CmdOrCtrl+S")
        menu = MenuConfig(menu_type=MenuType.FILE, label="File", items=[item])
        d = menu.to_dict()
        assert d["label"] == "File"
        assert len(d["items"]) == 1
        assert d["items"][0]["shortcut"] == "CmdOrCtrl+S"

    def test_separator(self) -> None:
        item = MenuItem(item_type=MenuItemType.SEPARATOR)
        d = item.to_dict()
        assert d["item_type"] == "separator"


class TestDesktopNotification:
    def test_defaults(self) -> None:
        n = DesktopNotification(title="Hello", message="World")
        assert n.level == NotificationLevel.INFO
        assert n.persistent is False

    def test_to_dict(self) -> None:
        n = DesktopNotification(
            title="Warning", message="Low disk", level=NotificationLevel.WARNING
        )
        d = n.to_dict()
        assert d["level"] == "warning"


class TestDialogConfig:
    def test_defaults(self) -> None:
        d = DialogConfig(title="Open File", dialog_type="open_file")
        assert d.confirm_label == "OK"

    def test_result(self) -> None:
        r = DialogResult(accepted=True, selected_paths=["/tmp/test.txt"])
        d = r.to_dict()
        assert d["accepted"] is True


class TestPerformanceMetrics:
    def test_to_dict(self) -> None:
        m = DesktopPerformanceMetrics(cpu_usage_percent=45.5, memory_usage_percent=60.0)
        d = m.to_dict()
        assert d["cpu_usage_percent"] == 45.5
        assert d["memory_usage_percent"] == 60.0


class TestDiagnostics:
    def test_to_dict(self) -> None:
        diag = DesktopDiagnosticsInfo(os_name="Windows", os_version="11", os_arch="x86_64")
        d = diag.to_dict()
        assert d["os_name"] == "Windows"

    def test_defaults(self) -> None:
        diag = DesktopDiagnosticsInfo()
        assert diag.display_count == 1


class TestDesktopConfig:
    def test_defaults(self) -> None:
        cfg = DesktopConfig()
        assert cfg.theme == ThemeMode.SYSTEM
        assert cfg.auto_save_interval_seconds == 30

    def test_to_dict(self) -> None:
        cfg = DesktopConfig(theme=ThemeMode.DARK, language="fr-FR")
        d = cfg.to_dict()
        assert d["theme"] == "dark"
        assert d["language"] == "fr-FR"


class TestKeyboardShortcut:
    def test_to_dict(self) -> None:
        s = KeyboardShortcut(
            key="p",
            modifiers=["CmdOrCtrl", "Shift"],
            action="view.command_palette",
            label="Command Palette",
        )
        d = s.to_dict()
        assert d["key"] == "p"
        assert "Shift" in d["modifiers"]


class TestClipboard:
    def test_to_dict(self) -> None:
        c = ClipboardContent(text="hello")
        d = c.to_dict()
        assert d["text"] == "hello"

    def test_empty(self) -> None:
        c = ClipboardContent()
        assert c.text is None


class TestDragDrop:
    def test_to_dict(self) -> None:
        p = DragDropPayload(file_paths=["/tmp/a.txt", "/tmp/b.txt"])
        d = p.to_dict()
        assert len(d["file_paths"]) == 2


class TestTerminal:
    def test_config_to_dict(self) -> None:
        c = TerminalConfig(title="My Terminal", rows=40, cols=120)
        d = c.to_dict()
        assert d["rows"] == 40

    def test_info_to_dict(self) -> None:
        info = TerminalInfo(id="t1", title="Test", pid=12345, running=True)
        d = info.to_dict()
        assert d["pid"] == 12345


class TestProcessInfo:
    def test_to_dict(self) -> None:
        p = ProcessInfo(pid=1001, name="python", command="python server.py", cpu_percent=10.5)
        d = p.to_dict()
        assert d["cpu_percent"] == 10.5


class TestTabInfo:
    def test_to_dict(self) -> None:
        tab = TabInfo(title="Dashboard", url="/dashboard", active=True)
        d = tab.to_dict()
        assert d["active"] is True


class TestWorkspaceLayout:
    def test_to_dict(self) -> None:
        panel = PanelConfig(title="Terminal", position=PanelPosition.BOTTOM)
        layout = WorkspaceLayout(name="Dev Layout", panels=[panel])
        d = layout.to_dict()
        assert d["name"] == "Dev Layout"
        assert len(d["panels"]) == 1


class TestDesktopRuntimeState:
    def test_to_dict(self) -> None:
        state = DesktopRuntimeState(status=DesktopRuntimeStatus.RUNNING)
        d = state.to_dict()
        assert d["status"] == "running"

    def test_default_status(self) -> None:
        state = DesktopRuntimeState()
        assert state.status == DesktopRuntimeStatus.STOPPED


class TestDesktopEvent:
    def test_to_dict(self) -> None:
        evt = DesktopEvent(event_type=DesktopEventType.STARTED, payload={"version": "1.0"})
        d = evt.to_dict()
        assert d["event_type"] == "desktop.started"
