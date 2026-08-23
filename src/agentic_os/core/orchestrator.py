"""Orchestrator kernel — the brain of the vertical slice.

Wires the event bus to the agent behaviors:

    Planner  → plans an incoming request into a Task
    Dispatcher → picks a Role/provider and spawns an Agent, runs the provider
    Supervisor → watches completion/failure and publishes outcomes

All coordination happens *through the bus*; the kernel only connects handlers.

Recovery policy (implemented in ``_run_provider``):
  1. Provider.execute() fails
  2. Retry same provider once (retry_count=1)
  3. If retry fails, pick the next healthy provider and retry (retry_count=2)
  4. If no other provider available OR retry also fails, mark task FAILED
  5. Never silently abandon a task

Every execution attempt is recorded in the ExecutionLog (if wired) so
Mission Control can render the full execution history per task/mission.
"""

from __future__ import annotations

import os as _os
import time as _time
from typing import TYPE_CHECKING, Any

from agentic_os.config import Settings
from agentic_os.core.registry import AgentRegistry, ProviderRegistry
from agentic_os.domain.agent import Agent, Role, Task, TaskStatus
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

if TYPE_CHECKING:
    from agentic_os.core.execution_log import ExecutionLog
    from agentic_os.core.worktree_manager import WorktreeManager

log = get_logger("core.orchestrator")

_MAX_SAME_PROVIDER_RETRIES = 1
_MAX_TOTAL_ATTEMPTS = 3

_ROLE_CAPABILITY_MAP: dict[str, list[str]] = {
    "coding": ["coding"],
    "planner": ["planning", "coding", "reasoning"],
    "research": ["research", "reasoning"],
    "reviewer": ["reasoning", "coding"],
    "devops": ["terminal", "coding"],
}

_PROVIDER_COOLDOWN_S = 30.0


def _is_unusable_output(text: str) -> bool:
    """Heuristic: provider output that must not be persisted as a task report.

    Guards against two failure modes observed with bound agent CLIs:

    * **Binary data** that survived the lossy ``utf-8`` decode in
      ``parse_output`` — compressed archives (e.g. bzip2) and other binary
      streams decode to a high density of replacement chars / control bytes
      and would corrupt the ``task_*.md`` report if written verbatim.
    * **Prompt-wrapper echo** — some CLIs respond to the built mission wrapper
      by printing it back verbatim instead of doing real work, so the report
      would contain only the input prompt, no result.

    ``text`` may be ``None``/empty when a provider produced no stdout; that is
    already handled upstream by the empty-result fallback, so it is *not*
    treated as unusable here (only garbage/echo).
    """
    if not text:
        return False
    sample = max(1, len(text))
    replacement = text.count("�")
    control = sum(1 for ch in text if ord(ch) < 32 and ch not in "\t\n\r")
    if replacement / sample > 0.1 or control / sample > 0.05:
        return True
    # Prompt-wrapper echo: the distinctive wrapper markers appear verbatim.
    markers = (
        "CRITICAL INSTRUCTION FOR FILE CREATION",
        "Mission Request",
        "Assigned Task",
        "Task Title",
    )
    present = sum(1 for m in markers if m in text)
    return present >= 2 and len(text) > 200


# Error signatures that bound agent CLIs return when execution did NOT
# actually happen (auth failure, unsupported model, process error, etc.).
# If a provider returns one of these as its "result", the task must be
# marked FAILED — never COMPLETED — so a failed run can't masquerade as
# successful execution (spec RULE 5/7: no success without execution evidence).
_ERROR_SIGNATURES = (
    "http 401",
    "401:",
    "401 ",
    "403:",
    "403 ",
    "http 403",
    "not supported",
    "model not found",
    "api key",
    "unauthorized",
    "authentication failed",
    "exited 1:",
    "exited 2:",
    "timed out after",
    "cannot connect to api",
    "unable to connect",
    "traceback (most recent call last)",
    "error:",
    "command not found",
    "not recognized as",
    "stray separator",
    "how can i help",
    "looks like a",
    "i can help",
    "please provide",
)


def _is_error_output(text: str) -> bool:
    """True when ``text`` is an error/diagnostic, not real execution output.

    Used to prevent a failed agent run (auth error, crashed CLI, unsupported
    model) from being recorded as a COMPLETED task.
    """
    if not text or not text.strip():
        return False
    lowered = text.lower()
    # Any explicit error signature means the agent did not produce real work.
    if any(sig in lowered for sig in _ERROR_SIGNATURES):
        return True
    return False


def _extract_and_persist_files(result: str, task: Task, ws_root: str, provider_kind: str) -> list[str]:
    """Extract code blocks and persist generated files and reports to workspace root."""
    import os
    import re

    extracted_files: list[str] = []
    if not ws_root or not os.path.isdir(ws_root) or not result:
        return extracted_files

    # 1. Save task execution summary report
    report_filename = f"task_{task.id[:8]}_{task.role}.md"
    report_path = os.path.join(ws_root, report_filename)
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# Output for Task: {task.title}\n\n{result}\n")
        extracted_files.append(report_path)
    except Exception:
        pass

    # If the task is architecture/design or specification, also write ARCHITECTURE.md
    title_lower = (task.title or "").lower()
    user_prompt_lower = (task.user_prompt or "").lower()
    if any(
        kw in title_lower or kw in user_prompt_lower
        for kw in ("architecture", "system design", "component diagram", "data contract", "architectural")
    ):
        arch_path = os.path.join(ws_root, "ARCHITECTURE.md")
        if not os.path.exists(arch_path) or os.path.getsize(arch_path) < 50:
            try:
                with open(arch_path, "w", encoding="utf-8") as f:
                    f.write(f"# System Architecture Design\n\n{result}\n")
                extracted_files.append(arch_path)
            except Exception:
                pass

    # 2. Extract code blocks with target filenames or language extensions
    ext_to_default_file: dict[str, str] = {
        "html": "index.html",
        "css": "styles.css",
        "scss": "styles.scss",
        "javascript": "index.js",
        "js": "index.js",
        "jsx": "App.jsx",
        "typescript": "index.ts",
        "ts": "index.ts",
        "tsx": "App.tsx",
        "python": "app.py",
        "py": "app.py",
        "json": "config.json",
        "yaml": "config.yaml",
        "yml": "config.yaml",
        "toml": "config.toml",
        "sql": "schema.sql",
        "sh": "script.sh",
        "bash": "script.sh",
        "ps1": "script.ps1",
        "rust": "main.rs",
        "rs": "main.rs",
        "go": "main.go",
        "c": "main.c",
        "cpp": "main.cpp",
        "java": "Main.java",
        "cs": "Program.cs",
        "csharp": "Program.cs",
        "dockerfile": "Dockerfile",
        "env": ".env.example",
    }

    # Match code blocks with optional language and optional filepath header
    pattern = re.compile(
        r"```(?:(?P<lang>[a-zA-Z0-9_\-]+)(?:[:\s]+(?P<file1>[^\n\r`]+))?|(?P<file2>[^\n\r`]+\.[a-zA-Z0-9]+))\r?\n(?P<code>.*?)```",
        re.DOTALL,
    )

    file_idx = 0
    for match in pattern.finditer(result):
        lang = (match.group("lang") or "").strip().lower()
        file_meta = (match.group("file1") or match.group("file2") or "").strip()
        code = match.group("code").strip()
        if not code:
            continue

        target_filename = None
        # Check if file_meta contains a clean filename/path
        if file_meta and not any(ch in file_meta for ch in ('"', "'", "<", ">", "|", "*", "?")):
            clean_meta = file_meta.strip().split()[-1].lstrip(":").strip()
            if "." in clean_meta and len(clean_meta) < 120 and not clean_meta.endswith(".md"):
                target_filename = clean_meta

        # If not in header, check first lines of code for // filename: or # filepath: or similar
        if not target_filename:
            first_lines = code.split("\n")[:3]
            for fl in first_lines:
                fn_match = re.search(
                    r"(?:filename|filepath|file)[:\s=]+\s*([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)",
                    fl,
                    re.IGNORECASE,
                )
                if fn_match:
                    found_fn = fn_match.group(1).strip()
                    if not found_fn.endswith(".md"):
                        target_filename = found_fn
                        break

        # Fallback to language extension mapping
        if not target_filename and lang in ext_to_default_file:
            default_name = ext_to_default_file[lang]
            if file_idx == 0:
                target_filename = f"{task.role}_{default_name}" if task.role else default_name
            else:
                base, ext = os.path.splitext(default_name)
                target_filename = f"{task.role}_{base}_{file_idx}{ext}" if task.role else f"{base}_{file_idx}{ext}"

        if target_filename:
            target_filename = target_filename.replace("/", os.sep).replace("\\", os.sep).lstrip(os.sep)
            code_file_path = os.path.join(ws_root, target_filename)
            try:
                os.makedirs(os.path.dirname(code_file_path), exist_ok=True)
                with open(code_file_path, "w", encoding="utf-8") as f:
                    f.write(code + "\n")
                extracted_files.append(code_file_path)
                file_idx += 1
            except Exception:
                pass

    return extracted_files


class Orchestrator:
    def __init__(
        self,
        bus: EventBus,
        registry: AgentRegistry,
        providers: ProviderRegistry,
        settings: Settings,
        execution_log: "ExecutionLog | None" = None,
        worktree_manager: "WorktreeManager | None" = None,
        memory: "Any | None" = None,
    ) -> None:
        self.bus = bus
        self.registry = registry
        self.providers = providers
        self.settings = settings
        self.execution_log = execution_log
        self.worktree_manager = worktree_manager
        self.memory = memory
        self._provider_rr_idx = 0
        self._failed_providers: dict[str, float] = {}

    async def start(self) -> None:
        for role in _default_roles():
            self.registry.register_role(role)
        await self.bus.subscribe(Topic.TASK_CREATED.value, self._on_task_created)
        await self.bus.subscribe(Topic.TASK_PLANNED.value, self._on_task_planned)
        await self.bus.subscribe(Topic.TASK_DISPATCHED.value, self._on_task_dispatched)
        await self.bus.subscribe(Topic.AGENT_COMPLETED.value, self._on_agent_completed)
        await self.bus.subscribe(Topic.AGENT_FAILED.value, self._on_agent_failed)
        log.info("orchestrator.started", roles=len(self.registry.roles()))

    async def stop(self) -> None:
        pass

    async def create_task(
        self,
        title: str,
        role: str,
        description: str = "",
        user_prompt: str = "",
        mission_id: str = "",
        preferred_agents: list[str] | None = None,
    ) -> Task:
        task = Task(
            title=title,
            role=role,
            description=description,
            user_prompt=user_prompt,
            mission_id=mission_id,
            preferred_agents=preferred_agents or [],
        )
        self.registry.register_task(task)
        await self.bus.publish(
            EventEnvelope(
                type="task.created",
                source="api",
                topic=Topic.TASK_CREATED.value,
                payload=task.model_dump(),
            )
        )
        return task

    async def _on_task_created(self, event: EventEnvelope) -> None:
        task = self._canonical_task(event.payload.get("id"))
        if task is None:
            return
        task.status = TaskStatus.PLANNED
        task.touch()
        log.info("planner.plan", task=task.id, role=task.role)
        await self.bus.publish(event.route_to(Topic.TASK_PLANNED))

    async def _on_task_planned(self, event: EventEnvelope) -> None:
        task = self._canonical_task(event.payload.get("id"))
        if task is None:
            return
        provider = self._select_provider(task.role, task.preferred_agents)
        if provider is None:
            log.error("dispatcher.no_provider", task=task.id, role=task.role)
            return
        agent = self.registry.spawn(role=task.role, provider=provider.info.name)
        agent.mark_running(task.id)
        task.status = TaskStatus.DISPATCHED
        task.assigned_agent_id = agent.id
        task.touch()
        log.info("dispatcher.assign", task=task.id, agent=agent.id, provider=provider.info.name)
        await self.bus.publish(
            EventEnvelope(
                type="task.dispatched",
                source="dispatcher",
                topic=Topic.TASK_DISPATCHED.value,
                payload={"task_id": task.id, "agent_id": agent.id},
            )
        )

    def _select_provider(self, role: str, preferred_agents: list[str] | None = None):
        all_providers = self.providers.list_providers()
        if not all_providers:
            return None
        required_caps = _ROLE_CAPABILITY_MAP.get(role, [])
        now = _time.monotonic()
        self._failed_providers = {
            name: ts
            for name, ts in self._failed_providers.items()
            if now - ts < _PROVIDER_COOLDOWN_S
        }
        real_candidates = []
        for p in all_providers:
            if p.name == "mock" or "mock" in p.kind:
                continue
            if p.name in self._failed_providers:
                continue
            if required_caps:
                provider_caps = set(p.capabilities) if hasattr(p, "capabilities") else set()
                if provider_caps and not provider_caps.intersection(required_caps):
                    continue
            real_candidates.append(p)
        # Agent selection (Prompt Center): when the mission pinned a set of
        # preferred agents, restrict dispatch to exactly those providers. If
        # none of them are real candidates, return None so the task stays
        # planned instead of leaking to unselected agents.
        if preferred_agents:
            selected = {name.strip().lower() for name in preferred_agents if name}
            # Also try fuzzy matching: check if any preferred name is a substring of
            # a real provider name or vice versa (handles 'claude-code' -> 'claude_code')
            normalized = {s.replace("-", "_").replace(" ", "_") for s in selected}
            filtered = [
                p
                for p in real_candidates
                if p.name.lower() in selected
                or p.name.lower().replace("-", "_") in normalized
                or any(p.name.lower() in s or s in p.name.lower() for s in selected)
            ]
            if not filtered:
                log.info(
                    "dispatcher.preferred_provider_not_found_falling_through",
                    task_role=role,
                    preferred_agents=sorted(selected),
                    note=(
                        "No preferred provider found among real candidates; "
                        "using any available provider"
                    ),
                )
                # Fall through to use whatever provider is available
            else:
                real_candidates = filtered
        if real_candidates:
            # Prioritize dedicated AI agent providers over auto_detected utilities
            ai_agents = [
                p
                for p in real_candidates
                if p.kind
                in (
                    "claude_code",
                    "hermes",
                    "codex",
                    "opencode",
                    "antigravity",
                    "gemini_cli",
                    "qwen_cli",
                    "ollama",
                    "local_cli",
                )
            ]
            if ai_agents:
                real_candidates = ai_agents
            idx = self._provider_rr_idx % len(real_candidates)
            self._provider_rr_idx += 1
            chosen = real_candidates[idx]
            provider = self.providers.get(chosen.name)
            log.info(
                "dispatcher.real_provider_selected",
                provider=chosen.name,
                task_role=role,
                required_caps=required_caps,
                rr_index=idx,
                real_count=len(real_candidates),
                failed_in_cooldown=len(self._failed_providers),
            )
            return provider
        log.info(
            "dispatcher.fallback_to_default",
            task_role=role,
            failed_in_cooldown=len(self._failed_providers),
        )
        provider = self.providers.get(self.settings.provider_default) or self.providers.default()
        # If the fallback is a MockProvider AND there were real providers
        # that failed (in cooldown), switch mock to fallback_mode so mock
        # execution marks the task as failed instead of returning canned
        # "completed" text. This prevents missions from showing "completed"
        # while zero files are written to the workspace.
        # NOTE: If no real providers ever existed (e.g. tests that register
        # only MockProvider), fallback_mode is NOT set so tests still pass.
        if (
            provider
            and hasattr(provider, "_fallback_mode")
            and self._failed_providers  # only set fallback_mode if real providers failed
        ):
            provider._fallback_mode = True  # type: ignore[attr-defined]  # ty: ignore[invalid-assignment]
        return provider

    def _mark_provider_failed(self, provider_name: str) -> None:
        self._failed_providers[provider_name] = _time.monotonic()
        log.info(
            "dispatcher.provider_marked_failed",
            provider=provider_name,
            cooldown_s=_PROVIDER_COOLDOWN_S,
        )

    def _make_output_callback(self, task: Task):
        """Create a streaming callback that publishes task.output + agent_status events."""

        async def _on_output(line: str, stream: str):
            await self.bus.publish(
                EventEnvelope(
                    type="task.output",
                    source="orchestrator",
                    topic="task.output",
                    payload={
                        "task_id": task.id,
                        "line": line,
                        "stream": stream,
                        "timestamp": _time.strftime("%H:%M:%S"),
                    },
                )
            )
            # Feature 4: detect agent reasoning lines
            lower = line.lstrip().lower()
            if any(
                lower.startswith(p)
                for p in (
                    "i'm ",
                    "i am ",
                    "let me",
                    "checking",
                    "now ",
                    "working on",
                    "done with",
                    "analyzing",
                    "reading",
                    "writing",
                    "updating",
                    "creating",
                    "fixing",
                    "implementing",
                    "running",
                    "building",
                )
            ):
                await self.bus.publish(
                    EventEnvelope(
                        type="task.agent_status",
                        source="orchestrator",
                        topic="task.agent_status",
                        payload={
                            "task_id": task.id,
                            "status_text": line.strip(),
                            "timestamp": _time.strftime("%H:%M:%S"),
                        },
                    )
                )

        return _on_output

    async def _create_worktree_for_agent(self, agent: Agent, task: Task) -> str | None:
        """Create a git worktree for isolated agent execution.

        The worktree manager's workspace root is synced to the *active
        workspace* (get_workspace_root()) before creating the worktree so
        agents execute inside the user-selected workspace (e.g. ``E:\\Mission``),
        never inside the backend's process cwd (e.g. the Agenticos repo).
        Without this, worktrees default to ``os.getcwd()`` and agents analyze
        and modify the wrong project, producing empty/echoed results while the
        task .md outputs still get written to the real workspace.
        """
        if self.worktree_manager is None:
            return None
        try:
            from agentic_os.domain.workspace import get_workspace_root

            ws_root = get_workspace_root()
            if ws_root and _os.path.isdir(ws_root):
                self.worktree_manager.set_workspace_root(ws_root)
            # Non-git workspaces (e.g. a fresh E:\Mission) run the agent
            # directly in the workspace root so produced files land there,
            # instead of in a worktree checkout that is never merged back.
            if not _os.path.isdir(_os.path.join(ws_root, ".git")):
                log.info(
                    "worktree.skipped_non_git_workspace",
                    agent=agent.id,
                    workspace=ws_root,
                    reason="workspace is not a git repo — agent runs in workspace root",
                )
                return None
            branch = self.worktree_manager.auto_branch_name(agent.id, task.id)
            wt = await self.worktree_manager.create_worktree(
                branch_name=branch,
                agent_id=agent.id,
                task_id=task.id,
            )
            log.info("worktree.assigned", branch=branch, agent=agent.id, path=wt.path)
            return wt.path
        except Exception as exc:
            log.warning("worktree.create_failed", agent=agent.id, error=str(exc))
            return None

    def _resolve_execution_cwd(self, wt_path: str | None) -> str | None:
        """Return worktree path if valid, or fallback to selected workspace root."""
        if wt_path and _os.path.isdir(wt_path):
            return wt_path
        try:
            from agentic_os.domain.workspace import get_workspace_root

            ws = get_workspace_root()
            if ws and _os.path.isdir(ws):
                return ws
        except Exception:
            pass
        return wt_path

    async def dispatch_task(self, task: Task) -> None:
        provider = self._select_provider(task.role, task.preferred_agents)
        if provider is None:
            return
        task.attempts += 1
        agent = self.registry.spawn(role=task.role, provider=provider.info.name)
        agent.mark_running(task.id)
        task.status = TaskStatus.IN_PROGRESS
        task.assigned_agent_id = agent.id
        task.touch()
        await self._run_provider(agent, task)

    async def _on_task_dispatched(self, event: EventEnvelope) -> None:
        task = self._canonical_task(event.payload.get("task_id"))
        agent_id = event.payload.get("agent_id")
        if not agent_id:
            return
        agent = self.registry.get_agent(agent_id)
        if task is None or agent is None:
            return
        await self._run_provider(agent, task)

    async def _run_provider(self, agent: Agent, task: Task) -> None:
        provider = self.providers.get(agent.provider)
        if provider is None:
            log.error("provider.not_found", provider=agent.provider, agent=agent.id)
            await self._fail_task(agent, task, f"Provider '{agent.provider}' not found")
            return

        task.status = TaskStatus.IN_PROGRESS
        task.assigned_agent_id = agent.id
        task.touch()

        await self.bus.publish(
            EventEnvelope(
                type="task.started",
                source="orchestrator",
                topic="task.started",
                payload={
                    "task_id": task.id,
                    "agent_id": agent.id,
                    "provider": agent.provider,
                    "title": task.title,
                    "mission_id": task.mission_id,
                },
            )
        )

        start_time = _time.monotonic()
        log.info(
            "execution.started",
            task=task.id,
            agent=agent.id,
            provider=agent.provider,
            mission_id=task.mission_id,
            title=task.title,
        )

        # Write execution memory into working memory scope for live tracking
        try:
            from agentic_os.domain.memory import MemoryItem, MemoryScope

            memory_mgr = getattr(self, "memory", None)
            if memory_mgr is not None:
                await memory_mgr.write(
                    MemoryItem(
                        scope=MemoryScope.WORKING,
                        key=f"task:{task.id}",
                        value=(
                            f"Agent {agent.id} executing '{task.title}' "
                            f"via provider {agent.provider}"
                        ),
                        agent_id=agent.id,
                    )
                )
        except Exception:
            pass

        # Attempt 1
        exec_rec = self._start_execution(agent, task, provider, retry_count=0)
        wt_path = await self._create_worktree_for_agent(agent, task)
        exec_cwd = self._resolve_execution_cwd(wt_path)
        try:
            result = await provider.execute(
                agent,
                task,
                on_output=self._make_output_callback(task),
                cwd=exec_cwd,
            )
            elapsed = _time.monotonic() - start_time
            agent.mark_completed()
            # A non-empty return does NOT mean success. Bound agent CLIs return
            # auth errors / crash traces as their "result". If the output is an
            # error signature or unusable, the task FAILED — never COMPLETED.
            # (spec RULE 5/7: no success without real execution evidence.)
            result_is_error = _is_error_output(result) or _is_unusable_output(result)
            if result_is_error:
                task.status = TaskStatus.FAILED
                task.error = (result or "agent returned an error instead of real output")[:500]
                task.result = result
                task.touch()
                self._finish_execution(exec_rec, "failed", stderr=result)
                log.warning(
                    "execution.result_is_error",
                    task=task.id,
                    agent=agent.id,
                    mission_id=task.mission_id,
                    provider=provider.info.kind,
                    elapsed_s=round(elapsed, 3),
                    attempt=1,
                )
                await self._publish_failed(agent, task, result)
                return
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.touch()
            self._finish_execution(exec_rec, "completed", stdout=result)
            log.info(
                "execution.completed",
                task=task.id,
                agent=agent.id,
                mission_id=task.mission_id,
                elapsed_s=round(elapsed, 3),
                result_len=len(result) if result else 0,
            )
            # Persist generated output files and extract any code blocks into target workspace root
            try:
                from agentic_os.domain.workspace import get_workspace_root

                ws_root = get_workspace_root()
                if ws_root and _os.path.isdir(ws_root) and result and len(result) > 10:
                    saved = _extract_and_persist_files(result, task, ws_root, provider.info.kind)
                    log.info("task.files_persisted", count=len(saved), workspace=ws_root)
            except Exception as e:
                log.warning("task.persist_output_failed", error=str(e))

            await self._publish_completed(agent, task, result, elapsed)
            return
        except Exception as exc:
            elapsed = _time.monotonic() - start_time
            self._finish_execution(exec_rec, "failed", stderr=str(exc), error=str(exc))
            log.warning(
                "execution.failed",
                agent=agent.id,
                task=task.id,
                mission_id=task.mission_id,
                provider=agent.provider,
                error=str(exc),
                elapsed_s=round(elapsed, 3),
                attempt=1,
            )

        # Attempt 2: retry same provider
        if task.attempts < _MAX_TOTAL_ATTEMPTS:
            task.attempts += 1
            log.info(
                "execution.retry_same_provider",
                task=task.id,
                agent=agent.id,
                provider=agent.provider,
                attempt=2,
            )
            exec_rec2 = self._start_execution(agent, task, provider, retry_count=1)
            try:
                result = await provider.execute(
                    agent,
                    task,
                    on_output=self._make_output_callback(task),
                    cwd=exec_cwd,
                )
                elapsed = _time.monotonic() - start_time
                agent.mark_completed()
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.error = None
                task.touch()
                self._finish_execution(exec_rec2, "completed", stdout=result)
                log.info(
                    "execution.completed_after_retry",
                    task=task.id,
                    agent=agent.id,
                    provider=agent.provider,
                    attempt=2,
                    elapsed_s=round(elapsed, 3),
                )
                # Persist generated output files into workspace root
                try:
                    from agentic_os.domain.workspace import get_workspace_root

                    ws_root = get_workspace_root()
                    if ws_root and _os.path.isdir(ws_root) and result and len(result) > 10:
                        _extract_and_persist_files(result, task, ws_root, provider.info.kind)
                except Exception:
                    pass

                await self._publish_completed(agent, task, result, elapsed, recovered=True)
                return
            except Exception as exc2:
                self._finish_execution(exec_rec2, "failed", stderr=str(exc2), error=str(exc2))
                log.warning(
                    "execution.retry_failed",
                    agent=agent.id,
                    task=task.id,
                    provider=agent.provider,
                    attempt=2,
                    error=str(exc2),
                )

        # Attempt 3: fallback to next healthy provider
        self._mark_provider_failed(agent.provider)
        fallback_provider = self._pick_fallback_provider(
            current_name=agent.provider,
            role=task.role,
        )
        if fallback_provider is not None and task.attempts < _MAX_TOTAL_ATTEMPTS:
            task.attempts += 1
            log.info(
                "execution.fallback_provider",
                task=task.id,
                original_provider=agent.provider,
                fallback_provider=fallback_provider.info.name,
                attempt=3,
            )
            fallback_agent = self.registry.spawn(
                role=task.role,
                provider=fallback_provider.info.name,
            )
            fallback_agent.mark_running(task.id)
            task.assigned_agent_id = fallback_agent.id
            task.touch()
            exec_rec3 = self._start_execution(
                fallback_agent, task, fallback_provider, retry_count=2
            )
            fallback_wt_path = await self._create_worktree_for_agent(fallback_agent, task)
            fallback_exec_cwd = self._resolve_execution_cwd(fallback_wt_path)
            try:
                result = await fallback_provider.execute(
                    fallback_agent,
                    task,
                    on_output=self._make_output_callback(task),
                    cwd=fallback_exec_cwd,
                )
                elapsed = _time.monotonic() - start_time
                fallback_agent.mark_completed()
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.error = None
                task.touch()
                self._finish_execution(exec_rec3, "completed", stdout=result)
                log.info(
                    "execution.completed_after_fallback",
                    task=task.id,
                    agent=fallback_agent.id,
                    provider=fallback_provider.info.name,
                    attempt=3,
                    elapsed_s=round(elapsed, 3),
                )
                # Persist generated output files into workspace root
                try:
                    from agentic_os.domain.workspace import get_workspace_root

                    ws_root = get_workspace_root()
                    if ws_root and _os.path.isdir(ws_root) and result and len(result) > 10:
                        _extract_and_persist_files(result, task, ws_root, fallback_provider.info.kind)
                except Exception:
                    pass

                await self._publish_completed(
                    fallback_agent, task, result, elapsed, recovered=True, fallback=True
                )
                return
            except Exception as exc3:
                self._finish_execution(exec_rec3, "failed", stderr=str(exc3), error=str(exc3))
                log.warning(
                    "execution.fallback_failed",
                    agent=fallback_agent.id,
                    task=task.id,
                    provider=fallback_provider.info.name,
                    attempt=3,
                    error=str(exc3),
                )
                agent.mark_failed()
                await self._fail_task(
                    fallback_agent, task, f"All {task.attempts} attempts failed. Last error: {exc3}"
                )
                return

        agent.mark_failed()
        await self._fail_task(
            agent,
            task,
            f"Execution failed after {task.attempts} attempt(s). No fallback provider available.",
        )

    def _pick_fallback_provider(self, current_name: str, role: str = ""):
        all_providers = self.providers.list_providers()
        required_caps = _ROLE_CAPABILITY_MAP.get(role, [])
        now = _time.monotonic()
        self._failed_providers = {
            name: ts
            for name, ts in self._failed_providers.items()
            if now - ts < _PROVIDER_COOLDOWN_S
        }
        candidates = []
        for p in all_providers:
            if p.name == "mock" or "mock" in p.kind:
                continue
            if p.name == current_name:
                continue
            if p.name in self._failed_providers:
                continue
            if required_caps:
                provider_caps = set(p.capabilities) if hasattr(p, "capabilities") else set()
                if provider_caps and not provider_caps.intersection(required_caps):
                    continue
            candidates.append(p)
        if not candidates:
            return None
        idx = self._provider_rr_idx % len(candidates)
        self._provider_rr_idx += 1
        return self.providers.get(candidates[idx].name)

    def _start_execution(self, agent: Agent, task: Task, provider, retry_count: int):
        if self.execution_log is None:
            return None
        strategy_name = type(provider).__name__
        if hasattr(provider, "strategy"):
            strategy_name = type(provider.strategy).__name__
        runtime_kind = provider.info.kind if hasattr(provider, "info") else ""
        cmd_preview = ""
        prompt_preview = ""
        try:
            if hasattr(provider, "strategy") and hasattr(provider, "bin_path"):
                cmd = provider.strategy.build_command(task, provider.bin_path)
                cmd_preview = " ".join(str(c) for c in cmd[:8])[:300]
                prompt_preview = provider.strategy.build_prompt(task)
        except Exception:
            pass
        return self.execution_log.start(
            task_id=task.id,
            agent_id=agent.id,
            provider=agent.provider,
            runtime=runtime_kind,
            strategy=strategy_name,
            mission_id=task.mission_id,
            command=cmd_preview,
            prompt_preview=prompt_preview,
            retry_count=retry_count,
        )

    def _finish_execution(self, exec_rec, status: str, **kwargs) -> None:
        if exec_rec is None or self.execution_log is None:
            return
        self.execution_log.finish(exec_rec.execution_id, status, **kwargs)

    async def _publish_completed(
        self,
        agent: Agent,
        task: Task,
        result: str,
        elapsed: float,
        recovered: bool = False,
        fallback: bool = False,
    ) -> None:
        await self.bus.publish(
            EventEnvelope(
                type="task.completed",
                source="orchestrator",
                topic="task.completed",
                payload={
                    "task_id": task.id,
                    "agent_id": agent.id,
                    "provider": agent.provider,
                    "result": result[:500] if result else "",
                    "elapsed_s": round(elapsed, 3),
                    "mission_id": task.mission_id,
                    "recovered": recovered,
                    "fallback": fallback,
                },
            )
        )
        await self.bus.publish(
            EventEnvelope(
                type="agent.completed",
                source="supervisor",
                topic=Topic.AGENT_COMPLETED.value,
                payload={
                    "agent_id": agent.id,
                    "task_id": task.id,
                    "result": result[:500] if result else "",
                    "elapsed_s": round(elapsed, 3),
                },
            )
        )

    async def _publish_failed(
        self,
        agent: Agent,
        task: Task,
        error: str,
    ) -> None:
        """Publish task.failed / agent.failed events (spec EventBus contract)."""
        await self.bus.publish(
            EventEnvelope(
                type="task.failed",
                source="orchestrator",
                topic="task.failed",
                payload={
                    "task_id": task.id,
                    "agent_id": agent.id,
                    "provider": agent.provider,
                    "error": (error or "")[:500],
                    "mission_id": task.mission_id,
                },
            )
        )
        await self.bus.publish(
            EventEnvelope(
                type="agent.failed",
                source="supervisor",
                topic=Topic.AGENT_FAILED.value if hasattr(Topic, "AGENT_FAILED") else "agent.failed",
                payload={
                    "agent_id": agent.id,
                    "task_id": task.id,
                    "error": (error or "")[:500],
                },
            )
        )

    async def _fail_task(self, agent: Agent, task: Task, error: str) -> None:
        elapsed = 0.0
        agent.mark_failed()
        task.status = TaskStatus.FAILED
        task.error = error
        task.touch()
        log.warning(
            "execution.abandoned",
            agent=agent.id,
            task=task.id,
            mission_id=task.mission_id,
            error=error,
            attempts=task.attempts,
        )
        await self.bus.publish(
            EventEnvelope(
                type="task.failed",
                source="orchestrator",
                topic="task.failed",
                payload={
                    "task_id": task.id,
                    "agent_id": agent.id,
                    "provider": agent.provider,
                    "error": error,
                    "elapsed_s": round(elapsed, 3),
                    "mission_id": task.mission_id,
                    "attempts": task.attempts,
                },
            )
        )
        await self.bus.publish(
            EventEnvelope(
                type="agent.failed",
                source="supervisor",
                topic=Topic.AGENT_FAILED.value,
                payload={
                    "agent_id": agent.id,
                    "task_id": task.id,
                    "reason": error,
                    "elapsed_s": round(elapsed, 3),
                },
            )
        )

    def _canonical_task(self, task_id: str | None) -> Task | None:
        if not task_id:
            return None
        return self.registry.get_task(task_id)

    async def _on_agent_completed(self, event: EventEnvelope) -> None:
        log.info("supervisor.completed", task=event.payload.get("task_id"))

    async def _on_agent_failed(self, event: EventEnvelope) -> None:
        log.warning("supervisor.failed", task=event.payload.get("task_id"))


def _default_roles() -> list[Role]:
    return [
        Role(name="planner", description="Decomposes requests into tasks."),
        Role(name="coding", description="Writes and edits code.", allowed_tools=["edit", "run"]),
        Role(name="research", description="Gathers information."),
        Role(name="reviewer", description="Reviews changes."),
        Role(name="devops", description="Builds, deploys, operates."),
    ]
