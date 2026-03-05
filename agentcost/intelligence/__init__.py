"""
AgentCost Intelligence Layer — Phase 3

Cost-aware decision making inspired by DeerFlow's configuration-driven architecture.

Components:
    TierRegistry       — classify models into economy/standard/premium tiers
    TokenAnalyzer      — context efficiency scoring and waste detection
    BudgetGate         — pre-execution budget checks for workflow nodes
    ComplexityRouter   — auto-classify prompts and route to appropriate tier
"""

from .tier_registry import (
    CostTier,
    TierRegistry,
    get_tier_registry,
)
from .token_analyzer import TokenAnalyzer, EfficiencyReport
from .budget_gate import BudgetGate, GateDecision
from .complexity_router import (
    ComplexityLevel,
    ComplexityRouter,
    ClassificationResult,
)

__all__ = [
    "CostTier",
    "TierRegistry",
    "get_tier_registry",
    "TokenAnalyzer",
    "EfficiencyReport",
    "BudgetGate",
    "GateDecision",
    "ComplexityLevel",
    "ComplexityRouter",
    "ClassificationResult",
]
