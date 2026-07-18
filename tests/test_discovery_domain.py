"""Tests for agentic_os.domain.discovery domain models."""

from datetime import UTC, datetime, timedelta

import pytest

from agentic_os.domain.discovery import (
    DiscoveryCacheEntry,
    DiscoveryProfile,
    DiscoveryProviderConfig,
    DiscoveryRule,
    DiscoveryTelemetryEntry,
    ProfileResult,
    ValidationResult,
)

# ── DiscoveryProviderConfig ──


class TestDiscoveryProviderConfig:
    def test_defaults(self) -> None:
        config = DiscoveryProviderConfig(name="test", provider_type="path")
        assert config.name == "test"
        assert config.provider_type == "path"
        assert config.enabled is True
        assert config.interval_seconds == 60.0
        assert config.timeout_seconds == 10.0
        assert config.confidence_override is None
        assert config.extra == {}

    def test_extra_default_factory_empty(self) -> None:
        a = DiscoveryProviderConfig(name="a", provider_type="t")
        b = DiscoveryProviderConfig(name="b", provider_type="t")
        # Each instance should have its own extra dict (not shared)
        assert a.extra is not b.extra
        assert a.extra == {}
        assert b.extra == {}

    def test_custom_values(self) -> None:
        config = DiscoveryProviderConfig(
            name="nim",
            provider_type="nvidia_nim",
            enabled=False,
            interval_seconds=120.0,
            timeout_seconds=30.0,
            confidence_override=0.9,
            extra={"endpoint": "http://localhost:8000"},
        )
        assert config.name == "nim"
        assert config.provider_type == "nvidia_nim"
        assert config.enabled is False
        assert config.interval_seconds == 120.0
        assert config.timeout_seconds == 30.0
        assert config.confidence_override == 0.9
        assert config.extra == {"endpoint": "http://localhost:8000"}

    def test_with_enabled_returns_new_instance(self) -> None:
        config = DiscoveryProviderConfig(name="test", provider_type="path")
        disabled = config.with_enabled(False)
        assert disabled.enabled is False
        # original unchanged (frozen)
        assert config.enabled is True
        assert disabled.name == config.name
        assert disabled.provider_type == config.provider_type

    def test_with_enabled_default_arg(self) -> None:
        config = DiscoveryProviderConfig(name="test", provider_type="path", enabled=False)
        re_enabled = config.with_enabled()
        assert re_enabled.enabled is True

    def test_with_interval_returns_new_instance(self) -> None:
        config = DiscoveryProviderConfig(name="test", provider_type="path")
        changed = config.with_interval(300.0)
        assert changed.interval_seconds == 300.0
        assert config.interval_seconds == 60.0  # original unchanged
        assert changed.name == config.name
        assert changed.enabled == config.enabled

    def test_with_interval_zero(self) -> None:
        config = DiscoveryProviderConfig(name="test", provider_type="path")
        changed = config.with_interval(0.0)
        assert changed.interval_seconds == 0.0

    def test_to_dict(self) -> None:
        config = DiscoveryProviderConfig(
            name="test",
            provider_type="path",
            confidence_override=0.85,
            extra={"key": "value"},
        )
        d = config.to_dict()
        assert d["name"] == "test"
        assert d["provider_type"] == "path"
        assert d["enabled"] is True
        assert d["confidence_override"] == 0.85
        assert d["extra"] == {"key": "value"}
        # extra should be a plain dict copy, not the same object
        assert d["extra"] is not config.extra

    def test_to_dict_confidence_none(self) -> None:
        config = DiscoveryProviderConfig(name="test", provider_type="path")
        d = config.to_dict()
        assert d["confidence_override"] is None

    def test_frozen_prevents_mutation(self) -> None:
        config = DiscoveryProviderConfig(name="test", provider_type="path")
        with pytest.raises(AttributeError):
            config.name = "changed"  # type: ignore[misc]

    def test_confidence_override_zero(self) -> None:
        config = DiscoveryProviderConfig(name="test", provider_type="path", confidence_override=0.0)
        assert config.confidence_override == 0.0


# ── DiscoveryProfile ──


class TestDiscoveryProfile:
    def test_defaults(self) -> None:
        profile = DiscoveryProfile(name="full")
        assert profile.name == "full"
        assert profile.description == ""
        assert profile.provider_configs == ()
        assert profile.schedule_cron is None
        assert profile.interval_seconds == 60.0
        assert profile.validate_after_discovery is True
        assert profile.profile_after_discovery is True
        assert profile.auto_register is True
        assert profile.tags == ()

    def test_custom_values(self) -> None:
        configs = (DiscoveryProviderConfig(name="p1", provider_type="path"),)
        profile = DiscoveryProfile(
            name="quick",
            description="Quick scan",
            provider_configs=configs,
            schedule_cron="*/5 * * * *",
            interval_seconds=300.0,
            validate_after_discovery=False,
            profile_after_discovery=False,
            auto_register=False,
            tags=("fast", "lightweight"),
        )
        assert profile.name == "quick"
        assert profile.description == "Quick scan"
        assert len(profile.provider_configs) == 1
        assert profile.schedule_cron == "*/5 * * * *"
        assert profile.interval_seconds == 300.0
        assert profile.validate_after_discovery is False
        assert profile.profile_after_discovery is False
        assert profile.auto_register is False
        assert profile.tags == ("fast", "lightweight")

    def test_tags_empty_tuple(self) -> None:
        profile = DiscoveryProfile(name="test", tags=())
        assert profile.tags == ()

    def test_tags_default_factory_is_empty(self) -> None:
        a = DiscoveryProfile(name="a")
        assert a.tags == ()

    def test_with_provider_adds_new(self) -> None:
        profile = DiscoveryProfile(name="test")
        config = DiscoveryProviderConfig(name="p1", provider_type="path")
        updated = profile.with_provider(config)
        assert len(updated.provider_configs) == 1
        assert updated.provider_configs[0].name == "p1"
        # original unchanged
        assert profile.provider_configs == ()

    def test_with_provider_replaces_existing(self) -> None:
        config_orig = DiscoveryProviderConfig(name="p1", provider_type="path", enabled=True)
        profile = DiscoveryProfile(name="test", provider_configs=(config_orig,))
        config_new = DiscoveryProviderConfig(name="p1", provider_type="nim", enabled=False)
        updated = profile.with_provider(config_new)
        assert len(updated.provider_configs) == 1
        assert updated.provider_configs[0].provider_type == "nim"
        assert updated.provider_configs[0].enabled is False

    def test_with_provider_preserves_other_configs(self) -> None:
        c1 = DiscoveryProviderConfig(name="p1", provider_type="path")
        c2 = DiscoveryProviderConfig(name="p2", provider_type="env")
        profile = DiscoveryProfile(name="test", provider_configs=(c1, c2))
        c3 = DiscoveryProviderConfig(name="p3", provider_type="nim")
        updated = profile.with_provider(c3)
        assert len(updated.provider_configs) == 3

    def test_without_provider_removes_matching(self) -> None:
        c1 = DiscoveryProviderConfig(name="p1", provider_type="path")
        c2 = DiscoveryProviderConfig(name="p2", provider_type="env")
        profile = DiscoveryProfile(name="test", provider_configs=(c1, c2))
        updated = profile.without_provider("p1")
        assert len(updated.provider_configs) == 1
        assert updated.provider_configs[0].name == "p2"

    def test_without_provider_noop_if_not_found(self) -> None:
        profile = DiscoveryProfile(
            name="test",
            provider_configs=(DiscoveryProviderConfig(name="p1", provider_type="path"),),
        )
        updated = profile.without_provider("nonexistent")
        assert len(updated.provider_configs) == 1

    def test_with_schedule_updates_cron(self) -> None:
        profile = DiscoveryProfile(name="test")
        updated = profile.with_schedule(cron="0 * * * *")
        assert updated.schedule_cron == "0 * * * *"
        assert updated.interval_seconds == 60.0  # unchanged

    def test_with_schedule_updates_interval(self) -> None:
        profile = DiscoveryProfile(name="test")
        updated = profile.with_schedule(interval=120.0)
        assert updated.interval_seconds == 120.0
        assert updated.schedule_cron is None  # unchanged

    def test_with_schedule_both(self) -> None:
        profile = DiscoveryProfile(name="test")
        updated = profile.with_schedule(cron="*/10 * * * *", interval=600.0)
        assert updated.schedule_cron == "*/10 * * * *"
        assert updated.interval_seconds == 600.0

    def test_with_schedule_preserves_cron_when_not_specified(self) -> None:
        profile = DiscoveryProfile(name="test", schedule_cron="0 * * * *")
        updated = profile.with_schedule(interval=120.0)
        assert updated.schedule_cron == "0 * * * *"  # preserved
        assert updated.interval_seconds == 120.0

    def test_to_dict(self) -> None:
        config = DiscoveryProviderConfig(name="p1", provider_type="path")
        profile = DiscoveryProfile(
            name="test",
            description="desc",
            provider_configs=(config,),
            tags=("a", "b"),
        )
        d = profile.to_dict()
        assert d["name"] == "test"
        assert d["description"] == "desc"
        assert len(d["provider_configs"]) == 1
        assert d["provider_configs"][0]["name"] == "p1"
        assert d["tags"] == ["a", "b"]
        assert d["schedule_cron"] is None


# ── DiscoveryRule ──


class TestDiscoveryRule:
    def test_defaults(self) -> None:
        rule = DiscoveryRule(field="version", operator="eq", value="1.0")
        assert rule.field == "version"
        assert rule.operator == "eq"
        assert rule.value == "1.0"
        assert rule.action == "accept"

    def test_custom_action(self) -> None:
        rule = DiscoveryRule(field="version", operator="eq", value="1.0", action="reject")
        assert rule.action == "reject"

    def test_matches_eq(self) -> None:
        rule = DiscoveryRule(field="version", operator="eq", value="1.0")
        assert rule.matches({"version": "1.0"}) is True
        assert rule.matches({"version": "2.0"}) is False

    def test_matches_ne(self) -> None:
        rule = DiscoveryRule(field="version", operator="ne", value="1.0")
        assert rule.matches({"version": "2.0"}) is True
        assert rule.matches({"version": "1.0"}) is False

    def test_matches_gt(self) -> None:
        rule = DiscoveryRule(field="version", operator="gt", value="1.0")
        assert rule.matches({"version": "2.0"}) is True
        assert rule.matches({"version": "0.5"}) is False
        assert rule.matches({"version": "1.0"}) is False

    def test_matches_gte(self) -> None:
        rule = DiscoveryRule(field="version", operator="gte", value="1.0")
        assert rule.matches({"version": "1.0"}) is True
        assert rule.matches({"version": "2.0"}) is True
        assert rule.matches({"version": "0.5"}) is False

    def test_matches_lt(self) -> None:
        rule = DiscoveryRule(field="version", operator="lt", value="2.0")
        assert rule.matches({"version": "1.0"}) is True
        assert rule.matches({"version": "3.0"}) is False

    def test_matches_lte(self) -> None:
        rule = DiscoveryRule(field="version", operator="lte", value="2.0")
        assert rule.matches({"version": "2.0"}) is True
        assert rule.matches({"version": "1.0"}) is True
        assert rule.matches({"version": "3.0"}) is False

    def test_matches_in_with_list(self) -> None:
        rule = DiscoveryRule(field="engine_type", operator="in", value=["llm", "embedding"])
        assert rule.matches({"engine_type": "llm"}) is True
        assert rule.matches({"engine_type": "embedding"}) is True
        assert rule.matches({"engine_type": "reranker"}) is False

    def test_matches_in_with_tuple(self) -> None:
        rule = DiscoveryRule(field="engine_type", operator="in", value=("llm", "embedding"))
        assert rule.matches({"engine_type": "llm"}) is True
        assert rule.matches({"engine_type": "reranker"}) is False

    def test_matches_in_with_set(self) -> None:
        rule = DiscoveryRule(field="engine_type", operator="in", value={"llm", "embedding"})
        assert rule.matches({"engine_type": "embedding"}) is True

    def test_matches_in_fallback_scalar(self) -> None:
        rule = DiscoveryRule(field="version", operator="in", value="1.0")
        assert rule.matches({"version": "1.0"}) is True
        assert rule.matches({"version": "2.0"}) is False

    def test_matches_contains_string(self) -> None:
        rule = DiscoveryRule(field="name", operator="contains", value="gpt")
        assert rule.matches({"name": "gpt-4"}) is True
        assert rule.matches({"name": "claude"}) is False

    def test_matches_contains_list(self) -> None:
        rule = DiscoveryRule(field="capabilities", operator="contains", value="streaming")
        assert rule.matches({"capabilities": ["streaming", "tools"]}) is True
        assert rule.matches({"capabilities": ["tools"]}) is False

    def test_matches_contains_non_string_or_list(self) -> None:
        rule = DiscoveryRule(field="version", operator="contains", value="1")
        # version is a string, so it works
        assert rule.matches({"version": "1.0"}) is True

    def test_matches_matches_regex(self) -> None:
        rule = DiscoveryRule(field="version", operator="matches", value=r"^\d+\.\d+$")
        assert rule.matches({"version": "1.0"}) is True
        assert rule.matches({"version": "abc"}) is False

    def test_matches_unknown_operator_returns_false(self) -> None:
        rule = DiscoveryRule(field="version", operator="unknown", value="1.0")
        assert rule.matches({"version": "1.0"}) is False

    def test_matches_field_missing_returns_false(self) -> None:
        rule = DiscoveryRule(field="nonexistent", operator="eq", value="x")
        assert rule.matches({"version": "1.0"}) is False

    def test_matches_field_is_none_returns_false(self) -> None:
        rule = DiscoveryRule(field="version", operator="eq", value="1.0")
        assert rule.matches({"version": None}) is False

    def test_to_dict(self) -> None:
        rule = DiscoveryRule(field="version", operator="gte", value="1.0", action="reject")
        d = rule.to_dict()
        assert d["field"] == "version"
        assert d["operator"] == "gte"
        assert d["value"] == "1.0"
        assert d["action"] == "reject"


# ── DiscoveryCacheEntry ──


class TestDiscoveryCacheEntry:
    def test_defaults(self) -> None:
        now = datetime.now(UTC)
        expires = now + timedelta(minutes=5)
        entry = DiscoveryCacheEntry(
            key="k1",
            registration_json='{"name": "foo"}',
            confidence=0.85,
            provider_name="path",
            discovered_at=now,
            expires_at=expires,
        )
        assert entry.key == "k1"
        assert entry.hit_count == 0
        assert entry._version == 1

    def test_is_expired_future(self) -> None:
        now = datetime.now(UTC)
        expires = now + timedelta(hours=1)
        entry = DiscoveryCacheEntry(
            key="k1",
            registration_json="{}",
            confidence=0.5,
            provider_name="p",
            discovered_at=now,
            expires_at=expires,
        )
        assert entry.is_expired() is False

    def test_is_expired_past(self) -> None:
        now = datetime.now(UTC)
        expires = now - timedelta(seconds=1)
        entry = DiscoveryCacheEntry(
            key="k1",
            registration_json="{}",
            confidence=0.5,
            provider_name="p",
            discovered_at=now,
            expires_at=expires,
        )
        assert entry.is_expired() is True

    def test_with_hit_increments_count(self) -> None:
        now = datetime.now(UTC)
        expires = now + timedelta(minutes=5)
        entry = DiscoveryCacheEntry(
            key="k1",
            registration_json="{}",
            confidence=0.5,
            provider_name="p",
            discovered_at=now,
            expires_at=expires,
        )
        hit = entry.with_hit()
        assert hit.hit_count == 1
        assert entry.hit_count == 0  # original unchanged
        assert hit.key == entry.key

    def test_with_hit_multiple_times(self) -> None:
        now = datetime.now(UTC)
        expires = now + timedelta(minutes=5)
        entry = DiscoveryCacheEntry(
            key="k1",
            registration_json="{}",
            confidence=0.5,
            provider_name="p",
            discovered_at=now,
            expires_at=expires,
        )
        e1 = entry.with_hit()
        e2 = e1.with_hit()
        e3 = e2.with_hit()
        assert e3.hit_count == 3

    def test_to_dict(self) -> None:
        now = datetime.now(UTC)
        expires = now + timedelta(minutes=5)
        entry = DiscoveryCacheEntry(
            key="k1",
            registration_json="{}",
            confidence=0.9,
            provider_name="path",
            discovered_at=now,
            expires_at=expires,
            hit_count=3,
        )
        d = entry.to_dict()
        assert d["key"] == "k1"
        assert d["provider_name"] == "path"
        assert d["confidence"] == 0.9
        assert d["hit_count"] == 3
        assert d["expired"] is False
        assert d["discovered_at"] == now.isoformat()
        assert d["expires_at"] == expires.isoformat()


# ── DiscoveryTelemetryEntry ──


class TestDiscoveryTelemetryEntry:
    def test_defaults(self) -> None:
        entry = DiscoveryTelemetryEntry()
        assert entry.profile_name == "default"
        assert entry.completed_at is None
        assert entry.providers_run == 0
        assert entry.providers_failed == 0
        assert entry.engines_found == 0
        assert entry.engines_new == 0
        assert entry.engines_validated == 0
        assert entry.engines_registered == 0
        assert entry.errors == ()
        assert entry.id is not None

    def test_unique_ids(self) -> None:
        a = DiscoveryTelemetryEntry()
        b = DiscoveryTelemetryEntry()
        assert a.id != b.id

    def test_duration_zero_when_not_completed(self) -> None:
        entry = DiscoveryTelemetryEntry()
        assert entry.duration_ms == 0.0

    def test_duration_positive_when_completed(self) -> None:
        started = datetime.now(UTC) - timedelta(seconds=2)
        completed = datetime.now(UTC)
        entry = DiscoveryTelemetryEntry(
            id="e1",
            started_at=started,
            completed_at=completed,
        )
        duration = entry.duration_ms
        assert duration == pytest.approx(2000.0, abs=50.0)

    def test_with_completed_sets_completed_at(self) -> None:
        entry = DiscoveryTelemetryEntry()
        completed = entry.with_completed()
        assert completed.completed_at is not None
        assert completed.profile_name == entry.profile_name

    def test_with_completed_overrides_fields(self) -> None:
        entry = DiscoveryTelemetryEntry()
        completed = entry.with_completed(providers_run=3, engines_found=5)
        assert completed.providers_run == 3
        assert completed.engines_found == 5

    def test_with_completed_preserves_errors(self) -> None:
        entry = DiscoveryTelemetryEntry(errors=("timeout",))
        completed = entry.with_completed(errors=("timeout", "crash"))
        assert completed.errors == ("timeout", "crash")

    def test_to_dict_without_completion(self) -> None:
        entry = DiscoveryTelemetryEntry(id="t1", profile_name="quick", providers_run=2)
        d = entry.to_dict()
        assert d["id"] == "t1"
        assert d["profile_name"] == "quick"
        assert d["completed_at"] is None
        assert d["duration_ms"] == 0.0
        assert d["providers_run"] == 2

    def test_to_dict_with_completion(self) -> None:
        started = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        completed = datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC)
        entry = DiscoveryTelemetryEntry(
            id="t2",
            started_at=started,
            completed_at=completed,
            engines_found=10,
        )
        d = entry.to_dict()
        assert d["completed_at"] == completed.isoformat()
        assert d["duration_ms"] == 5000.0
        assert d["engines_found"] == 10


# ── ValidationResult ──


class TestValidationResult:
    def test_defaults(self) -> None:
        result = ValidationResult(engine_id="e1", engine_name="test", valid=True)
        assert result.engine_id == "e1"
        assert result.engine_name == "test"
        assert result.valid is True
        assert result.executable_exists is False
        assert result.version_detected is None
        assert result.health_check_passed is False
        assert result.capability_match is False
        assert result.permission_ok is True
        assert result.integrity_ok is True
        assert result.errors == ()
        assert result.warnings == ()

    def test_to_dict(self) -> None:
        result = ValidationResult(
            engine_id="e1",
            engine_name="test",
            valid=True,
            executable_exists=True,
            version_detected="1.0",
        )
        d = result.to_dict()
        assert d["engine_id"] == "e1"
        assert d["engine_name"] == "test"
        assert d["valid"] is True
        assert d["executable_exists"] is True
        assert d["version_detected"] == "1.0"
        assert d["errors"] == []
        assert d["warnings"] == []

    def test_passed_factory(self) -> None:
        result = ValidationResult.passed(engine_id="e1", engine_name="test")
        assert result.valid is True
        assert result.engine_id == "e1"
        assert result.engine_name == "test"

    def test_passed_factory_with_extra(self) -> None:
        result = ValidationResult.passed(
            engine_id="e1",
            engine_name="test",
            executable_exists=True,
            health_check_passed=True,
        )
        assert result.valid is True
        assert result.executable_exists is True
        assert result.health_check_passed is True

    def test_failed_factory(self) -> None:
        result = ValidationResult.failed("e1", "test", "executable not found", "permission denied")
        assert result.valid is False
        assert result.errors == ("executable not found", "permission denied")

    def test_failed_factory_with_extra(self) -> None:
        result = ValidationResult.failed(
            "e1",
            "test",
            "timeout",
            permission_ok=False,
            integrity_ok=False,
        )
        assert result.valid is False
        assert result.errors == ("timeout",)
        assert result.permission_ok is False
        assert result.integrity_ok is False

    def test_failed_factory_no_errors(self) -> None:
        result = ValidationResult.failed("e1", "test")
        assert result.valid is False
        assert result.errors == ()

    def test_frozen(self) -> None:
        result = ValidationResult(engine_id="e1", engine_name="test", valid=True)
        with pytest.raises(AttributeError):
            result.valid = False  # type: ignore[misc]


# ── ProfileResult ──


class TestProfileResult:
    def test_defaults(self) -> None:
        result = ProfileResult(
            engine_id="e1",
            engine_name="test",
            version="1.0",
            executable_path="/usr/bin/test",
            platform="linux",
        )
        assert result.engine_id == "e1"
        assert result.engine_name == "test"
        assert result.version == "1.0"
        assert result.executable_path == "/usr/bin/test"
        assert result.platform == "linux"
        assert result.capabilities == ()
        assert result.supports_streaming is False
        assert result.supports_mcp is False
        assert result.latency_estimate_ms == 0.0
        assert result.cost_estimate == 0.0
        assert result.resource_footprint_mb == 0.0
        assert result.config_defaults == {}

    def test_to_dict(self) -> None:
        result = ProfileResult(
            engine_id="e1",
            engine_name="test",
            version="1.0",
            executable_path="/usr/bin/test",
            platform="linux",
            capabilities=("streaming", "tools"),
            supports_streaming=True,
            latency_estimate_ms=150.0,
            config_defaults={"model": "gpt-4"},
        )
        d = result.to_dict()
        assert d["engine_id"] == "e1"
        assert d["engine_name"] == "test"
        assert d["version"] == "1.0"
        assert d["capabilities"] == ["streaming", "tools"]
        assert d["supports_streaming"] is True
        assert d["latency_estimate_ms"] == 150.0
        assert d["config_defaults"] == {"model": "gpt-4"}

    def test_from_registration_minimal(self) -> None:
        result = ProfileResult.from_registration(
            engine_id="e1",
            engine_name="test",
            version="1.0",
            executable_path="/usr/bin/test",
            capabilities=["streaming"],
        )
        assert result.engine_id == "e1"
        assert result.engine_name == "test"
        assert result.version == "1.0"
        assert result.executable_path == "/usr/bin/test"
        assert result.capabilities == ("streaming",)
        # platform is derived from the OS, just check it's a non-empty string
        assert isinstance(result.platform, str)
        assert len(result.platform) > 0

    def test_from_registration_with_platform_override(self) -> None:
        result = ProfileResult.from_registration(
            engine_id="e1",
            engine_name="test",
            version="1.0",
            executable_path="/usr/bin/test",
            capabilities=[],
            platform_name="darwin",
        )
        assert result.platform == "darwin"

    def test_from_registration_empty_capabilities(self) -> None:
        result = ProfileResult.from_registration(
            engine_id="e1",
            engine_name="test",
            version="1.0",
            executable_path="/usr/bin/test",
            capabilities=[],
            platform_name="linux",
        )
        assert result.capabilities == ()
