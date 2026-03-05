"""
Tests for agentcost.plugins Phase 2 expansions:
    - TrackerPlugin
    - ReactorPlugin
    - PluginModule
    - PluginRegistry slots property
    - Reactor activation with ReactionEngine
    - Scaffold templates for new types
"""

import pytest
from dataclasses import field


# ── TrackerPlugin ────────────────────────────────────────────────────────────


class TestTrackerPlugin:
    def test_tracker_abstract(self):
        from agentcost.plugins import TrackerPlugin

        # TrackerPlugin is abstract — can't instantiate directly
        with pytest.raises(TypeError):
            TrackerPlugin()

    def test_tracker_implementation(self):
        from agentcost.plugins import (
            TrackerPlugin,
            PluginMeta,
            PluginType,
            HealthStatus,
        )

        class InMemoryTracker(TrackerPlugin):
            meta = PluginMeta(
                name="memory-tracker",
                version="1.0.0",
                plugin_type=PluginType.TRACKER,
            )

            def __init__(self):
                self._traces = []

            def record_trace(self, event: dict) -> None:
                self._traces.append(event)

            def get_spend(self, scope: str, scope_id: str, period: str = "month") -> float:
                return sum(
                    t.get("cost", 0.0)
                    for t in self._traces
                    if t.get(scope) == scope_id
                )

        tracker = InMemoryTracker()
        tracker.record_trace({"project": "prod", "cost": 1.50})
        tracker.record_trace({"project": "prod", "cost": 2.50})
        tracker.record_trace({"project": "dev", "cost": 0.10})

        assert tracker.get_spend("project", "prod") == 4.0
        assert tracker.get_spend("project", "dev") == 0.10
        assert tracker.check_budget("project", "prod", 5.0) is True
        assert tracker.check_budget("project", "prod", 3.0) is False


# ── ReactorPlugin ────────────────────────────────────────────────────────────


class TestReactorPlugin:
    def test_reactor_abstract(self):
        from agentcost.plugins import ReactorPlugin

        with pytest.raises(TypeError):
            ReactorPlugin()

    def test_reactor_implementation(self):
        from agentcost.plugins import (
            ReactorPlugin,
            PluginMeta,
            PluginType,
        )

        calls = []

        class JiraReactor(ReactorPlugin):
            meta = PluginMeta(
                name="jira-reactor",
                version="1.0.0",
                plugin_type=PluginType.REACTOR,
            )

            def get_actions(self):
                return {
                    "create-jira-ticket": self._create_ticket,
                }

            def _create_ticket(self, event_type, data):
                calls.append((event_type, data.get("message")))
                return True

        reactor = JiraReactor()
        actions = reactor.get_actions()
        assert "create-jira-ticket" in actions

        # Call the action
        result = actions["create-jira-ticket"]("budget.exceeded", {"message": "Over budget"})
        assert result is True
        assert calls == [("budget.exceeded", "Over budget")]


# ── PluginModule ─────────────────────────────────────────────────────────────


class TestPluginModule:
    def test_plugin_module_creation(self):
        from agentcost.plugins import PluginModule, NotifierPlugin, PluginMeta, PluginType, NotifyEvent, SendResult

        class TestNotifier(NotifierPlugin):
            meta = PluginMeta(
                name="test-notifier",
                version="1.0.0",
                plugin_type=PluginType.NOTIFIER,
            )

            def __init__(self):
                self._url = ""

            def configure(self, config):
                self._url = config.get("webhook_url", "")

            def send(self, event: NotifyEvent) -> SendResult:
                return SendResult(success=bool(self._url))

        module = PluginModule(
            name="agentcost-test-notifier",
            version="1.0.0",
            plugins=[TestNotifier],
            default_config={"webhook_url": "https://hooks.example.com"},
            slot="notifier",
            description="Test notifier module",
        )

        assert module.name == "agentcost-test-notifier"
        assert module.slot == "notifier"

        # Instantiate with default config
        instances = module.instantiate()
        assert len(instances) == 1
        assert instances[0]._url == "https://hooks.example.com"

        # Instantiate with override config
        instances2 = module.instantiate({"webhook_url": "https://override.com"})
        assert instances2[0]._url == "https://override.com"


# ── PluginRegistry Slots ─────────────────────────────────────────────────────


class TestRegistrySlots:
    def _make_registry(self):
        from agentcost.plugins import PluginRegistry
        return PluginRegistry()

    def test_empty_slots(self):
        reg = self._make_registry()
        slots = reg.slots
        assert slots == {
            "notifier": [],
            "policy": [],
            "exporter": [],
            "provider": [],
            "tracker": [],
            "reactor": [],
            "runtime": [],
            "agent": [],
        }

    def test_load_tracker(self):
        from agentcost.plugins import (
            PluginRegistry,
            TrackerPlugin,
            PluginMeta,
            PluginType,
        )

        class DummyTracker(TrackerPlugin):
            meta = PluginMeta(name="dummy-tracker", version="1.0", plugin_type=PluginType.TRACKER)

            def record_trace(self, event):
                pass

            def get_spend(self, scope, scope_id, period="month"):
                return 0.0

        reg = PluginRegistry()
        reg.load(DummyTracker())

        assert len(reg.trackers) == 1
        assert reg.trackers[0].meta.name == "dummy-tracker"
        assert "dummy-tracker" in reg.slots["tracker"]

    def test_load_reactor(self):
        from agentcost.plugins import (
            PluginRegistry,
            ReactorPlugin,
            PluginMeta,
            PluginType,
        )

        class DummyReactor(ReactorPlugin):
            meta = PluginMeta(name="dummy-reactor", version="1.0", plugin_type=PluginType.REACTOR)

            def get_actions(self):
                return {"dummy-action": lambda et, d: True}

        reg = PluginRegistry()
        reg.load(DummyReactor())

        assert len(reg.reactors) == 1
        assert "dummy-reactor" in reg.slots["reactor"]

    def test_unload_tracker(self):
        from agentcost.plugins import (
            PluginRegistry,
            TrackerPlugin,
            PluginMeta,
            PluginType,
        )

        class T(TrackerPlugin):
            meta = PluginMeta(name="rm-me", version="1.0", plugin_type=PluginType.TRACKER)
            def record_trace(self, e): pass
            def get_spend(self, s, si, p="month"): return 0.0

        reg = PluginRegistry()
        reg.load(T())
        assert len(reg.trackers) == 1
        reg.unload("rm-me")
        assert len(reg.trackers) == 0

    def test_load_module(self):
        from agentcost.plugins import (
            PluginModule,
            PluginRegistry,
            ExporterPlugin,
            PluginMeta,
            PluginType,
        )

        class E(ExporterPlugin):
            meta = PluginMeta(name="mod-exp", version="1.0", plugin_type=PluginType.EXPORTER)
            def export(self, traces, fmt="json"):
                return b"[]"

        module = PluginModule(name="test-module", version="1.0", plugins=[E], slot="exporter")
        reg = PluginRegistry()
        reg.load_module(module)
        assert len(reg.exporters) == 1
        assert "mod-exp" in reg.slots["exporter"]

    def test_activate_reactors(self):
        from agentcost.plugins import (
            PluginRegistry,
            ReactorPlugin,
            PluginMeta,
            PluginType,
        )
        from agentcost.reactions import ReactionEngine

        class MyReactor(ReactorPlugin):
            meta = PluginMeta(name="test-reactor", version="1.0", plugin_type=PluginType.REACTOR)

            def get_actions(self):
                return {"custom-ping": lambda et, d: True}

        reg = PluginRegistry()
        reg.load(MyReactor())

        engine = ReactionEngine()
        count = reg.activate_reactors(engine)
        assert count == 1
        assert "custom-ping" in engine.stats["registered_actions"]


# ── Scaffold New Types ───────────────────────────────────────────────────────


class TestScaffoldNewTypes:
    def test_scaffold_tracker(self, tmp_path):
        from agentcost.plugins.scaffold import scaffold_plugin

        path = scaffold_plugin("my-tracker", plugin_type="tracker", output_dir=str(tmp_path))
        plugin_py = (tmp_path / "agentcost-my-tracker" / "my_tracker" / "plugin.py").read_text()
        assert "TrackerPlugin" in plugin_py
        assert "record_trace" in plugin_py
        assert "get_spend" in plugin_py

    def test_scaffold_reactor(self, tmp_path):
        from agentcost.plugins.scaffold import scaffold_plugin

        path = scaffold_plugin("my-reactor", plugin_type="reactor", output_dir=str(tmp_path))
        plugin_py = (tmp_path / "agentcost-my-reactor" / "my_reactor" / "plugin.py").read_text()
        assert "ReactorPlugin" in plugin_py
        assert "get_actions" in plugin_py

    def test_scaffold_all_types(self, tmp_path):
        """All 8 plugin types should scaffold without error."""
        from agentcost.plugins.scaffold import scaffold_plugin, PLUGIN_TEMPLATES

        for ptype in PLUGIN_TEMPLATES:
            path = scaffold_plugin(f"test-{ptype}", plugin_type=ptype, output_dir=str(tmp_path))
            assert (tmp_path / f"agentcost-test-{ptype}" / "pyproject.toml").exists()


# ── PluginType Enum ──────────────────────────────────────────────────────────


class TestPluginType:
    def test_eight_types(self):
        from agentcost.plugins import PluginType

        assert len(PluginType) == 8
        values = {pt.value for pt in PluginType}
        assert values == {"notifier", "policy", "exporter", "provider", "tracker", "reactor", "runtime", "agent"}
