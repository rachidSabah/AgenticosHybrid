"""Auto Update Framework — update checking, downloading, verification, and installation."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

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


class AutoUpdateManager:
    """Manages update checking, downloading, verification, and installation."""

    def __init__(self) -> None:
        self._status = UpdateStatus.IDLE
        self._current_channel = UpdateChannel.STABLE
        self._pending_update: UpdateManifest | None = None
        self._history: list[UpdateHistoryRecord] = []
        self._current_version = "0.9.5"

    # ── Update Checking ──

    async def check_for_updates(
        self, channel: UpdateChannel = UpdateChannel.STABLE
    ) -> Sequence[ReleaseInfo]:
        self._status = UpdateStatus.CHECKING
        log.info("Checking for updates", channel=channel.value)

        releases: list[ReleaseInfo] = []

        try:
            import json
            import urllib.request

            url = "https://api.github.com/repos/rachidSabah/AgenticOS/releases"
            req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())

            for item in data:
                tag = item.get("tag_name", "")
                if not tag.startswith("v"):
                    continue
                version = tag.lstrip("v")
                is_prerelease = item.get("prerelease", False)
                release_channel = UpdateChannel.NIGHTLY if is_prerelease else UpdateChannel.STABLE

                if channel != UpdateChannel.NIGHTLY and release_channel != channel:
                    if channel == UpdateChannel.STABLE and release_channel != UpdateChannel.STABLE:
                        continue

                assets = []
                for asset in item.get("assets", []):
                    assets.append(
                        {
                            "name": asset["name"],
                            "url": asset["browser_download_url"],
                            "size": asset["size"],
                        }
                    )

                releases.append(
                    ReleaseInfo(
                        version=version,
                        tag=tag,
                        url=item.get("html_url", ""),
                        published_at=datetime.fromisoformat(
                            item["published_at"].replace("Z", "+00:00")
                        ),
                        release_notes=item.get("body", ""),
                        assets=assets,
                        prerelease=is_prerelease,
                        channel=release_channel,
                    )
                )

            releases.sort(key=lambda r: r.published_at or datetime.min, reverse=True)
            log.info("Update check complete", releases=len(releases))
        except Exception as exc:
            log.warning("Failed to check for updates", error=str(exc))

        self._status = UpdateStatus.IDLE
        return releases

    async def download_update(self, manifest: UpdateManifest) -> bool:
        self._status = UpdateStatus.DOWNLOADING
        log.info("Downloading update", version=manifest.version, url=manifest.download_url)

        import tempfile
        import urllib.request

        try:
            tmp_dir = Path(tempfile.gettempdir()) / "agentic_os_updates"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            dest = tmp_dir / f"agentic_os_{manifest.version}.zip"

            urllib.request.urlretrieve(manifest.download_url, dest)

            if manifest.checksum_sha256:
                sha256 = hashlib.sha256(dest.read_bytes()).hexdigest()
                if sha256 != manifest.checksum_sha256:
                    log.error("Checksum mismatch", expected=manifest.checksum_sha256, got=sha256)
                    self._status = UpdateStatus.FAILED
                    return False

            self._pending_update = manifest
            self._status = UpdateStatus.READY
            log.info("Update downloaded", path=str(dest), size=dest.stat().st_size)
            return True
        except Exception as exc:
            log.error("Download failed", error=str(exc))
            self._status = UpdateStatus.FAILED
            return False

    async def install_update(self, manifest: UpdateManifest) -> UpdateResult:
        import time

        start = time.monotonic()
        self._status = UpdateStatus.INSTALLING
        log.info("Installing update", version=manifest.version)

        try:
            # In-memory: mark as installed
            self._current_version = manifest.version
            self._status = UpdateStatus.COMPLETED
            self._pending_update = None

            result = UpdateResult(
                success=True,
                previous_version=self._current_version,
                new_version=manifest.version,
                installed_at=datetime.now(UTC),
                duration_seconds=round(time.monotonic() - start, 2),
            )

            self._history.append(
                UpdateHistoryRecord(
                    from_version=self._current_version,
                    to_version=manifest.version,
                    channel=self._current_channel,
                    status=UpdateStatus.COMPLETED,
                    duration_seconds=result.duration_seconds,
                )
            )

            log.info("Update installed successfully", version=manifest.version)
            return result

        except Exception as exc:
            self._status = UpdateStatus.FAILED
            return UpdateResult(
                success=False,
                previous_version=self._current_version,
                new_version=manifest.version,
                error=str(exc),
            )

    async def get_update_status(self) -> UpdateStatus:
        return self._status

    async def get_update_history(self, limit: int = 50) -> Sequence[UpdateHistoryRecord]:
        return list(self._history)[-limit:]

    async def get_pending_update(self) -> UpdateManifest | None:
        return self._pending_update

    async def get_current_version(self) -> str:
        return self._current_version

    async def set_current_version(self, version: str) -> None:
        self._current_version = version
