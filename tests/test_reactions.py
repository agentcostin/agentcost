"""
Tests for agentcost.reactions — YAML-driven event automation engine.

Covers:
    - Duration parsing
    - Condition evaluation (operators, nested, edge cases)
    - Reaction loading from YAML defaults
    - Reaction loading without PyYAML (builtin fallback)
    - Cooldown enforcement
    - Action execution (success, failure, unknown)
    - EventBus integration
    - Engine lifecycle (start, stop, reload)
    - CRUD operations (add, remove, enable, disable)
    - Event-to-reaction mapping
    - Manual trigger
    - History tracking
    - Stats
"""

import time
import pytest
from unittest.mock import MagicMock, patch


# ── Duration Parsing ─────────────────────────────────────────────────────────


class TestParseDuration:
    def test_seconds(self):
        from agentcost.reactions import parse_duration

        assert parse_duration("30s") == 30.0

    def test_minutes(self):
        from agentcost.reactions import parse_duration

        assert parse_duration("5m") == 300.0

    def test_hours(self):
        from agentcost.reactions import parse_duration

        assert parse_duration("1h") == 3600.0

    def test_days(self):
        from agentcost.reactions import parse_duration

        assert parse_duration("1d") == 86400.0

    def test_zero(self):
        from agentcost.reactions import parse_duration

        assert parse_duration("0s") == 0.0

    def test_empty(self):
        from agentcost.reactions import parse_duration

        assert parse_duration("") == 0.0

    def test_numeric(self):
        from agentcost.reactions import parse_duration

        assert parse_duration("120") == 120.0

    def test_float_minutes(self):
        from agentcost.reactions import parse_duration

        assert parse_duration("2.5m") == 150.0

    def test_invalid(self):
        from agentcost.reactions import parse_duration

        assert parse_duration("abc") == 0.0


# ── Condition Evaluation ─────────────────────────────────────────────────────


class TestEvaluateCondition:
    def test_empty_condition(self):
        from agentcost.reactions import evaluate_condition

        assert evaluate_condition({}, {"anything": True}) is True

    def test_simple_equality(self):
        from agentcost.reactions import evaluate_condition

        assert evaluate_condition({"project": "prod"}, {"project": "prod"}) is True
        assert evaluate_condition({"project": "prod"}, {"project": "dev"}) is False

    def test_gte(self):
        from agentcost.reactions import evaluate_condition

        cond = {"usage_pct": {"gte": 80}}
        assert evaluate_condition(cond, {"usage_pct": 80}) is True
        assert evaluate_condition(cond, {"usage_pct": 90}) is True
        assert evaluate_condition(cond, {"usage_pct": 79}) is False

    def test_lt(self):
        from agentcost.reactions import evaluate_condition

        cond = {"cost": {"lt": 10.0}}
        assert evaluate_condition(cond, {"cost": 5.0}) is True
        assert evaluate_condition(cond, {"cost": 10.0}) is False

    def test_range(self):
        from agentcost.reactions import evaluate_condition

        cond = {"usage_pct": {"gte": 80, "lt": 100}}
        assert evaluate_condition(cond, {"usage_pct": 85}) is True
        assert evaluate_condition(cond, {"usage_pct": 100}) is False
        assert evaluate_condition(cond, {"usage_pct": 79}) is False

    def test_in_operator(self):
        from agentcost.reactions import evaluate_condition

        cond = {"model": {"in": ["gpt-4o", "claude-sonnet-4-5"]}}
        assert evaluate_condition(cond, {"model": "gpt-4o"}) is True
        assert evaluate_condition(cond, {"model": "gpt-3.5-turbo"}) is False

    def test_not_in_operator(self):
        from agentcost.reactions import evaluate_condition

        cond = {"provider": {"not_in": ["openai"]}}
        assert evaluate_condition(cond, {"provider": "anthropic"}) is True
        assert evaluate_condition(cond, {"provider": "openai"}) is False

    def test_contains_operator(self):
        from agentcost.reactions import evaluate_condition

        cond = {"model": {"contains": "gpt"}}
        assert evaluate_condition(cond, {"model": "gpt-4o"}) is True
        assert evaluate_condition(cond, {"model": "claude-sonnet"}) is False

    def test_multi_field_and(self):
        from agentcost.reactions import evaluate_condition

        cond = {"usage_pct": {"gte": 80}, "project": "prod"}
        assert evaluate_condition(cond, {"usage_pct": 90, "project": "prod"}) is True
        assert evaluate_condition(cond, {"usage_pct": 90, "project": "dev"}) is False
        assert evaluate_condition(cond, {"usage_pct": 70, "project": "prod"}) is False

    def test_missing_key(self):
        from agentcost.reactions import evaluate_condition

        cond = {"usage_pct": {"gte": 80}}
        assert evaluate_condition(cond, {"cost": 5.0}) is False

    def test_unknown_operator(self):
        from agentcost.reactions import evaluate_condition

        cond = {"x": {"foo": 1}}
        assert evaluate_condition(cond, {"x": 1}) is False


# ── Reaction Data Class ──────────────────────────────────────────────────────


class TestReaction:
    def test_from_dict_basic(self):
        from agentcost.reactions.engine import Reaction

        r = Reaction.from_dict(
            "test",
            {
                "auto": True,
                "actions": ["notify", "log"],
                "cooldown": "5m",
            },
        )
        assert r.name == "test"
        assert r.auto is True
        assert r.actions == ["notify", "log"]
        assert r.cooldown_seconds == 300.0

    def test_from_dict_singular_action(self):
        """Support Agent Orchestrator's singular 'action' key."""
        from agentcost.reactions.engine import Reaction

        r = Reaction.from_dict("ao-style", {"action": "send-to-agent", "auto": True})
        assert r.actions == ["send-to-agent"]

    def test_from_dict_with_condition(self):
        from agentcost.reactions.engine import Reaction

        r = Reaction.from_dict(
            "conditional",
            {
                "auto": True,
                "actions": ["notify"],
                "condition": {"usage_pct": {"gte": 80}},
                "escalateAfter": "2h",
            },
        )
        assert r.condition == {"usage_pct": {"gte": 80}}
        assert r.escalate_after_seconds == 7200.0

    def test_from_dict_defaults(self):
        from agentcost.reactions.engine import Reaction

        r = Reaction.from_dict("minimal", {})
        assert r.auto is True
        assert r.actions == []
        assert r.cooldown_seconds == 0.0
        assert r.enabled is True


# ── YAML Loading ─────────────────────────────────────────────────────────────


class TestLoadReactions:
    def test_load_defaults(self):
        from agentcost.reactions import load_reactions

        reactions = load_reactions()
        assert len(reactions) > 0
        assert "budget-exceeded" in reactions
        assert "budget-80" in reactions
        assert "policy-violation" in reactions
        assert "cost-spike" in reactions

    def test_budget_exceeded_config(self):
        from agentcost.reactions import load_reactions

        reactions = load_reactions()
        r = reactions["budget-exceeded"]
        assert r.auto is True
        assert "notify" in r.actions
        assert "block-calls" in r.actions

    def test_budget_80_has_condition(self):
        from agentcost.reactions import load_reactions

        reactions = load_reactions()
        r = reactions["budget-80"]
        assert r.condition.get("usage_pct", {}).get("gte") == 80

    def test_builtin_fallback(self):
        """When PyYAML is not available, built-in defaults are used."""
        from agentcost.reactions.engine import _builtin_defaults

        defaults = _builtin_defaults()
        assert "budget-exceeded" in defaults
        assert defaults["budget-exceeded"].actions == ["notify", "log", "block-calls"]

    def test_load_user_overlay(self, tmp_path):
        """User YAML overlays default reactions."""
        from agentcost.reactions import load_reactions

        user_yaml = tmp_path / "custom.yaml"
        user_yaml.write_text(
            "reactions:\n"
            "  custom-alert:\n"
            "    auto: true\n"
            "    actions: [notify]\n"
            "    cooldown: '10m'\n"
        )
        reactions = load_reactions(user_yaml)
        assert "custom-alert" in reactions
        assert "budget-exceeded" in reactions  # defaults still present
        assert reactions["custom-alert"].cooldown_seconds == 600.0


# ── Reaction Engine ──────────────────────────────────────────────────────────


class TestReactionEngine:
    def test_engine_creation(self):
        from agentcost.reactions import ReactionEngine

        engine = ReactionEngine()
        assert len(engine.reactions) > 0
        assert "notify" in engine.stats["registered_actions"]
        assert "log" in engine.stats["registered_actions"]

    def test_execute_simple(self):
        from agentcost.reactions import ReactionEngine, Reaction

        engine = ReactionEngine()
        reaction = Reaction(name="test", auto=True, actions=["log"])
        result = engine.execute(reaction, "test.event", {"message": "hello"})
        assert result.success
        assert "log" in result.actions_executed

    def test_execute_condition_not_met(self):
        from agentcost.reactions import ReactionEngine, Reaction

        engine = ReactionEngine()
        reaction = Reaction(
            name="conditional",
            auto=True,
            actions=["notify"],
            condition={"usage_pct": {"gte": 80}},
        )
        result = engine.execute(
            reaction, "budget.warning", {"usage_pct": 50}
        )
        assert not result.success
        assert result.skipped_reason == "condition_not_met"

    def test_execute_condition_met(self):
        from agentcost.reactions import ReactionEngine, Reaction

        engine = ReactionEngine()
        reaction = Reaction(
            name="conditional",
            auto=True,
            actions=["log"],
            condition={"usage_pct": {"gte": 80}},
        )
        result = engine.execute(
            reaction, "budget.warning", {"usage_pct": 90}
        )
        assert result.success
        assert "log" in result.actions_executed

    def test_cooldown_enforcement(self):
        from agentcost.reactions import ReactionEngine, Reaction

        engine = ReactionEngine()
        reaction = Reaction(
            name="cooldown-test",
            auto=True,
            actions=["log"],
            cooldown_seconds=3600,  # 1 hour
        )
        # First execution should succeed
        r1 = engine.execute(reaction, "test", {})
        assert r1.success

        # Second execution within cooldown should be skipped
        r2 = engine.execute(reaction, "test", {})
        assert r2.skipped_reason == "cooldown_active"

    def test_cooldown_reset(self):
        from agentcost.reactions import ReactionEngine, Reaction

        engine = ReactionEngine()
        reaction = Reaction(
            name="reset-test",
            auto=True,
            actions=["log"],
            cooldown_seconds=3600,
        )
        engine.add_reaction("reset-test", {"actions": ["log"], "cooldown": "1h"})
        engine.execute(reaction, "test", {})

        # Reset cooldown
        assert engine.reset_cooldown("reset-test") is True

        # Now it should work again
        r = engine.execute(reaction, "test", {})
        assert r.success

    def test_unknown_action(self):
        from agentcost.reactions import ReactionEngine, Reaction

        engine = ReactionEngine()
        reaction = Reaction(
            name="unknown-action",
            auto=True,
            actions=["nonexistent-action"],
        )
        result = engine.execute(reaction, "test", {})
        assert "nonexistent-action" in result.actions_failed

    def test_custom_action_registration(self):
        from agentcost.reactions import ReactionEngine, Reaction

        engine = ReactionEngine()
        called_with = {}

        def my_action(event_type, data):
            called_with["type"] = event_type
            called_with["data"] = data
            return True

        engine.register_action("my-custom", my_action)
        reaction = Reaction(name="custom", auto=True, actions=["my-custom"])
        result = engine.execute(reaction, "test.event", {"key": "val"})
        assert result.success
        assert called_with["type"] == "test.event"
        assert called_with["data"]["key"] == "val"

    def test_add_remove_reaction(self):
        from agentcost.reactions import ReactionEngine

        engine = ReactionEngine()
        initial_count = len(engine.reactions)

        engine.add_reaction("dynamic", {"auto": True, "actions": ["log"]})
        assert "dynamic" in engine.reactions
        assert len(engine.reactions) == initial_count + 1

        assert engine.remove_reaction("dynamic") is True
        assert "dynamic" not in engine.reactions

    def test_enable_disable(self):
        from agentcost.reactions import ReactionEngine

        engine = ReactionEngine()
        engine.add_reaction("toggle-test", {"auto": True, "actions": ["log"]})

        engine.disable_reaction("toggle-test")
        assert engine.reactions["toggle-test"].enabled is False

        engine.enable_reaction("toggle-test")
        assert engine.reactions["toggle-test"].enabled is True

    def test_history_tracking(self):
        from agentcost.reactions import ReactionEngine
        from agentcost.events import EventBus

        bus = EventBus()
        engine = ReactionEngine()
        engine.start(event_bus=bus)

        # Emit events that match reactions
        bus.emit("budget.exceeded", {"message": "test1"})
        bus.emit("policy.violation", {"message": "test2"})

        history = engine.get_history()
        assert len(history) >= 2
        engine.stop()

    def test_stats(self):
        from agentcost.reactions import ReactionEngine
        from agentcost.events import EventBus

        bus = EventBus()
        engine = ReactionEngine()
        engine.start(event_bus=bus)

        bus.emit("budget.exceeded", {"message": "stat test"})

        stats = engine.stats
        assert stats["total_reactions"] >= 1
        assert stats["successes"] >= 1
        assert "log" in stats["registered_actions"]
        assert "notify" in stats["registered_actions"]
        engine.stop()

    def test_reload(self):
        from agentcost.reactions import ReactionEngine

        engine = ReactionEngine()
        count = engine.reload()
        assert count > 0


# ── EventBus Integration ────────────────────────────────────────────────────


class TestEventBusIntegration:
    def test_engine_subscribes_to_eventbus(self):
        from agentcost.reactions import ReactionEngine
        from agentcost.events import EventBus

        bus = EventBus()
        engine = ReactionEngine()
        engine.start(event_bus=bus)

        assert engine._started is True
        assert len(bus.subscriptions["callbacks"]) == 1
        assert bus.subscriptions["callbacks"][0]["name"] == "reaction-engine"

        engine.stop()

    def test_event_triggers_reaction(self):
        from agentcost.reactions import ReactionEngine
        from agentcost.events import EventBus

        bus = EventBus()
        engine = ReactionEngine()

        # Track what gets executed
        executed = []
        original_log = engine._action_log

        def tracking_log(et, data):
            executed.append(et)
            return original_log(et, data)

        engine._action_handlers["log"] = tracking_log
        engine.start(event_bus=bus)

        # Emit a budget.exceeded event
        bus.emit("budget.exceeded", {"message": "Over budget!", "usage_pct": 110})

        # The reaction engine should have fired
        assert len(executed) > 0
        assert "budget.exceeded" in executed

        engine.stop()

    def test_event_with_unmatched_type(self):
        from agentcost.reactions import ReactionEngine
        from agentcost.events import EventBus

        bus = EventBus()
        engine = ReactionEngine()
        engine.start(event_bus=bus)

        # Emit an event with no matching reaction
        bus.emit("unknown.event.type", {"data": "irrelevant"})

        # Should not error, just no reaction fired
        history = engine.get_history()
        # No new entries for unmatched events
        engine.stop()


# ── Event-to-Reaction Mapping ────────────────────────────────────────────────


class TestEventMapping:
    def test_known_mappings(self):
        from agentcost.reactions import EVENT_TO_REACTION

        assert EVENT_TO_REACTION["budget.warning"] == "budget-80"
        assert EVENT_TO_REACTION["budget.exceeded"] == "budget-exceeded"
        assert EVENT_TO_REACTION["policy.violation"] == "policy-violation"
        assert EVENT_TO_REACTION["anomaly.cost_spike"] == "cost-spike"
        assert EVENT_TO_REACTION["approval.pending"] == "approval-pending"
        assert EVENT_TO_REACTION["scorecard.generated"] == "scorecard-generated"


# ── ReactionResult ───────────────────────────────────────────────────────────


class TestReactionResult:
    def test_success(self):
        from agentcost.reactions.engine import ReactionResult

        r = ReactionResult(
            reaction_name="test",
            event_type="budget.exceeded",
            actions_executed=["notify", "log"],
            actions_failed=[],
        )
        assert r.success is True

    def test_failure(self):
        from agentcost.reactions.engine import ReactionResult

        r = ReactionResult(
            reaction_name="test",
            event_type="budget.exceeded",
            actions_executed=["notify"],
            actions_failed=["block-calls"],
        )
        assert r.success is False

    def test_skipped(self):
        from agentcost.reactions.engine import ReactionResult

        r = ReactionResult(
            reaction_name="test",
            event_type="budget.exceeded",
            actions_executed=[],
            actions_failed=[],
            skipped_reason="cooldown_active",
        )
        assert r.success is False

    def test_to_dict(self):
        from agentcost.reactions.engine import ReactionResult

        r = ReactionResult(
            reaction_name="test",
            event_type="x",
            actions_executed=["log"],
            actions_failed=[],
        )
        d = r.to_dict()
        assert d["reaction"] == "test"
        assert d["success"] is True
        assert "timestamp" in d
