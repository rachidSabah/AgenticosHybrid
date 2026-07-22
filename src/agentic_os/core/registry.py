"""In-memory registries for agents, roles, tasks, and providers.

Registries are intentionally simple, synchronous, and the single source of
truth for runtime state in the kernel. (A future Postgres/SQLAlchemy adapter
can back these via the same interface without changing callers.)
"""

from __future__ import annotations

from agentic_os.domain.agent import Agent, ProviderInfo, Role, Task
from agentic_os.ports.provider import ProviderAdapter


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._roles: dict[str, Role] = {}
        self._tasks: dict[str, Task] = {}

    # ── roles ──
    def register_role(self, role: Role) -> Role:
        self._roles[role.name] = role
        return role

    def get_role(self, name: str) -> Role | None:
        return self._roles.get(name)

    def roles(self) -> list[Role]:
        return list(self._roles.values())

    # ── agents ──
    def register_agent(self, agent: Agent) -> Agent:
        self._agents[agent.id] = agent
        return agent

    def get_agent(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def agents(self) -> list[Agent]:
        return list(self._agents.values())

    def spawn(self, role: str, provider: str, model: str = "", name: str = "") -> Agent:
        if role not in self._roles:
            raise KeyError(f"unknown role: {role}")
        agent = Agent(
            role=role, provider=provider, model=model, name=name or f"{role}-{len(self._agents)}"
        )
        return self.register_agent(agent)

    # ── tasks ──
    def register_task(self, task: Task) -> Task:
        self._tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def tasks(self) -> list[Task]:
        return list(self._tasks.values())


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> None:
        self._providers[adapter.info.name] = adapter

    def get(self, name: str) -> ProviderAdapter | None:
        return self._providers.get(name)

    def list_providers(self) -> list[ProviderInfo]:
        return [a.info for a in self._providers.values()]

    def default(self) -> ProviderAdapter | None:
        return next(iter(self._providers.values()), None)


__all__ = ["AgentRegistry", "ProviderRegistry"]
