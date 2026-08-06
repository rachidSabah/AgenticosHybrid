"""Tests for the provider execution strategy framework.

Verifies:
  - Each strategy builds the correct CLI command
  - ProviderFactory creates the correct adapter
  - Strategies handle stdin vs arg correctly
  - Timeouts are per-strategy
  - Health commands are non-interactive
"""

from __future__ import annotations

from agentic_os.adapters.providers.strategies import (
    AGYExecutionStrategy,
    AiderExecutionStrategy,
    ClaudeExecutionStrategy,
    CodexExecutionStrategy,
    GeminiExecutionStrategy,
    GenericExecutionStrategy,
    HermesExecutionStrategy,
    OllamaExecutionStrategy,
    OpenCodeExecutionStrategy,
    ProviderExecutionStrategy,
    ProviderFactory,
    get_strategy,
    register_strategy,
)
from agentic_os.domain.agent import Task


def make_task(title: str = "Test", description: str = "Write hello world") -> Task:
    return Task(title=title, role="coding", description=description)


# ── Strategy Command Building ──────────────────────────────────────────


class TestStrategyCommands:
    def test_claude_builds_correct_command(self):
        s = ClaudeExecutionStrategy()
        cmd = s.build_command(make_task(), "claude")
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "--output-format" in cmd
        assert "text" in cmd
        # Prompt must be in stdin, not argv (avoids cmd.exe 8191-char limit)
        stdin = s.build_stdin(make_task())
        assert stdin is not None
        assert b"Write hello world" in stdin

    def test_hermes_builds_correct_command(self):
        s = HermesExecutionStrategy()
        cmd = s.build_command(make_task(), "hermes")
        assert cmd[0] == "hermes"
        assert "-z" in cmd
        # hermes has NO --output-format flag (exit 2 if passed)
        assert "--output-format" not in cmd
        # Prompt is passed as -z argument (not stdin)
        assert any("Write hello world" in c for c in cmd)

    def test_opencode_uses_run_subcommand(self):
        s = OpenCodeExecutionStrategy()
        cmd = s.build_command(make_task(), "opencode")
        assert cmd[0] == "opencode"
        assert "run" in cmd
        # opencode reads prompt from stdin via "-"
        assert "-" in cmd
        stdin = s.build_stdin(make_task())
        assert stdin is not None
        assert b"Write hello world" in stdin

    def test_codex_uses_prompt_flag(self):
        s = CodexExecutionStrategy()
        cmd = s.build_command(make_task(), "codex")
        assert cmd[0] == "codex"
        assert "--prompt" in cmd

    def test_aider_uses_message_flag(self):
        s = AiderExecutionStrategy()
        cmd = s.build_command(make_task(), "aider")
        assert cmd[0] == "aider"
        assert "--message" in cmd
        assert "--no-auto-commits" in cmd

    def test_gemini_uses_p_flag(self):
        s = GeminiExecutionStrategy()
        cmd = s.build_command(make_task(), "gemini")
        assert cmd[0] == "gemini"
        assert "-p" in cmd
        assert "--output-format" in cmd
        assert "text" in cmd
        # Gemini reads prompt from stdin when -p has empty value
        stdin = s.build_stdin(make_task())
        assert stdin is not None
        assert b"Write hello world" in stdin

    def test_agy_uses_run_subcommand(self):
        s = AGYExecutionStrategy()
        cmd = s.build_command(make_task(), "agy")
        assert cmd[0] == "agy"
        assert "run" in cmd

    def test_ollama_uses_run_with_model_and_stdin(self):
        s = OllamaExecutionStrategy()
        cmd = s.build_command(make_task(), "ollama")
        assert cmd[0] == "ollama"
        assert "run" in cmd
        assert "llama3" in cmd
        # Ollama reads prompt from stdin
        stdin = s.build_stdin(make_task())
        assert stdin is not None
        assert b"Write hello world" in stdin

    def test_generic_uses_stdin(self):
        s = GenericExecutionStrategy(kind="unknown")
        cmd = s.build_command(make_task(), "some-binary")
        assert cmd == ["some-binary"]
        stdin = s.build_stdin(make_task())
        assert stdin is not None
        assert b"Write hello world" in stdin


# ── Strategy Properties ────────────────────────────────────────────────


class TestStrategyProperties:
    def test_claude_kind(self):
        assert ClaudeExecutionStrategy().kind == "claude_code"

    def test_hermes_kind(self):
        assert HermesExecutionStrategy().kind == "hermes"

    def test_opencode_kind(self):
        assert OpenCodeExecutionStrategy().kind == "opencode"

    def test_aider_has_longer_timeout(self):
        assert AiderExecutionStrategy().timeout_s == 180.0

    def test_gemini_has_longer_timeout(self):
        assert GeminiExecutionStrategy().timeout_s == 180.0

    def test_ollama_has_longest_timeout(self):
        assert OllamaExecutionStrategy().timeout_s == 300.0

    def test_default_timeout_is_120(self):
        assert ClaudeExecutionStrategy().timeout_s == 120.0

    def test_hermes_has_extended_timeout(self):
        """Hermes runs with workspace context + tool calls routinely exceed 120s."""
        assert HermesExecutionStrategy().timeout_s == 600.0

    def test_all_strategies_support_streaming(self):
        for cls in [
            ClaudeExecutionStrategy,
            HermesExecutionStrategy,
            OpenCodeExecutionStrategy,
            CodexExecutionStrategy,
            AiderExecutionStrategy,
            GeminiExecutionStrategy,
            AGYExecutionStrategy,
            OllamaExecutionStrategy,
            GenericExecutionStrategy,
        ]:
            assert cls().supports_streaming is True


# ── Health Commands ────────────────────────────────────────────────────


class TestHealthCommands:
    def test_claude_health_uses_version(self):
        cmd = ClaudeExecutionStrategy().health_command("claude")
        assert cmd == ["claude", "--version"]

    def test_hermes_health_uses_help(self):
        """Hermes CLI --version performs a network update check — must use --help."""
        cmd = HermesExecutionStrategy().health_command("hermes")
        assert cmd == ["hermes", "--help"]

    def test_gemini_health_uses_version(self):
        """Gemini CLI --help can trigger interactive auth flow — must use --version."""
        cmd = GeminiExecutionStrategy().health_command("gemini")
        assert cmd == ["gemini", "--version"]

    def test_ollama_health_uses_list(self):
        cmd = OllamaExecutionStrategy().health_command("ollama")
        assert cmd == ["ollama", "list"]

    def test_generic_health_returns_none(self):
        """Generic strategy has no health command — uses shutil.which only."""
        cmd = GenericExecutionStrategy().health_command("some-binary")
        assert cmd is None


# ── Factory ────────────────────────────────────────────────────────────


class TestProviderFactory:
    def test_create_claude_code(self):
        adapter = ProviderFactory.create("claude_code", "claude", name="test")
        assert adapter.info.kind == "claude_code"
        assert isinstance(adapter.strategy, ClaudeExecutionStrategy)

    def test_create_hermes(self):
        adapter = ProviderFactory.create("hermes", "hermes", name="test")
        assert adapter.info.kind == "hermes"
        assert isinstance(adapter.strategy, HermesExecutionStrategy)

    def test_create_opencode(self):
        adapter = ProviderFactory.create("opencode", "opencode", name="test")
        assert isinstance(adapter.strategy, OpenCodeExecutionStrategy)

    def test_create_gemini(self):
        adapter = ProviderFactory.create("gemini_cli", "gemini", name="test")
        assert isinstance(adapter.strategy, GeminiExecutionStrategy)

    def test_create_unknown_kind_uses_generic(self):
        adapter = ProviderFactory.create("unknown_kind", "some-bin", name="test")
        assert isinstance(adapter.strategy, GenericExecutionStrategy)
        assert adapter.strategy.kind == "unknown_kind"

    def test_supported_kinds_includes_all(self):
        kinds = ProviderFactory.supported_kinds()
        for expected in [
            "claude_code",
            "hermes",
            "opencode",
            "codex",
            "aider",
            "gemini_cli",
            "antigravity",
            "ollama",
        ]:
            assert expected in kinds

    def test_is_supported(self):
        assert ProviderFactory.is_supported("claude_code") is True
        assert ProviderFactory.is_supported("unknown") is False

    def test_register_custom_strategy(self):
        class CustomStrategy(ProviderExecutionStrategy):
            @property
            def kind(self) -> str:
                return "custom"

            def build_command(self, task: Task, bin_path: str) -> list[str]:
                return [bin_path, "custom-flag"]

        register_strategy("custom", CustomStrategy)
        adapter = ProviderFactory.create("custom", "my-cli", name="test")
        assert isinstance(adapter.strategy, CustomStrategy)
        cmd = adapter.strategy.build_command(make_task(), "my-cli")
        assert "custom-flag" in cmd


# ── Prompt Building ────────────────────────────────────────────────────


class TestPromptBuilding:
    def test_prompt_includes_title_and_description(self):
        s = ClaudeExecutionStrategy()
        task = Task(title="My Title", role="coding", description="My Description")
        prompt = s.build_prompt(task)
        assert "My Title" in prompt
        assert "My Description" in prompt

    def test_prompt_strips_whitespace(self):
        s = GenericExecutionStrategy()
        task = Task(title="  Title  ", role="coding", description="  Desc  ")
        prompt = s.build_prompt(task)
        assert prompt.startswith("Title")
        assert prompt.endswith("Desc")

    def test_prompt_survives_in_command(self):
        """The prompt must appear in build_stdin for stdin-based CLIs.

        For CLIs that read from stdin (claude, opencode, gemini), the prompt
        is NOT in the argv — it's sent via build_stdin to avoid the Windows
        cmd.exe 8191-char command line limit.
        """
        s = ClaudeExecutionStrategy()
        task = Task(title="Write hello", role="coding", description="in Python")
        stdin = s.build_stdin(task)
        assert stdin is not None
        assert b"Write hello" in stdin
        assert b"in Python" in stdin


# ── Output Parsing ─────────────────────────────────────────────────────


class TestOutputParsing:
    def test_default_parse_decodes_stdout(self):
        s = ClaudeExecutionStrategy()
        result = s.parse_output(b"Hello World", b"", make_task())
        assert result == "Hello World"

    def test_default_parse_handles_utf8_errors(self):
        s = GenericExecutionStrategy()
        result = s.parse_output(b"\xff\xfe invalid", b"", make_task())
        # Should not crash — errors='replace'
        assert isinstance(result, str)

    def test_ollama_parse_extracts_stdout_only(self):
        s = OllamaExecutionStrategy()
        result = s.parse_output(b"Result", b"Loading model...", make_task())
        assert result == "Result"


# ── Environment Building ───────────────────────────────────────────────


class TestEnvBuilding:
    def test_claude_sets_anthropic_api_key(self):
        s = ClaudeExecutionStrategy()
        env = s.build_env("sk-test-key")
        assert env["ANTHROPIC_API_KEY"] == "sk-test-key"

    def test_hermes_sets_hermes_config(self):
        s = HermesExecutionStrategy()
        env = s.build_env("config-path")
        assert env["HERMES_CONFIG"] == "config-path"

    def test_generic_does_not_set_api_key(self):
        s = GenericExecutionStrategy()
        env = s.build_env("some-key")
        assert "ANTHROPIC_API_KEY" not in env

    def test_env_preserves_os_environ(self):
        s = ClaudeExecutionStrategy()
        env = s.build_env("")
        # Must contain PATH (or equivalent)
        assert "PATH" in env or "Path" in env


# ── Strategy Registry ──────────────────────────────────────────────────


class TestStrategyRegistry:
    def test_get_strategy_returns_correct_class(self):
        assert isinstance(get_strategy("claude_code"), ClaudeExecutionStrategy)
        assert isinstance(get_strategy("hermes"), HermesExecutionStrategy)
        assert isinstance(get_strategy("opencode"), OpenCodeExecutionStrategy)
        assert isinstance(get_strategy("gemini_cli"), GeminiExecutionStrategy)
        assert isinstance(get_strategy("ollama"), OllamaExecutionStrategy)

    def test_get_strategy_falls_back_to_generic(self):
        s = get_strategy("nonexistent")
        assert isinstance(s, GenericExecutionStrategy)
        assert s.kind == "nonexistent"


# ── Integration: Full Adapter ──────────────────────────────────────────


class TestStrategyBasedProvider:
    def test_adapter_has_correct_info(self):
        adapter = ProviderFactory.create(
            kind="claude_code",
            bin_path="claude",
            name="test_claude",
            display_name="Claude Code",
            capabilities=["coding"],
        )
        assert adapter.info.name == "test_claude"
        assert adapter.info.kind == "claude_code"
        assert adapter.info.supports_streaming is True

    def test_adapter_strategy_is_correct(self):
        adapter = ProviderFactory.create("gemini_cli", "gemini")
        assert isinstance(adapter.strategy, GeminiExecutionStrategy)
        assert adapter.strategy.timeout_s == 180.0

    def test_adapter_builds_correct_env(self):
        adapter = ProviderFactory.create("claude_code", "claude", api_key="sk-test")
        env = adapter.strategy.build_env("sk-test")
        assert env["ANTHROPIC_API_KEY"] == "sk-test"
