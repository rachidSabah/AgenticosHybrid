"""Benchmark runner — measures startup time, memory, CPU, and subsystem performance."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

REPORT_DIR = Path("docs/benchmarks")
REPORT_DIR.mkdir(parents=True, exist_ok=True)


async def benchmark_startup_time() -> dict[str, object]:
    """Measure how long it takes to create and initialize key managers."""
    from agentic_os.core.desktop.hardening import DesktopHardeningManager

    times: dict[str, float] = {}

    t0 = time.perf_counter()
    mgr = DesktopHardeningManager()
    times["instantiation"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    await mgr.validate_startup()
    times["startup_validation"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    await mgr.check_integrity()
    times["integrity_check"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    await mgr.run_self_diagnostics()
    times["self_diagnostics"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    await mgr.monitor_threads()
    times["thread_monitoring"] = time.perf_counter() - t0

    return times


async def benchmark_memory_usage() -> dict[str, object]:
    """Measure memory usage of key modules."""
    metrics: dict[str, object] = {}
    try:
        import psutil

        process = psutil.Process()
        metrics["process_memory_mb"] = round(process.memory_info().rss / (1024 * 1024), 1)
        metrics["cpu_percent"] = process.cpu_percent(interval=0.1)
        metrics["thread_count"] = process.num_threads()
        metrics["open_handles"] = process.num_handles()
    except ImportError:
        import threading

        metrics["thread_count"] = threading.active_count()
        metrics["note"] = "psutil not available, limited metrics"

    return metrics


async def benchmark_runtime_discovery() -> dict[str, object]:
    """Benchmark runtime discovery speed."""
    from agentic_os.core.desktop import RuntimeDiscoveryManager

    mgr = RuntimeDiscoveryManager()
    t0 = time.perf_counter()
    result = await mgr.discover_runtimes()
    duration = time.perf_counter() - t0

    return {
        "discovery_duration_seconds": round(duration, 3),
        "total_discovered": result.total_discovered,
        "runtimes": [r.to_dict() for r in result.runtimes],
    }


async def benchmark_update_system() -> dict[str, object]:
    """Benchmark update check speed."""
    from agentic_os.core.desktop import AutoUpdateManager
    from agentic_os.domain.desktop import UpdateChannel

    mgr = AutoUpdateManager()
    t0 = time.perf_counter()
    releases = await mgr.check_for_updates(UpdateChannel.STABLE)
    duration = time.perf_counter() - t0

    return {
        "check_duration_seconds": round(duration, 3),
        "releases_found": len(releases),
        "current_version": await mgr.get_current_version(),
    }


async def benchmark_first_run() -> dict[str, object]:
    """Benchmark first-run wizard completion."""
    from agentic_os.core.desktop import FirstRunWizard

    wizard = FirstRunWizard()
    t0 = time.perf_counter()
    for step in [
        "welcome",
        "workspace",
        "config",
        "runtime_discovery",
        "provider",
        "plugin",
        "database",
        "health",
        "complete",
    ]:
        await wizard.run_step(step)
    duration = time.perf_counter() - t0

    return {
        "full_wizard_duration_seconds": round(duration, 3),
        "completed": await wizard.is_completed(),
    }


async def main() -> dict[str, object]:
    ok = "[OK]"
    print("=" * 60)
    print("AgenticOS Benchmark Suite")
    print(f"Started at: {datetime.now(UTC).isoformat()}")
    print("=" * 60)

    results: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "version": "1.0.0-rc1",
        "platform": os.name,
        "python_version": __import__("sys").version,
    }

    print("\n[1/5] Startup time benchmark...")
    results["startup_times"] = await benchmark_startup_time()
    print(f"  {ok} Done: {results['startup_times']}")

    print("\n[2/5] Memory usage benchmark...")
    results["memory_usage"] = await benchmark_memory_usage()
    print(f"  {ok} Done: {results['memory_usage']}")

    print("\n[3/5] Runtime discovery benchmark...")
    results["runtime_discovery"] = await benchmark_runtime_discovery()
    print(f"  {ok} Done: {results['runtime_discovery']}")

    print("\n[4/5] Update system benchmark...")
    results["update_system"] = await benchmark_update_system()
    print(f"  {ok} Done: {results['update_system']}")

    print("\n[5/5] First-run wizard benchmark...")
    results["first_run"] = await benchmark_first_run()
    print(f"  {ok} Done: {results['first_run']}")

    report_path = REPORT_DIR / "benchmark_report.json"
    report_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n{ok} Report saved to {report_path}")

    print(f"\n{'=' * 60}")
    print("Benchmark Complete")
    print(f"{'=' * 60}")
    return results


if __name__ == "__main__":
    asyncio.run(main())
