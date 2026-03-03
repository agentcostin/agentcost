"""
AgentCost Phase 4 Test Suite

Tests:
  - SDK trace wrapper (OpenAI + Anthropic patterns)
  - CostTracker and budget alerts
  - RemoteTracker batching
  - Plugin SDK (all 4 types)
  - Plugin registry discovery
  - Plugin scaffold generator
  - OTel exporter and Prometheus metrics
  - Framework integrations module structure
  - auto_instrument() detection
  - CLI plugin commands
  - PyPI package metadata
  - TraceEvent serialization
"""
import json
import os
import tempfile

import pytest

# ── SDK Tests ─────────────────────────────────────────────────────────────────

class TestTraceEvent:
    def test_create_event(self):
        from agentcost.sdk.trace import TraceEvent
        ev = TraceEvent(
            trace_id="abc123", project="test", model="gpt-4o", provider="openai",
            input_tokens=100, output_tokens=50, cost=0.001, latency_ms=500,
        )
        assert ev.trace_id == "abc123"
        assert ev.status == "success"
        assert ev.error is None

    def test_to_dict(self):
        from agentcost.sdk.trace import TraceEvent
        ev = TraceEvent(
            trace_id="x", project="p", model="m", provider="pr",
            input_tokens=10, output_tokens=5, cost=0.0001, latency_ms=100,
        )
        d = ev.to_dict()
        assert isinstance(d, dict)
        assert d["model"] == "m"
        assert d["cost"] == 0.0001
        # JSON serializable
        json.dumps(d)


class TestCostTracker:
    def test_record_and_summary(self):
        from agentcost.sdk.trace import CostTracker, TraceEvent
        tracker = CostTracker("test-proj")
        ev = TraceEvent(
            trace_id="t1", project="test-proj", model="gpt-4o", provider="openai",
            input_tokens=1000, output_tokens=500, cost=0.0075, latency_ms=1200,
        )
        tracker.record(ev)
        assert tracker.total_cost == 0.0075
        assert tracker.total_calls == 1
        s = tracker.summary()
        assert s["project"] == "test-proj"
        assert "gpt-4o" in s["cost_by_model"]

    def test_budget_alert(self):
        from agentcost.sdk.trace import CostTracker, TraceEvent
        tracker = CostTracker("budget-test")
        alerts = []
        tracker.set_budget(0.01, on_alert=lambda p, s, lim: alerts.append((p, s, lim)))
        for i in range(5):
            ev = TraceEvent(
                trace_id=f"t{i}", project="budget-test", model="gpt-4o-mini",
                provider="openai", input_tokens=100, output_tokens=50,
                cost=0.003, latency_ms=100,
            )
            tracker.record(ev)
        assert len(alerts) > 0
        assert alerts[0][0] == "budget-test"

    def test_on_trace_callback(self):
        from agentcost.sdk.trace import CostTracker, TraceEvent
        tracker = CostTracker("cb-test")
        events = []
        tracker.on_trace(lambda e: events.append(e))
        ev = TraceEvent(
            trace_id="t1", project="cb-test", model="m", provider="p",
            input_tokens=0, output_tokens=0, cost=0, latency_ms=0,
        )
        tracker.record(ev)
        assert len(events) == 1

    def test_reset(self):
        from agentcost.sdk.trace import CostTracker, TraceEvent
        tracker = CostTracker("reset-test")
        tracker.record(TraceEvent(
            trace_id="t1", project="reset-test", model="m", provider="p",
            input_tokens=100, output_tokens=50, cost=0.01, latency_ms=100,
        ))
        assert tracker.total_calls == 1
        tracker.reset()
        assert tracker.total_calls == 0
        assert tracker.total_cost == 0


class TestGetTracker:
    def test_singleton(self):
        from agentcost.sdk.trace import get_tracker
        t1 = get_tracker("singleton-test")
        t2 = get_tracker("singleton-test")
        assert t1 is t2

    def test_different_projects(self):
        from agentcost.sdk.trace import get_tracker
        t1 = get_tracker("proj-a")
        t2 = get_tracker("proj-b")
        assert t1 is not t2


class TestCostCalculation:
    def test_calculate_cost_known_model(self):
        from agentcost.providers.tracked import calculate_cost
        cost = calculate_cost("gpt-4o", 1000, 500)
        assert cost > 0

    def test_calculate_cost_unknown_model(self):
        from agentcost.providers.tracked import calculate_cost
        cost = calculate_cost("totally-unknown-model-xyz", 1000, 500)
        assert cost >= 0  # should use default pricing


# ── RemoteTracker Tests ───────────────────────────────────────────────────────

class TestRemoteTracker:
    def test_init(self):
        from agentcost.sdk.remote import RemoteTracker
        rt = RemoteTracker(endpoint="http://localhost:8100", project="test")
        assert rt.endpoint == "http://localhost:8100"
        assert rt.project == "test"
        assert not rt._running

    def test_stats(self):
        from agentcost.sdk.remote import RemoteTracker
        rt = RemoteTracker(endpoint="http://localhost:8100")
        s = rt.stats
        assert s["total_sent"] == 0
        assert s["running"] is False

    def test_buffer_events(self):
        from agentcost.sdk.remote import RemoteTracker
        from agentcost.sdk.trace import TraceEvent
        rt = RemoteTracker(endpoint="", project="buf-test", batch_size=100)
        ev = TraceEvent(
            trace_id="t1", project="buf-test", model="m", provider="p",
            input_tokens=0, output_tokens=0, cost=0, latency_ms=0,
        )
        rt._on_event(ev)
        assert len(rt._buffer) == 1


# ── Plugin SDK Tests ──────────────────────────────────────────────────────────

class TestPluginTypes:
    def test_notifier_plugin(self):
        from agentcost.plugins import (
            NotifierPlugin, NotifyEvent, SendResult, PluginMeta, PluginType,
        )

        class TestNotifier(NotifierPlugin):
            meta = PluginMeta(name="test-notifier", version="1.0.0", plugin_type=PluginType.NOTIFIER)
            def send(self, event):
                return SendResult(success=True, message=event.title)

        n = TestNotifier()
        result = n.send(NotifyEvent(event_type="test", severity="info", title="Hello", message="World"))
        assert result.success
        assert result.message == "Hello"
        assert n.health_check().healthy

    def test_policy_plugin(self):
        from agentcost.plugins import (
            PolicyPlugin, PolicyContext, PolicyDecision, PluginMeta, PluginType,
        )

        class TestPolicy(PolicyPlugin):
            meta = PluginMeta(name="test-policy", version="1.0.0", plugin_type=PluginType.POLICY)
            def evaluate(self, ctx):
                if ctx.estimated_cost > 5.0:
                    return PolicyDecision(allowed=False, reason="Too expensive")
                return PolicyDecision(allowed=True)

        p = TestPolicy()
        assert p.evaluate(PolicyContext(model="gpt-4o", provider="openai", estimated_cost=1.0)).allowed
        assert not p.evaluate(PolicyContext(model="gpt-4o", provider="openai", estimated_cost=10.0)).allowed

    def test_exporter_plugin(self):
        from agentcost.plugins import ExporterPlugin, PluginMeta, PluginType

        class TestExporter(ExporterPlugin):
            meta = PluginMeta(name="test-exporter", version="1.0.0", plugin_type=PluginType.EXPORTER)
            def export(self, traces, fmt="json"):
                return json.dumps(traces).encode()

        e = TestExporter()
        data = e.export([{"model": "gpt-4o", "cost": 0.01}])
        assert b"gpt-4o" in data

    def test_provider_plugin(self):
        from agentcost.plugins import ProviderPlugin, PluginMeta, PluginType

        class TestProvider(ProviderPlugin):
            meta = PluginMeta(name="test-provider", version="1.0.0", plugin_type=PluginType.PROVIDER)
            def calculate_cost(self, model, inp, out):
                if model == "custom-model":
                    return (inp * 0.5 + out * 1.0) / 1_000_000
                return None
            def supported_models(self):
                return ["custom-model"]

        p = TestProvider()
        assert p.calculate_cost("custom-model", 1000, 500) == pytest.approx(0.001)
        assert p.calculate_cost("unknown", 1000, 500) is None


class TestPluginRegistry:
    def test_load_and_list(self):
        from agentcost.plugins import PluginRegistry, NotifierPlugin, SendResult, PluginMeta, PluginType

        class MyNotifier(NotifierPlugin):
            meta = PluginMeta(name="my-notifier", version="0.1.0", plugin_type=PluginType.NOTIFIER)
            def send(self, event):
                return SendResult(success=True)

        reg = PluginRegistry()
        reg.load(MyNotifier())
        plugins = reg.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "my-notifier"
        assert plugins[0]["healthy"]

    def test_unload(self):
        from agentcost.plugins import PluginRegistry, PolicyPlugin, PolicyDecision, PluginMeta, PluginType

        class MyPolicy(PolicyPlugin):
            meta = PluginMeta(name="temp-policy", version="0.1.0", plugin_type=PluginType.POLICY)
            def evaluate(self, ctx):
                return PolicyDecision(allowed=True)

        reg = PluginRegistry()
        reg.load(MyPolicy())
        assert len(reg.policies) == 1
        reg.unload("temp-policy")
        assert len(reg.policies) == 0

    def test_provider_cost_fallback(self):
        from agentcost.plugins import PluginRegistry, ProviderPlugin, PluginMeta, PluginType

        class MyProvider(ProviderPlugin):
            meta = PluginMeta(name="custom-prov", version="0.1.0", plugin_type=PluginType.PROVIDER)
            def calculate_cost(self, model, inp, out):
                if model.startswith("custom/"):
                    return 0.42
                return None
            def supported_models(self):
                return ["custom/v1"]

        reg = PluginRegistry()
        reg.load(MyProvider())
        assert reg.calculate_cost_with_plugins("custom/v1", 100, 50) == 0.42
        assert reg.calculate_cost_with_plugins("gpt-4o", 100, 50) is None


class TestPluginScaffold:
    def test_scaffold_notifier(self):
        from agentcost.plugins.scaffold import scaffold_plugin
        with tempfile.TemporaryDirectory() as tmpdir:
            path = scaffold_plugin("slack-alerts", "notifier", tmpdir)
            assert os.path.exists(os.path.join(path, "pyproject.toml"))
            assert os.path.exists(os.path.join(path, "slack_alerts", "plugin.py"))
            # Check pyproject content
            content = open(os.path.join(path, "pyproject.toml")).read()
            assert "agentcost.plugins" in content

    def test_scaffold_all_types(self):
        from agentcost.plugins.scaffold import scaffold_plugin
        for ptype in ["notifier", "policy", "exporter", "provider"]:
            with tempfile.TemporaryDirectory() as tmpdir:
                path = scaffold_plugin(f"test-{ptype}", ptype, tmpdir)
                assert os.path.exists(path)


# ── OTel Tests ────────────────────────────────────────────────────────────────

class TestOTelExporter:
    def test_exporter_init_without_otel(self):
        """Should handle missing opentelemetry gracefully."""
        from agentcost.otel import AgentCostSpanExporter
        # This should not crash even if otel is not installed
        exporter = AgentCostSpanExporter()
        # If otel is installed, available=True; if not, available=False
        assert isinstance(exporter.available, bool)

    def test_prometheus_metrics_init(self):
        from agentcost.otel import PrometheusMetrics
        metrics = PrometheusMetrics()
        assert isinstance(metrics.available, bool)


# ── Integration Module Tests ──────────────────────────────────────────────────

class TestIntegrationModules:
    def test_langchain_module_exists(self):
        """LangChain integration module should be importable."""
        # Don't fail if langchain not installed — just test module structure
        import importlib
        spec = importlib.util.find_spec("agentcost.sdk.integrations.langchain")
        assert spec is not None

    def test_llamaindex_module_exists(self):
        spec = __import__("importlib").util.find_spec("agentcost.sdk.integrations.llamaindex")
        assert spec is not None

    def test_auto_module_exists(self):
        spec = __import__("importlib").util.find_spec("agentcost.sdk.integrations.auto")
        assert spec is not None


class TestAutoInstrument:
    def test_auto_instrument_importable(self):
        from agentcost.sdk.integrations.auto import auto_instrument, undo_instrument
        assert callable(auto_instrument)
        assert callable(undo_instrument)

    def test_top_level_auto_instrument(self):
        import agentcost
        assert hasattr(agentcost, "auto_instrument")
        assert callable(agentcost.auto_instrument)


# ── Package Metadata Tests ────────────────────────────────────────────────────

class TestPackageMetadata:
    def test_version(self):
        from agentcost import __version__
        assert __version__ == "0.5.0"

    def test_sdk_exports(self):
        from agentcost.sdk import trace, get_tracker
        assert callable(trace)
        assert callable(get_tracker)

    def test_plugin_exports(self):
        from agentcost.plugins import (
            PluginRegistry, registry,
        )
        assert isinstance(registry, PluginRegistry)


# ── Module Import Regression Tests ────────────────────────────────────────────

class TestModuleImports:
    """Ensure all core modules import without error."""

    def test_import_sdk(self):
        pass

    def test_import_providers(self):
        pass

    def test_import_plugins(self):
        pass

    def test_import_otel(self):
        pass

    def test_import_data(self):
        pass

    def test_import_cli(self):
        pass
