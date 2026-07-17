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
    sub.add_parser("serve", help="Run the orchestrator kernel + API")
    args = parser.parse_args(argv)
    if args.command == "serve":
        import anyio

        anyio.run(run_serve)
    return 0


if __name__ == "__main__":
    sys.exit(main())
