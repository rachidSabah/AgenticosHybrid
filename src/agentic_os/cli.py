"""Agentic OS CLI entrypoint.

Usage:
    python -m agentic_os serve      # run kernel + FastAPI control plane
"""

from __future__ import annotations

import argparse
import sys

from agentic_os.kernel import run_serve


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
        import anyio

        anyio.run(run_serve, args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
