"""Built-in capabilities.

Each capability is a small, independent, testable unit. Sensitive capabilities
(terminal, docker, git, filesystem) set ``requires_approval=True`` so the
Security Framework's approval gate can intercept them. The engine composes
agents from these at runtime (ADR-0007).
"""

from __future__ import annotations

import asyncio

from agentic_os.domain.agent import Agent, Task
from agentic_os.domain.capability import CapabilityCategory
from agentic_os.ports.capability import Capability, CapabilityResult


class _Base:
    requires_approval = False

    async def run(self, agent: Agent, task: Task, context: dict) -> CapabilityResult:
        raise NotImplementedError


class ReasoningCapability(_Base):
    name = "reasoning"
    description = "Decomposes problems and forms plans via structured thought."
    category = CapabilityCategory.COGNITION

    async def run(self, agent: Agent, task: Task, context: dict) -> CapabilityResult:
        # The heavy lifting is delegated to the provider; here we record the
        # reasoning step and pass the task through with a reasoning prefix.
        return CapabilityResult(ok=True, output=f"[reasoning] analyzing: {task.title}")


class PlanningCapability(_Base):
    name = "planning"
    description = "Breaks a goal into ordered sub-tasks."
    category = CapabilityCategory.COGNITION

    async def run(self, agent: Agent, task: Task, context: dict) -> CapabilityResult:
        return CapabilityResult(ok=True, output=f"[planning] steps for: {task.title}")


class CodingCapability(_Base):
    name = "coding"
    description = "Writes and edits source code."
    category = CapabilityCategory.CODE

    async def run(self, agent: Agent, task: Task, context: dict) -> CapabilityResult:
        return CapabilityResult(ok=True, output=f"[coding] implementing: {task.title}")


class ResearchCapability(_Base):
    name = "research"
    description = "Gathers information from sources."
    category = CapabilityCategory.KNOWLEDGE

    async def run(self, agent: Agent, task: Task, context: dict) -> CapabilityResult:
        return CapabilityResult(ok=True, output=f"[research] findings for: {task.title}")


class VisionCapability(_Base):
    name = "vision"
    description = "Interprets images and visual input."
    category = CapabilityCategory.KNOWLEDGE

    async def run(self, agent: Agent, task: Task, context: dict) -> CapabilityResult:
        return CapabilityResult(ok=True, output="[vision] image interpreted")


class MemoryCapability(_Base):
    name = "memory"
    description = "Reads/writes the memory system."
    category = CapabilityCategory.KNOWLEDGE

    async def run(self, agent: Agent, task: Task, context: dict) -> CapabilityResult:
        return CapabilityResult(ok=True, output="[memory] accessed")


class BrowserCapability(_Base):
    name = "browser"
    description = "Navigates the web."
    category = CapabilityCategory.KNOWLEDGE

    async def run(self, agent: Agent, task: Task, context: dict) -> CapabilityResult:
        return CapabilityResult(ok=True, output="[browser] navigated")


class _ShellCapability(_Base):
    """Base for shell-backed capabilities (terminal/git/docker/filesystem)."""

    requires_approval = True
    cmd: list[str] = []

    async def run(self, agent: Agent, task: Task, context: dict) -> CapabilityResult:
        # Approval is enforced by the Security Framework *before* this runs.
        # Here we execute the shell command scoped to the agent's workspace.
        workspace = context.get("workspace", ".")
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.cmd,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc.communicate()
        except FileNotFoundError as exc:
            return CapabilityResult(ok=False, output="", meta={"error": str(exc)})
        ok = proc.returncode == 0
        return CapabilityResult(
            ok=ok,
            output=(out or err).decode(errors="replace").strip(),
            meta={"returncode": proc.returncode},
        )


class TerminalCapability(_ShellCapability):
    name = "terminal"
    description = "Runs shell commands (requires approval)."
    category = CapabilityCategory.EXECUTION
    cmd = ["cmd", "/c", "echo", "terminal-ok"]


class GitCapability(_ShellCapability):
    name = "git"
    description = "Version control operations (requires approval)."
    category = CapabilityCategory.CODE
    cmd = ["git", "--version"]


class DockerCapability(_ShellCapability):
    name = "docker"
    description = "Container operations (requires approval)."
    category = CapabilityCategory.EXECUTION
    cmd = ["docker", "--version"]


class FilesystemCapability(_ShellCapability):
    name = "filesystem"
    description = "Filesystem reads/writes (requires approval)."
    category = CapabilityCategory.CODE
    cmd = ["cmd", "/c", "dir"]


BUILTIN_CAPABILITIES: list[Capability] = [
    ReasoningCapability(),
    PlanningCapability(),
    CodingCapability(),
    ResearchCapability(),
    VisionCapability(),
    MemoryCapability(),
    BrowserCapability(),
    TerminalCapability(),
    GitCapability(),
    DockerCapability(),
    FilesystemCapability(),
]


def capability_names() -> list[str]:
    return [c.name for c in BUILTIN_CAPABILITIES]
