"""Pluggable strategies for decomposition and consensus."""

from agentic_os.core.orchestration.strategies.consensus import (
    SimpleMajorityConsensus,
    WeightedConsensus,
)
from agentic_os.core.orchestration.strategies.decomposition import (
    LLMDecomposition,
    RuleBasedDecomposition,
    TemplateBasedDecomposition,
)

__all__ = [
    "RuleBasedDecomposition",
    "TemplateBasedDecomposition",
    "LLMDecomposition",
    "SimpleMajorityConsensus",
    "WeightedConsensus",
]
