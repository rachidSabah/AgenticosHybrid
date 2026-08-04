"""Agentic OS CLI entrypoint.

Usage:
    python -m agentic_os serve      # run kernel + FastAPI control plane
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentic-os", description="Agentic OS kernel")
    sub = parser.add_subparsers(dest="command", required=True)
    serve_parser = sub.add_parser("serve", help="Run the orchestrator kernel + API")
    serve_parser.add_argument(
        "--host", default="127.0.0.1", help="Host IP to bind (default: 127.0.0.1)"
    )
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    args = parser.parse_args(argv)
    if args.command == "serve":
        # On Windows, force SelectorEventLoop to avoid ProactorEventLoop
        # stability issues. The ProactorEventLoop (default on Windows since
        # Python 3.8) has known bugs where concurrent subprocess pipe I/O
        # can crash the process silently — no Python traceback, no error
        # log, just a dead process. This was observed repeatedly on Windows
        # CI runners: the backend starts, serves /healthz, then crashes
        # ~10s later when a background task spawns subprocesses.
        #
        # SelectorEventLoop does NOT support subprocesses on Windows
        # (asyncio.create_subprocess_exec raises NotImplementedError), but
        # all such call sites have try/except guards that return empty
        # results. The REST-API and all non-subsystem code paths work
        # normally under SelectorEventLoop.
        if sys.platform == "win32":
            import asyncio

            # set_event_loop_policy is deprecated in Python 3.14+ but still
            # works. It's the only way to force SelectorEventLoop on Windows
            # before the event loop is created. Suppress the deprecation
            # diagnostic — when this is removed in Python 3.16, we'll need a
            # different approach, but for now (Python 3.12/3.13) it's the
            # correct fix.
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # noqa: TD006

        import anyio

        from agentic_os.core.kernel_bootstrap import run_container_serve

        anyio.run(run_container_serve, args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
