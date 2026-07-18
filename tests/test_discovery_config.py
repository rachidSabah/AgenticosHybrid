"""Tests for agentic_os.core.discovery.config.DiscoveryConfiguration."""

from agentic_os.core.discovery.config import DiscoveryConfiguration
from agentic_os.domain.discovery import DiscoveryProfile, DiscoveryProviderConfig, DiscoveryRule


class TestDiscoveryConfiguration:
    def test_defaults(self) -> None:
        config = DiscoveryConfiguration()
        assert config.enabled is True
        assert config.default_profile == "default"
        assert config.cache_ttl_seconds == 300.0
        assert config.max_cache_entries == 1000
        assert config.telemetry_max_entries == 1000
        assert config.profiles == {}
        assert config.rules == []

    def test_add_and_get_profile(self) -> None:
        config = DiscoveryConfiguration()
        profile = DiscoveryProfile(name="full")
        config.add_profile(profile)
        retrieved = config.get_profile("full")
        assert retrieved is not None
        assert retrieved.name == "full"

    def test_add_profile_overwrites_duplicate(self) -> None:
        config = DiscoveryConfiguration()
        p1 = DiscoveryProfile(name="test", description="first")
        p2 = DiscoveryProfile(name="test", description="second")
        config.add_profile(p1)
        config.add_profile(p2)
        retrieved = config.get_profile("test")
        assert retrieved is not None
        assert retrieved.description == "second"

    def test_remove_profile_returns_true(self) -> None:
        config = DiscoveryConfiguration()
        config.add_profile(DiscoveryProfile(name="full"))
        result = config.remove_profile("full")
        assert result is True
        assert config.get_profile("full") is None

    def test_remove_profile_returns_false_for_unknown(self) -> None:
        config = DiscoveryConfiguration()
        result = config.remove_profile("nonexistent")
        assert result is False

    def test_get_profile_returns_none_for_unknown(self) -> None:
        config = DiscoveryConfiguration()
        retrieved = config.get_profile("nonexistent")
        assert retrieved is None

    def test_list_profiles(self) -> None:
        config = DiscoveryConfiguration()
        config.add_profile(DiscoveryProfile(name="full"))
        config.add_profile(DiscoveryProfile(name="quick"))
        profiles = config.list_profiles()
        assert len(profiles) == 2
        names = {p["name"] for p in profiles}
        assert names == {"full", "quick"}

    def test_get_active_profiles(self) -> None:
        config = DiscoveryConfiguration()
        enabled_cfg = DiscoveryProviderConfig(name="p1", provider_type="path", enabled=True)
        disabled_cfg = DiscoveryProviderConfig(name="p2", provider_type="env", enabled=False)
        active_profile = DiscoveryProfile(name="active", provider_configs=(enabled_cfg,))
        inactive_profile = DiscoveryProfile(name="inactive", provider_configs=(disabled_cfg,))
        config.add_profile(active_profile)
        config.add_profile(inactive_profile)
        active = config.get_active_profiles()
        assert len(active) == 1
        assert active[0].name == "active"

    def test_get_active_profiles_empty_when_all_disabled(self) -> None:
        config = DiscoveryConfiguration()
        disabled_cfg = DiscoveryProviderConfig(name="p1", provider_type="path", enabled=False)
        profile = DiscoveryProfile(name="all_disabled", provider_configs=(disabled_cfg,))
        config.add_profile(profile)
        assert config.get_active_profiles() == []

    def test_add_and_get_rules(self) -> None:
        config = DiscoveryConfiguration()
        rule = DiscoveryRule(field="version", operator="gte", value="1.0")
        config.add_rule(rule)
        rules = config.get_rules()
        assert len(rules) == 1
        assert rules[0].field == "version"

    def test_add_multiple_rules(self) -> None:
        config = DiscoveryConfiguration()
        config.add_rule(DiscoveryRule(field="version", operator="gte", value="1.0"))
        config.add_rule(DiscoveryRule(field="version", operator="lt", value="3.0"))
        assert len(config.get_rules()) == 2

    def test_get_rules_filtered_by_action(self) -> None:
        config = DiscoveryConfiguration()
        config.add_rule(DiscoveryRule(field="v", operator="eq", value="1.0", action="accept"))
        config.add_rule(DiscoveryRule(field="v", operator="eq", value="bug", action="reject"))
        config.add_rule(DiscoveryRule(field="v", operator="eq", value="2.0", action="accept"))
        accept_rules = config.get_rules(action="accept")
        reject_rules = config.get_rules(action="reject")
        assert len(accept_rules) == 2
        assert len(reject_rules) == 1
        assert reject_rules[0].value == "bug"

    def test_remove_rule_by_index(self) -> None:
        config = DiscoveryConfiguration()
        config.add_rule(DiscoveryRule(field="v1", operator="eq", value="1.0"))
        config.add_rule(DiscoveryRule(field="v2", operator="eq", value="2.0"))
        result = config.remove_rule(0)
        assert result is True
        assert len(config.get_rules()) == 1
        assert config.get_rules()[0].field == "v2"

    def test_remove_rule_out_of_bounds(self) -> None:
        config = DiscoveryConfiguration()
        result = config.remove_rule(0)
        assert result is False
        result = config.remove_rule(-1)
        assert result is False
        result = config.remove_rule(42)
        assert result is False

    def test_clear_rules(self) -> None:
        config = DiscoveryConfiguration()
        config.add_rule(DiscoveryRule(field="v", operator="eq", value="1.0"))
        config.add_rule(DiscoveryRule(field="v", operator="eq", value="2.0"))
        config.clear_rules()
        assert config.rules == []

    def test_to_dict(self) -> None:
        config = DiscoveryConfiguration(enabled=False)
        config.add_profile(DiscoveryProfile(name="quick"))
        config.add_rule(DiscoveryRule(field="version", operator="gte", value="1.0"))
        d = config.to_dict()
        assert d["enabled"] is False
        assert d["default_profile"] == "default"
        assert len(d["profiles"]) == 1
        assert d["profiles"][0]["name"] == "quick"
        assert len(d["rules"]) == 1
        assert d["rules"][0]["field"] == "version"
