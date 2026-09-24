"""Agent package manager — signed .agent packages with install/upgrade/rollback.

An ``.agent`` file is a real gzipped tar archive containing:

* ``manifest.json`` — package name, version, entrypoint, capabilities, the
  file index (path, size, sha256) and the signature;
* every payload file the package ships.

Signing is HMAC-SHA256 over the canonical manifest bytes with a local
signing key (created at first use, mode 0600). Anyone holding the key can
sign: this is integrity + authenticity for locally managed packages, not a
public PKI — and the UI says exactly that.

Lifecycle:
* ``pack``     — build a package from a directory, sign it;
* ``verify``   — re-check the signature AND every file checksum; a tampered
                 byte anywhere is reported with the exact file;
* ``install``  — verify, then materialize into the installed tree and record
                 a checkpoint (file index + hashes) in the package journal;
* ``upgrade``  — install a new version for the same package name; the old
                 version stays on disk and in the journal;
* ``rollback`` — replay the previous version's checkpoint: re-write every
                 recorded file and verify every hash after the replay, so a
                 rollback is a verified replay, not a guess.

Honesty rules: a package that fails verification is never installed; a
rollback reports what it actually restored; the journal only records what
really happened, when it happened.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import secrets
import shutil
import tarfile
import time
import uuid
from pathlib import Path
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("packages.manager")

DEFAULT_PACKAGES_DIR = "~/.agentic_os/data/packages"
MANIFEST_NAME = "manifest.json"
SIGNATURE_ALGO = "HMAC-SHA256"


class PackageError(ValueError):
    """Operator-facing package error (mapped to HTTP 400/404)."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _canonical_pretty(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, indent=2, sort_keys=True).encode("utf-8")


class AgentPackageManager:
    """Pack, verify, install, upgrade, and roll back signed agent packages."""

    def __init__(self, data_dir: str = "") -> None:
        base = Path(data_dir or os.path.expanduser(DEFAULT_PACKAGES_DIR))
        base.mkdir(parents=True, exist_ok=True)
        self._dir = base
        self._installed_dir = base / "installed"
        self._installed_dir.mkdir(parents=True, exist_ok=True)
        self._journal_path = base / "package-journal.jsonl"
        self._key_path = base / "signing.key"

    # ── signing key ──────────────────────────────────────────────────────

    def _signing_key(self) -> bytes:
        if self._key_path.exists():
            return self._key_path.read_bytes().strip()
        key = secrets.token_hex(32).encode("utf-8")
        self._key_path.write_bytes(key)
        try:
            self._key_path.chmod(0o600)
        except Exception:
            pass
        return key

    def key_id(self) -> str:
        """Stable short id of the current signing key (safe to display)."""
        return _sha256_bytes(self._signing_key())[:12]

    # ── journal (append-only, real events) ───────────────────────────────

    def _append_journal(self, entry: dict[str, Any]) -> None:
        entry = {"id": f"pkg-{uuid.uuid4().hex[:8]}", "ts": time.time(), **entry}
        try:
            with self._journal_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            log.debug("package journal append failed", exc_info=True)

    def journal(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self._journal_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            lines = self._journal_path.read_text(encoding="utf-8").strip().split("\n")
        except Exception:
            return []
        for line in lines:
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        rows.sort(key=lambda r: float(r.get("ts") or 0), reverse=True)
        return rows[:limit]

    # ── pack / sign ──────────────────────────────────────────────────────

    def pack(
        self,
        source_dir: str,
        name: str,
        version: str,
        entrypoint: str = "",
        description: str = "",
        capabilities: list[str] | None = None,
        out_path: str = "",
    ) -> dict[str, Any]:
        src = Path(source_dir).expanduser()
        if not src.is_dir():
            raise PackageError(f"source directory does not exist: {src}")
        if not name.strip() or not version.strip():
            raise PackageError("package name and version are required")
        files: list[dict[str, Any]] = []
        for p in sorted(src.rglob("*")):
            if p.is_file():
                rel = p.relative_to(src).as_posix()
                data = p.read_bytes()
                files.append({"path": rel, "size": len(data), "sha256": _sha256_bytes(data)})
        if not files:
            raise PackageError("source directory contains no files to package")
        manifest: dict[str, Any] = {
            "name": name.strip(),
            "version": version.strip(),
            "entrypoint": entrypoint.strip(),
            "description": description.strip(),
            "capabilities": sorted({str(c) for c in (capabilities or [])}),
            "files": files,
            "created_at": time.time(),
            "algorithm": SIGNATURE_ALGO,
        }
        signature = hmac.new(self._signing_key(), _canonical(manifest), hashlib.sha256).hexdigest()
        manifest["signature"] = signature

        out = Path(out_path).expanduser() if out_path else self._dir / f"{name}-{version}.agent"
        out.parent.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            mbytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
            info = tarfile.TarInfo(name=MANIFEST_NAME)
            info.size = len(mbytes)
            info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(mbytes))
            for p in sorted(src.rglob("*")):
                if p.is_file():
                    tar.add(p, arcname=p.relative_to(src).as_posix())
        out.write_bytes(buf.getvalue())
        self._append_journal(
            {
                "action": "pack",
                "name": manifest["name"],
                "version": manifest["version"],
                "path": str(out),
                "files": len(files),
                "key_id": self.key_id(),
            }
        )
        return {
            "package": manifest["name"],
            "version": manifest["version"],
            "path": str(out),
            "files": len(files),
            "bytes": out.stat().st_size,
            "signature": signature,
            "algorithm": SIGNATURE_ALGO,
            "key_id": self.key_id(),
        }

    # ── read + verify ────────────────────────────────────────────────────

    def _read_archive(self, path: str) -> tuple[dict[str, Any], dict[str, bytes]]:
        p = Path(path).expanduser()
        if not p.is_file():
            raise PackageError(f"package file not found: {p}")
        try:
            with tarfile.open(p, mode="r:gz") as tar:
                names = tar.getnames()
                if MANIFEST_NAME not in names:
                    raise PackageError("not a valid .agent package: manifest.json missing")
                manifest_raw = tar.extractfile(MANIFEST_NAME)
                if manifest_raw is None:
                    raise PackageError("manifest.json is not readable")
                manifest = json.loads(manifest_raw.read().decode("utf-8"))
                files: dict[str, bytes] = {}
                for member in tar.getmembers():
                    if member.name == MANIFEST_NAME or not member.isfile():
                        continue
                    f = tar.extractfile(member)
                    if f is not None:
                        files[member.name] = f.read()
        except PackageError:
            raise
        except Exception as exc:
            raise PackageError(f"unreadable .agent archive: {exc}") from exc
        return manifest, files

    def verify(self, path: str) -> dict[str, Any]:
        manifest, files = self._read_archive(path)
        problems: list[str] = []
        signature = str(manifest.get("signature", ""))
        check = {k: v for k, v in manifest.items() if k != "signature"}
        expected = hmac.new(self._signing_key(), _canonical(check), hashlib.sha256).hexdigest()
        signature_ok = hmac.compare_digest(signature, expected)
        if not signature_ok:
            problems.append("signature does not verify against the local signing key")
        listed = manifest.get("files", [])
        for entry in listed:
            fpath = str(entry.get("path", ""))
            data = files.get(fpath)
            if data is None:
                problems.append(f"missing file: {fpath}")
                continue
            if _sha256_bytes(data) != entry.get("sha256"):
                problems.append(f"checksum mismatch: {fpath}")
            if len(data) != entry.get("size"):
                problems.append(f"size mismatch: {fpath}")
        extra = set(files) - {str(e.get("path")) for e in listed}
        for fpath in sorted(extra):
            problems.append(f"unlisted file present: {fpath}")
        return {
            "path": str(path),
            "name": manifest.get("name", ""),
            "version": manifest.get("version", ""),
            "signature_ok": signature_ok,
            "files_checked": len(listed),
            "ok": signature_ok and not problems,
            "problems": problems,
        }

    # ── installed tree ───────────────────────────────────────────────────

    def _installed_root(self, name: str) -> Path:
        safe = name.replace("/", "_").replace("\\", "_")
        return self._installed_dir / safe

    def list_installed(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self._installed_dir.is_dir():
            return out
        for pkg_dir in sorted(self._installed_dir.iterdir()):
            if not pkg_dir.is_dir():
                continue
            versions = sorted((v.name for v in pkg_dir.iterdir() if v.is_dir()), reverse=True)
            current = self._current_version(pkg_dir.name)
            meta: dict[str, Any] = {}
            if current:
                manifest_path = pkg_dir / current / MANIFEST_NAME
                if manifest_path.is_file():
                    try:
                        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
                    except Exception:
                        meta = {}
            out.append(
                {
                    "name": pkg_dir.name,
                    "versions": versions,
                    "current": current or "",
                    "entrypoint": meta.get("entrypoint", ""),
                    "capabilities": meta.get("capabilities", []),
                    "files": len(meta.get("files", [])),
                }
            )
        return out

    def _write_version(self, manifest: dict[str, Any], files: dict[str, bytes]) -> Path:
        root = self._installed_root(str(manifest["name"])) / str(manifest["version"])
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        resolved_root = str(root.resolve())
        # The manifest itself is part of the installed tree: rollback replay
        # reads it from the version checkpoint.
        (root / MANIFEST_NAME).write_bytes(_canonical_pretty(manifest))
        for rel, data in files.items():
            target = root / rel
            if not str(target.resolve()).startswith(resolved_root):
                raise PackageError(f"unsafe path in package: {rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return root

    def _current_path(self, name: str) -> Path:
        return self._installed_root(name) / "CURRENT"

    def _set_current(self, name: str, version: str) -> None:
        self._installed_root(name).mkdir(parents=True, exist_ok=True)
        self._current_path(name).write_text(version, encoding="utf-8")

    def _current_version(self, name: str) -> str | None:
        root = self._installed_root(name)
        if not root.is_dir():
            return None
        cp = self._current_path(name)
        if cp.is_file():
            v = cp.read_text(encoding="utf-8").strip()
            if v and (root / v).is_dir():
                return v
        versions = sorted((v.name for v in root.iterdir() if v.is_dir()), reverse=True)
        return versions[0] if versions else None

    # ── install / upgrade / rollback ─────────────────────────────────────

    def install(self, path: str) -> dict[str, Any]:
        verdict = self.verify(path)
        if not verdict["ok"]:
            raise PackageError(
                "package failed verification and was NOT installed: "
                + "; ".join(verdict["problems"])
            )
        manifest, files = self._read_archive(path)
        name = str(manifest["name"])
        version = str(manifest["version"])
        previous = self._current_version(name)
        self._write_version(manifest, files)
        self._set_current(name, version)
        self._append_journal(
            {
                "action": "install",
                "name": name,
                "version": version,
                "previous_version": previous,
                "files": len(files),
                "checkpoint": [
                    {"path": e["path"], "sha256": e["sha256"]} for e in manifest.get("files", [])
                ],
            }
        )
        return {
            "installed": f"{name}@{version}",
            "previous_version": previous,
            "files": len(files),
            "verified": True,
        }

    def upgrade(self, path: str) -> dict[str, Any]:
        manifest, _files = self._read_archive(path)
        name = str(manifest["name"])
        current = self._current_version(name)
        if current is None:
            raise PackageError(f"package {name!r} is not installed; use install, not upgrade")
        if str(manifest["version"]) == current:
            raise PackageError(f"version {current} is already installed; a new version is required")
        result = self.install(path)
        self._append_journal(
            {
                "action": "upgrade",
                "name": name,
                "version": str(manifest["version"]),
                "previous_version": current,
            }
        )
        result["upgraded_from"] = current
        return result

    def rollback(self, name: str) -> dict[str, Any]:
        if not name.strip():
            raise PackageError("package name is required")
        entries = [
            e
            for e in self.journal(limit=1000)
            if e.get("action") in ("install", "upgrade", "rollback") and e.get("name") == name
        ]
        entries.sort(key=lambda e: float(e.get("ts") or 0))
        current = self._current_version(name)
        if current is None:
            raise PackageError(f"package {name!r} is not installed")
        # Walk the journal backwards from the current version to the latest
        # checkpoint with a DIFFERENT version — that checkpoint is the state
        # to replay.
        target: dict[str, Any] | None = None
        for e in reversed(entries):
            if e.get("version") != current and e.get("checkpoint"):
                target = e
                break
        if target is None:
            raise PackageError(
                f"no earlier version checkpoint found for {name!r}; nothing to roll back to"
            )
        target_version = str(target["version"])
        target_root = self._installed_root(name) / target_version
        # Replay the checkpoint: every recorded file must exist in the target
        # version tree with exactly the recorded hash. Then re-materialize the
        # tree via _write_version so the replay is what becomes installed.
        replay: dict[str, bytes] = {}
        problems: list[str] = []
        for entry in target.get("checkpoint", []):
            rel = str(entry.get("path", ""))
            want = str(entry.get("sha256", ""))
            f = target_root / rel
            if not f.is_file():
                problems.append(f"checkpoint file missing on disk: {rel}")
                continue
            data = f.read_bytes()
            got = _sha256_bytes(data)
            if got != want:
                problems.append(f"checkpoint hash mismatch during replay: {rel}")
            replay[rel] = data
        if problems:
            raise PackageError(
                "rollback replay did not verify; installed tree untouched: " + "; ".join(problems)
            )
        manifest_path = target_root / MANIFEST_NAME
        if not manifest_path.is_file():
            raise PackageError(
                f"checkpoint manifest missing for {name}@{target_version}; cannot replay"
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise PackageError(f"checkpoint manifest unreadable: {exc}") from exc
        self._write_version(manifest, replay)
        self._set_current(name, target_version)
        self._append_journal(
            {
                "action": "rollback",
                "name": name,
                "version": target_version,
                "previous_version": current,
                "files_restored": len(replay),
            }
        )
        return {
            "rolled_back": f"{name}@{target_version}",
            "from_version": current,
            "files_restored": len(replay),
            "verified": True,
        }


# Process singleton wired lazily by the API layer.
package_manager: AgentPackageManager | None = None


def get_package_manager() -> AgentPackageManager:
    global package_manager
    if package_manager is None:
        package_manager = AgentPackageManager()
    return package_manager
