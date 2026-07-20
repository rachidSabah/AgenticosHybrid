"""Learning & Optimization Engine — core implementation."""

from agentic_os.core.learning.benchmark import BenchmarkManager
from agentic_os.core.learning.cost import CostOptimizer
from agentic_os.core.learning.evaluation import EvaluationEngine
from agentic_os.core.learning.experiment import ExperimentManager
from agentic_os.core.learning.history import HistoricalAnalyzer
from agentic_os.core.learning.manager import LearningManager
from agentic_os.core.learning.model_selection import ModelSelectionEngine
from agentic_os.core.learning.optimization import OptimizationManager
from agentic_os.core.learning.performance import PerformanceOptimizer
from agentic_os.core.learning.policy import PolicyEngine
from agentic_os.core.learning.prompt import PromptOptimizationManager
from agentic_os.core.learning.publisher import LearningEventPublisher
from agentic_os.core.learning.quality import QualityOptimizer
from agentic_os.core.learning.recommendation import RecommendationEngine
from agentic_os.core.learning.routing import RoutingOptimizer
from agentic_os.core.learning.strategy import StrategyManager
from agentic_os.core.learning.swarm import SwarmOptimizer
from agentic_os.core.learning.telemetry import LearningTelemetry

__all__ = [
    "LearningManager",
    "OptimizationManager",
    "BenchmarkManager",
    "StrategyManager",
    "RecommendationEngine",
    "HistoricalAnalyzer",
    "RoutingOptimizer",
    "CostOptimizer",
    "PerformanceOptimizer",
    "QualityOptimizer",
    "SwarmOptimizer",
    "PromptOptimizationManager",
    "PolicyEngine",
    "EvaluationEngine",
    "ExperimentManager",
    "ModelSelectionEngine",
    "LearningTelemetry",
    "LearningEventPublisher",
]
