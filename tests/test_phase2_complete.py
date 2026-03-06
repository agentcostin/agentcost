"""
AgentCost Phase 2 Completion — Test Suite

Tests for all Phase 2 remaining items:
  - 8-slot plugin architecture (RuntimePlugin, AgentPlugin)
  - Built-in notifier plugins (Slack, Webhook, Email, PagerDuty)
  - InMemoryTrackerPlugin
  - AgentLifecyclePlugin (state machine with all transitions)
  - PagerDutyReactorPlugin (example reactor)
  - SDK budget events (CostTracker → EventBus)
  - Scaffold templates for runtime/agent types
  - Registry helpers (model override, rate limits, agent state)
"""

import os
import tempfile
import time

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Eight-Slot Plugin Architecture
# ═══════════════════════════════════════════════════════════════════════════════


class TestEightSlotArchitecture:
    def test_plugin_type_enum_has_eight(self):
        from agentcost.plugins import PluginType

        assert len(PluginType) == 8
        assert PluginType.RUNTIME == "runtime"
        assert PluginType.AGENT == "agent"

    def test_runtime_plugin_abstract(self):
        from agentcost.plugins import RuntimePlugin

        with pytest.raises(TypeError):
            RuntimePlugin()

    def test_agent_plugin_abstract(self):
        from agentcost.plugins import AgentPlugin

        with pytest.raises(TypeError):
            AgentPlugin()

    def test_registry_has_eight_slots(self):
        from agentcost.plugins import PluginRegistry

        reg = PluginRegistry()
        slots = reg.slots
        assert len(slots) == 8
        assert "runtime" in slots
        assert "agent" in slots
        assert "notifier" in slots
        assert "policy" in slots
        assert "exporter" in slots
        assert "provider" in slots
        assert "tracker" in slots
        assert "reactor" in slots

    def test_runtime_plugin_impl(self):
        from agentcost.plugins import RuntimePlugin, PluginMeta, PluginType

        class TestRuntime(RuntimePlugin):
            meta = PluginMeta(
                name="test-runtime",
                version="0.1.0",
                plugin_type=PluginType.RUNTIME,
            )

            def get_model_override(self, model, ctx):
                if model == "gpt-4o":
                    return "gpt-4o-mini"
                return None

            def check_rate_limit(self, scope, scope_id):
                return True

        rt = TestRuntime()
        assert rt.get_model_override("gpt-4o", {}) == "gpt-4o-mini"
        assert rt.get_model_override("claude-3", {}) is None
        assert rt.check_rate_limit("project", "demo")
        assert rt.get_feature_flags() == {}  # default

    def test_agent_plugin_impl(self):
        from agentcost.plugins import AgentPlugin, PluginMeta, PluginType

        class TestAgent(AgentPlugin):
            meta = PluginMeta(
                name="test-agent",
                version="0.1.0",
                plugin_type=PluginType.AGENT,
            )
            _states = {}

            def get_agent_state(self, agent_id):
                return self._states.get(agent_id, "registered")

            def transition(self, agent_id, new_state, reason=""):
                self._states[agent_id] = new_state
                return True

        ap = TestAgent()
        assert ap.get_agent_state("a1") == "registered"
        assert ap.transition("a1", "active")
        assert ap.get_agent_state("a1") == "active"
        assert ap.get_workspace_config("proj") == {}  # default

    def test_registry_load_runtime(self):
        from agentcost.plugins import (
            PluginRegistry,
            RuntimePlugin,
            PluginMeta,
            PluginType,
        )

        class MyRuntime(RuntimePlugin):
            meta = PluginMeta(
                name="my-runtime",
                version="1.0.0",
                plugin_type=PluginType.RUNTIME,
            )

            def get_model_override(self, m, c):
                return None

            def check_rate_limit(self, s, sid):
                return True

        reg = PluginRegistry()
        reg.load(MyRuntime())
        assert len(reg.runtimes) == 1
        assert reg.slots["runtime"] == ["my-runtime"]

    def test_registry_load_agent(self):
        from agentcost.plugins import (
            PluginRegistry,
            AgentPlugin,
            PluginMeta,
            PluginType,
        )

        class MyAgent(AgentPlugin):
            meta = PluginMeta(
                name="my-agent",
                version="1.0.0",
                plugin_type=PluginType.AGENT,
            )

            def get_agent_state(self, aid):
                return "active"

            def transition(self, aid, ns, r=""):
                return True

        reg = PluginRegistry()
        reg.load(MyAgent())
        assert len(reg.agents) == 1
        assert reg.slots["agent"] == ["my-agent"]

    def test_registry_unload_runtime_and_agent(self):
        from agentcost.plugins import (
            PluginRegistry,
            RuntimePlugin,
            AgentPlugin,
            PluginMeta,
            PluginType,
        )

        class R(RuntimePlugin):
            meta = PluginMeta(name="r1", version="1.0", plugin_type=PluginType.RUNTIME)

            def get_model_override(self, m, c):
                return None

            def check_rate_limit(self, s, sid):
                return True

        class A(AgentPlugin):
            meta = PluginMeta(name="a1", version="1.0", plugin_type=PluginType.AGENT)

            def get_agent_state(self, aid):
                return "active"

            def transition(self, aid, ns, r=""):
                return True

        reg = PluginRegistry()
        reg.load(R())
        reg.load(A())
        assert len(reg.runtimes) == 1
        assert len(reg.agents) == 1

        reg.unload("r1")
        reg.unload("a1")
        assert len(reg.runtimes) == 0
        assert len(reg.agents) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Built-in Notifier Plugins
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuiltinNotifiers:
    def test_slack_no_url(self):
        from agentcost.plugins.builtins import SlackNotifierPlugin
        from agentcost.plugins import NotifyEvent

        slack = SlackNotifierPlugin()
        result = slack.send(
            NotifyEvent(
                event_type="budget.warning",
                severity="warning",
                message="test",
            )
        )
        assert not result.success
        assert "webhook_url" in result.message

    def test_slack_health(self):
        from agentcost.plugins.builtins import SlackNotifierPlugin

        slack = SlackNotifierPlugin()
        assert not slack.health_check().healthy
        slack.configure({"webhook_url": "https://hooks.example.com/test"})
        assert slack.health_check().healthy

    def test_webhook_no_url(self):
        from agentcost.plugins.builtins import WebhookNotifierPlugin
        from agentcost.plugins import NotifyEvent

        wh = WebhookNotifierPlugin()
        result = wh.send(
            NotifyEvent(
                event_type="test",
                severity="info",
                message="hello",
            )
        )
        assert not result.success

    def test_webhook_health(self):
        from agentcost.plugins.builtins import WebhookNotifierPlugin

        wh = WebhookNotifierPlugin()
        assert not wh.health_check().healthy
        wh.configure({"url": "https://example.com/hook"})
        assert wh.health_check().healthy

    def test_email_no_recipients(self):
        from agentcost.plugins.builtins import EmailNotifierPlugin
        from agentcost.plugins import NotifyEvent

        em = EmailNotifierPlugin()
        result = em.send(
            NotifyEvent(
                event_type="test",
                severity="info",
                message="hi",
            )
        )
        assert not result.success

    def test_email_stub_sends(self):
        from agentcost.plugins.builtins import EmailNotifierPlugin
        from agentcost.plugins import NotifyEvent

        em = EmailNotifierPlugin()
        em.configure({"recipients": ["admin@example.com"]})
        result = em.send(
            NotifyEvent(
                event_type="budget.exceeded",
                severity="critical",
                message="over budget",
            )
        )
        assert result.success
        assert result.message == "stub"

    def test_pagerduty_no_key(self):
        from agentcost.plugins.builtins import PagerDutyNotifierPlugin
        from agentcost.plugins import NotifyEvent

        pd = PagerDutyNotifierPlugin()
        result = pd.send(
            NotifyEvent(
                event_type="test",
                severity="warning",
                message="test",
            )
        )
        assert not result.success

    def test_pagerduty_stub_sends(self):
        from agentcost.plugins.builtins import PagerDutyNotifierPlugin
        from agentcost.plugins import NotifyEvent

        pd = PagerDutyNotifierPlugin()
        pd.configure({"routing_key": "abc123"})
        result = pd.send(
            NotifyEvent(
                event_type="budget.exceeded",
                severity="critical",
                message="budget blown",
            )
        )
        assert result.success

    def test_notifier_plugin_meta(self):
        from agentcost.plugins.builtins import (
            SlackNotifierPlugin,
            WebhookNotifierPlugin,
            EmailNotifierPlugin,
            PagerDutyNotifierPlugin,
        )
        from agentcost.plugins import PluginType

        for cls in [
            SlackNotifierPlugin,
            WebhookNotifierPlugin,
            EmailNotifierPlugin,
            PagerDutyNotifierPlugin,
        ]:
            p = cls()
            assert p.meta.plugin_type == PluginType.NOTIFIER
            assert p.meta.version == "1.0.0"

    def test_load_notifiers_into_registry(self):
        from agentcost.plugins import PluginRegistry
        from agentcost.plugins.builtins import SlackNotifierPlugin, EmailNotifierPlugin

        reg = PluginRegistry()
        slack = SlackNotifierPlugin()
        email = EmailNotifierPlugin()
        reg.load(slack, {"webhook_url": "https://hooks.example.com"})
        reg.load(email, {"recipients": ["admin@test.com"]})

        assert len(reg.notifiers) == 2
        assert reg.slots["notifier"] == ["builtin-slack", "builtin-email"]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. InMemoryTrackerPlugin
# ═══════════════════════════════════════════════════════════════════════════════


class TestInMemoryTracker:
    def test_record_and_spend(self):
        from agentcost.plugins.builtins import InMemoryTrackerPlugin

        t = InMemoryTrackerPlugin()
        t.record_trace({"project": "demo", "cost": 0.05, "model": "gpt-4o"})
        t.record_trace({"project": "demo", "cost": 0.03, "model": "gpt-4o-mini"})
        assert abs(t.get_spend("project", "demo") - 0.08) < 0.0001

    def test_multi_scope(self):
        from agentcost.plugins.builtins import InMemoryTrackerPlugin

        t = InMemoryTrackerPlugin()
        t.record_trace({"project": "p1", "agent_id": "a1", "cost": 0.10})
        t.record_trace({"project": "p1", "agent_id": "a2", "cost": 0.20})
        assert abs(t.get_spend("project", "p1") - 0.30) < 0.0001
        assert abs(t.get_spend("agent_id", "a1") - 0.10) < 0.0001
        assert abs(t.get_spend("agent_id", "a2") - 0.20) < 0.0001

    def test_check_budget(self):
        from agentcost.plugins.builtins import InMemoryTrackerPlugin

        t = InMemoryTrackerPlugin()
        t.record_trace({"project": "p1", "cost": 0.50})
        assert t.check_budget("project", "p1", 1.00)
        assert not t.check_budget("project", "p1", 0.40)

    def test_get_traces(self):
        from agentcost.plugins.builtins import InMemoryTrackerPlugin

        t = InMemoryTrackerPlugin()
        for i in range(5):
            t.record_trace({"project": "p1", "cost": 0.01, "idx": i})
        traces = t.get_traces(limit=3)
        assert len(traces) == 3
        assert traces[0]["idx"] == 2  # last 3

    def test_reset(self):
        from agentcost.plugins.builtins import InMemoryTrackerPlugin

        t = InMemoryTrackerPlugin()
        t.record_trace({"project": "p1", "cost": 1.00})
        assert t.get_spend("project", "p1") == 1.00
        t.reset()
        assert t.get_spend("project", "p1") == 0.0
        assert t.get_traces() == []

    def test_health(self):
        from agentcost.plugins.builtins import InMemoryTrackerPlugin

        t = InMemoryTrackerPlugin()
        h = t.health_check()
        assert h.healthy
        assert h.details["trace_count"] == 0

    def test_max_traces_cap(self):
        from agentcost.plugins.builtins import InMemoryTrackerPlugin

        t = InMemoryTrackerPlugin()
        t._max_traces = 10
        for i in range(25):
            t.record_trace({"project": "p1", "cost": 0.01})
        assert len(t._traces) == 10


# ═══════════════════════════════════════════════════════════════════════════════
# 4. AgentLifecyclePlugin — State Machine
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentLifecycle:
    def test_initial_state(self):
        from agentcost.plugins.builtins import AgentLifecyclePlugin

        lc = AgentLifecyclePlugin()
        assert lc.get_agent_state("unknown") == "registered"

    def test_register_agent(self):
        from agentcost.plugins.builtins import AgentLifecyclePlugin

        lc = AgentLifecyclePlugin()
        assert lc.register_agent("a1")
        assert not lc.register_agent("a1")  # duplicate

    def test_happy_path(self):
        """registered → active → budget_warning → suspended → resumed → active"""
        from agentcost.plugins.builtins import AgentLifecyclePlugin

        lc = AgentLifecyclePlugin()
        lc.register_agent("a1")

        assert lc.transition("a1", "active", "startup")
        assert lc.get_agent_state("a1") == "active"

        assert lc.transition("a1", "budget_warning", "80% used")
        assert lc.get_agent_state("a1") == "budget_warning"

        assert lc.transition("a1", "suspended", "100% used")
        assert lc.get_agent_state("a1") == "suspended"

        assert lc.transition("a1", "resumed", "budget reset")
        assert lc.get_agent_state("a1") == "resumed"

        assert lc.transition("a1", "active", "back online")
        assert lc.get_agent_state("a1") == "active"

    def test_invalid_transitions(self):
        from agentcost.plugins.builtins import AgentLifecyclePlugin

        lc = AgentLifecyclePlugin()
        lc.register_agent("a1")

        # registered → suspended (invalid, must go through active first)
        assert not lc.transition("a1", "suspended")
        # registered → budget_warning (invalid)
        assert not lc.transition("a1", "budget_warning")
        # registered → resumed (invalid)
        assert not lc.transition("a1", "resumed")

    def test_terminated_is_final(self):
        from agentcost.plugins.builtins import AgentLifecyclePlugin

        lc = AgentLifecyclePlugin()
        lc.register_agent("a1")
        lc.transition("a1", "active")
        lc.transition("a1", "terminated", "shutdown")
        assert lc.get_agent_state("a1") == "terminated"

        # No transitions from terminated
        assert not lc.transition("a1", "active")
        assert not lc.transition("a1", "registered")
        assert not lc.transition("a1", "resumed")

    def test_suspended_to_active_invalid(self):
        """Must go through 'resumed' before going back to 'active'."""
        from agentcost.plugins.builtins import AgentLifecyclePlugin

        lc = AgentLifecyclePlugin()
        lc.register_agent("a1")
        lc.transition("a1", "active")
        lc.transition("a1", "suspended", "budget exceeded")

        assert not lc.transition("a1", "active")  # invalid
        assert lc.transition("a1", "resumed", "budget replenished")
        assert lc.transition("a1", "active")  # now valid

    def test_all_valid_transitions(self):
        from agentcost.plugins.builtins import VALID_TRANSITIONS

        # Verify all states are defined
        assert "registered" in VALID_TRANSITIONS
        assert "active" in VALID_TRANSITIONS
        assert "budget_warning" in VALID_TRANSITIONS
        assert "suspended" in VALID_TRANSITIONS
        assert "resumed" in VALID_TRANSITIONS
        assert "terminated" in VALID_TRANSITIONS

        # terminated has no outgoing transitions
        assert VALID_TRANSITIONS["terminated"] == set()

    def test_get_all_agents(self):
        from agentcost.plugins.builtins import AgentLifecyclePlugin

        lc = AgentLifecyclePlugin()
        lc.register_agent("a1")
        lc.register_agent("a2")
        lc.transition("a1", "active")

        agents = lc.get_all_agents()
        assert agents["a1"] == "active"
        assert agents["a2"] == "registered"

    def test_transition_history(self):
        from agentcost.plugins.builtins import AgentLifecyclePlugin

        lc = AgentLifecyclePlugin()
        lc.register_agent("a1")
        lc.transition("a1", "active", "boot")
        lc.transition("a1", "budget_warning", "80%")

        history = lc.get_transition_history("a1")
        assert len(history) == 2
        assert history[0]["from_state"] == "registered"
        assert history[0]["to_state"] == "active"
        assert history[1]["to_state"] == "budget_warning"

    def test_workspace_config(self):
        from agentcost.plugins.builtins import AgentLifecyclePlugin

        lc = AgentLifecyclePlugin()
        assert lc.get_workspace_config("proj1") == {}

        lc.set_workspace_config(
            "proj1",
            {
                "default_model": "gpt-4o-mini",
                "budget_limit": 100.0,
                "team": "engineering",
            },
        )
        cfg = lc.get_workspace_config("proj1")
        assert cfg["default_model"] == "gpt-4o-mini"
        assert cfg["budget_limit"] == 100.0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PagerDutyReactorPlugin
# ═══════════════════════════════════════════════════════════════════════════════


class TestPagerDutyReactor:
    def test_actions_registered(self):
        from agentcost.plugins.builtins import PagerDutyReactorPlugin

        pd = PagerDutyReactorPlugin()
        actions = pd.get_actions()
        assert "pagerduty-trigger" in actions
        assert "pagerduty-resolve" in actions
        assert callable(actions["pagerduty-trigger"])

    def test_trigger_incident(self):
        from agentcost.plugins.builtins import PagerDutyReactorPlugin

        pd = PagerDutyReactorPlugin()
        pd.configure({"routing_key": "test-key-123"})
        ok = pd._trigger_incident(
            "budget.exceeded",
            {
                "message": "Budget exceeded for project demo",
                "severity": "critical",
                "project": "demo",
            },
        )
        assert ok
        assert len(pd._incidents) == 1

    def test_resolve_incident(self):
        from agentcost.plugins.builtins import PagerDutyReactorPlugin

        pd = PagerDutyReactorPlugin()
        pd._trigger_incident("budget.exceeded", {"dedup_key": "test-1"})
        assert "test-1" in pd._incidents
        pd._resolve_incident("budget.resolved", {"dedup_key": "test-1"})
        assert "test-1" not in pd._incidents

    def test_dry_run_without_key(self):
        from agentcost.plugins.builtins import PagerDutyReactorPlugin

        pd = PagerDutyReactorPlugin()  # no routing_key
        ok = pd._trigger_incident("test", {"message": "dry run"})
        assert ok  # still succeeds, just logs

    def test_health_check(self):
        from agentcost.plugins.builtins import PagerDutyReactorPlugin

        pd = PagerDutyReactorPlugin()
        h = pd.health_check()
        assert h.healthy
        assert h.details["routing_key_set"] is False
        pd.configure({"routing_key": "key"})
        h = pd.health_check()
        assert h.details["routing_key_set"] is True

    def test_meta(self):
        from agentcost.plugins.builtins import PagerDutyReactorPlugin
        from agentcost.plugins import PluginType

        pd = PagerDutyReactorPlugin()
        assert pd.meta.plugin_type == PluginType.REACTOR
        assert "pagerduty" in pd.meta.name.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. SDK Budget Events via EventBus
# ═══════════════════════════════════════════════════════════════════════════════


class TestSDKBudgetEvents:
    def test_warning_at_80_percent(self):
        import sys
        from agentcost.sdk.trace import CostTracker, TraceEvent

        trace_mod = sys.modules["agentcost.sdk.trace"]
        events_captured = []

        tracker = CostTracker("budget-test")
        tracker.set_budget(1.00)

        orig_emit = trace_mod._emit_budget_event

        def capture_emit(event_type, project, spend, limit):
            events_captured.append((event_type, project, spend, limit))

        trace_mod._emit_budget_event = capture_emit
        try:
            # Push to 79% — no event
            tracker.record(
                TraceEvent(
                    trace_id="t1",
                    project="budget-test",
                    model="gpt-4o",
                    provider="openai",
                    input_tokens=100,
                    output_tokens=50,
                    cost=0.79,
                    latency_ms=100,
                )
            )
            assert len(events_captured) == 0

            # Push to 81% — warning event
            tracker.record(
                TraceEvent(
                    trace_id="t2",
                    project="budget-test",
                    model="gpt-4o",
                    provider="openai",
                    input_tokens=100,
                    output_tokens=50,
                    cost=0.02,
                    latency_ms=100,
                )
            )
            assert len(events_captured) == 1
            assert events_captured[0][0] == "budget.warning"
            assert events_captured[0][1] == "budget-test"

            # Push to 105% — exceeded event
            tracker.record(
                TraceEvent(
                    trace_id="t3",
                    project="budget-test",
                    model="gpt-4o",
                    provider="openai",
                    input_tokens=100,
                    output_tokens=50,
                    cost=0.25,
                    latency_ms=100,
                )
            )
            assert len(events_captured) == 2
            assert events_captured[1][0] == "budget.exceeded"
        finally:
            trace_mod._emit_budget_event = orig_emit

    def test_events_only_emitted_once(self):
        import sys
        from agentcost.sdk.trace import CostTracker, TraceEvent

        trace_mod = sys.modules["agentcost.sdk.trace"]
        events_captured = []

        orig = trace_mod._emit_budget_event

        def capture(et, p, s, l):
            events_captured.append(et)

        trace_mod._emit_budget_event = capture
        try:
            t = CostTracker("once-test")
            t.set_budget(1.00)

            # Cross 80% twice
            t.record(
                TraceEvent(
                    trace_id="a",
                    project="once-test",
                    model="m",
                    provider="p",
                    input_tokens=0,
                    output_tokens=0,
                    cost=0.85,
                    latency_ms=0,
                )
            )
            t.record(
                TraceEvent(
                    trace_id="b",
                    project="once-test",
                    model="m",
                    provider="p",
                    input_tokens=0,
                    output_tokens=0,
                    cost=0.01,
                    latency_ms=0,
                )
            )
            # Warning should fire only once
            warning_count = events_captured.count("budget.warning")
            assert warning_count == 1

            # Cross 100% twice
            t.record(
                TraceEvent(
                    trace_id="c",
                    project="once-test",
                    model="m",
                    provider="p",
                    input_tokens=0,
                    output_tokens=0,
                    cost=0.20,
                    latency_ms=0,
                )
            )
            t.record(
                TraceEvent(
                    trace_id="d",
                    project="once-test",
                    model="m",
                    provider="p",
                    input_tokens=0,
                    output_tokens=0,
                    cost=0.10,
                    latency_ms=0,
                )
            )
            exceeded_count = events_captured.count("budget.exceeded")
            assert exceeded_count == 1
        finally:
            trace_mod._emit_budget_event = orig

    def test_reset_clears_event_flags(self):
        from agentcost.sdk.trace import CostTracker

        t = CostTracker("reset-test")
        t.set_budget(1.00)
        t._warning_emitted = True
        t._exceeded_emitted = True
        t.reset()
        assert not t._warning_emitted
        assert not t._exceeded_emitted

    def test_set_budget_resets_flags(self):
        from agentcost.sdk.trace import CostTracker

        t = CostTracker("flag-test")
        t._warning_emitted = True
        t._exceeded_emitted = True
        t.set_budget(2.00)
        assert not t._warning_emitted
        assert not t._exceeded_emitted

    def test_custom_warning_threshold(self):
        from agentcost.sdk.trace import CostTracker

        t = CostTracker("thresh-test")
        t.warning_threshold = 0.50  # 50%
        assert t.warning_threshold == 0.50


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Scaffold Templates for Runtime & Agent
# ═══════════════════════════════════════════════════════════════════════════════


class TestScaffoldNewSlots:
    def test_runtime_template_exists(self):
        from agentcost.plugins.scaffold import PLUGIN_TEMPLATES

        assert "runtime" in PLUGIN_TEMPLATES

    def test_agent_template_exists(self):
        from agentcost.plugins.scaffold import PLUGIN_TEMPLATES

        assert "agent" in PLUGIN_TEMPLATES

    def test_all_eight_templates(self):
        from agentcost.plugins.scaffold import PLUGIN_TEMPLATES

        expected = {
            "notifier",
            "policy",
            "exporter",
            "provider",
            "tracker",
            "reactor",
            "runtime",
            "agent",
        }
        assert set(PLUGIN_TEMPLATES.keys()) == expected

    def test_scaffold_runtime(self):
        from agentcost.plugins.scaffold import scaffold_plugin

        with tempfile.TemporaryDirectory() as d:
            path = scaffold_plugin("budget-router", "runtime", output_dir=d)
            assert os.path.isdir(path)
            assert os.path.exists(os.path.join(path, "pyproject.toml"))
            plugin_py = os.path.join(path, "budget_router", "plugin.py")
            assert os.path.exists(plugin_py)
            code = open(plugin_py).read()
            assert "RuntimePlugin" in code
            assert "get_model_override" in code
            assert "check_rate_limit" in code

    def test_scaffold_agent(self):
        from agentcost.plugins.scaffold import scaffold_plugin

        with tempfile.TemporaryDirectory() as d:
            path = scaffold_plugin("my-lifecycle", "agent", output_dir=d)
            assert os.path.isdir(path)
            plugin_py = os.path.join(path, "my_lifecycle", "plugin.py")
            assert os.path.exists(plugin_py)
            code = open(plugin_py).read()
            assert "AgentPlugin" in code
            assert "get_agent_state" in code
            assert "transition" in code
            assert "VALID_TRANSITIONS" in code


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Registry Helpers (model override, rate limits, agent state)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegistryHelpers:
    def test_get_model_override_no_plugins(self):
        from agentcost.plugins import PluginRegistry

        reg = PluginRegistry()
        assert reg.get_model_override("gpt-4o", {}) == "gpt-4o"

    def test_get_model_override_with_runtime(self):
        from agentcost.plugins import (
            PluginRegistry,
            RuntimePlugin,
            PluginMeta,
            PluginType,
        )

        class Downgrader(RuntimePlugin):
            meta = PluginMeta(
                name="downgrader", version="1.0", plugin_type=PluginType.RUNTIME
            )

            def get_model_override(self, model, ctx):
                if model == "gpt-4o" and ctx.get("budget_pressure"):
                    return "gpt-4o-mini"
                return None

            def check_rate_limit(self, s, sid):
                return True

        reg = PluginRegistry()
        reg.load(Downgrader())

        # No pressure → no override
        assert reg.get_model_override("gpt-4o", {}) == "gpt-4o"
        # With pressure → downgrade
        assert (
            reg.get_model_override("gpt-4o", {"budget_pressure": True}) == "gpt-4o-mini"
        )

    def test_check_rate_limits_all_pass(self):
        from agentcost.plugins import PluginRegistry

        reg = PluginRegistry()
        assert reg.check_rate_limits("project", "demo")  # no plugins = pass

    def test_check_rate_limits_blocked(self):
        from agentcost.plugins import (
            PluginRegistry,
            RuntimePlugin,
            PluginMeta,
            PluginType,
        )

        class Blocker(RuntimePlugin):
            meta = PluginMeta(
                name="blocker", version="1.0", plugin_type=PluginType.RUNTIME
            )

            def get_model_override(self, m, c):
                return None

            def check_rate_limit(self, s, sid):
                return False  # always block

        reg = PluginRegistry()
        reg.load(Blocker())
        assert not reg.check_rate_limits("project", "demo")

    def test_get_agent_state_via_registry(self):
        from agentcost.plugins import PluginRegistry
        from agentcost.plugins.builtins import AgentLifecyclePlugin

        reg = PluginRegistry()
        lc = AgentLifecyclePlugin()
        reg.load(lc)
        lc.register_agent("a1")
        lc.transition("a1", "active")

        assert reg.get_agent_state("a1") == "active"
        assert reg.get_agent_state("unknown") == "registered"

    def test_transition_agent_via_registry(self):
        from agentcost.plugins import PluginRegistry
        from agentcost.plugins.builtins import AgentLifecyclePlugin

        reg = PluginRegistry()
        lc = AgentLifecyclePlugin()
        reg.load(lc)
        lc.register_agent("a1")
        lc.transition("a1", "active")

        assert reg.transition_agent("a1", "budget_warning", "80%")
        assert reg.get_agent_state("a1") == "budget_warning"

    def test_no_agent_plugin_returns_none(self):
        from agentcost.plugins import PluginRegistry

        reg = PluginRegistry()
        assert reg.get_agent_state("a1") is None
        assert not reg.transition_agent("a1", "active")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Full Integration: Tracker → Budget → Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestPhase2Integration:
    def test_tracker_in_registry_records(self):
        from agentcost.plugins import PluginRegistry
        from agentcost.plugins.builtins import InMemoryTrackerPlugin

        reg = PluginRegistry()
        tracker = InMemoryTrackerPlugin()
        reg.load(tracker)

        # Simulate what SDK trace does
        for t in reg.trackers:
            t.record_trace({"project": "int-test", "cost": 0.05})
        assert tracker.get_spend("project", "int-test") == 0.05

    def test_reactor_registers_actions_with_engine(self):
        from agentcost.plugins import PluginRegistry
        from agentcost.plugins.builtins import PagerDutyReactorPlugin

        reg = PluginRegistry()
        reg.load(PagerDutyReactorPlugin())

        # Mock engine
        class MockEngine:
            actions = {}

            def register_action(self, name, handler):
                self.actions[name] = handler

        engine = MockEngine()
        count = reg.activate_reactors(engine)
        assert count == 2
        assert "pagerduty-trigger" in engine.actions
        assert "pagerduty-resolve" in engine.actions

    def test_lifecycle_transitions_via_registry_helpers(self):
        from agentcost.plugins import PluginRegistry
        from agentcost.plugins.builtins import AgentLifecyclePlugin

        reg = PluginRegistry()
        lc = AgentLifecyclePlugin()
        reg.load(lc)
        lc.register_agent("int-agent")

        # Full lifecycle through registry
        assert reg.transition_agent("int-agent", "active", "boot")
        assert reg.get_agent_state("int-agent") == "active"
        assert reg.transition_agent("int-agent", "budget_warning", "80%")
        assert reg.transition_agent("int-agent", "suspended", "100%")
        assert not reg.transition_agent("int-agent", "active")  # invalid
        assert reg.transition_agent("int-agent", "resumed", "reset")
        assert reg.transition_agent("int-agent", "active", "ok")
        assert reg.get_agent_state("int-agent") == "active"
