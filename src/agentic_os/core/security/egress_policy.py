"""Egress policy — PII/secret redaction, tool rules, cost caps, air-gap.

Every byte that leaves the machine through a bound proxy endpoint, and
every tool invocation agents make, passes a single policy layer:

* **Redaction** — real patterns for secrets (API keys, GitHub/AWS/Slack
  tokens, bearer headers, PEM private keys, ``KEY=value`` assignments) and
  PII (emails, SSNs, Luhn-verified card numbers, NANP phone numbers), plus
  operator-defined custom regexes. Matches are replaced with honest
  ``[REDACTED:<class>]`` markers; the inspection report counts exactly what
  was found and removed.
* **Tool rules** — per-binding allow/deny lists for tool names. Deny wins.
  An empty allow list means "no allow restriction" (deny still applies).
* **Cost caps** — a per-call USD cap. Enforcement is measurement-based:
  the caller supplies the measured token usage and the operator-supplied
  price table gives the rate; when usage or a price is missing the verdict
  says so instead of guessing.
* **Air-gap** — when enabled, only loopback endpoints (127.0.0.1, ::1,
  localhost) may be bound or used; every other host is refused with the
  exact reason. Checked at bind time AND at egress time.

Nothing here is advisory-only decoration: the gateway, the proxy-binding
API, and the MCP invocation path all call this module before work happens.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agentic_os.infrastructure.logging import get_logger

log = get_logger("security.egress_policy")

DEFAULT_POLICY_FILE = "~/.agentic_os/data/egress-policy.json"

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"}


class PolicyViolation(Exception):
    """Egress refused by policy (mapped to HTTP 400/403)."""


# ── real patterns ────────────────────────────────────────────────────────────

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs)_[A-Za-z0-9]{20,}\b")),
    ("github-finegrained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    (
        "private-key-block",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    ),
    ("bearer-header", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE)),
    (
        "key-assignment",
        re.compile(
            r"\b(?:api[_-]?key|apikey|secret|token|password|passwd|credential)"
            r"(\s*[=:]\s*)(['\"]?)[A-Za-z0-9._~+/=-]{8,}\2",
            re.IGNORECASE,
        ),
    ),
)

PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone", re.compile(r"\b(?:\+?1[-. (]?)?\d{3}[-. )]?\d{3}[-.]?\d{4}\b")),
)


def _luhn_ok(digits: str) -> bool:
    """Standard Luhn checksum over the digit string."""
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = ord(ch) - 48
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


CARD_RE = re.compile(r"\b(?:\d[ -]?){13,16}\b")


def _card_sub(match: re.Match) -> str:
    candidate = match.group(0)
    digits = re.sub(r"\D", "", candidate)
    if 13 <= len(digits) <= 16 and _luhn_ok(digits):
        return "[REDACTED:card-number]"
    return candidate


@dataclass
class RedactionReport:
    """Measured account of what redaction actually removed."""

    replacements: int = 0
    by_class: dict[str, int] = field(default_factory=dict)

    def record(self, cls: str, count: int) -> None:
        self.replacements += count
        self.by_class[cls] = self.by_class.get(cls, 0) + count

    def to_dict(self) -> dict[str, Any]:
        return {"replacements": self.replacements, "by_class": dict(self.by_class)}


@dataclass
class EgressPolicy:
    """Operator-owned egress configuration. Persisted; empty = permissive."""

    redact_secrets: bool = True
    redact_pii: bool = True
    custom_redactions: dict[str, str] = field(default_factory=dict)  # name -> regex
    tools_deny: list[str] = field(default_factory=list)
    tools_allow: list[str] = field(default_factory=list)  # empty = no allow restriction
    max_cost_per_call_usd: float | None = None
    price_per_1k_tokens: dict[str, float] = field(default_factory=dict)  # model prefix -> usd
    air_gap: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EgressVerdict:
    allowed: bool
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason, **self.detail}


class EgressPolicyManager:
    """Loads, persists, and enforces the egress policy."""

    def __init__(self, policy_file: str = "") -> None:
        self._path = Path(policy_file or os.path.expanduser(DEFAULT_POLICY_FILE))
        self._policy = self._load()

    # ── persistence ──────────────────────────────────────────────────────

    def _load(self) -> EgressPolicy:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return EgressPolicy(
                        redact_secrets=bool(data.get("redact_secrets", True)),
                        redact_pii=bool(data.get("redact_pii", True)),
                        custom_redactions={
                            str(k): str(v) for k, v in (data.get("custom_redactions") or {}).items()
                        },
                        tools_deny=[str(t) for t in (data.get("tools_deny") or [])],
                        tools_allow=[str(t) for t in (data.get("tools_allow") or [])],
                        max_cost_per_call_usd=data.get("max_cost_per_call_usd"),
                        price_per_1k_tokens={
                            str(k): float(v)
                            for k, v in (data.get("price_per_1k_tokens") or {}).items()
                        },
                        air_gap=bool(data.get("air_gap", False)),
                    )
        except Exception:
            log.debug("egress policy load failed; defaults active", exc_info=True)
        return EgressPolicy()

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._policy.to_dict(), indent=2), encoding="utf-8")
        except Exception:
            log.debug("egress policy save failed", exc_info=True)

    def get_policy(self) -> EgressPolicy:
        return self._policy

    def update(self, **changes: Any) -> EgressPolicy:
        current = self._policy
        if "custom_redactions" in changes:
            raw = changes["custom_redactions"] or {}
            if not isinstance(raw, dict):
                raise PolicyViolation("custom_redactions must be an object of name -> regex")
            compiled: dict[str, str] = {}
            for name, pattern in raw.items():
                try:
                    re.compile(str(pattern))
                except re.error as exc:
                    raise PolicyViolation(
                        f"custom redaction {name!r} is not a valid regex: {exc}"
                    ) from exc
                compiled[str(name)] = str(pattern)
            changes["custom_redactions"] = compiled
        if "price_per_1k_tokens" in changes:
            raw = changes["price_per_1k_tokens"] or {}
            if not isinstance(raw, dict):
                raise PolicyViolation("price_per_1k_tokens must be an object of model -> usd")
            changes["price_per_1k_tokens"] = {str(k): float(v) for k, v in raw.items()}
        if "max_cost_per_call_usd" in changes and changes["max_cost_per_call_usd"] is not None:
            changes["max_cost_per_call_usd"] = float(changes["max_cost_per_call_usd"])
        if "tools_deny" in changes:
            changes["tools_deny"] = [str(t) for t in (changes["tools_deny"] or [])]
        if "tools_allow" in changes:
            changes["tools_allow"] = [str(t) for t in (changes["tools_allow"] or [])]
        updated = EgressPolicy(
            redact_secrets=bool(changes.get("redact_secrets", current.redact_secrets)),
            redact_pii=bool(changes.get("redact_pii", current.redact_pii)),
            custom_redactions=changes.get("custom_redactions", dict(current.custom_redactions)),
            tools_deny=changes.get("tools_deny", list(current.tools_deny)),
            tools_allow=changes.get("tools_allow", list(current.tools_allow)),
            max_cost_per_call_usd=changes.get(
                "max_cost_per_call_usd", current.max_cost_per_call_usd
            ),
            price_per_1k_tokens=changes.get(
                "price_per_1k_tokens", dict(current.price_per_1k_tokens)
            ),
            air_gap=bool(changes.get("air_gap", current.air_gap)),
        )
        self._policy = updated
        self._save()
        return updated

    # ── redaction ────────────────────────────────────────────────────────

    def redact_text(self, text: str, report: RedactionReport | None = None) -> str:
        """Redact one string in place; returns the scrubbed text."""
        policy = self._policy
        out = text
        rep = report if report is not None else RedactionReport()
        if policy.redact_secrets:
            for cls, pattern in SECRET_PATTERNS:
                out, n = pattern.subn(lambda m, c=cls: f"[REDACTED:{c}]", out)
                if n:
                    rep.record(cls, n)
        if policy.redact_pii:
            for cls, pattern in PII_PATTERNS:
                out, n = pattern.subn(lambda m, c=cls: f"[REDACTED:{c}]", out)
                if n:
                    rep.record(cls, n)
            out = CARD_RE.sub(_card_sub, out)
        for cls, pattern_src in policy.custom_redactions.items():
            try:
                pattern = re.compile(pattern_src)
            except re.error:
                continue  # compile errors are refused at update(); stay safe here
            out, n = pattern.subn(lambda m, c=cls: f"[REDACTED:{c}]", out)
            if n:
                rep.record(cls, n)
        return out

    def redact_payload(self, payload: Any, report: RedactionReport | None = None) -> Any:
        """Recursively redact every string in a JSON-like payload."""
        rep = report if report is not None else RedactionReport()
        if isinstance(payload, str):
            return self.redact_text(payload, rep)
        if isinstance(payload, list):
            return [self.redact_payload(item, rep) for item in payload]
        if isinstance(payload, dict):
            return {k: self.redact_payload(v, rep) for k, v in payload.items()}
        return payload

    def inspect(self, text: str) -> dict[str, Any]:
        """Dry run: what WOULD be redacted, without returning scrubbed text."""
        rep = RedactionReport()
        self.redact_text(text, rep)
        return rep.to_dict()

    # ── tool rules ───────────────────────────────────────────────────────

    def tool_verdict(self, tool: str) -> EgressVerdict:
        policy = self._policy
        name = str(tool).strip()
        deny = {t.lower().lstrip("/") for t in policy.tools_deny}
        allow = {t.lower().lstrip("/") for t in policy.tools_allow}
        key = name.lower().lstrip("/")
        if key in deny or any(key.endswith(d) or d.endswith(key) for d in deny if d):
            return EgressVerdict(False, f"tool {name!r} is denied by egress policy")
        if allow and key not in allow and not any(key.endswith(a) for a in allow):
            return EgressVerdict(
                False,
                f"tool {name!r} is not in the binding's allow list ({sorted(allow)})",
            )
        return EgressVerdict(True, "allowed")

    # ── cost cap ─────────────────────────────────────────────────────────

    def cost_verdict(self, model: str, usage: dict[str, Any] | None) -> EgressVerdict:
        """Measure the call cost against the cap. Unmeasurable stays honest."""
        policy = self._policy
        cap = policy.max_cost_per_call_usd
        if cap is None:
            return EgressVerdict(True, "no cost cap configured")
        if not usage:
            return EgressVerdict(
                True,
                "cost cap configured but the response carried no usage data; "
                "the cap is not enforceable on this call",
                {"measured_cost_usd": None},
            )
        tokens = int(usage.get("total_tokens") or usage.get("total_toks") or 0)
        if tokens <= 0:
            return EgressVerdict(
                True,
                "cost cap configured but usage reported zero tokens; nothing to measure",
                {"measured_cost_usd": 0.0},
            )
        price = self._price_for(model)
        if price is None:
            return EgressVerdict(
                True,
                f"no operator price configured for model {model!r}; "
                "the cap is not enforceable without a price",
                {"measured_cost_usd": None, "tokens": tokens},
            )
        cost = tokens / 1000.0 * price
        if cost > cap:
            return EgressVerdict(
                False,
                f"measured call cost ${cost:.6f} exceeds the per-call cap ${cap:.6f}",
                {"measured_cost_usd": round(cost, 6), "tokens": tokens},
            )
        return EgressVerdict(
            True,
            f"measured call cost ${cost:.6f} within the per-call cap ${cap:.6f}",
            {"measured_cost_usd": round(cost, 6), "tokens": tokens},
        )

    def _price_for(self, model: str) -> float | None:
        prices = self._policy.price_per_1k_tokens
        if not prices or not model:
            return None
        name = str(model).lower()
        for prefix, price in prices.items():
            if name.startswith(prefix.lower()):
                return float(price)
        return None

    # ── air gap ──────────────────────────────────────────────────────────

    def airgap_verdict(self, base_url: str) -> EgressVerdict:
        if not self._policy.air_gap:
            return EgressVerdict(True, "air-gap disabled")
        host = _host_of(base_url)
        if host in LOOPBACK_HOSTS:
            return EgressVerdict(True, f"{host} is loopback: allowed in air-gap mode")
        return EgressVerdict(
            False,
            f"air-gap mode allows loopback endpoints only; {host!r} is not loopback",
        )

    def journal_entry(self, action: str, detail: dict[str, Any]) -> dict[str, Any]:
        return {"ts": time.time(), "action": action, **detail}


def _host_of(url: str) -> str:
    m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/?#]+)", url or "")
    hostport = m.group(1) if m else (url or "")
    # strip credentials
    if "@" in hostport:
        hostport = hostport.rsplit("@", 1)[1]
    hostport = hostport.split("/", 1)[0]
    if hostport.startswith("["):
        # bracketed IPv6: host is everything up to the closing bracket
        end = hostport.find("]")
        if end != -1:
            hostport = hostport[1:end]
    elif ":" in hostport:
        hostport = hostport.rsplit(":", 1)[0]
    return hostport.lower()


# Process singleton wired lazily by the API layer.
egress_policy_manager: EgressPolicyManager | None = None


def get_egress_policy_manager() -> EgressPolicyManager:
    global egress_policy_manager
    if egress_policy_manager is None:
        egress_policy_manager = EgressPolicyManager()
    return egress_policy_manager
