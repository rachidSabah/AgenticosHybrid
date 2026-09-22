"""Active proxy profile — one switchable source of truth for model routing.

AgenticOS must work with *any* OpenAI-compatible proxy (Nexus, LiteLLM,
OpenRouter, Ollama, vLLM, LM Studio, direct OpenAI), not one hardcoded host.

Design rules
------------
* No proxy host is hardcoded into application logic. The default below is a
  convenience only and is always overridden by the persisted profile.
* A profile is inert data. It never guesses health — see
  ``adapters.providers.proxy_failover`` for live probing.
* Failures are explicit: callers get ``None`` / empty rather than a stale URL
  that produces a 120s hang.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_PROXY_FILE = "~/.agentic_os/data/proxy.json"

# Convenience default only. Overridden by the persisted profile.
_NEXUS_DEFAULT = {
    "name": "nexus",
    "base_url": "http://127.0.0.1:8787/v1",
    "api_key_env": "",
    "model": "",
    "wire": "chat",
}


@dataclass
class ProxyProfile:
    """A single OpenAI-compatible endpoint."""

    name: str
    base_url: str
    api_key_env: str = ""
    model: str = ""
    wire: str = "chat"

    def api_key(self) -> str:
        """Resolve the API key.

        If ``api_key_env`` names an environment variable, read it. Otherwise
        fall back to the profile name (Nexus accepts any non-empty bearer).
        """
        if self.api_key_env:
            return os.environ.get(self.api_key_env, "")
        return self.name

    def models_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/models"


@dataclass
class ProxyChain:
    """Ordered list of proxies; first healthy one wins."""

    profiles: list[ProxyProfile] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.profiles


def _proxy_file() -> Path:
    override = os.environ.get("AGENTICOS_PROXY_FILE")
    if override:
        return Path(override)
    return Path(os.path.expanduser(DEFAULT_PROXY_FILE))


def _default_profiles() -> list[ProxyProfile]:
    return [ProxyProfile(**_NEXUS_DEFAULT)]


def get_proxy_chain() -> ProxyChain:
    """Load the persisted proxy chain; fall back to the single default.

    A malformed or missing file is not an error — it yields the default chain.
    """
    f = _proxy_file()
    try:
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            raw = data.get("profiles")
            if isinstance(raw, list) and raw:
                profiles = [
                    ProxyProfile(
                        name=str(p.get("name", "")),
                        base_url=str(p.get("base_url", "")),
                        api_key_env=str(p.get("api_key_env", "")),
                        model=str(p.get("model", "")),
                        wire=str(p.get("wire", "chat")),
                    )
                    for p in raw
                    if isinstance(p, dict) and p.get("base_url")
                ]
                if profiles:
                    return ProxyChain(profiles=profiles)
    except Exception:
        pass
    return ProxyChain(profiles=_default_profiles())


def set_proxy_chain(chain: ProxyChain) -> ProxyChain:
    """Persist the proxy chain. Best-effort — never raises on disk failure."""
    f = _proxy_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            json.dumps({"profiles": [asdict(p) for p in chain.profiles]}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return chain


def get_active_profile() -> ProxyProfile:
    """First profile in the chain (callers should prefer health-checked selection)."""
    return get_proxy_chain().profiles[0]
