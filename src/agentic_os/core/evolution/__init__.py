"""Phase 17 — Autonomous Agent Evolution, Self-Construction & Continuous Improvement.

Builds on the existing Phase 1-16 architecture:
  Discovery → EventBus → BrainRegistry → Executive/Cognitive/Swarm/Ecosystem/Cluster
  → EvolutionController (this layer) → DashboardBroadcaster → Store → UI

This layer turns the platform into a continuously self-improving system
that can:
  - Analyze its own performance + capability gaps
  - Propose improvements with safety validation
  - Generate plans for new capabilities/agents/workflows (plans, not code)
  - Schedule + apply improvements with rollback support
  - Synthesize knowledge from historical data

All additive — reuses Phase 15 EvolutionEngine (recommendations),
Phase 12 ImprovementPlanner (cognitive proposals), Phase 11
ExecutiveMemory (reflections/decisions) as input sources. Does NOT
replace any existing engine.
"""

from agentic_os.core.evolution.advisors import (
    PerformanceOptimizer,
    RefactoringAdvisor,
)
from agentic_os.core.evolution.capability_expansion_engine import (
    CapabilityExpansionEngine,
)
from agentic_os.core.evolution.code_generation_planner import CodeGenerationPlanner
from agentic_os.core.evolution.controller import EvolutionController
from agentic_os.core.evolution.domain import (
    EvolutionStatistics,
    GenerationPlan,
    GenerationTargetType,
    ImprovementPriority,
    ImprovementProposal,
    ImprovementStatus,
    ImprovementType,
    KnowledgeSynthesis,
    SafetyValidationReport,
    SystemReadiness,
    SystemReadinessLevel,
    ValidationCheck,
    ValidationCheckResult,
    ValidationCheckType,
)
from agentic_os.core.evolution.improvement_engine import ImprovementEngine
from agentic_os.core.evolution.manager import EvolutionManager
from agentic_os.core.evolution.regression_guard import RegressionGuard
from agentic_os.core.evolution.review_synthesis import (
    AutonomousReviewer,
    KnowledgeSynthesizer,
)
from agentic_os.core.evolution.safety_validator import SafetyValidator
from agentic_os.core.evolution.scheduler import ImprovementScheduler

__all__ = [
    "AutonomousReviewer",
    "CapabilityExpansionEngine",
    "CodeGenerationPlanner",
    "EvolutionController",
    "EvolutionManager",
    "EvolutionStatistics",
    "GenerationPlan",
    "GenerationTargetType",
    "ImprovementEngine",
    "ImprovementPriority",
    "ImprovementProposal",
    "ImprovementScheduler",
    "ImprovementStatus",
    "ImprovementType",
    "KnowledgeSynthesis",
    "KnowledgeSynthesizer",
    "PerformanceOptimizer",
    "RefactoringAdvisor",
    "RegressionGuard",
    "SafetyValidationReport",
    "SafetyValidator",
    "SystemReadiness",
    "SystemReadinessLevel",
    "ValidationCheck",
    "ValidationCheckResult",
    "ValidationCheckType",
]
