#!/usr/bin/env python3
"""Installer Discovery — CLI tool for offline AI runtime discovery.

Usage:
    python scripts/installer-discover.py              # Quick scan
    python scripts/installer-discover.py --full        # Full install pipeline
    python scripts/installer-discover.py --report      # Show last report
    python scripts/installer-discover.py --validate    # Validate only
    python scripts/installer-discover.py --json        # JSON output
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="AgenticOS Installer Discovery — find all AI runtimes"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full install pipeline (discover + validate + bind + report)",
    )
    parser.add_argument("--quick", action="store_true", default=True, help="Quick scan (default)")
    parser.add_argument("--validate", action="store_true", help="Validate only")
    parser.add_argument("--report", action="store_true", help="Show last install report")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--previous-version", type=str, default=None, help="Previous version for upgrade migration"
    )
    args = parser.parse_args()

    asyncio.run(async_main(args))


async def async_main(args: argparse.Namespace):
    # Ensure the package is importable
    _ensure_paths()

    from services.installer.engine import InstallerIntelligence
    from services.installer.report import InstallReportGenerator

    engine = InstallerIntelligence()

    if args.report:
        _show_report(args.json)
        return

    if args.full:
        t0 = time.perf_counter()
        result = await engine.run_full_install(previous_version=args.previous_version)
        elapsed = time.perf_counter() - t0

        if args.json:
            _print_json_result(result, elapsed)
        else:
            _print_installer_result(result, elapsed)

    elif args.validate:
        report = await engine.run_quick_scan()
        if args.json:
            print(
                json.dumps(
                    {
                        "total_found": report.total_found,
                        "total_passed": report.total_passed,
                        "total_failed": report.total_failed,
                        "passed": [
                            {
                                "provider_id": r.provider_id,
                                "executable_path": r.executable_path,
                                "version": r.version,
                                "capabilities": list(r.detected_capabilities),
                                "launch_time_ms": round(r.launch_time_ms, 1),
                            }
                            for r in report.passed
                        ],
                        "failed": [
                            {
                                "provider_id": r.provider_id,
                                "executable_path": r.executable_path,
                                "errors": r.errors,
                            }
                            for r in report.failed
                        ],
                        "not_found": report.not_found,
                        "duration_seconds": round(report.duration_seconds, 2),
                    },
                    indent=2,
                )
            )
        else:
            _print_validation_report(report)

    else:
        # Quick scan (default)
        report = await engine.run_quick_scan()
        if args.json:
            print(
                json.dumps(
                    {
                        "total_found": report.total_found,
                        "total_passed": report.total_passed,
                        "total_failed": report.total_failed,
                        "duration_seconds": round(report.duration_seconds, 2),
                    }
                )
            )
        else:
            _print_validation_report(report)

    await engine.shutdown()


def _ensure_paths():
    """Ensure services/ and src/ are on sys.path."""
    repo_root = Path(__file__).resolve().parent.parent
    for p in [repo_root, repo_root / "src", repo_root / "services"]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def _print_validation_report(report):
    """Print a human-readable validation report."""
    print("=" * 56)
    print("  Mission Control — Runtime Discovery Report")
    print("=" * 56)
    print()

    if report.passed:
        print("  ✓ Found and Validated:")
        print()
        for r in report.passed:
            cap_str = ", ".join(sorted(r.detected_capabilities)[:5])
            if len(r.detected_capabilities) > 5:
                cap_str += "..."
            print(f"    ✓ {r.provider_id:<20s} {r.version or '?':<20s} {r.launch_time_ms:5.0f}ms")
            print(f"      {r.executable_path}")
            if cap_str:
                print(f"      [{cap_str}]")
            print()

    if report.failed:
        print("  ✗ Found but Validation Failed:")
        print()
        for r in report.failed:
            print(f"    ✗ {r.provider_id}: {r.errors[0] if r.errors else 'unknown error'}")
        print()

    if report.not_found:
        print("  - Not Found:")
        for nf in report.not_found:
            print(f"    {nf}")
        print()

    print(
        f"  Summary: {report.total_found} found, "
        f"{report.total_passed} validated, "
        f"{report.total_failed} failed"
    )
    print(f"  Duration: {report.duration_seconds:.2f}s")
    print()


def _print_installer_result(result, elapsed: float):
    """Print a human-readable installer result."""
    print("=" * 56)
    print("  Mission Control — Installation Report")
    print("=" * 56)
    print()

    for phase in result.phases:
        status = "✓" if phase.success else "✗"
        print(f"  {status} {phase.phase} ({phase.duration_seconds:.1f}s)")
        if phase.details:
            print(f"     {phase.details}")
    print()

    print(f"  Bound Providers: {len(result.bound_providers)}")
    for pid in result.bound_providers:
        print(f"    ✓ {pid}")

    if result.binding_errors:
        print(f"  Binding Errors:")
        for err in result.binding_errors:
            print(f"    ✗ {err}")

    print()
    print(f"  Total: {result.total_duration_seconds:.1f}s")
    print(f"  Result: {'SUCCESS' if result.success else 'FAILED'}")
    print()


def _print_json_result(result, elapsed: float):
    """Print installer result as JSON."""
    data = {
        "success": result.success,
        "duration_seconds": round(elapsed, 2),
        "phases": [
            {
                "phase": p.phase,
                "success": p.success,
                "duration_seconds": round(p.duration_seconds, 2),
            }
            for p in result.phases
        ],
        "bound_providers": result.bound_providers,
        "binding_errors": result.binding_errors,
    }
    print(json.dumps(data, indent=2))


def _show_report(as_json: bool):
    """Display the last saved install report."""
    _ensure_paths()
    from services.installer.report import InstallReportGenerator

    gen = InstallReportGenerator()
    report = gen.load()
    if report is None:
        print("No install report found.")
        sys.exit(1)

    if as_json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        print(report.to_markdown())


if __name__ == "__main__":
    main()
