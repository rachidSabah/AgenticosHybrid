"""SecretsManager adapter over the encrypted SecretStore (Security Framework)."""

from __future__ import annotations

from agentic_os.ports.provider_management import SecretStore
from agentic_os.ports.security import SecretsManager


class SecretStoreSecretsManager(SecretsManager):
    """Thin :class:`SecretsManager` that wraps the frozen ``SecretStore`` port.

    The encrypted-at-rest store (ADR-0006) already owns persistence; this
    adapter just re-exposes it under the Security vocabulary so the framework
    facade has one consistent dependency surface.
    """

    def __init__(self, store: SecretStore) -> None:
        self._store = store

    async def put(self, name: str, secret: str) -> None:
        await self._store.put(name, secret)

    async def get(self, name: str) -> str | None:
        return await self._store.get(name)

    async def delete(self, name: str) -> bool:
        await self._store.delete(name)
        return not await self._store.exists(name)
