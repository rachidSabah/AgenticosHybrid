"""Workspace domain model and active workspace state manager.

Persists the user-assigned workspace path to disk so it survives
backend restarts. Without persistence, every restart resets the
workspace from the user-assigned path (e.g. ``E:\\Mission``) back to
the process cwd, causing missions to write to the wrong folder.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_workspace_state: dict[str, str] = {"path": ""}

_WORKSPACE_FILE = Path.home() / ".agentic_os" / "data" / "workspace.json"


def get_workspace_root() -> str:
    """Get current active workspace path, defaulting to current working directory.

    If the in-memory path is empty, attempts to load the persisted
    workspace file. Falls back to ``os.getcwd()`` if no persisted path
    exists or the persisted directory no longer exists.
    """
    if _workspace_state["path"]:
        return _workspace_state["path"]

    # Try loading persisted path
    try:
        if _WORKSPACE_FILE.exists():
            data = json.loads(_WORKSPACE_FILE.read_text(encoding="utf-8"))
            persisted_path = data.get("path", "")
            if persisted_path and os.path.isdir(persisted_path):
                _workspace_state["path"] = persisted_path
                return persisted_path
    except Exception:
        pass  # best-effort — fall through to cwd

    return os.getcwd()


def set_workspace_root(path: str) -> str:
    """Set active workspace path and persist to disk.

    Writes ``{"path": <realpath>}`` to ``~/.agentic_os/data/workspace.json``
    so the workspace survives backend restarts. Persistence is best-effort
    (wrapped in try/except) to avoid breaking if the home directory is
    read-only or doesn't exist.
    """
    _workspace_state["path"] = os.path.realpath(path)

    # Persist to disk (best-effort)
    try:
        _WORKSPACE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _WORKSPACE_FILE.write_text(
            json.dumps({"path": _workspace_state["path"]}),
            encoding="utf-8",
        )
    except Exception:
        pass  # best-effort — don't crash if persistence fails

    return _workspace_state["path"]
