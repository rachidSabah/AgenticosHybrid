"""API Key Vault — high-level key management over a SecretStore.

Implements :class:`ApiKeyVault`. Keys are namespaced by provider so the vault
can back multiple providers. The plaintext key is never exposed in logs.
"""

from __future__ import annotations

from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.provider_management import SecretStore

log = get_logger("providers.vault")


class ApiKeyVaultImpl:
    _PREFIX = "provider:key:"

    def __init__(self, store: SecretStore) -> None:
        self._store = store

    def _ref(self, provider: str) -> str:
        return f"{self._PREFIX}{provider}"

    async def store_key(self, provider: str, api_key: str) -> None:
        await self._store.put(self._ref(provider), api_key)
        log.info("vault.key_stored", provider=provider)

    async def get_key(self, provider: str) -> str | None:
        return await self._store.get(self._ref(provider))

    async def revoke(self, provider: str) -> None:
        await self._store.delete(self._ref(provider))
        log.info("vault.key_revoked", provider=provider)
