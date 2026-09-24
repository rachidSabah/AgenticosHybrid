"""Egress policy — real redaction, tool rules, cost caps, air-gap.

Patterns are tested against real secret/PII fixtures; Luhn is exercised
with a genuinely valid card number (4111 1111 1111 1111) and a genuinely
invalid one; air-gap verdicts are tested on real URLs.
"""

from __future__ import annotations

import pytest

from agentic_os.core.security.egress_policy import (
    EgressPolicyManager,
    PolicyViolation,
)


@pytest.fixture
def mgr(tmp_path):
    return EgressPolicyManager(policy_file=str(tmp_path / "egress.json"))


SECRETS_SAMPLE = (
    "use this key sk-abcdef1234567890abcdef and the github token "
    "ghp_0123456789abcdef0123456789abcdef0123 plus AWS AKIAIOSFODNN7EXAMPLE, "
    "API_KEY=supersecret99, and Authorization: Bearer abc.def.ghi1234567890"
)

PII_SAMPLE = (
    "contact jane.doe@example.com or +1 (555) 123-4567, "
    "SSN 123-45-6789, card 4111 1111 1111 1111, "
    "and the fake card 1111 1111 1111 1112 which must survive"
)


# ── secret redaction ─────────────────────────────────────────────────────────


def test_secrets_are_redacted_with_honest_markers(mgr):
    out = mgr.redact_text(SECRETS_SAMPLE)
    assert "sk-abcdef1234567890abcdef" not in out
    assert "ghp_0123456789" not in out
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "supersecret99" not in out
    assert "[REDACTED:openai-key]" in out
    assert "[REDACTED:github-token]" in out
    assert "[REDACTED:aws-access-key]" in out


def test_pem_private_key_block_is_redacted(mgr):
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nmore\n-----END RSA PRIVATE KEY-----\ndone"
    out = mgr.redact_text(text)
    assert "MIIEow" not in out
    assert "[REDACTED:private-key-block]" in out
    assert "done" in out


def test_redaction_report_counts_every_class(mgr):
    report = mgr.inspect(SECRETS_SAMPLE)
    assert report["replacements"] >= 5
    assert report["by_class"]["openai-key"] == 1
    assert report["by_class"]["github-token"] == 1
    assert report["by_class"]["aws-access-key"] == 1


# ── PII redaction ────────────────────────────────────────────────────────────


def test_pii_redacted_and_luhn_filters_fake_cards(mgr):
    out = mgr.redact_text(PII_SAMPLE)
    assert "[REDACTED:email]" in out
    assert "jane.doe@example.com" not in out
    assert "[REDACTED:ssn]" in out
    assert "[REDACTED:card-number]" in out
    # Luhn-invalid card must survive: redaction never invents findings
    assert "1111 1111 1111 1112" in out


def test_pii_can_be_disabled(mgr):
    mgr.update(redact_pii=False)
    out = mgr.redact_text("mail me at jane.doe@example.com")
    assert "jane.doe@example.com" in out


def test_custom_regexes_are_applied_and_validated(mgr):
    mgr.update(custom_redactions={"project-codename": r"\bProject\s+Bluebird\b"})
    out = mgr.redact_text("we shipped Project Bluebird yesterday")
    assert "Bluebird" not in out
    assert "[REDACTED:project-codename]" in out
    with pytest.raises(PolicyViolation):
        mgr.update(custom_redactions={"bad": r"([unclosed"})


def test_redact_payload_walks_nested_json(mgr):
    payload = {
        "messages": [
            {"role": "user", "content": "token ghp_0123456789abcdef0123456789abcdef0123"},
        ],
        "meta": ["a@b.com"],
    }
    out = mgr.redact_payload(payload)
    assert "ghp_0123456789" not in out["messages"][0]["content"]
    assert out["meta"] == ["[REDACTED:email]"]


# ── tool rules ───────────────────────────────────────────────────────────────


def test_deny_wins_and_allow_list_gates(mgr):
    mgr.update(tools_deny=["terminal"])
    assert mgr.tool_verdict("mcplocal/terminal").allowed is False
    assert mgr.tool_verdict("filesystem/read").allowed is True
    mgr.update(tools_deny=[], tools_allow=["filesystem/read"])
    assert mgr.tool_verdict("filesystem/read").allowed is True
    assert mgr.tool_verdict("filesystem/write").allowed is False


def test_tool_verdict_reasons_are_explicit(mgr):
    mgr.update(tools_deny=["terminal"])
    v = mgr.tool_verdict("mcplocal/terminal")
    assert v.allowed is False
    assert "denied" in v.reason


# ── cost cap ─────────────────────────────────────────────────────────────────


def test_cost_cap_enforced_with_operator_price(mgr):
    mgr.update(max_cost_per_call_usd=0.01, price_per_1k_tokens={"gpt-": 0.002})
    # 10000 tokens * $0.002/1k = $0.02 > $0.01 cap
    v = mgr.cost_verdict("gpt-4o", {"total_tokens": 10000})
    assert v.allowed is False
    assert "exceeds" in v.reason
    # 2000 tokens -> $0.004 within cap
    v2 = mgr.cost_verdict("gpt-4o", {"total_tokens": 2000})
    assert v2.allowed is True


def test_cost_cap_honest_when_unmeasurable(mgr):
    mgr.update(max_cost_per_call_usd=0.01)
    v_missing_price = mgr.cost_verdict("unknown-model", {"total_tokens": 999999})
    assert v_missing_price.allowed is True
    assert "no operator price" in v_missing_price.reason
    v_no_usage = mgr.cost_verdict("gpt-4o", None)
    assert v_no_usage.allowed is True
    assert "no usage data" in v_no_usage.reason
    v2 = mgr.cost_verdict("gpt-4o", {})  # no cap... wait cap set above? recreated mgr
    # mgr was updated above; still capped, empty usage -> zero tokens honest pass
    assert v2.allowed is True


# ── air gap ──────────────────────────────────────────────────────────────────


def test_airgap_blocks_non_loopback_and_allows_localhost(mgr):
    assert mgr.airgap_verdict("http://api.openai.com/v1").allowed is True  # air-gap off
    mgr.update(air_gap=True)
    v_bad = mgr.airgap_verdict("http://api.openai.com/v1")
    assert v_bad.allowed is False
    assert "loopback" in v_bad.reason
    for ok_url in (
        "http://127.0.0.1:8000/v1",
        "http://localhost:11434/v1",
        "http://[::1]:8000/v1",
    ):
        assert mgr.airgap_verdict(ok_url).allowed is True, ok_url


def test_host_extraction_handles_credentials_and_ports():
    from agentic_os.core.security.egress_policy import _host_of

    assert _host_of("http://user:pass@Example.com:8080/v1") == "example.com"
    assert _host_of("https://127.0.0.1:9000") == "127.0.0.1"
    assert _host_of("http://[::1]:8000/v1") == "::1"


# ── persistence ──────────────────────────────────────────────────────────────


def test_policy_persists_across_instances(tmp_path):
    f = str(tmp_path / "p.json")
    m1 = EgressPolicyManager(policy_file=f)
    m1.update(air_gap=True, tools_deny=["terminal"], max_cost_per_call_usd=0.5)
    m2 = EgressPolicyManager(policy_file=f)
    policy = m2.get_policy()
    assert policy.air_gap is True
    assert policy.tools_deny == ["terminal"]
    assert policy.max_cost_per_call_usd == 0.5
