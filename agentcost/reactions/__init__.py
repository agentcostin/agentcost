"""
AgentCost Reactions — YAML-driven event automation.

Inspired by ComposioHQ/agent-orchestrator's reaction system,
adapted for cost management events.

Usage:
    from agentcost.reactions import ReactionEngine, get_reaction_engine

    # Start with defaults
    engine = get_reaction_engine()
    engine.start()  # subscribes to EventBus

    # Or load custom config
    engine = ReactionEngine(config_path="my-reactions.yaml")
    engine.register_action("custom-action", my_handler)
    engine.start()
"""

from .engine import (
    ReactionEngine,
    Reaction,
    ReactionResult,
    evaluate_condition,
    parse_duration,
    load_reactions,
    get_reaction_engine,
    EVENT_TO_REACTION,
)

__all__ = [
    "ReactionEngine",
    "Reaction",
    "ReactionResult",
    "evaluate_condition",
    "parse_duration",
    "load_reactions",
    "get_reaction_engine",
    "EVENT_TO_REACTION",
]
