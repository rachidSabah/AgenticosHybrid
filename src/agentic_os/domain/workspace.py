"""Workspace domain model and active workspace state manager."""

from __future__ import annotations

import json
import os
from pathlib import Path

_workspace_state: dict[str, str] = {"path": ""}
_STATE_FILE = Path.home() / ".agentic_os" / "data" / "workspace.json"


def _load_persisted() -> str:
    """Load the last active workspace from disk, if it still exists."""
    try:
        if _STATE_FILE.is_file():
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            path = data.get("path", "")
            if path and os.path.isdir(path):
                return path
    except Exception:
        pass
    return ""


def get_workspace_root() -> str:
    """Get current active workspace path, defaulting to current working directory."""
    if _workspace_state["path"]:
        return _workspace_state["path"]
    persisted = _load_persisted()
    if persisted:
        _workspace_state["path"] = persisted
        return persisted
    return os.getcwd()


def set_workspace_root(path: str) -> str:
    """Set active workspace path (persisted across restarts)."""
    real = os.path.realpath(path)
    _workspace_state["path"] = real
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps({"path": real}), encoding="utf-8")
    except Exception:
        pass
    return real
