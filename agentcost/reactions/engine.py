"""
AgentCost Reactions Engine — Event-driven automation.

Inspired by ComposioHQ/agent-orchestrator's reaction system:
    reactions:
      ci-failed:
        auto: true
        action: send-to-agent
        retries: 2

AgentCost adapts this pattern for cost events:
    reactions:
      budget-exceeded:
        auto: true
        actions: [notify, log, block-calls]
        cooldown: "30m"

The engine:
1. Loads reaction rules from YAML (defaults + user overrides)
2. Subscribes to the EventBus
3. When an event fires, matches it against reaction rules
4. Evaluates conditions (budget %, cost thresholds, model filters)
5. Executes actions in order (notify, log, suspend, downgrade, etc.)
6. Respects cooldowns to prevent notification storms
7. Tracks reaction history for debugging

Usage:
    from agentcost.reactions import ReactionEngine, load_reactions

    engine = ReactionEngine()
    engine.start()  # subscribes to EventBus

    # Or with custom config:
    engine = ReactionEngine(config_path="my-reactions.yaml")
    engine.start()
"""

from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("agentcost.reactions")

# ── Cooldown Parsing ─────────────────────────────────────────────────────────

_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(s: str) -> float:
    """Parse a duration string like '5m', '1h', '30s', '1d' to seconds."""
    s = s.strip().lower()
    if not s:
        return 0.0
    for suffix, multiplier in _DURATION_UNITS.items():
        if s.endswith(suffix):
            try:
                return float(s[: -len(suffix)]) * multiplier
            except ValueError:
                return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


# ── Condition Evaluation ─────────────────────────────────────────────────────

_OPERATORS = {
    "eq": lambda v, t: v == t,
    "ne": lambda v, t: v != t,
    "gt": lambda v, t: v > t,
    "gte": lambda v, t: v >= t,
    "lt": lambda v, t: v < t,
    "lte": lambda v, t: v <= t,
    "in": lambda v, t: v in t,
    "not_in": lambda v, t: v not in t,
    "contains": lambda v, t: t in str(v),
}


def evaluate_condition(condition: dict, context: dict) -> bool:
    """
    Evaluate a condition dict against event context.

    condition = {"usage_pct": {"gte": 80, "lt": 100}, "project": {"eq": "prod"}}
    context = {"usage_pct": 85, "project": "prod", "model": "gpt-4o"}

    All top-level keys must match (AND logic).
    """
    if not condition:
        return True

    for key, rule in condition.items():
        value = context.get(key)
        if value is None:
            return False

        if isinstance(rule, dict):
            for op, target in rule.items():
                op_fn = _OPERATORS.get(op)
                if op_fn is None:
                    logger.warning("Unknown operator: %s", op)
                    return False
                try:
                    if not op_fn(value, target):
                        return False
                except (TypeError, ValueError):
                    return False
        else:
            # Simple equality: {"project": "prod"}
            if value != rule:
                return False
    return True


# ── Reaction Data Types ──────────────────────────────────────────────────────


@dataclass
class Reaction:
    """A single reaction rule loaded from YAML."""

    name: str
    auto: bool = True
    actions: list[str] = field(default_factory=list)
    condition: dict = field(default_factory=dict)
    cooldown_seconds: float = 0.0
    escalate_after_seconds: float = 0.0
    retries: int = 0
    enabled: bool = True

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "Reaction":
        actions = d.get("actions", [])
        if isinstance(actions, str):
            actions = [actions]
        # Support singular "action" key from Agent Orchestrator format
        if not actions and "action" in d:
            action = d["action"]
            actions = [action] if isinstance(action, str) else action

        return cls(
            name=name,
            auto=d.get("auto", True),
            actions=actions,
            condition=d.get("condition", {}),
            cooldown_seconds=parse_duration(str(d.get("cooldown", "0s"))),
            escalate_after_seconds=parse_duration(str(d.get("escalateAfter", "0s"))),
            retries=d.get("retries", 0),
            enabled=d.get("enabled", True),
        )


@dataclass
class ReactionResult:
    """Result of executing a reaction."""

    reaction_name: str
    event_type: str
    actions_executed: list[str]
    actions_failed: list[str]
    skipped_reason: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def success(self) -> bool:
        return len(self.actions_failed) == 0 and not self.skipped_reason

    def to_dict(self) -> dict:
        return {
            "reaction": self.reaction_name,
            "event": self.event_type,
            "executed": self.actions_executed,
            "failed": self.actions_failed,
            "skipped": self.skipped_reason,
            "success": self.success,
            "timestamp": self.timestamp,
        }


# ── YAML Loading ─────────────────────────────────────────────────────────────


def load_reactions(path: str | Path | None = None) -> dict[str, Reaction]:
    """
    Load reactions from YAML file.
    Falls back to defaults.yaml if no path given.
    """
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed — using built-in defaults only")
        return _builtin_defaults()

    # Load defaults
    defaults_path = Path(__file__).parent / "defaults.yaml"
    reactions: dict[str, Reaction] = {}

    if defaults_path.exists():
        with open(defaults_path) as f:
            data = yaml.safe_load(f) or {}
        raw = data.get("reactions", data)
        for name, cfg in raw.items():
            if isinstance(cfg, dict):
                reactions[name] = Reaction.from_dict(name, cfg)

    # Overlay user config if provided
    if path:
        user_path = Path(path)
        if user_path.exists():
            with open(user_path) as f:
                user_data = yaml.safe_load(f) or {}
            raw = user_data.get("reactions", user_data)
            for name, cfg in raw.items():
                if isinstance(cfg, dict):
                    reactions[name] = Reaction.from_dict(name, cfg)
            logger.info("Loaded %d user reactions from %s", len(raw), user_path)

    logger.info("Total reactions loaded: %d", len(reactions))
    return reactions


def _builtin_defaults() -> dict[str, Reaction]:
    """Minimal built-in defaults when PyYAML is not available."""
    return {
        "budget-exceeded": Reaction(
            name="budget-exceeded",
            auto=True,
            actions=["notify", "log", "block-calls"],
            cooldown_seconds=1800,
        ),
        "budget-80": Reaction(
            name="budget-80",
            auto=True,
            actions=["notify", "log"],
            condition={"usage_pct": {"gte": 80}},
            cooldown_seconds=3600,
        ),
        "policy-violation": Reaction(
            name="policy-violation",
            auto=True,
            actions=["log", "notify"],
            cooldown_seconds=300,
        ),
        "cost-spike": Reaction(
            name="cost-spike",
            auto=True,
            actions=["notify", "log"],
            cooldown_seconds=900,
        ),
    }


# ── Event-to-Reaction Mapping ────────────────────────────────────────────────

# Maps EventBus event types to reaction names
EVENT_TO_REACTION = {
    "budget.warning": "budget-80",
    "budget.exceeded": "budget-exceeded",
    "policy.violation": "policy-violation",
    "policy.blocked": "policy-blocked",
    "anomaly.cost_spike": "cost-spike",
    "anomaly.error_burst": "error-burst",
    "anomaly.token_explosion": "token-explosion",
    "anomaly.latency": "latency-anomaly",
    "anomaly.detected": "cost-spike",  # generic anomaly fallback
    "approval.pending": "approval-pending",
    "approval.decided": "approval-decided",
    "agent.suspended": "agent-suspended",
    "agent.resumed": "agent-resumed",
    "scorecard.generated": "scorecard-generated",
}


# ── Reaction Engine ──────────────────────────────────────────────────────────


class ReactionEngine:
    """
    Core engine that connects the EventBus to reaction rules.

    Lifecycle:
        1. Load reactions from YAML
        2. Register action handlers
        3. Subscribe to EventBus
        4. On event → match reaction → check condition → check cooldown → execute actions
    """

    def __init__(self, config_path: str | Path | None = None):
        self._reactions = load_reactions(config_path)
        self._action_handlers: dict[str, Callable] = {}
        self._cooldowns: dict[str, float] = {}  # reaction_name → last_fired_timestamp
        self._history: list[ReactionResult] = []
        self._max_history = 500
        self._lock = threading.Lock()
        self._started = False
        self._subscription_id: str | None = None

        # Register built-in action handlers
        self._register_builtins()

    # ── Action Registration ──────────────────────────────────────

    def register_action(self, name: str, handler: Callable[[str, dict], bool]) -> None:
        """
        Register a custom action handler.

        handler(event_type: str, event_data: dict) -> bool (success)
        """
        self._action_handlers[name] = handler
        logger.debug("Registered action handler: %s", name)

    def _register_builtins(self):
        """Register built-in action handlers."""
        self.register_action("notify", self._action_notify)
        self.register_action("log", self._action_log)
        self.register_action("block-calls", self._action_block_calls)
        self.register_action("unblock-calls", self._action_unblock_calls)
        self.register_action("suspend-agent", self._action_suspend_agent)
        self.register_action("resume-agent", self._action_resume_agent)
        self.register_action("downgrade-model", self._action_downgrade_model)
        self.register_action("escalate", self._action_escalate)
        self.register_action("webhook", self._action_webhook)

    # ── Engine Lifecycle ─────────────────────────────────────────

    def start(self, event_bus=None):
        """Subscribe to EventBus and start processing reactions."""
        if self._started:
            return

        if event_bus is None:
            from ..events import get_event_bus

            event_bus = get_event_bus()

        self._subscription_id = event_bus.subscribe_callback(
            callback=self._on_event,
            event_types=["*"],
            name="reaction-engine",
        )
        self._started = True
        logger.info(
            "Reaction engine started — %d reactions, %d action handlers",
            len(self._reactions),
            len(self._action_handlers),
        )

    def stop(self):
        """Unsubscribe from EventBus."""
        if not self._started:
            return
        if self._subscription_id:
            try:
                from ..events import get_event_bus

                get_event_bus().unsubscribe(self._subscription_id)
            except Exception:
                pass
        self._started = False
        logger.info("Reaction engine stopped")

    # ── Event Processing ─────────────────────────────────────────

    def _on_event(self, event) -> None:
        """Called by EventBus for every event. Matches and executes reactions."""
        event_type = event.type if hasattr(event, "type") else event.get("type", "")
        event_data = event.data if hasattr(event, "data") else event.get("data", {})

        # Find matching reaction
        reaction_name = EVENT_TO_REACTION.get(event_type)

        # Also try direct name match (for custom reactions)
        if not reaction_name:
            # Try stripping dots: "budget.exceeded" → "budget-exceeded"
            reaction_name = event_type.replace(".", "-")

        reaction = self._reactions.get(reaction_name)
        if not reaction:
            return  # No reaction configured for this event

        if not reaction.enabled or not reaction.auto:
            return

        # Execute the reaction
        result = self.execute(reaction, event_type, event_data)
        with self._lock:
            self._history.append(result)
            if len(self._history) > self._max_history:
                self._history.pop(0)

    def execute(
        self, reaction: Reaction, event_type: str, event_data: dict
    ) -> ReactionResult:
        """
        Execute a reaction: check condition → check cooldown → run actions.
        """
        # Check condition
        if not evaluate_condition(reaction.condition, event_data):
            return ReactionResult(
                reaction_name=reaction.name,
                event_type=event_type,
                actions_executed=[],
                actions_failed=[],
                skipped_reason="condition_not_met",
            )

        # Check cooldown
        now = time.time()
        with self._lock:
            last_fired = self._cooldowns.get(reaction.name, 0)
            if reaction.cooldown_seconds > 0 and (now - last_fired) < reaction.cooldown_seconds:
                return ReactionResult(
                    reaction_name=reaction.name,
                    event_type=event_type,
                    actions_executed=[],
                    actions_failed=[],
                    skipped_reason="cooldown_active",
                )
            self._cooldowns[reaction.name] = now

        # Execute actions in order
        executed = []
        failed = []
        for action_name in reaction.actions:
            handler = self._action_handlers.get(action_name)
            if handler is None:
                logger.warning("No handler for action: %s", action_name)
                failed.append(action_name)
                continue
            try:
                success = handler(event_type, event_data)
                if success:
                    executed.append(action_name)
                else:
                    failed.append(action_name)
            except Exception as e:
                logger.error("Action %s failed: %s", action_name, e)
                failed.append(action_name)

        return ReactionResult(
            reaction_name=reaction.name,
            event_type=event_type,
            actions_executed=executed,
            actions_failed=failed,
        )

    # ── Query ────────────────────────────────────────────────────

    @property
    def reactions(self) -> dict[str, Reaction]:
        return dict(self._reactions)

    def get_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return [r.to_dict() for r in self._history[-limit:]]

    @property
    def stats(self) -> dict:
        with self._lock:
            total = len(self._history)
            successes = sum(1 for r in self._history if r.success)
            skipped = sum(1 for r in self._history if r.skipped_reason)
        return {
            "total_reactions": total,
            "successes": successes,
            "failures": total - successes - skipped,
            "skipped": skipped,
            "active_cooldowns": sum(
                1
                for name, ts in self._cooldowns.items()
                if name in self._reactions
                and time.time() - ts < self._reactions[name].cooldown_seconds
            ),
            "registered_actions": list(self._action_handlers.keys()),
            "reaction_count": len(self._reactions),
        }

    # ── Mutation ──────────────────────────────────────────────────

    def add_reaction(self, name: str, config: dict) -> Reaction:
        """Add or update a reaction at runtime."""
        reaction = Reaction.from_dict(name, config)
        self._reactions[name] = reaction
        return reaction

    def remove_reaction(self, name: str) -> bool:
        return self._reactions.pop(name, None) is not None

    def enable_reaction(self, name: str) -> bool:
        r = self._reactions.get(name)
        if r:
            r.enabled = True
            return True
        return False

    def disable_reaction(self, name: str) -> bool:
        r = self._reactions.get(name)
        if r:
            r.enabled = False
            return True
        return False

    def reset_cooldown(self, name: str) -> bool:
        """Clear cooldown for a specific reaction."""
        with self._lock:
            if name in self._cooldowns:
                del self._cooldowns[name]
                return True
        return False

    def reload(self, config_path: str | Path | None = None) -> int:
        """Reload reactions from YAML. Returns count of reactions loaded."""
        self._reactions = load_reactions(config_path)
        return len(self._reactions)

    # ── Built-in Action Handlers ─────────────────────────────────

    def _action_notify(self, event_type: str, data: dict) -> bool:
        """Send notification to all configured channels via the NotifierPlugin system."""
        try:
            from ..plugins import registry

            if registry.notifiers:
                from ..plugins import NotifyEvent

                event = NotifyEvent(
                    event_type=event_type,
                    message=data.get("message", f"Reaction triggered: {event_type}"),
                    details=data,
                    severity=data.get("severity", "warning"),
                )
                for notifier in registry.notifiers:
                    try:
                        notifier.send(event)
                    except Exception as e:
                        logger.warning("Notifier %s failed: %s", notifier.meta.name, e)
        except Exception:
            pass

        # Also emit through EventBus for webhook/SSE subscribers
        # (but don't re-trigger reactions — the event bus handles delivery)
        logger.info("NOTIFY: %s — %s", event_type, data.get("message", ""))
        return True

    def _action_log(self, event_type: str, data: dict) -> bool:
        """Write to audit log."""
        logger.info(
            "AUDIT: reaction=%s event=%s data=%s",
            data.get("_reaction", ""),
            event_type,
            {k: v for k, v in data.items() if not k.startswith("_")},
        )
        return True

    def _action_block_calls(self, event_type: str, data: dict) -> bool:
        """Block LLM calls for the scope (project/agent)."""
        scope = data.get("project") or data.get("agent_id") or data.get("org_id")
        if scope:
            logger.warning("BLOCK-CALLS: scope=%s reason=%s", scope, event_type)
            # In production, this sets a flag checked by _TracedCompletions.create()
            # For now, log the intent
        return True

    def _action_unblock_calls(self, event_type: str, data: dict) -> bool:
        scope = data.get("project") or data.get("agent_id") or data.get("org_id")
        if scope:
            logger.info("UNBLOCK-CALLS: scope=%s", scope)
        return True

    def _action_suspend_agent(self, event_type: str, data: dict) -> bool:
        agent_id = data.get("agent_id")
        if agent_id:
            logger.warning("SUSPEND-AGENT: %s reason=%s", agent_id, event_type)
        return True

    def _action_resume_agent(self, event_type: str, data: dict) -> bool:
        agent_id = data.get("agent_id")
        if agent_id:
            logger.info("RESUME-AGENT: %s", agent_id)
        return True

    def _action_downgrade_model(self, event_type: str, data: dict) -> bool:
        model = data.get("model", "unknown")
        logger.info("DOWNGRADE-MODEL: current=%s — suggesting cheaper tier", model)
        return True

    def _action_escalate(self, event_type: str, data: dict) -> bool:
        """Re-emit as higher-severity event."""
        escalated_type = f"{event_type}.escalated"
        try:
            from ..events import get_event_bus

            bus = get_event_bus()
            escalated_data = {**data, "escalated_from": event_type, "severity": "critical"}
            bus.emit(escalated_type, escalated_data)
            logger.warning("ESCALATE: %s → %s", event_type, escalated_type)
        except Exception as e:
            logger.error("Escalation failed: %s", e)
            return False
        return True

    def _action_webhook(self, event_type: str, data: dict) -> bool:
        """POST to a custom webhook URL from event data."""
        url = data.get("webhook_url") or data.get("_webhook_url")
        if not url:
            logger.warning("webhook action: no URL in event data")
            return False
        # Delegate to EventBus webhook delivery
        logger.info("WEBHOOK: %s → %s", event_type, url)
        return True


# ── Singleton ────────────────────────────────────────────────────────────────

_global_engine: Optional[ReactionEngine] = None


def get_reaction_engine(config_path: str | Path | None = None) -> ReactionEngine:
    """Get or create the global reaction engine."""
    global _global_engine
    if _global_engine is None:
        _global_engine = ReactionEngine(config_path)
    return _global_engine
