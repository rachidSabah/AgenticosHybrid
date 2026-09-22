"""Tests for CLI argument construction.

These encode the invocation contract verified against Codex v0.153.2 —
getting these wrong is why prompts produced markdown instead of files.
"""

from __future__ import annotations

from agentic_os.adapters.providers.generic_cli import build_codex_args, is_codex


def test_is_codex_detects_codex_binary():
    assert is_codex("codex")
    assert is_codex("C:\\path\\to\\codex.EXE")
    assert is_codex("codex.exe")
    assert is_codex("/usr/local/bin/codex")
    assert is_codex("/opt/codex")


def test_is_codex_rejects_others():
    assert not is_codex("claude")
    assert not is_codex("opencode")


def test_codex_args_use_exec_subcommand():
    args = build_codex_args("codex", "do the thing")
    assert args[1] == "exec"


def test_codex_args_enable_file_writes():
    """Without workspace-write Codex cannot create files."""
    args = build_codex_args("codex", "x")
    assert "-s" in args
    assert "workspace-write" in args


def test_codex_args_skip_git_repo_check():
    """Non-git workspaces otherwise abort before doing any work."""
    assert "--skip-git-repo-check" in build_codex_args("codex", "x")


def test_prompt_is_last_positional_arg():
    """Prompt must be argv, not stdin — stdin makes Codex block."""
    prompt = "create index.html"
    args = build_codex_args("codex", prompt)
    assert args[-1] == prompt


def test_full_arg_shape():
    expected = ["codex", "exec", "-s", "workspace-write", "--skip-git-repo-check", "hello"]
    assert build_codex_args("codex", "hello") == expected
