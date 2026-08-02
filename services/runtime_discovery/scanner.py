"""Filesystem scanner — reusable directory/executable scanning utility.

Scans the local filesystem for executables, binaries, and configuration files
across standard system paths, user paths, and custom directories. Provides
version detection and capability inference from discovered binaries.

This is a foundational utility consumed by discovery providers, CLI discovery,
MCP discovery, and plugin discovery — not a standalone provider itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.logging import get_logger

_log = get_logger(__name__)

__all__ = [
    "Scanner",
    "ScannedBinary",
    "ScanResult",
]

_WIN_STANDARD_DIRS = [
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData\\chocolatey\\bin",
    "C:\\tools",
]

_NIX_STANDARD_DIRS = [
    "/usr/local/bin",
    "/usr/bin",
    "/opt",
]

_USER_RELATIVE_DIRS = [
    ".local/bin",
    "bin",
    "AppData/Local",
    "AppData/Roaming",
]

_WIN_EXECUTABLE_EXTS = {".exe", ".cmd", ".bat", ".ps1", ".com"}


class ScannedBinary:
    """Result of scanning a single binary/executable on the filesystem."""

    def __init__(
        self,
        binary_path: str,
        *,
        name: str | None = None,
        version: str | None = None,
        source: str = "path",
        is_executable: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.binary_path = binary_path
        self.name = name or Path(binary_path).stem
        self.version = version
        self.source = source
        self.is_executable = is_executable
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "binary_path": self.binary_path,
            "name": self.name,
            "version": self.version,
            "source": self.source,
            "is_executable": self.is_executable,
            "metadata": dict(self.metadata),
        }


class ScanResult:
    """Aggregated result of a scan operation."""

    def __init__(
        self,
        *,
        binaries: list[ScannedBinary] | None = None,
        directories_scanned: int = 0,
        errors: list[str] | None = None,
    ) -> None:
        self.binaries = binaries or []
        self.directories_scanned = directories_scanned
        self.errors = errors or []

    def __len__(self) -> int:
        return len(self.binaries)

    def merge(self, other: ScanResult) -> ScanResult:
        self.binaries.extend(other.binaries)
        self.directories_scanned += other.directories_scanned
        self.errors.extend(other.errors)
        return self


class Scanner:
    """Reusable filesystem scanner for executables and binaries.

    Scans PATH, standard install directories, and custom paths.
    Detects versions via ``--version`` and identifies executables.
    """

    @staticmethod
    def get_standard_paths() -> list[str]:
        """Return list of standard system directories to scan."""
        if os.name == "nt":
            dirs = list(_WIN_STANDARD_DIRS)
            for env_var in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData", "AppData"):
                val = os.environ.get(env_var)
                if val:
                    dirs.append(val)
        else:
            dirs = list(_NIX_STANDARD_DIRS)

        home = Path.home()
        for rel in _USER_RELATIVE_DIRS:
            candidate = home / rel
            if candidate.is_dir():
                dirs.append(str(candidate.resolve()))

        return dirs

    @staticmethod
    def scan_path(
        binary_names: list[str],
        *,
        path_env: str | None = None,
    ) -> ScanResult:
        """Scan PATH entries for the given binary names."""
        result = ScanResult()
        path_dirs = (path_env or os.environ.get("PATH", "")).split(os.pathsep)
        seen: set[str] = set()

        for directory in path_dirs:
            if not directory or not Path(directory).is_dir():
                continue
            dir_path = Path(directory)
            for name in binary_names:
                for candidate in Scanner._resolve_candidates(dir_path, name):
                    resolved = str(candidate.resolve())
                    if resolved not in seen and candidate.is_file():
                        seen.add(resolved)
                        version = Scanner.detect_version(resolved)
                        result.binaries.append(
                            ScannedBinary(
                                binary_path=resolved,
                                name=name,
                                version=version,
                                source="path",
                            )
                        )
        return result

    @staticmethod
    def scan_directories(
        binary_names: list[str],
        directories: list[str],
        *,
        recursive: bool = False,
    ) -> ScanResult:
        """Scan specific directories for the given binary names."""
        result = ScanResult()
        seen: set[str] = set()

        for directory in directories:
            dir_path = Path(directory)
            if not dir_path.is_dir():
                continue
            result.directories_scanned += 1
            try:
                entries = dir_path.rglob("*") if recursive else dir_path.iterdir()
                for entry in entries:
                    if entry.is_file() and Scanner._name_matches_any(entry, binary_names):
                        resolved = str(entry.resolve())
                        if resolved not in seen:
                            seen.add(resolved)
                            version = Scanner.detect_version(resolved)
                            result.binaries.append(
                                ScannedBinary(
                                    binary_path=resolved,
                                    name=entry.stem,
                                    version=version,
                                    source="install_dir",
                                )
                            )
            except PermissionError:
                _log.debug("Permission denied scanning %s", directory)
                result.errors.append(f"Permission denied: {directory}")
            except OSError as exc:
                _log.debug("Error scanning %s: %s", directory, exc)
                result.errors.append(f"Error scanning {directory}: {exc}")

        return result

    @staticmethod
    def scan_all(
        binary_names: list[str],
        *,
        extra_dirs: list[str] | None = None,
    ) -> ScanResult:
        """Convenience: scan PATH + standard directories + extras."""
        result = ScanResult()
        path_result = Scanner.scan_path(binary_names)
        result.merge(path_result)

        dirs = Scanner.get_standard_paths()
        if extra_dirs:
            dirs.extend(extra_dirs)
        dir_result = Scanner.scan_directories(binary_names, dirs)
        result.merge(dir_result)

        home_dirs = [str(Path.home() / d) for d in _USER_RELATIVE_DIRS]
        home_result = Scanner.scan_directories(binary_names, home_dirs)
        result.merge(home_result)

        return result

    @staticmethod
    def detect_version(binary_path: str, flag: str = "--version") -> str | None:
        """Run the binary with ``--version`` and return the first output line."""
        try:
            result = subprocess.run(
                [binary_path, flag],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = (result.stdout or result.stderr).strip()
            return output.split("\n")[0] if output else None
        except FileNotFoundError:
            return None
        except subprocess.TimeoutExpired:
            _log.debug("Version check timed out for %s", binary_path)
            return None
        except Exception as exc:
            _log.debug("Version check failed for %s: %s", binary_path, exc)
            return None

    @staticmethod
    def is_executable(path: str) -> bool:
        """Check if the path is an executable."""
        try:
            p = Path(path)
            if not p.is_file():
                return False
            if os.name == "nt":
                return p.suffix.lower() in _WIN_EXECUTABLE_EXTS or os.access(p, os.X_OK)
            return os.access(p, os.X_OK)
        except OSError:
            return False

    @staticmethod
    def which(name: str) -> str | None:
        """Find a binary on PATH, returning its full path or None."""
        resolved = shutil.which(name)
        return resolved if resolved else None

    # ── Internal helpers ──

    @staticmethod
    def _resolve_candidates(dir_path: Path, name: str) -> list[Path]:
        """Resolve possible file paths for a binary name in a directory."""
        candidates: list[Path] = [dir_path / name]
        if os.name == "nt":
            for ext in _WIN_EXECUTABLE_EXTS:
                candidates.append(dir_path / f"{name}{ext}")
        return candidates

    @staticmethod
    def _name_matches_any(entry: Path, names: list[str]) -> bool:
        """Check if a filesystem entry's stem matches any name."""
        stem = entry.stem.lower()
        return any(stem == n.lower() or stem.startswith(f"{n}.") for n in names)
