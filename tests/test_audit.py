"""Tests for Forensic Audit, Subsystem Benchmarks, OmniRoute Engine, and Kernel Daemon."""

from __future__ import annotations

import os

import pytest

from agentic_os.audit.benchmarks import (
    benchmark_ast_parsing,
    benchmark_event_loop_lag,
    benchmark_memory_footprint,
    benchmark_omniroute_speed,
    benchmark_sqlite_wal_contention,
    benchmark_subprocess_pipe_overhead,
    benchmark_worktree_isolation,
    run_all_micro_benchmarks,
)
from agentic_os.audit.blueprints import get_architectural_blueprints
from agentic_os.audit.bottlenecks import audit_subsystem_bottlenecks
from agentic_os.core.omniroute.engine import STRATEGIES, OmniRouteEngine
from agentic_os.server.daemon import KernelDaemon


@pytest.mark.asyncio
async def test_audit_subsystem_bottlenecks():
    items = await audit_subsystem_bottlenecks()
    assert isinstance(items, list)
    assert len(items) >= 7
    for item in items:
        assert "id" in item
        assert "name" in item
        assert "subsystem" in item
        assert "severity" in item
        assert "before_latency_ms" in item
        assert "after_latency_ms" in item
        assert "speedup" in item
        assert "status" in item


def test_get_architectural_blueprints():
    blueprints = get_architectural_blueprints()
    assert isinstance(blueprints, list)
    assert len(blueprints) >= 5
    for bp in blueprints:
        assert "id" in bp
        assert "title" in bp
        assert "subsystem" in bp
        assert "before" in bp
        assert "after" in bp
        assert "code" in bp["before"]
        assert "code" in bp["after"]


@pytest.mark.asyncio
async def test_benchmark_event_loop_lag():
    res = await benchmark_event_loop_lag()
    assert res["subsystem"] == "Async Event Loop"
    assert res["iterations"] == 20
    assert "mean_ms" in res
    assert "p95_ms" in res
    assert res["status"] in ("PASS", "WARNING")


@pytest.mark.asyncio
async def test_benchmark_sqlite_wal_contention():
    res = await benchmark_sqlite_wal_contention()
    assert "SQLite" in res["subsystem"]
    assert res["iterations"] == 50
    assert "mean_ms" in res
    assert res["status"] in ("PASS", "WARNING")


@pytest.mark.asyncio
async def test_benchmark_subprocess_pipe_overhead():
    res = await benchmark_subprocess_pipe_overhead()
    assert "Subprocess" in res["subsystem"]
    assert "mean_ms" in res
    assert res["status"] in ("PASS", "WARNING")


@pytest.mark.asyncio
async def test_benchmark_omniroute_speed():
    res = await benchmark_omniroute_speed()
    assert "OmniRoute" in res["subsystem"]
    assert res["iterations"] == 100
    assert "mean_ms" in res
    assert res["status"] in ("PASS", "FAIL")


@pytest.mark.asyncio
async def test_benchmark_ast_parsing():
    res = await benchmark_ast_parsing()
    assert res["subsystem"] == "AST Parse Latency"
    assert "sync_time_ms" in res
    assert "offloaded_time_ms" in res
    assert res["status"] == "PASS"


@pytest.mark.asyncio
async def test_benchmark_worktree_isolation():
    res = await benchmark_worktree_isolation()
    assert res["subsystem"] == "Worktree Isolation"
    assert "duration_ms" in res
    assert res["status"] == "PASS"


@pytest.mark.asyncio
async def test_benchmark_memory_footprint():
    res = await benchmark_memory_footprint()
    assert res["subsystem"] == "Memory Footprint"
    assert "process_rss_mb" in res
    assert res["status"] in ("PASS", "WARNING")


@pytest.mark.asyncio
async def test_run_all_micro_benchmarks():
    res = await run_all_micro_benchmarks()
    assert "total_duration_ms" in res
    assert res["benchmarks_count"] == 7
    assert res["passed_count"] >= 5
    assert len(res["results"]) == 7


# ── OmniRoute Engine Tests ──


def test_omniroute_policies():
    engine = OmniRouteEngine()
    policies = engine.list_policies()
    assert len(policies) == len(STRATEGIES)
    strat_keys = {p["strategy"] for p in policies}
    assert "latency" in strat_keys
    assert "cost" in strat_keys
    assert "reasoning" in strat_keys
    assert "privacy" in strat_keys


def test_omniroute_resolve_and_circuit_breaker():
    engine = OmniRouteEngine(failure_threshold=2)

    # Initial resolve
    decision = engine.resolve(prompt="Generate code", strategy="latency")
    assert decision["strategy"] == "latency"
    assert decision["selected_provider"] == "groq"
    assert decision["is_fallback"] is False
    assert decision["decision_time_ms"] >= 0.0

    # Record 1 failure - not tripped yet
    engine.record_failure("groq")
    assert engine._provider_health["groq"] == "HEALTHY"

    # Record 2nd failure - trips circuit breaker
    engine.record_failure("groq")
    assert engine._provider_health["groq"] == "TRIPPED"

    # Next resolve uses fallback
    fallback_decision = engine.resolve(prompt="Generate code", strategy="latency")
    assert fallback_decision["is_fallback"] is True
    assert fallback_decision["selected_provider"] == "google"
    assert fallback_decision["selected_model"] == "gemini-2.5-flash"

    # Check failover history
    failovers = engine.get_failovers()
    assert len(failovers) >= 1
    assert failovers[-1]["tripped_provider"] == "groq"

    # Record success resets circuit breaker
    engine.record_success("groq")
    assert engine._provider_health["groq"] == "HEALTHY"
    reset_decision = engine.resolve(prompt="Generate code", strategy="latency")
    assert reset_decision["is_fallback"] is False
    assert reset_decision["selected_provider"] == "groq"


def test_omniroute_compress_context():
    engine = OmniRouteEngine()

    # Empty prompt
    res_empty = engine.compress_context("")
    assert res_empty["original_characters"] == 0
    assert res_empty["compressed_characters"] == 0

    # Prompt with extra newlines and spaces
    dirty_prompt = "Hello    world!\n\n\n\nThis is   a test.\n\n\n\n"
    res = engine.compress_context(dirty_prompt)
    assert res["original_characters"] > res["compressed_characters"]
    assert res["savings_percent"] > 0
    assert "\n\n\n" not in res["optimized_prompt"]


# ── Kernel Daemon Tests ──


@pytest.mark.asyncio
async def test_kernel_daemon_lifecycle():
    daemon = KernelDaemon()
    assert daemon.uptime_sec >= 0.0

    health = daemon.health()
    assert health["status"] == "ok"
    assert health["version"] == "1.0.0-rc10"
    assert health["event_loop"] == "running"

    # Track / untrack PID
    daemon.track_pid(12345)
    assert 12345 in daemon._child_pids
    daemon.untrack_pid(12345)
    assert 12345 not in daemon._child_pids


@pytest.mark.asyncio
async def test_kernel_daemon_exec_process():
    daemon = KernelDaemon()
    cmd = "cmd.exe" if os.name == "nt" else "sh"
    args = ["/c", "echo test_kernel_exec"] if os.name == "nt" else ["-c", "echo test_kernel_exec"]

    res = await daemon.exec_process(cmd=cmd, args=args, timeout=5.0)
    assert res["returncode"] == 0
    assert "test_kernel_exec" in res["stdout"]
    assert res["timeout"] is False
    assert res["duration_ms"] >= 0.0
