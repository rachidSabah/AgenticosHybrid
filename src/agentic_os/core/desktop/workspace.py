"""Workspace Manager — manages desktop workspaces, tabs, and panels."""

from __future__ import annotations

from collections.abc import Sequence

from agentic_os.domain.desktop import (
    PanelConfig,
    TabInfo,
    Workspace,
    WorkspaceLayout,
    WorkspaceStatus,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.workspace")


class WorkspaceManager:
    """Manages desktop workspaces, their layouts, tabs, and panels."""

    def __init__(self) -> None:
        self._workspaces: dict[str, Workspace] = {}
        self._active_workspace_id: str = ""

    # ── Workspace CRUD ──

    async def create_workspace(self, name: str) -> Workspace:
        ws = Workspace(name=name)
        self._workspaces[ws.id] = ws
        if not self._active_workspace_id:
            self._active_workspace_id = ws.id
        log.info("Workspace created", workspace_id=ws.id, name=name)
        return ws

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        return self._workspaces.get(workspace_id)

    async def list_workspaces(self) -> Sequence[Workspace]:
        return list(self._workspaces.values())

    async def update_workspace(self, workspace: Workspace) -> Workspace:
        self._workspaces[workspace.id] = workspace
        return workspace

    async def delete_workspace(self, workspace_id: str) -> bool:
        if workspace_id in self._workspaces:
            del self._workspaces[workspace_id]
            if self._active_workspace_id == workspace_id:
                self._active_workspace_id = next(iter(self._workspaces), "")
            return True
        return False

    async def switch_workspace(self, workspace_id: str) -> Workspace:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            raise ValueError(f"Workspace not found: {workspace_id}")
        for w in self._workspaces.values():
            w.status = WorkspaceStatus.INACTIVE
        ws.status = WorkspaceStatus.ACTIVE
        self._active_workspace_id = workspace_id
        log.info("Workspace switched", workspace_id=workspace_id)
        return ws

    async def get_active_workspace(self) -> Workspace | None:
        if self._active_workspace_id:
            return self._workspaces.get(self._active_workspace_id)
        return None

    # ── Layout ──

    async def get_workspace_layout(self, workspace_id: str) -> WorkspaceLayout | None:
        ws = self._workspaces.get(workspace_id)
        return ws.layout if ws else None

    async def update_workspace_layout(
        self, workspace_id: str, layout: WorkspaceLayout
    ) -> WorkspaceLayout:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            raise ValueError(f"Workspace not found: {workspace_id}")
        ws.layout = layout
        return layout

    # ── Tabs ──

    async def add_tab(self, workspace_id: str, tab: TabInfo) -> TabInfo:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            raise ValueError(f"Workspace not found: {workspace_id}")
        tab.order = len(ws.tabs)
        ws.tabs.append(tab)
        return tab

    async def remove_tab(self, workspace_id: str, tab_id: str) -> bool:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return False
        ws.tabs = [t for t in ws.tabs if t.id != tab_id]
        return True

    async def activate_tab(self, workspace_id: str, tab_id: str) -> bool:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return False
        for t in ws.tabs:
            t.active = t.id == tab_id
        return True

    # ── Panels ──

    async def add_panel(self, workspace_id: str, panel: PanelConfig) -> PanelConfig:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            raise ValueError(f"Workspace not found: {workspace_id}")
        panel.order = len(ws.layout.panels)
        ws.layout.panels.append(panel)
        return panel

    async def remove_panel(self, workspace_id: str, panel_id: str) -> bool:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return False
        ws.layout.panels = [p for p in ws.layout.panels if p.id != panel_id]
        return True

    async def get_workspace_count(self) -> int:
        return len(self._workspaces)
