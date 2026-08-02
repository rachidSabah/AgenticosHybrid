"""Cognitive Intelligence Layer (Phase 12).

Builds on the existing production pipeline:
  Discovery → BrainRegistry → EventBus → Executive Layer → Mission Planner

This layer adds:
  - CognitiveController: long-running cognitive intelligence
  - WorldModel: continuously updated system understanding
  - KnowledgeGraph: entity relationships + graph traversal
  - StrategicPlanner: strategic recommendations
  - PredictionEngine: mission outcome predictions
  - ExperienceReplay: pattern extraction from completed missions
  - EvaluationEngine: continuous self-evaluation
  - ImprovementPlanner: autonomous improvement proposals
  - ObjectiveManager: long-term objective lifecycle
  - CognitiveScheduler: background cognitive cycle
  - CognitiveMemory: cognitive-specific indexes
"""

from agentic_os.core.cognitive.controller import CognitiveController
from agentic_os.core.cognitive.domain import (
    EvaluationScore,
    ExperienceRecord,
    ImprovementProposal,
    LongTermObjective,
    ObjectivePriority,
    ObjectiveStatus,
    Prediction,
)
from agentic_os.core.cognitive.evaluation_engine import EvaluationEngine
from agentic_os.core.cognitive.experience_replay import ExperienceReplay
from agentic_os.core.cognitive.improvement_planner import ImprovementPlanner
from agentic_os.core.cognitive.knowledge_graph import KnowledgeGraph
from agentic_os.core.cognitive.memory import CognitiveMemory
from agentic_os.core.cognitive.objective_manager import ObjectiveManager
from agentic_os.core.cognitive.prediction_engine import PredictionEngine
from agentic_os.core.cognitive.scheduler import CognitiveScheduler
from agentic_os.core.cognitive.strategic_planner import StrategicPlanner
from agentic_os.core.cognitive.world_model import WorldModel

__all__ = [
    "CognitiveController",
    "CognitiveMemory",
    "CognitiveScheduler",
    "EvaluationEngine",
    "EvaluationScore",
    "ExperienceRecord",
    "ExperienceReplay",
    "ImprovementPlanner",
    "ImprovementProposal",
    "KnowledgeGraph",
    "LongTermObjective",
    "ObjectiveManager",
    "ObjectivePriority",
    "ObjectiveStatus",
    "Prediction",
    "PredictionEngine",
    "StrategicPlanner",
    "WorldModel",
]
