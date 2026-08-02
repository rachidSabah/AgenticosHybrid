"""Executive Intelligence Layer.

Builds on the existing production pipeline:
  Discovery → EventBus → BrainRegistry → DashboardBroadcaster → Store → UI

This layer adds:
  - ExecutiveController: long-running executive intelligence
  - GoalManager: goal lifecycle management
  - DecisionEngine: intelligent runtime selection
  - ReflectionEngine: post-mission analysis
  - ExecutiveMemory: semantic indexes over existing MemoryManager
"""

from agentic_os.core.executive.controller import ExecutiveController
from agentic_os.core.executive.decision_engine import DecisionEngine
from agentic_os.core.executive.domain import (
    Decision,
    Goal,
    GoalDependency,
    GoalPriority,
    GoalResult,
    GoalStatus,
    Reflection,
)
from agentic_os.core.executive.goal_manager import GoalManager
from agentic_os.core.executive.memory import ExecutiveMemory
from agentic_os.core.executive.reflection_engine import ReflectionEngine

__all__ = [
    "Decision",
    "DecisionEngine",
    "ExecutiveController",
    "ExecutiveMemory",
    "Goal",
    "GoalDependency",
    "GoalManager",
    "GoalPriority",
    "GoalResult",
    "GoalStatus",
    "Reflection",
    "ReflectionEngine",
]
