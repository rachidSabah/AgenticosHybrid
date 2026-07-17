"""Encrypted secret store (at-rest encryption via Fernet).

Implements :class:`SecretStore`. Secrets are encrypted with a Fernet key derived
from ``AGENTIC_OS_MASTER_KEY`` (or a generated, persisted key file). Plaintext
is never written to disk. Falls back to an in-memory store when no persistence
path is configured (dev/tests).
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

from agentic_os.infrastructure.logging import get_logger

log = get_logger("security.secret_store")

_DEFAULT_PATH_ENV = os.environ.get("AGENTIC_OS_VAULT_PATH", "").strip()
_DEFAULT_PATH = Path(_DEFAULT_PATH_ENV).expanduser() if _DEFAULT_PATH_ENV else None


class EncryptedSecretStore:
    def __init__(self, path: Path | None = None) -> None:
        # None (or empty) path => purely in-memory store (no persistence).
        self._path = path
        self._mem: dict[str, str] = {}
        self._fernet = self._load_or_create_key()
        if self._path is not None and self._path.exists():
            self._load()

    # ── key management ──
    def _load_or_create_key(self) -> Fernet:
        raw = os.environ.get("AGENTIC_OS_MASTER_KEY")
        if raw:
            return Fernet(self._normalize_key(raw))
        key_file = Path(
            os.environ.get("AGENTIC_OS_KEY_FILE", "~/.agentic-os/master.key")
        ).expanduser()
        if key_file.exists():
            return Fernet(key_file.read_bytes().strip())
        if not key_file.parent.exists():
            key_file.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        key_file.write_bytes(key)
        key_file.chmod(0o600)
        return Fernet(key)

    @staticmethod
    def _normalize_key(raw: str) -> bytes:
        # Accept either a urlsafe-base64 Fernet key or arbitrary passphrase.
        try:
            Fernet(raw.encode() if isinstance(raw, str) else raw)
            return raw.encode()
        except Exception:
            import hashlib

            digest = hashlib.sha256(raw.encode()).digest()
            return base64.urlsafe_b64encode(digest)

    # ── persistence ──
    def _load(self) -> None:
        assert self._path is not None
        try:
            blob = json.loads(self._path.read_text())
            for k, v in blob.items():
                self._mem[k] = self._fernet.decrypt(v.encode()).decode()
        except Exception as exc:  # noqa: BLE001
            log.warning("secret_store.load_failed", error=str(exc))

    def _persist(self) -> None:
        if self._path is None:
            return
        blob = {k: self._fernet.encrypt(v.encode()).decode() for k, v in self._mem.items()}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob))
        tmp.replace(self._path)
        self._path.chmod(0o600)

    # ── SecretStore protocol ──
    async def put(self, key: str, value: str) -> None:
        self._mem[key] = value
        self._persist()

    async def get(self, key: str) -> str | None:
        return self._mem.get(key)

    async def delete(self, key: str) -> None:
        self._mem.pop(key, None)
        self._persist()

    async def exists(self, key: str) -> bool:
        return key in self._mem
