"""Goal decomposition strategies — break high-level goals into subtasks."""

from dataclasses import dataclass, field

from agentic_os.domain.orchestration import AgentTask, OrchestrationGoal
from agentic_os.ports.orchestration import DecompositionStrategy


@dataclass
class RuleBasedDecomposition(DecompositionStrategy):
    """Decomposes goals using keyword matching against task templates.

    Default implementation matches goal title keywords against known patterns
    and creates 2-5 subtasks with appropriate dependency ordering.
    """

    name: str = "rule-based"

    _templates: dict[str, tuple[tuple[str, str, list[str]], ...]] = field(
        default_factory=lambda: {
            "code": (
                ("Analyze requirements", "Understand the problem and constraints", []),
                ("Design solution", "Architect the solution approach", ["Analyze requirements"]),
                ("Implement changes", "Write the code changes", ["Design solution"]),
                ("Test and verify", "Run tests to verify correctness", ["Implement changes"]),
            ),
            "research": (
                ("Define research scope", "Clarify the research question and boundaries", []),
                (
                    "Gather information",
                    "Collect relevant data and sources",
                    ["Define research scope"],
                ),
                (
                    "Analyze findings",
                    "Synthesize and analyze collected information",
                    ["Gather information"],
                ),
                (
                    "Summarize results",
                    "Produce a concise summary of findings",
                    ["Analyze findings"],
                ),
            ),
            "deploy": (
                ("Prepare artifacts", "Build and package deployment artifacts", []),
                ("Stage deployment", "Deploy to staging environment", ["Prepare artifacts"]),
                ("Run smoke tests", "Verify deployment with smoke tests", ["Stage deployment"]),
                ("Promote to production", "Deploy to production", ["Run smoke tests"]),
            ),
            "test": (
                ("Identify test scenarios", "Determine what to test and test data", []),
                ("Write test cases", "Implement the test cases", ["Identify test scenarios"]),
                ("Execute tests", "Run the test suite", ["Write test cases"]),
                ("Report results", "Document test outcomes", ["Execute tests"]),
            ),
            "analyze": (
                ("Collect data", "Gather necessary data sources", []),
                ("Process data", "Clean and transform the data", ["Collect data"]),
                ("Analyze", "Perform the analysis", ["Process data"]),
                ("Report", "Document findings and insights", ["Analyze"]),
            ),
        }
    )

    async def decompose(self, goal: OrchestrationGoal) -> list[AgentTask]:
        """Decompose a goal into subtasks by matching keywords in the title."""
        title_lower = goal.title.lower()
        tasks: list[AgentTask] = []

        # Find matching template
        template_keywords = {
            "code": ("code", "implement", "write", "program", "build", "develop", "feature"),
            "research": ("research", "investigate", "explore", "study", "learn", "understand"),
            "deploy": ("deploy", "release", "ship", "publish", "rollout", "launch"),
            "test": ("test", "verify", "validate", "check", "qa", "quality"),
            "analyze": ("analyze", "analysis", "evaluate", "assess", "review", "audit"),
        }

        matched_template = "analyze"  # default fallback
        for tmpl, keywords in template_keywords.items():
            if any(kw in title_lower for kw in keywords):
                matched_template = tmpl
                break

        template = self._templates.get(matched_template, self._templates["analyze"])

        for title, description, dependencies in template:
            task = AgentTask(
                goal_id=goal.id,
                title=title,
                description=description,
                depends_on=tuple(dependencies),
                input_data={
                    "source_goal": goal.title,
                    "context": dict(goal.context),
                },
            )
            tasks.append(task)

        return tasks


@dataclass
class TemplateBasedDecomposition(DecompositionStrategy):
    """Decomposes goals using predefined named templates."""

    name: str = "template-based"

    _templates: dict[str, tuple[tuple[str, str, list[str]], ...]] = field(default_factory=dict)

    def register_template(self, name: str, tasks: tuple[tuple[str, str, list[str]], ...]) -> None:
        """Register a named decomposition template."""
        self._templates[name] = tasks

    async def decompose(self, goal: OrchestrationGoal) -> list[AgentTask]:
        """Decompose using a template looked up from goal context."""
        template_name = goal.context.get("template", goal.title.lower().replace(" ", "_"))
        template = self._templates.get(template_name)

        if template is None:
            # Fall back to rule-based
            fallback = RuleBasedDecomposition()
            return await fallback.decompose(goal)

        tasks: list[AgentTask] = []
        for title, description, dependencies in template:
            task = AgentTask(
                goal_id=goal.id,
                title=title,
                description=description,
                depends_on=tuple(dependencies),
                input_data={
                    "source_goal": goal.title,
                    "template": template_name,
                    "context": dict(goal.context),
                },
            )
            tasks.append(task)

        return tasks


@dataclass
class LLMDecomposition(DecompositionStrategy):
    """LLM-based decomposition — stub for future integration.

    Currently returns a single generic task. When connected to an LLM
    provider, this will use natural language understanding to decompose
    goals into appropriate subtasks.
    """

    name: str = "llm"

    async def decompose(self, goal: OrchestrationGoal) -> list[AgentTask]:
        """Stub: returns a single composite task ready for LLM decomposition."""
        return [
            AgentTask(
                goal_id=goal.id,
                title=goal.title,
                description=goal.description or f"Execute: {goal.title}",
                input_data={
                    "source_goal": goal.title,
                    "context": dict(goal.context),
                    "llm_decomposition": True,
                },
            ),
        ]
