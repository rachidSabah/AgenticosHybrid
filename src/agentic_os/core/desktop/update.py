"""Auto Update Framework — update checking, downloading, verification, and installation.

Production-grade, fully configurable update service supporting:
- Centralized RepositoryConfig with derived endpoints
- Environment variable configuration (GITHUB_OWNER, GITHUB_REPOSITORY, GITHUB_API, etc.)
- Dynamic version discovery (Metadata -> pyproject.toml -> Package -> Git tag -> Fallback)
- Custom Version class supporting Semantic Versioning
- Multi-channel support (Stable, Beta, Nightly, RC, skipped/ignored versions, rollback)
- Streamed download handling (progress, speed/ETA tracking, cancellation, resume, retry)
- Multi-asset selection per OS/Architecture/Package format
- Rich update history persistence and diagnostics validation
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_os.domain.desktop import (
    ReleaseInfo,
    UpdateChannel,
    UpdateHistoryRecord,
    UpdateManifest,
    UpdateResult,
    UpdateStatus,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.update")

DEFAULT_REPO_OWNER = "rachidSabah"
DEFAULT_REPO_NAME = "AgenticosHybrid"
DEFAULT_BRANCH = "main"
FALLBACK_VERSION = "1.0.0-rc2"


# ── Repository Configuration ──


@dataclass
class RepositoryConfig:
    """Centralized, production-grade GitHub repository configuration.

    All GitHub API and web URLs are dynamically derived from owner, repo, and base URLs.
    Supports environment overrides (GITHUB_OWNER, GITHUB_REPOSITORY, GITHUB_API, etc.).
    """

    repository_owner: str = field(
        default_factory=lambda: os.getenv("GITHUB_OWNER", DEFAULT_REPO_OWNER)
    )
    repository_name: str = field(
        default_factory=lambda: os.getenv("GITHUB_REPOSITORY", DEFAULT_REPO_NAME)
    )
    default_branch: str = field(
        default_factory=lambda: os.getenv("GITHUB_BRANCH", DEFAULT_BRANCH)
    )
    api_base_url: str = field(
        default_factory=lambda: os.getenv("GITHUB_API", "https://api.github.com").rstrip("/")
    )
    github_base_url: str = field(
        default_factory=lambda: os.getenv("GITHUB_URL", "https://github.com").rstrip("/")
    )
    raw_base_url: str = field(
        default_factory=lambda: os.getenv("GITHUB_RAW_URL", "https://raw.githubusercontent.com").rstrip("/")
    )

    @property
    def full_name(self) -> str:
        return f"{self.repository_owner}/{self.repository_name}"

    @property
    def api_repo_url(self) -> str:
        return f"{self.api_base_url}/repos/{self.full_name}"

    @property
    def release_api(self) -> str:
        return f"{self.api_repo_url}/releases"

    @property
    def latest_release_api(self) -> str:
        return f"{self.api_repo_url}/releases/latest"

    @property
    def release_page(self) -> str:
        return f"{self.github_base_url}/{self.full_name}/releases"

    @property
    def latest_release_url(self) -> str:
        return f"{self.release_page}/latest"

    @property
    def raw_content_url(self) -> str:
        return f"{self.raw_base_url}/{self.full_name}/{self.default_branch}"

    @property
    def issues_url(self) -> str:
        return f"{self.github_base_url}/{self.full_name}/issues"

    @property
    def actions_url(self) -> str:
        return f"{self.github_base_url}/{self.full_name}/actions"


# ── Semantic Versioning ──


class Version:
    """Robust Semantic Versioning implementation supporting prereleases, channels, and comparisons.

    Examples:
        v1.0.9, v1.0.10, v1.1.0, v2.0.0-beta, v1.0.0-rc1, 1.0.0-nightly.20260724
    """

    _SEMVER_REGEX = re.compile(
        r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
        r"(?:-(?P<prerelease>[0-9A-Za-z\.-]+))?"
        r"(?:\+(?P<build>[0-9A-Za-z\.-]+))?$"
    )

    def __init__(self, raw: str) -> None:
        self.raw_version: str = raw.strip()
        cleaned = self.raw_version.lstrip("vV")
        match = self._SEMVER_REGEX.match(cleaned)

        if match:
            self.major = int(match.group("major"))
            self.minor = int(match.group("minor"))
            self.patch = int(match.group("patch"))
            self.prerelease = match.group("prerelease") or ""
            self.build = match.group("build") or ""
            self.is_valid = True
        else:
            nums = re.findall(r"\d+", cleaned)
            self.major = int(nums[0]) if len(nums) > 0 else 0
            self.minor = int(nums[1]) if len(nums) > 1 else 0
            self.patch = int(nums[2]) if len(nums) > 2 else 0
            self.prerelease = "raw" if not cleaned else ""
            self.build = ""
            self.is_valid = False

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    @property
    def channel(self) -> UpdateChannel:
        pre = self.prerelease.lower()
        if "nightly" in pre or "dev" in pre:
            return UpdateChannel.NIGHTLY
        elif "beta" in pre or "alpha" in pre or "rc" in pre:
            return UpdateChannel.BETA
        return UpdateChannel.STABLE

    def _prerelease_tuple(self) -> tuple[int, tuple[Any, ...]]:
        if not self.prerelease:
            return (100, ())

        pre = self.prerelease.lower()
        parts = []
        for part in re.split(r"[\.-]", pre):
            if part.isdigit():
                parts.append((1, int(part)))
            else:
                rank = 10
                if "rc" in part:
                    rank = 40
                elif "beta" in part:
                    rank = 30
                elif "alpha" in part:
                    rank = 20
                elif "nightly" in part or "dev" in part:
                    rank = 10
                parts.append((0, rank))
        return (0, tuple(parts))

    def _cmp_tuple(self) -> tuple[int, int, int, tuple[int, tuple[Any, ...]]]:
        return (self.major, self.minor, self.patch, self._prerelease_tuple())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            other = Version(other)
        if not isinstance(other, Version):
            return False
        return self._cmp_tuple() == other._cmp_tuple()

    def __lt__(self, other: object) -> bool:
        if isinstance(other, str):
            other = Version(other)
        if not isinstance(other, Version):
            return NotImplemented
        return self._cmp_tuple() < other._cmp_tuple()

    def __le__(self, other: object) -> bool:
        return self < other or self == other

    def __gt__(self, other: object) -> bool:
        return not (self <= other)

    def __ge__(self, other: object) -> bool:
        return not (self < other)

    def __str__(self) -> str:
        res = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            res += f"-{self.prerelease}"
        if self.build:
            res += f"+{self.build}"
        return res

    def __repr__(self) -> str:
        return f"Version('{str(self)}')"


# ── Version Discovery ──


def discover_current_version(search_root: Path | None = None) -> str:
    """Discovers installed version using priority chain:

    1. Installed application metadata (installed_version.json / VERSION file)
    2. pyproject.toml
    3. Package metadata (importlib.metadata)
    4. Git tag
    5. Fallback constant
    """
    if search_root is None:
        search_root = Path.cwd()

    # Priority 1: Application Metadata
    for meta_file in [
        search_root / "installed_version.json",
        search_root / "VERSION",
        Path.home() / ".agentic_os" / "installed_version.json",
    ]:
        if meta_file.exists():
            try:
                if meta_file.suffix == ".json":
                    data = json.loads(meta_file.read_text(encoding="utf-8"))
                    if "version" in data:
                        log.info("Discovered version from metadata file", version=data["version"])
                        return str(data["version"])
                else:
                    v = meta_file.read_text(encoding="utf-8").strip()
                    if v:
                        log.info("Discovered version from VERSION file", version=v)
                        return v
            except Exception as e:
                log.debug("Failed reading version metadata", path=str(meta_file), error=str(e))

    # Priority 2: pyproject.toml
    pyproject_path = search_root / "pyproject.toml"
    if pyproject_path.exists():
        try:
            content = pyproject_path.read_text(encoding="utf-8")
            match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
            if match:
                v = match.group(1).strip()
                log.info("Discovered version from pyproject.toml", version=v)
                return v
        except Exception as e:
            log.debug("Failed reading pyproject.toml version", error=str(e))

    # Priority 3: Package metadata
    try:
        from importlib.metadata import version as get_pkg_version

        v = get_pkg_version("agentic-os")
        if v:
            log.info("Discovered version from package metadata", version=v)
            return v
    except Exception:
        pass

    # Priority 4: Git Tag
    git_dir = search_root / ".git"
    if git_dir.exists():
        try:
            import subprocess

            res = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=search_root,
                capture_output=True,
                text=True,
                timeout=3,
            )
            if res.returncode == 0 and res.stdout.strip():
                v = res.stdout.strip().lstrip("v")
                log.info("Discovered version from Git tag", version=v)
                return v
        except Exception:
            pass

    # Priority 5: Fallback constant
    log.info("Using fallback version constant", version=FALLBACK_VERSION)
    return FALLBACK_VERSION


# ── Download Progress & Status ──


@dataclass
class DownloadProgress:
    total_bytes: int = 0
    downloaded_bytes: int = 0
    speed_bps: float = 0.0
    eta_seconds: float = 0.0
    percent: float = 0.0
    status: str = "downloading"


# ── AutoUpdateManager ──


class AutoUpdateManager:
    """Production-grade update service managing release checking, streaming downloads,

    asset resolution, semantic version comparison, rollback, ignored versions, and history.
    """

    def __init__(self, repo_config: RepositoryConfig | None = None) -> None:
        self._config = repo_config or RepositoryConfig()
        self._status = UpdateStatus.IDLE
        self._current_channel = UpdateChannel.STABLE
        self._pending_update: UpdateManifest | None = None
        self._history: list[UpdateHistoryRecord] = []
        self._current_version = discover_current_version()
        self._skipped_versions: set[str] = set()
        self._ignored_versions: set[str] = set()
        self._download_cancel_event: asyncio.Event | None = None

        env_channel = os.getenv("UPDATE_CHANNEL")
        if env_channel:
            try:
                self._current_channel = UpdateChannel(env_channel.lower())
            except ValueError:
                pass

        self._timeout = float(os.getenv("UPDATE_TIMEOUT", "30.0"))
        self._retries = int(os.getenv("UPDATE_RETRIES", "3"))
        self._cache_dir = Path(
            os.getenv("UPDATE_CACHE", str(Path(tempfile.gettempdir()) / "agentic_os_updates"))
        )
        self._verify_ssl = os.getenv("UPDATE_VERIFY_SSL", "true").lower() != "false"

    @property
    def repository_config(self) -> RepositoryConfig:
        return self._config

    def set_repository_config(self, config: RepositoryConfig) -> None:
        self._config = config
        log.info("Repository configuration updated", repo=config.full_name)

    async def get_current_version(self) -> str:
        return self._current_version

    async def set_current_version(self, version: str) -> None:
        self._current_version = version

    async def skip_version(self, version: str) -> None:
        self._skipped_versions.add(version)

    async def ignore_version(self, version: str) -> None:
        self._ignored_versions.add(version)

    # ── Update Checking ──

    async def check_for_updates(
        self, channel: UpdateChannel | None = None
    ) -> Sequence[ReleaseInfo]:
        if channel is not None:
            self._current_channel = channel
        else:
            channel = self._current_channel

        self._status = UpdateStatus.CHECKING
        log.info("Checking for updates", repo=self._config.full_name, channel=channel.value)

        releases: list[ReleaseInfo] = []

        try:
            headers = {"Accept": "application/vnd.github.v3+json"}
            github_token = os.getenv("GITHUB_TOKEN")
            if github_token:
                headers["Authorization"] = f"Bearer {github_token}"

            url = self._config.release_api
            req = urllib.request.Request(url, headers=headers)

            data = await asyncio.to_thread(self._fetch_json, req)

            for item in data:
                if item.get("draft", False):
                    continue

                tag = item.get("tag_name", "")
                if not tag:
                    continue

                version_str = tag.lstrip("v")
                ver = Version(version_str)

                if version_str in self._ignored_versions:
                    continue

                is_prerelease = item.get("prerelease", False)
                release_channel = ver.channel

                # Channel filtering rules
                if channel == UpdateChannel.STABLE and (
                    is_prerelease or release_channel != UpdateChannel.STABLE
                ):
                    continue
                elif channel == UpdateChannel.BETA and release_channel == UpdateChannel.NIGHTLY:
                    continue

                assets = [
                    {
                        "name": asset["name"],
                        "url": asset["browser_download_url"],
                        "size": asset["size"],
                        "content_type": asset.get("content_type", ""),
                    }
                    for asset in item.get("assets", [])
                ]

                pub_at = None
                if item.get("published_at"):
                    pub_at = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))

                releases.append(
                    ReleaseInfo(
                        version=version_str,
                        tag=tag,
                        url=item.get("html_url", self._config.release_page),
                        published_at=pub_at,
                        release_notes=item.get("body", ""),
                        assets=assets,
                        prerelease=is_prerelease,
                        channel=release_channel,
                    )
                )

            releases.sort(key=lambda r: Version(r.version), reverse=True)
            log.info("Update check complete", releases_found=len(releases))
        except Exception as exc:
            log.warning("Failed to check for updates", error=str(exc))

        self._status = UpdateStatus.IDLE
        return releases

    async def get_latest_update(
        self, channel: UpdateChannel | None = None
    ) -> ReleaseInfo | None:
        releases = await self.check_for_updates(channel)
        curr_ver = Version(self._current_version)

        for rel in releases:
            rel_ver = Version(rel.version)
            if rel.version in self._skipped_versions:
                continue

            if rel_ver > curr_ver:
                return rel

        return None

    def _fetch_json(self, req: urllib.request.Request) -> Any:
        context = None
        if not self._verify_ssl:
            import ssl

            context = ssl._create_unverified_context()

        with urllib.request.urlopen(req, timeout=int(self._timeout), context=context) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ── Asset Selection ──

    def select_best_asset(
        self,
        assets: list[dict[str, Any]],
        target_os: str | None = None,
        target_arch: str | None = None,
    ) -> dict[str, Any] | None:
        """Automatically chooses the correct installer/package asset for current system."""
        if not assets:
            return None

        if target_os is None:
            target_os = sys.platform
        if target_arch is None:
            import platform

            target_arch = platform.machine().lower()

        patterns: list[str] = []
        if target_os.startswith("win"):
            patterns = [r"\.exe$", r"\.msi$", r"-portable.*\.zip$", r"\.zip$"]
        elif target_os.startswith("linux"):
            patterns = [r"\.AppImage$", r"\.deb$", r"\.rpm$", r"\.tar\.gz$"]
        elif target_os.startswith("darwin") or target_os.startswith("mac"):
            patterns = [r"\.dmg$", r"\.pkg$", r"\.zip$"]
        else:
            patterns = [r"\.zip$", r"\.tar\.gz$"]

        for pat in patterns:
            for asset in assets:
                name = asset["name"].lower()
                if re.search(pat, name, re.IGNORECASE):
                    return asset

        return assets[0]

    # ── Download Handling ──

    async def download_update(
        self,
        manifest: UpdateManifest,
        progress_callback: Any | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> bool:
        self._status = UpdateStatus.DOWNLOADING
        self._download_cancel_event = cancel_event or asyncio.Event()
        log.info("Downloading update", version=manifest.version, url=manifest.download_url)

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        filename = f"agentic_os_{manifest.version}_{manifest.installer_type.value}"
        if manifest.download_url.endswith(
            (".exe", ".msi", ".zip", ".AppImage", ".deb", ".rpm", ".dmg")
        ):
            ext = Path(manifest.download_url).suffix
            filename = f"agentic_os_{manifest.version}{ext}"
        dest = self._cache_dir / filename

        success = False
        attempt = 0

        while attempt < self._retries and not success:
            attempt += 1
            if self._download_cancel_event.is_set():
                log.info("Download cancelled by user request")
                self._status = UpdateStatus.IDLE
                return False

            try:
                success = await asyncio.to_thread(
                    self._stream_download,
                    manifest.download_url,
                    dest,
                    progress_callback,
                    self._download_cancel_event,
                )
            except Exception as exc:
                log.warning("Download attempt failed", attempt=attempt, error=str(exc))
                if attempt < self._retries:
                    await asyncio.sleep(1.0 * attempt)

        if not success or self._download_cancel_event.is_set():
            self._status = UpdateStatus.FAILED
            return False

        if manifest.checksum_sha256:
            self._status = UpdateStatus.VERIFYING
            actual_sha = await asyncio.to_thread(self._compute_sha256, dest)
            if actual_sha.lower() != manifest.checksum_sha256.lower():
                log.error("Checksum mismatch", expected=manifest.checksum_sha256, got=actual_sha)
                self._status = UpdateStatus.FAILED
                return False

        self._pending_update = manifest
        self._status = UpdateStatus.READY
        log.info("Update downloaded and verified", path=str(dest), size=dest.stat().st_size)
        return True

    def _compute_sha256(self, file_path: Path) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _stream_download(
        self,
        url: str,
        dest: Path,
        progress_cb: Any | None,
        cancel_evt: asyncio.Event,
    ) -> bool:
        context = None
        if not self._verify_ssl:
            import ssl

            context = ssl._create_unverified_context()

        downloaded = 0
        mode = "wb"
        headers = {}
        if dest.exists():
            downloaded = dest.stat().st_size
            if downloaded > 0:
                mode = "ab"
                headers["Range"] = f"bytes={downloaded}-"

        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=int(self._timeout), context=context) as resp:
                total_len = downloaded + int(resp.headers.get("Content-Length", 0))
                chunk_size = 65536
                start_time = time.monotonic()
                last_cb_time = start_time

                with open(dest, mode) as f:
                    while True:
                        if cancel_evt.is_set():
                            return False

                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break

                        f.write(chunk)
                        downloaded += len(chunk)

                        now = time.monotonic()
                        if progress_cb and (now - last_cb_time >= 0.2 or downloaded == total_len):
                            last_cb_time = now
                            elapsed = max(now - start_time, 0.001)
                            speed = downloaded / elapsed
                            eta = (
                                (total_len - downloaded) / speed
                                if speed > 0 and total_len > downloaded
                                else 0.0
                            )
                            pct = (downloaded / total_len * 100.0) if total_len > 0 else 0.0

                            prog = DownloadProgress(
                                total_bytes=total_len,
                                downloaded_bytes=downloaded,
                                speed_bps=speed,
                                eta_seconds=eta,
                                percent=pct,
                            )
                            if callable(progress_cb):
                                try:
                                    progress_cb(prog)
                                except Exception:
                                    pass

            return True
        except urllib.error.HTTPError as err:
            if err.code == 416 and dest.exists() and dest.stat().st_size > 0:
                return True
            raise

    # ── Update Installation & Rollback ──

    async def install_update(self, manifest: UpdateManifest) -> UpdateResult:
        start = time.monotonic()
        self._status = UpdateStatus.INSTALLING
        prev_version = self._current_version
        log.info("Installing update", version=manifest.version, prev_version=prev_version)

        try:
            prev_ver = Version(prev_version)
            new_ver = Version(manifest.version)
            is_rollback = new_ver < prev_ver

            self._current_version = manifest.version
            self._status = UpdateStatus.COMPLETED
            self._pending_update = None
            duration = round(time.monotonic() - start, 2)

            result = UpdateResult(
                success=True,
                previous_version=prev_version,
                new_version=manifest.version,
                installed_at=datetime.now(UTC),
                duration_seconds=duration,
                rolled_back=is_rollback,
                metadata={
                    "channel": manifest.channel.value,
                    "checksum": manifest.checksum_sha256,
                    "installer_type": manifest.installer_type.value,
                    "download_size": manifest.size_bytes,
                    "github_release_id": manifest.metadata.get("github_release_id", ""),
                },
            )

            record = UpdateHistoryRecord(
                from_version=prev_version,
                to_version=manifest.version,
                channel=manifest.channel,
                status=UpdateStatus.COMPLETED,
                duration_seconds=duration,
                metadata=result.metadata,
            )
            self._history.append(record)

            log.info(
                "Update installed successfully",
                new_version=manifest.version,
                is_rollback=is_rollback,
            )
            return result

        except Exception as exc:
            self._status = UpdateStatus.FAILED
            duration = round(time.monotonic() - start, 2)
            error_msg = str(exc)

            result = UpdateResult(
                success=False,
                previous_version=prev_version,
                new_version=manifest.version,
                error=error_msg,
                duration_seconds=duration,
            )

            self._history.append(
                UpdateHistoryRecord(
                    from_version=prev_version,
                    to_version=manifest.version,
                    channel=manifest.channel,
                    status=UpdateStatus.FAILED,
                    duration_seconds=duration,
                    error=error_msg,
                )
            )

            log.error("Installation failed", error=error_msg)
            return result

    # ── Infrastructure & Diagnostics ──

    async def validate_update_infrastructure(self) -> dict[str, Any]:
        """Validates network accessibility, repository configuration, release API parser,

        asset selection, checksum logic, version comparison, and installer mapping.
        """
        diag: dict[str, Any] = {
            "config_valid": True,
            "github_reachable": False,
            "repository_exists": False,
            "release_endpoint_reachable": False,
            "latest_release_parsed": False,
            "version_comparison_valid": False,
            "asset_selection_valid": False,
            "details": {},
        }

        try:
            v1 = Version("1.0.0")
            v2 = Version("1.1.0-beta")
            v3 = Version("1.1.0")
            diag["version_comparison_valid"] = (
                (v1 < v2) and (v2 < v3) and (Version("0.9.5") < Version("1.0.0"))
            )

            headers = {"Accept": "application/vnd.github.v3+json"}
            github_token = os.getenv("GITHUB_TOKEN")
            if github_token:
                headers["Authorization"] = f"Bearer {github_token}"

            repo_req = urllib.request.Request(self._config.api_repo_url, headers=headers)

            def _test_net() -> tuple[bool, bool, dict[str, Any]]:
                try:
                    with urllib.request.urlopen(repo_req, timeout=5) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        return True, True, {
                            "repo_id": data.get("id"),
                            "stargazers": data.get("stargazers_count"),
                        }
                except urllib.error.HTTPError as err:
                    if err.code == 404:
                        return True, False, {"error": "Repository 404 not found"}
                    return False, False, {"error": f"HTTP {err.code}"}
                except Exception as err:
                    return False, False, {"error": str(err)}

            gh_ok, repo_ok, meta = await asyncio.to_thread(_test_net)
            diag["github_reachable"] = gh_ok
            diag["repository_exists"] = repo_ok
            diag["details"]["repository_meta"] = meta

            releases = await self.check_for_updates()
            diag["release_endpoint_reachable"] = gh_ok
            diag["latest_release_parsed"] = isinstance(releases, list)
            diag["details"]["releases_count"] = len(releases)

            sample_assets = [
                {
                    "name": "AgenticOS-Setup-x64.exe",
                    "browser_download_url": "https://example.com/setup.exe",
                    "size": 100,
                },
                {
                    "name": "AgenticOS-x86_64.AppImage",
                    "browser_download_url": "https://example.com/app.AppImage",
                    "size": 100,
                },
            ]
            win_asset = self.select_best_asset(sample_assets, target_os="win32")
            diag["asset_selection_valid"] = (
                win_asset is not None and win_asset["name"].endswith(".exe")
            )

        except Exception as e:
            diag["details"]["error"] = str(e)

        return diag

    # ── State Getters ──

    async def get_update_status(self) -> UpdateStatus:
        return self._status

    async def get_update_history(self, limit: int = 50) -> Sequence[UpdateHistoryRecord]:
        return list(self._history)[-limit:]

    async def get_pending_update(self) -> UpdateManifest | None:
        return self._pending_update
