"""Active proxy profile — one switchable source of truth for model routing.

AgenticOS is fully proxy-agnostic and ships with ZERO preconfigured proxies.
Model-routing endpoints (LiteLLM, OpenRouter, Ollama, vLLM, LM Studio, direct
OpenAI, or any external agent gateway such as Nexus) are bound MANUALLY by the
operator via the ``/api/proxy/*`` endpoints. Nothing is assumed, nothing is
auto-created, and removing one product must never affect the others.

Design rules
------------
* No proxy host is hardcoded into application logic and no default profile
  exists: with no persisted profile the chain is EMPTY and model routing is
  honestly unavailable until the operator binds an endpoint.
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

        Returns the value of the environment variable named by
        ``api_key_env``, or an empty string when none is declared or the
        variable is unset. No fabricated bearer: endpoints that require a
        key must have ``api_key_env`` configured by the operator.
        """
        if self.api_key_env:
            return os.environ.get(self.api_key_env, "")
        return ""

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
    """No proxy ships preconfigured — isolation is the default state."""
    return []


def get_proxy_chain() -> ProxyChain:
    """Load the persisted proxy chain; an empty chain when nothing is bound.

    A malformed or missing file is not an error — it yields an empty chain
    ("no proxy configured"), never an assumed endpoint.
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
    """First profile in the chain (callers should prefer health-checked selection).

    Raises ``RuntimeError`` when no proxy is bound — fail fast with the exact
    remediation instead of dereferencing an empty chain.
    """
    profiles = get_proxy_chain().profiles
    if not profiles:
        raise RuntimeError(
            "no proxy profiles configured — bind one manually via "
            "POST /api/proxy/profile (or /api/proxy/profile/add)"
        )
    return profiles[0]
