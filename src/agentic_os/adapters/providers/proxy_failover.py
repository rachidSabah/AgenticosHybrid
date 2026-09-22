"""Multi-proxy failover — probe an ordered chain and pick the first healthy proxy.

Why this exists
---------------
AgenticOS originally depended on a single proxy host. When that host went
offline every CLI invocation blocked until the 120s timeout, the execution was
abandoned, and the pipeline fell back to writing markdown summaries instead of
real source files. Measured: the local Nexus gateway returned connection-refused
on 6/6 probes while still being configured as the only provider.

Selection is therefore *always* based on a live probe. Health is never cached
and never assumed from configuration.

All functions are side-effect free apart from the HTTP probe itself.
"""

from __future__ import annotations

import httpx

from agentic_os.domain.proxy_profile import ProxyChain, ProxyProfile
from agentic_os.infrastructure.logging import get_logger

log = get_logger("proxy.failover")

DEFAULT_PROBE_TIMEOUT = 5.0


async def probe(profile: ProxyProfile, timeout: float = DEFAULT_PROBE_TIMEOUT) -> bool:
    """Return True when the proxy answers a models lookup.

    Any transport error is treated as "down" — never raised, so a dead proxy
    degrades instead of crashing the dispatcher.
    """
    try:
        headers = {"Authorization": f"Bearer {profile.api_key()}"} if profile.api_key() else {}
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(profile.models_url(), headers=headers)
        healthy = resp.status_code < 500
        log.debug(
            "proxy.probe",
            name=profile.name,
            base_url=profile.base_url,
            status=resp.status_code,
            healthy=healthy,
        )
        return healthy
    except Exception as exc:  # noqa: BLE001 - any failure means unreachable
        log.debug(
            "proxy.probe_failed",
            name=profile.name,
            base_url=profile.base_url,
            error=str(exc),
        )
        return False


def _as_list(proxies: ProxyChain | list[ProxyProfile] | None) -> list[ProxyProfile]:
    if proxies is None:
        return []
    if isinstance(proxies, ProxyChain):
        return proxies.profiles
    return list(proxies)


async def select_healthy_proxy(
    proxies: ProxyChain | list[ProxyProfile] | None,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
) -> ProxyProfile | None:
    """Return the first proxy that passes a live probe, or None if all are down.

    Callers MUST handle ``None`` by failing fast with a clear message rather
    than dispatching to a stale URL and waiting for a timeout.
    """
    for profile in _as_list(proxies):
        if await probe(profile, timeout=timeout):
            log.info("proxy.selected", name=profile.name, base_url=profile.base_url)
            return profile
    log.warning("proxy.all_unreachable", count=len(_as_list(proxies)))
    return None


def describe_unreachable(proxies: ProxyChain | list[ProxyProfile] | None) -> str:
    """Human-readable error listing every proxy that was tried."""
    names = [p.name for p in _as_list(proxies)]
    if not names:
        return "no proxies configured"
    return "all proxies unreachable: " + ", ".join(names)
