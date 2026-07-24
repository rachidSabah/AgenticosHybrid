"""AI provider discovery — detects configured AI providers on the system.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.logging import get_logger

_log = get_logger(__name__)

__all__ = ["ProviderDiscovery", "DiscoveredProvider"]

_PROVIDER_API_KEYS: dict[str, list[str]] = {
    "openai": ["OPENAI_API_KEY", "OPENAI_API_TOKEN"],
    "anthropic": ["ANTHROPIC_API_KEY", "ANTHROPIC_API_TOKEN", "CLAUDE_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
}

_PROVIDER_CONFIG_PATHS: dict[str, list[Path]] = {}


def _init() -> None:
    global _PROVIDER_CONFIG_PATHS
    if _PROVIDER_CONFIG_PATHS:
        return
    h = Path.home()
    _PROVIDER_CONFIG_PATHS = {
        "openai": [h / ".openai" / "config.json"],
        "anthropic": [h / ".claude" / "config.json"],
        "google": [h / ".gemini" / "config.json"],
    }


_init()


@dataclass
class DiscoveredProvider:
    name: str
    provider_type: str
    has_api_key: bool = False
    api_key_source: str | None = None
    endpoint: str | None = None
    config_path: str | None = None
    version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider_type": self.provider_type,
            "has_api_key": self.has_api_key,
            "api_key_source": self.api_key_source,
            "endpoint": self.endpoint,
            "config_path": self.config_path,
            "version": self.version,
            "metadata": dict(self.metadata),
            "discovered_at": self.discovered_at.isoformat(),
        }


class ProviderDiscovery:
    async def discover_all(self) -> list[DiscoveredProvider]:
        providers: list[DiscoveredProvider] = []
        providers.extend(self._discover_from_env())
        providers.extend(self._discover_from_configs())
        seen: set[str] = set()
        deduped: list[DiscoveredProvider] = []
        for p in providers:
            if p.name not in seen:
                seen.add(p.name)
                deduped.append(p)
            else:
                for e in deduped:
                    if e.name == p.name:
                        if p.has_api_key and not e.has_api_key:
                            e.has_api_key = True
                            e.api_key_source = p.api_key_source
                        if p.endpoint and not e.endpoint:
                            e.endpoint = p.endpoint
                        e.metadata.update(p.metadata)
                        break
        _log.info("Discovered %d providers", len(deduped))
        return deduped

    async def discover_by_type(self, t: str) -> list[DiscoveredProvider]:
        a = await self.discover_all()
        return [p for p in a if p.provider_type == t]

    @staticmethod
    def _discover_from_env() -> list[DiscoveredProvider]:
        r: list[DiscoveredProvider] = []
        for pn, ks in _PROVIDER_API_KEYS.items():
            for k in ks:
                v = os.environ.get(k)
                if v and v.strip():
                    ep = ProviderDiscovery._infer_endpoint(pn)
                    r.append(DiscoveredProvider(name=pn, provider_type=pn, has_api_key=True, api_key_source=f"env:{k}", endpoint=ep, metadata={"detected_by": "env_var"}))
                    break
        return r

    @staticmethod
    def _discover_from_configs() -> list[DiscoveredProvider]:
        r: list[DiscoveredProvider] = []
        for pn, ps in _PROVIDER_CONFIG_PATHS.items():
            for cp in ps:
                if cp.exists():
                    try:
                        d = json.loads(cp.read_text(encoding="utf-8"))
                        ak = d.get("api_key") or d.get("apikey") or ""
                        ep = d.get("endpoint") or d.get("base_url") or ""
                        r.append(DiscoveredProvider(name=pn, provider_type=pn, has_api_key=bool(ak), api_key_source=f"config:{cp}" if ak else None, endpoint=ep or ProviderDiscovery._infer_endpoint(pn), config_path=str(cp), version=d.get("version"), metadata={"detected_by": "config_file"}))
                    except (json.JSONDecodeError, OSError):
                        pass
                    break
        return r

    @staticmethod
    def _infer_endpoint(pn: str) -> str | None:
        eps = {"openai": "https://api.openai.com/v1", "anthropic": "https://api.anthropic.com", "google": "https://generativelanguage.googleapis.com"}
        return eps.get(pn)

    @staticmethod
    def get_supported_providers() -> list[str]:
        return list(_PROVIDER_API_KEYS.keys())
