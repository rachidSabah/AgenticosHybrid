"""Workspace domain model and active workspace state manager."""

from __future__ import annotations

import os

_workspace_state: dict[str, str] = {"path": ""}


def get_workspace_root() -> str:
    """Get current active workspace path, defaulting to current working directory."""
    if _workspace_state["path"]:
        return _workspace_state["path"]
    return os.getcwd()


def set_workspace_root(path: str) -> str:
    """Set active workspace path."""
    _workspace_state["path"] = os.path.realpath(path)
    return _workspace_state["path"]
