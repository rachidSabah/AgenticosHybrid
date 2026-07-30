"""Phase 15 — Autonomous Agent Ecosystem.

Builds on the existing Phase 1-14 architecture:
  Discovery → EventBus → BrainRegistry → Executive/Cognitive/Swarm
  → EcosystemManager (this layer) → DashboardBroadcaster → Store → UI

Components:
  - EcosystemController: long-running controller (subscriptions + lifecycle)
  - EcosystemManager: top-level coordinator (stats, health, refresh, optimize)
  - CapabilityGraph: live graph of Brain/Capability/Mission/Goal/Swarm nodes
  - CollaborationNetwork: trust + confidence graph between runtimes
  - EvolutionEngine: produces self-evolution recommendations
  - TaskMarketplace: global task market with deterministic bid selection

All additive — reuses EventBus, BrainRegistry, ExecutiveMemory, and
CognitiveMemory as canonical sources. Does NOT publish discovery events
or maintain a parallel registry.
"""

from agentic_os.core.ecosystem.capability_graph import CapabilityGraph
from agentic_os.core.ecosystem.collaboration_network import CollaborationNetwork
from agentic_os.core.ecosystem.controller import EcosystemController
from agentic_os.core.ecosystem.domain import (
    CollaborationLink,
    EcosystemHealth,
    EcosystemHealthLevel,
    EcosystemStats,
    EdgeType,
    EvolutionRecommendation,
    GraphEdge,
    GraphNode,
    MarketTask,
    NodeType,
    RecommendationType,
    TaskBid,
    TaskBidStrategy,
)
from agentic_os.core.ecosystem.evolution_engine import EvolutionEngine
from agentic_os.core.ecosystem.manager import EcosystemManager
from agentic_os.core.ecosystem.task_marketplace import TaskMarketplace

__all__ = [
    "CapabilityGraph",
    "CollaborationLink",
    "CollaborationNetwork",
    "EdgeType",
    "EcosystemController",
    "EcosystemHealth",
    "EcosystemHealthLevel",
    "EcosystemManager",
    "EcosystemStats",
    "EvolutionEngine",
    "EvolutionRecommendation",
    "GraphEdge",
    "GraphNode",
    "MarketTask",
    "NodeType",
    "RecommendationType",
    "TaskBid",
    "TaskBidStrategy",
    "TaskMarketplace",
]
