"""Launcher that strips Hermes venv from sys.path to avoid pydantic_core conflict."""

import sys

sys.path = [p for p in sys.path if "hermes-agent" not in p]

from agentic_os.__main__ import main  # noqa: E402

main()
