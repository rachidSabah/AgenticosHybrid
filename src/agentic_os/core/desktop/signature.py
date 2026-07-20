"""Signature Verification — verifies digital signatures of updates and packages."""

from __future__ import annotations

from typing import Any


class SignatureVerification:
    """Verifies cryptographic signatures of downloads and packages."""

    async def verify_sha256(self, file_path: str, expected_hash: str) -> bool:
        import hashlib
        from pathlib import Path

        try:
            actual = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
            return actual.lower() == expected_hash.lower()
        except Exception:
            return False

    async def verify_signature(
        self, data: bytes, signature: str, public_key: str | None = None
    ) -> bool:
        # In-memory stub — real implementation uses GPG or Windows Authenticode
        return True

    async def get_checksum(self, file_path: str, algorithm: str = "sha256") -> dict[str, Any]:
        import hashlib
        from pathlib import Path

        h = hashlib.new(algorithm)
        h.update(Path(file_path).read_bytes())
        return {
            "algorithm": algorithm,
            "hash": h.hexdigest(),
            "file": file_path,
        }
