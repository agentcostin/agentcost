"""
AgentCost Phase 6 — Hardening Integration Tests

End-to-end tests that verify components work together across phase boundaries:
  1. Multi-provider cost calculation paths
  2. ReactionEngine → NotifierPlugin dispatch
  3. SDK trace → TrackerPlugin → BudgetEvent → ReactionEngine chain
  4. Intelligence layer integration (Tier + Complexity + Gate + Analyzer)
  5. Plugin lifecycle (load → use → unload → verify cleanup)
  6. Agent lifecycle → EventBus → ReactionEngine
  7. Dashboard API data consistency
  8. Cost sync script structure
"""

import os
import sys
import time
import json
import tempfile

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Multi-Provider Cost Calculation
# ═══════════════════════════════════════════════════════════════════════════════


class TestMultiProviderCost:
    """Verify cost calculation works across all major providers."""

    PROVIDER_MODELS = {
        "openai": ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
        "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
        "deepseek": ["deepseek-chat"],
    }

    def test_all_providers_return_nonzero_cost(self):
        from agentcost.cost.calculator import calculate_cost

        for provider, models in self.PROVIDER_MODELS.items():
            for model in models:
                cost = calculate_cost(model, 1000, 500)
                assert cost > 0, f"{provider}/{model} returned zero cost"

    def test_prefix_stripping_all_providers(self):
        from agentcost.cost.calculator import calculate_cost

        prefixed = {
            "openai/gpt-4o": "gpt-4o",
            "anthropic/claude-3-5-sonnet-20241022": "claude-3-5-sonnet-20241022",
        }
        for prefixed_name, bare_name in prefixed.items():
            c1 = calculate_cost(prefixed_name, 1000, 500)
            c2 = calculate_cost(bare_name, 1000, 500)
            assert c1 == c2, f"Prefix mismatch: {prefixed_name} ({c1}) != {bare_name} ({c2})"

    def test_completion_cost_openai_format(self):
        from agentcost.cost.calculator import completion_cost

        response = {
            "model": "gpt-4o",
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }
        cost = completion_cost(response)
        assert cost > 0

    def test_completion_cost_anthropic_format(self):
        from agentcost.cost.calculator import completion_cost

        # completion_cost uses prompt_tokens/completion_tokens (normalized format)
        response = {
            "model": "claude-3-5-sonnet-20241022",
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }
        cost = completion_cost(response)
        assert cost > 0

    def test_completion_cost_with_cache(self):
        from agentcost.cost.calculator import completion_cost

        response = {
            "model": "claude-3-5-sonnet-20241022",
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "cache_read_input_tokens": 800,
            },
        }
        cached_cost = completion_cost(response)

        no_cache = {
            "model": "claude-3-5-sonnet-20241022",
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }
        normal_cost = completion_cost(no_cache)
        assert cached_cost <= normal_cost, "Cache should reduce or equal cost"

    def test_unknown_model_graceful(self):
        from agentcost.cost.calculator import calculate_cost

        cost = calculate_cost("nonexistent-model-xyz", 1000, 500)
        assert cost == 0  # graceful zero, never crashes


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ReactionEngine → NotifierPlugin End-to-End
# ═══════════════════════════════════════════════════════════════════════════════


class TestReactionNotifierDispatch:
    """Verify the full chain: event → reaction → notify action → notifier plugin."""

    def test_event_triggers_notifier(self):
        from agentcost.reactions.engine import ReactionEngine
        from agentcost.plugins import (
            PluginRegistry, NotifierPlugin, NotifyEvent, SendResult,
            PluginMeta, PluginType,
        )

        # Create a test notifier that records calls
        notifications = []

        class RecordingNotifier(NotifierPlugin):
            meta = PluginMeta(
                name="test-recorder", version="1.0.0",
                plugin_type=PluginType.NOTIFIER,
            )

            def send(self, event: NotifyEvent) -> SendResult:
                notifications.append(event)
                return SendResult(success=True)

        # Set up registry with test notifier
        reg = PluginRegistry()
        reg.load(RecordingNotifier())

        # Patch the global registry temporarily
        import agentcost.plugins as plugins_mod
        old_reg = plugins_mod.registry
        plugins_mod.registry = reg
        try:
            # Create engine and execute budget-exceeded reaction
            engine = ReactionEngine()
            reaction = engine.reactions.get("budget-exceeded")
            assert reaction is not None

            result = engine.execute(
                reaction, "budget.exceeded",
                {"message": "Budget blown!", "severity": "critical", "usage_pct": 105},
            )
            assert result.success
            assert "notify" in result.actions_executed

            # Verify notifier was called
            assert len(notifications) >= 1
            assert notifications[0].event_type == "budget.exceeded"
        finally:
            plugins_mod.registry = old_reg

    def test_custom_reactor_action_dispatch(self):
        from agentcost.reactions.engine import ReactionEngine

        actions_fired = []

        engine = ReactionEngine()
        engine.register_action(
            "test-custom", lambda et, ed: actions_fired.append(et) or True
        )
        engine.add_reaction("test-reaction", {
            "description": "Test",
            "event": "test.event",
            "actions": ["test-custom"],
            "auto": True,
        })

        reaction = engine.reactions["test-reaction"]
        result = engine.execute(reaction, "test.event", {})
        assert result.success
        assert "test-custom" in result.actions_executed
        assert "test.event" in actions_fired


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SDK Trace → Tracker → Budget Event Chain
# ═══════════════════════════════════════════════════════════════════════════════


class TestSDKTrackerBudgetChain:
    """Full chain: SDK CostTracker records → TrackerPlugin → budget events."""

    def test_tracker_records_via_plugin(self):
        from agentcost.sdk.trace import CostTracker, TraceEvent
        from agentcost.plugins import PluginRegistry
        from agentcost.plugins.builtins import InMemoryTrackerPlugin

        reg = PluginRegistry()
        tracker_plugin = InMemoryTrackerPlugin()
        reg.load(tracker_plugin)

        import agentcost.plugins as pm
        old_reg = pm.registry
        pm.registry = reg
        try:
            ct = CostTracker("integration-test")
            ct.set_budget(1.00)
            ct.record(TraceEvent(
                trace_id="t1", project="integration-test", model="gpt-4o",
                provider="openai", input_tokens=1000, output_tokens=500,
                cost=0.05, latency_ms=200,
            ))

            # Verify tracker plugin recorded it
            spend = tracker_plugin.get_spend("project", "integration-test")
            assert spend == pytest.approx(0.05, rel=0.01)
        finally:
            pm.registry = old_reg

    def test_budget_warning_fires_at_threshold(self):
        from agentcost.sdk.trace import CostTracker, TraceEvent

        trace_mod = sys.modules["agentcost.sdk.trace"]
        events = []
        orig = trace_mod._emit_budget_event

        def capture(et, p, s, l):
            events.append(et)

        trace_mod._emit_budget_event = capture
        try:
            ct = CostTracker("budget-chain-test")
            ct.set_budget(1.00)

            # Push past 80%
            ct.record(TraceEvent(
                trace_id="a", project="p", model="m", provider="p",
                input_tokens=0, output_tokens=0, cost=0.85, latency_ms=0,
            ))
            assert "budget.warning" in events

            # Push past 100%
            ct.record(TraceEvent(
                trace_id="b", project="p", model="m", provider="p",
                input_tokens=0, output_tokens=0, cost=0.20, latency_ms=0,
            ))
            assert "budget.exceeded" in events
        finally:
            trace_mod._emit_budget_event = orig


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Intelligence Layer Integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntelligenceIntegration:
    """Cross-component intelligence tests."""

    def test_complexity_to_tier_to_gate(self):
        """Classify → tier check → budget gate — full pipeline."""
        from agentcost.intelligence import (
            ComplexityRouter, TierRegistry, BudgetGate, CostTier,
        )

        router = ComplexityRouter()
        registry = TierRegistry()
        gate = BudgetGate(budget=5.00)

        # Simple question → economy tier → cheap model
        result = router.classify("What is 2+2?")
        model = router.route("What is 2+2?", provider="openai")
        assert result.suggested_tier == "economy"

        tier = registry.classify(model)
        assert tier in (CostTier.ECONOMY, CostTier.FREE, CostTier.STANDARD)

        decision = gate.check(model, estimated_tokens=100, provider="openai")
        assert decision.action == "allow"

    def test_token_analyzer_detects_waste(self):
        from agentcost.intelligence import TokenAnalyzer

        analyzer = TokenAnalyzer()

        # Record calls with excessive system prompts
        for _ in range(10):
            analyzer.record_call(
                model="gpt-4o", input_tokens=10000, output_tokens=200,
                max_context=128000, system_tokens=8000, project="wasteful",
            )

        report = analyzer.analyze("wasteful")
        assert report.efficiency_score < 80
        assert len(report.warnings) > 0
        assert len(report.recommendations) > 0

    def test_gate_downgrade_preserves_provider(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=1.00)
        gate.spent = 0.95  # 95% — triggers downgrade

        # OpenAI downgrade chain
        d = gate.check("gpt-4o", provider="openai")
        assert d.action == "downgrade"
        assert d.model == "gpt-4o-mini"

        # Anthropic downgrade chain
        d2 = gate.check("claude-3-5-sonnet-20241022", provider="anthropic")
        assert d2.action == "downgrade"
        assert d2.model == "claude-3-haiku-20240307"

    def test_tier_policy_blocks_premium(self):
        from agentcost.intelligence import TierRegistry

        reg = TierRegistry()
        result = reg.check_tier_policy("o1", allowed_tiers=["economy", "standard"])
        assert not result["allowed"]
        assert result["tier"] == "premium"
        assert result["suggested_alternative"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Plugin Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestPluginLifecycle:
    """Load → use → unload → verify cleanup for all 8 slot types."""

    def test_full_lifecycle_tracker(self):
        from agentcost.plugins import PluginRegistry
        from agentcost.plugins.builtins import InMemoryTrackerPlugin

        reg = PluginRegistry()
        t = InMemoryTrackerPlugin()

        # Load
        reg.load(t)
        assert len(reg.trackers) == 1

        # Use
        t.record_trace({"project": "p1", "cost": 0.05})
        assert t.get_spend("project", "p1") == 0.05

        # Unload
        reg.unload("builtin-memory-tracker")
        assert len(reg.trackers) == 0
        assert reg.get("builtin-memory-tracker") is None

    def test_full_lifecycle_agent(self):
        from agentcost.plugins import PluginRegistry
        from agentcost.plugins.builtins import AgentLifecyclePlugin

        reg = PluginRegistry()
        lc = AgentLifecyclePlugin()

        reg.load(lc)
        lc.register_agent("a1")
        lc.transition("a1", "active")
        assert reg.get_agent_state("a1") == "active"

        reg.unload("builtin-agent-lifecycle")
        assert len(reg.agents) == 0
        assert reg.get_agent_state("a1") is None  # no plugin → None

    def test_full_lifecycle_reactor(self):
        from agentcost.plugins import PluginRegistry
        from agentcost.plugins.builtins import PagerDutyReactorPlugin

        reg = PluginRegistry()
        pd = PagerDutyReactorPlugin()
        reg.load(pd)
        assert len(reg.reactors) == 1

        class MockEngine:
            actions = {}
            def register_action(self, name, handler):
                self.actions[name] = handler

        engine = MockEngine()
        count = reg.activate_reactors(engine)
        assert count == 2
        assert "pagerduty-trigger" in engine.actions

        reg.unload("example-pagerduty-reactor")
        assert len(reg.reactors) == 0

    def test_eight_slots_all_functional(self):
        from agentcost.plugins import PluginRegistry

        reg = PluginRegistry()
        slots = reg.slots
        assert len(slots) == 8
        for slot_name, plugins in slots.items():
            assert isinstance(plugins, list), f"Slot {slot_name} not a list"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Agent Lifecycle → EventBus Integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentLifecycleEvents:
    """Agent state transitions emit events to EventBus."""

    def test_transition_emits_event(self):
        from agentcost.plugins.builtins import AgentLifecyclePlugin
        from agentcost.events import EventBus

        bus = EventBus()
        events = []
        bus.subscribe_callback(
            callback=lambda e: events.append(e),
            event_types=["agent.*"],
            name="test-listener",
        )

        lc = AgentLifecyclePlugin()
        lc.register_agent("test-agent")

        # Monkey-patch to use our bus
        import agentcost.plugins.builtins as bmod
        orig = bmod._emit_lifecycle_event

        def emit_to_our_bus(agent_id, old, new, reason):
            bus.emit(f"agent.{new}", {
                "agent_id": agent_id,
                "from_state": old,
                "to_state": new,
                "reason": reason,
            })

        bmod._emit_lifecycle_event = emit_to_our_bus
        try:
            lc.transition("test-agent", "active", "boot")
            lc.transition("test-agent", "budget_warning", "80% used")
            lc.transition("test-agent", "suspended", "exceeded")

            assert len(events) == 3
            assert events[0].type == "agent.active"
            assert events[1].type == "agent.budget_warning"
            assert events[2].type == "agent.suspended"
        finally:
            bmod._emit_lifecycle_event = orig

    def test_invalid_transition_no_event(self):
        from agentcost.plugins.builtins import AgentLifecyclePlugin
        from agentcost.events import EventBus

        bus = EventBus()
        events = []
        bus.subscribe_callback(
            callback=lambda e: events.append(e),
            event_types=["agent.*"],
            name="test-noop",
        )

        lc = AgentLifecyclePlugin()
        lc.register_agent("a1")

        import agentcost.plugins.builtins as bmod
        orig = bmod._emit_lifecycle_event
        bmod._emit_lifecycle_event = lambda *a: bus.emit(f"agent.{a[2]}", {})
        try:
            result = lc.transition("a1", "suspended")  # invalid from registered
            assert result is False
            assert len(events) == 0  # no event emitted
        finally:
            bmod._emit_lifecycle_event = orig


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Dashboard API Data Consistency
# ═══════════════════════════════════════════════════════════════════════════════


class TestDashboardDataConsistency:
    """Verify that model registry, tier data, and search return consistent data."""

    def test_registry_and_tier_agree(self):
        from agentcost.cost.calculator import get_model_registry_for_dashboard
        from agentcost.intelligence.tier_registry import TierRegistry

        registry = get_model_registry_for_dashboard(providers=["openai"])
        tier_reg = TierRegistry()

        for model in registry[:20]:
            tier = tier_reg.classify(model["id"])
            # Both should classify — registry has a tier field too
            assert tier.value != "unknown" or model["input"] == 0

    def test_search_subset_of_registry(self):
        from agentcost.cost.calculator import get_model_registry_for_dashboard

        full = get_model_registry_for_dashboard()
        openai_only = get_model_registry_for_dashboard(providers=["openai"])

        full_ids = {m["id"] for m in full}
        openai_ids = {m["id"] for m in openai_only}
        assert openai_ids.issubset(full_ids)

    def test_tier_summary_matches_registry(self):
        from agentcost.intelligence.tier_registry import TierRegistry

        reg = TierRegistry()
        summary = reg.tier_summary()
        total_classified = sum(summary.values())
        assert total_classified > 100

    def test_provider_list_non_empty(self):
        from agentcost.cost.calculator import list_providers

        providers = list_providers()
        assert "openai" in providers
        assert "anthropic" in providers
        assert len(providers) >= 5


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Sync Script Validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestSyncScript:
    """Verify the upstream sync script structure without network calls."""

    def test_sync_module_importable(self):
        from agentcost.cost.sync_upstream import sync, _validate, _diff_summary
        assert callable(sync)
        assert callable(_validate)
        assert callable(_diff_summary)

    def test_validate_good_data(self):
        from agentcost.cost.sync_upstream import _validate

        good = {f"model-{i}": {"input_cost_per_token": 0.001} for i in range(200)}
        good["gpt-4o"] = {"input_cost_per_token": 0.0000025}
        good["gpt-4o-mini"] = {"input_cost_per_token": 0.00000015}
        good["claude-sonnet-4-5-20250929"] = {"input_cost_per_token": 0.000003}
        warnings = _validate(good)
        assert len(warnings) == 0

    def test_validate_small_data_warns(self):
        from agentcost.cost.sync_upstream import _validate

        small = {"model-1": {"input_cost_per_token": 0.001}}
        warnings = _validate(small)
        assert any("small" in w.lower() or "Suspiciously" in w for w in warnings)

    def test_diff_summary(self):
        from agentcost.cost.sync_upstream import _diff_summary

        old = {"a": {"input_cost_per_token": 1.0}, "b": {"input_cost_per_token": 2.0}}
        new = {"b": {"input_cost_per_token": 3.0}, "c": {"input_cost_per_token": 4.0}}
        diff = _diff_summary(old, new)
        assert "a" in diff["removed"]
        assert "c" in diff["added"]
        assert "b" in diff["price_changed"]

    def test_sync_dry_run_local_file(self):
        from agentcost.cost.sync_upstream import sync

        # Create a minimal valid JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {
                "gpt-4o": {"input_cost_per_token": 0.0000025, "output_cost_per_token": 0.00001},
                "gpt-4o-mini": {"input_cost_per_token": 0.00000015, "output_cost_per_token": 0.0000006},
                "claude-sonnet-4-5-20250929": {"input_cost_per_token": 0.000003, "output_cost_per_token": 0.000015},
            }
            # Add enough entries to pass validation
            for i in range(200):
                data[f"test-model-{i}"] = {"input_cost_per_token": 0.001}
            json.dump(data, f)
            f.flush()
            tmp_path = f.name

        try:
            result = sync(dry_run=True, file_path=tmp_path)
            assert result["status"] == "dry_run"
            assert "diff" in result
        finally:
            os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Scaffold Generates Valid Plugin Code
# ═══════════════════════════════════════════════════════════════════════════════


class TestScaffoldValidity:
    """Scaffolded plugins should produce importable Python code."""

    @pytest.mark.parametrize("plugin_type", [
        "notifier", "policy", "exporter", "provider",
        "tracker", "reactor", "runtime", "agent",
    ])
    def test_scaffold_produces_valid_python(self, plugin_type, tmp_path):
        from agentcost.plugins.scaffold import scaffold_plugin

        path = scaffold_plugin(f"test-{plugin_type}", plugin_type, output_dir=str(tmp_path))
        module_name = f"test_{plugin_type}".replace("-", "_")
        plugin_py = os.path.join(path, module_name, "plugin.py")
        assert os.path.exists(plugin_py)

        # Verify it's valid Python by compiling
        code = open(plugin_py).read()
        compile(code, plugin_py, "exec")  # raises SyntaxError if invalid


# ═══════════════════════════════════════════════════════════════════════════════
# 10. CI Workflow Files Exist
# ═══════════════════════════════════════════════════════════════════════════════


class TestCIFiles:
    """Verify CI/CD infrastructure files are present and valid."""

    def test_sync_pricing_workflow_exists(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", ".github", "workflows", "sync-pricing.yml"
        )
        assert os.path.exists(path)
        content = open(path).read()
        assert "sync_upstream" in content
        assert "cron" in content
        assert "create-pull-request" in content

    def test_ci_workflow_exists(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", ".github", "workflows", "ci.yml"
        )
        assert os.path.exists(path)
        content = open(path).read()
        assert "pytest" in content
        assert "ruff" in content

    def test_pyproject_includes_artifacts(self):
        path = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
        content = open(path).read()
        assert "reactions/*.yaml" in content
        assert "cost/*.json" in content

    def test_no_keycloak_docker(self):
        """Verify Keycloak Docker files were removed in Phase 5."""
        path = os.path.join(os.path.dirname(__file__), "..", "docker", "keycloak")
        assert not os.path.exists(path), "docker/keycloak/ should be removed"

    def test_no_start_sso_script(self):
        path = os.path.join(os.path.dirname(__file__), "..", "scripts", "start-sso.sh")
        assert not os.path.exists(path), "scripts/start-sso.sh should be removed"
