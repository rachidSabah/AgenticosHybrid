"""Desktop Runtime — core implementation."""

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
from agentic_os.core.desktop.manager import DesktopRuntimeManager
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

__all__ = [
    "DesktopRuntimeManager",
    "NativeWindowManager",
    "WorkspaceManager",
    "NativeNotificationService",
    "NativeFileIntegration",
    "NativeClipboardService",
    "NativeTerminalIntegration",
    "NativeProcessManager",
    "DesktopLogging",
    "DesktopConfigurationManager",
    "DesktopDiagnosticsManager",
    "DesktopPerformanceMonitor",
    "NativeMenuManager",
    "NativeDragDropService",
    "LocalDatabaseManager",
    "DesktopEventPublisher",
    "RuntimeDiscoveryManager",
    "AutoUpdateManager",
    "DesktopInstallerManager",
    "FirstRunWizard",
    "ChannelManager",
    "RollbackManager",
    "PortableRuntimeManager",
    "OfflineRuntimeManager",
    "BackupManager",
    "DeltaUpdateEngine",
    "SignatureVerification",
    "WindowsPlatformIntegration",
    "DesktopHardeningManager",
]
