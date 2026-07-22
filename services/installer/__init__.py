"""Installer Intelligence — automatic agent discovery, validation & binding."""

from services.installer.engine import InstallerIntelligence
from services.installer.validator import ValidationPipeline
from services.installer.watcher import RuntimeWatcher
from services.installer.healer import SelfHealingEngine
from services.installer.report import InstallReport, InstallReportGenerator

__all__ = [
    "InstallerIntelligence",
    "ValidationPipeline",
    "RuntimeWatcher",
    "SelfHealingEngine",
    "InstallReport",
    "InstallReportGenerator",
]
