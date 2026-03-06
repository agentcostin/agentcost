"""
AgentCost — Paperclip-Inspired Features Test Suite

Tests for:
  1. Goal-Aware Cost Attribution (Blocks 3.1-3.5)
  2. Governance Templates (Blocks 1.1-1.4)
  3. Heartbeat-Based Cost Monitoring (Blocks 2.1-2.4)
"""

import time
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Goal-Aware Cost Attribution
# ═══════════════════════════════════════════════════════════════════════════════


class TestGoalCRUD:
    def test_create_goal(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        goal = svc.create_goal("g1", "Launch V2", project="app", budget=500.0)
        assert goal.id == "g1"
        assert goal.name == "Launch V2"
        assert goal.budget == 500.0

    def test_create_duplicate_raises(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("g1", "Goal 1")
        with pytest.raises(ValueError, match="already exists"):
            svc.create_goal("g1", "Duplicate")

    def test_create_with_invalid_parent_raises(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        with pytest.raises(ValueError, match="Parent goal"):
            svc.create_goal("g1", "Child", parent_goal_id="nonexistent")

    def test_get_goal(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("g1", "Test")
        assert svc.get_goal("g1").name == "Test"
        assert svc.get_goal("unknown") is None

    def test_list_goals(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("g1", "A", project="p1")
        svc.create_goal("g2", "B", project="p2")
        svc.create_goal("g3", "C", project="p1")
        assert len(svc.list_goals()) == 3
        assert len(svc.list_goals(project="p1")) == 2

    def test_update_goal(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("g1", "Old Name")
        updated = svc.update_goal("g1", name="New Name", status="completed")
        assert updated.name == "New Name"
        assert updated.status == "completed"

    def test_delete_goal(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("g1", "Test")
        assert svc.delete_goal("g1")
        assert svc.get_goal("g1") is None
        assert not svc.delete_goal("g1")  # already deleted


class TestGoalHierarchy:
    def test_parent_child(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("parent", "Parent Goal")
        svc.create_goal("child1", "Child 1", parent_goal_id="parent")
        svc.create_goal("child2", "Child 2", parent_goal_id="parent")

        children = svc.get_children("parent")
        assert len(children) == 2

    def test_ancestry_chain(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("g", "Grandparent")
        svc.create_goal("p", "Parent", parent_goal_id="g")
        svc.create_goal("c", "Child", parent_goal_id="p")

        chain = svc.get_ancestry("c")
        assert len(chain) == 3
        assert chain[0].id == "c"
        assert chain[1].id == "p"
        assert chain[2].id == "g"

    def test_list_by_parent(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("root", "Root")
        svc.create_goal("a", "A", parent_goal_id="root")
        svc.create_goal("b", "B", parent_goal_id="root")
        svc.create_goal("c", "C")  # no parent

        top_level = svc.list_goals(parent_goal_id="")
        assert len(top_level) == 2  # root and c


class TestGoalCostAttribution:
    def test_record_and_get_cost(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("g1", "Test", budget=10.0)
        svc.record_spend("g1", 2.50)
        svc.record_spend("g1", 1.50)

        cost = svc.get_goal_cost("g1")
        assert cost["direct_cost"] == pytest.approx(4.0)
        assert cost["budget_used_pct"] == pytest.approx(40.0)

    def test_cost_rollup_to_parent(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("parent", "Parent", budget=100.0)
        svc.create_goal("child1", "C1", parent_goal_id="parent")
        svc.create_goal("child2", "C2", parent_goal_id="parent")

        svc.record_spend("parent", 10.0)
        svc.record_spend("child1", 20.0)
        svc.record_spend("child2", 30.0)

        cost = svc.get_goal_cost("parent", include_children=True)
        assert cost["direct_cost"] == pytest.approx(10.0)
        assert cost["children_cost"] == pytest.approx(50.0)
        assert cost["total_cost"] == pytest.approx(60.0)
        assert cost["budget_used_pct"] == pytest.approx(60.0)

    def test_cost_without_children(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("p", "P")
        svc.create_goal("c", "C", parent_goal_id="p")
        svc.record_spend("p", 5.0)
        svc.record_spend("c", 10.0)

        cost = svc.get_goal_cost("p", include_children=False)
        assert cost["direct_cost"] == pytest.approx(5.0)
        assert cost["children_cost"] == 0.0

    def test_deep_hierarchy_rollup(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("g", "Grand", budget=100.0)
        svc.create_goal("p", "Parent", parent_goal_id="g")
        svc.create_goal("c", "Child", parent_goal_id="p")

        svc.record_spend("c", 15.0)
        cost = svc.get_goal_cost("g", include_children=True)
        assert cost["total_cost"] == pytest.approx(15.0)

    def test_budget_check(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("g1", "Test", budget=10.0)
        svc.record_spend("g1", 5.0)

        check = svc.check_goal_budget("g1")
        assert check["allowed"]

        svc.record_spend("g1", 6.0)
        check = svc.check_goal_budget("g1")
        assert not check["allowed"]

    def test_no_budget_always_allowed(self):
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("g1", "No Budget")
        svc.record_spend("g1", 1000.0)
        check = svc.check_goal_budget("g1")
        assert check["allowed"]


class TestGoalSDKIntegration:
    def test_trace_event_has_goal_id(self):
        from agentcost.sdk.trace import TraceEvent

        ev = TraceEvent(
            trace_id="t1",
            project="p",
            model="m",
            provider="p",
            input_tokens=0,
            output_tokens=0,
            cost=0.1,
            latency_ms=0,
            goal_id="my-goal",
        )
        assert ev.goal_id == "my-goal"
        d = ev.to_dict()
        assert d["goal_id"] == "my-goal"

    def test_goal_spend_recorded_via_tracker(self):
        import sys
        from agentcost.sdk.trace import CostTracker, TraceEvent
        from agentcost.goals import GoalService

        svc = GoalService()
        svc.create_goal("sdk-goal", "SDK Test")

        # Monkey-patch goal service
        import agentcost.goals as gmod

        old = gmod._global_service
        gmod._global_service = svc

        try:
            tracker = CostTracker("goal-test")
            ev = TraceEvent(
                trace_id="t1",
                project="goal-test",
                model="gpt-4o",
                provider="openai",
                input_tokens=100,
                output_tokens=50,
                cost=0.05,
                latency_ms=100,
                goal_id="sdk-goal",
            )
            tracker.record(ev)

            cost = svc.get_goal_cost("sdk-goal")
            assert cost["direct_cost"] == pytest.approx(0.05)
        finally:
            gmod._global_service = old

    def test_singleton(self):
        from agentcost.goals import get_goal_service

        s1 = get_goal_service()
        s2 = get_goal_service()
        assert s1 is s2


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Governance Templates
# ═══════════════════════════════════════════════════════════════════════════════


class TestTemplate:
    def test_from_dict(self):
        from agentcost.templates import Template

        t = Template.from_dict(
            {
                "name": "test",
                "description": "A test template",
                "budgets": [{"project": "p1", "monthly_limit": 100}],
            }
        )
        assert t.name == "test"
        assert len(t.budgets) == 1

    def test_to_dict_roundtrip(self):
        from agentcost.templates import Template

        t = Template(name="rt", description="roundtrip", tags=["test"])
        d = t.to_dict()
        t2 = Template.from_dict(d)
        assert t2.name == "rt"
        assert t2.tags == ["test"]

    def test_to_yaml(self):
        from agentcost.templates import Template

        t = Template(name="yaml-test", description="YAML export")
        yaml_str = t.to_yaml()
        assert "name: yaml-test" in yaml_str

    def test_from_yaml(self):
        from agentcost.templates import Template

        yaml_str = """
name: from-yaml
description: Loaded from YAML
budgets:
  - project: p1
    monthly_limit: 200
"""
        t = Template.from_yaml(yaml_str)
        assert t.name == "from-yaml"
        assert t.budgets[0]["monthly_limit"] == 200


class TestTemplateRegistry:
    def test_list_builtin_templates(self):
        from agentcost.templates import TemplateRegistry

        reg = TemplateRegistry()
        templates = reg.list_templates()
        names = [t["name"] for t in templates]
        assert "startup" in names
        assert "enterprise" in names
        assert "soc2-compliance" in names
        assert "agency" in names
        assert "research-lab" in names
        assert len(templates) >= 5

    def test_get_template(self):
        from agentcost.templates import TemplateRegistry

        reg = TemplateRegistry()
        t = reg.get_template("startup")
        assert t is not None
        assert t.name == "startup"
        assert len(t.tier_restrictions) > 0

    def test_preview(self):
        from agentcost.templates import TemplateRegistry

        reg = TemplateRegistry()
        preview = reg.preview("enterprise")
        assert preview is not None
        assert len(preview["cost_centers"]) == 5
        assert len(preview["policies"]) >= 2

    def test_preview_unknown(self):
        from agentcost.templates import TemplateRegistry

        reg = TemplateRegistry()
        assert reg.preview("nonexistent") is None

    def test_apply(self):
        from agentcost.templates import TemplateRegistry

        reg = TemplateRegistry()
        result = reg.apply("startup")
        assert result["template"] == "startup"
        assert len(result["sections"]) > 0
        section_names = [s["section"] for s in result["sections"]]
        assert "budgets" in section_names

    def test_apply_unknown_raises(self):
        from agentcost.templates import TemplateRegistry

        reg = TemplateRegistry()
        with pytest.raises(ValueError, match="not found"):
            reg.apply("nonexistent")

    def test_add_custom_template(self):
        from agentcost.templates import TemplateRegistry, Template

        reg = TemplateRegistry()
        custom = Template(name="my-custom", description="Custom template")
        reg.add_template(custom)
        assert reg.get_template("my-custom") is not None

    def test_load_from_yaml(self):
        from agentcost.templates import TemplateRegistry

        reg = TemplateRegistry()
        yaml_str = """
name: yaml-loaded
description: Loaded from YAML
budgets:
  - project: demo
    monthly_limit: 100
"""
        t = reg.load_from_yaml(yaml_str)
        assert t.name == "yaml-loaded"
        assert reg.get_template("yaml-loaded") is not None

    def test_export(self):
        from agentcost.templates import TemplateRegistry

        reg = TemplateRegistry()
        yaml_str = reg.export_current("my-export", "Test export")
        assert "my-export" in yaml_str

    def test_singleton(self):
        from agentcost.templates import get_template_registry

        r1 = get_template_registry()
        r2 = get_template_registry()
        assert r1 is r2


class TestBuiltinTemplateContent:
    """Verify built-in templates have valid structure."""

    @pytest.mark.parametrize(
        "name", ["startup", "enterprise", "soc2-compliance", "agency", "research-lab"]
    )
    def test_template_has_required_fields(self, name):
        from agentcost.templates import TemplateRegistry

        reg = TemplateRegistry()
        t = reg.get_template(name)
        assert t.name == name
        assert t.description
        assert t.version
        assert isinstance(t.tier_restrictions, dict)
        assert isinstance(t.budgets, list)
        assert isinstance(t.policies, list)
        assert isinstance(t.settings, dict)

    def test_enterprise_has_5_cost_centers(self):
        from agentcost.templates import TemplateRegistry

        reg = TemplateRegistry()
        t = reg.get_template("enterprise")
        assert len(t.cost_centers) == 5

    def test_soc2_blocks_free_tier(self):
        from agentcost.templates import TemplateRegistry

        reg = TemplateRegistry()
        t = reg.get_template("soc2-compliance")
        has_block = any(
            p.get("action") == "deny"
            and any(c.get("value") == "free" for c in p.get("conditions", []))
            for p in t.policies
        )
        assert has_block

    def test_startup_restricts_to_economy_standard(self):
        from agentcost.templates import TemplateRegistry

        reg = TemplateRegistry()
        t = reg.get_template("startup")
        allowed = t.tier_restrictions.get("allowed_tiers", [])
        assert "economy" in allowed
        assert "standard" in allowed
        assert "premium" not in allowed


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Heartbeat-Based Cost Monitoring
# ═══════════════════════════════════════════════════════════════════════════════


class TestHeartbeatCycle:
    def test_start_and_end_cycle(self):
        from agentcost.heartbeat import HeartbeatTracker

        ht = HeartbeatTracker()
        cycle_id = ht.start_cycle("agent-1")
        assert cycle_id
        assert "agent-1" in ht.get_all_agents()

        ht.record_spend("agent-1", 0.05)
        ht.record_spend("agent-1", 0.03)

        summary = ht.end_cycle("agent-1")
        assert summary["cost"] == pytest.approx(0.08)
        assert summary["calls"] == 2
        assert summary["status"] == "completed"
        assert summary["duration_s"] >= 0  # may be 0 if cycle is very fast

    def test_end_nonexistent_cycle(self):
        from agentcost.heartbeat import HeartbeatTracker

        ht = HeartbeatTracker()
        assert ht.end_cycle("unknown") is None

    def test_auto_end_previous_cycle(self):
        from agentcost.heartbeat import HeartbeatTracker

        ht = HeartbeatTracker()
        ht.start_cycle("a1")
        ht.record_spend("a1", 0.10)

        # Starting a new cycle ends the previous one
        ht.start_cycle("a1")
        cycles = ht.get_agent_cycles("a1")
        assert len(cycles) == 1
        assert cycles[0]["cost"] == pytest.approx(0.10)

    def test_multiple_agents(self):
        from agentcost.heartbeat import HeartbeatTracker

        ht = HeartbeatTracker()
        ht.start_cycle("a1")
        ht.start_cycle("a2")
        ht.record_spend("a1", 0.05)
        ht.record_spend("a2", 0.10)
        ht.end_cycle("a1")
        ht.end_cycle("a2")

        assert ht.get_cumulative_spend("a1") == pytest.approx(0.05)
        assert ht.get_cumulative_spend("a2") == pytest.approx(0.10)


class TestHeartbeatAnomalyDetection:
    def test_detects_cost_spike(self):
        from agentcost.heartbeat import HeartbeatTracker

        ht = HeartbeatTracker(anomaly_multiplier=2.0)

        # Build baseline: 5 cycles at ~$0.10 each
        for i in range(5):
            ht.start_cycle("a1")
            ht.record_spend("a1", 0.10)
            ht.end_cycle("a1")

        # Spike: $0.50 (5x average)
        ht.start_cycle("a1")
        ht.record_spend("a1", 0.50)
        summary = ht.end_cycle("a1")
        assert summary["status"] == "anomaly"
        assert "rolling average" in summary["anomaly_reason"]

    def test_no_anomaly_for_normal_cost(self):
        from agentcost.heartbeat import HeartbeatTracker

        ht = HeartbeatTracker()
        for i in range(5):
            ht.start_cycle("a1")
            ht.record_spend("a1", 0.10)
            ht.end_cycle("a1")

        ht.start_cycle("a1")
        ht.record_spend("a1", 0.12)  # slightly above avg
        summary = ht.end_cycle("a1")
        assert summary["status"] == "completed"


class TestHeartbeatBudget:
    def test_auto_pause_at_100_percent(self):
        from agentcost.heartbeat import HeartbeatTracker

        ht = HeartbeatTracker()
        ht.set_budget("a1", 1.00)

        ht.start_cycle("a1")
        ht.record_spend("a1", 1.10)
        ht.end_cycle("a1")

        assert ht.is_paused("a1")

    def test_not_paused_under_budget(self):
        from agentcost.heartbeat import HeartbeatTracker

        ht = HeartbeatTracker()
        ht.set_budget("a1", 10.00)

        ht.start_cycle("a1")
        ht.record_spend("a1", 0.50)
        ht.end_cycle("a1")

        assert not ht.is_paused("a1")

    def test_resume_agent(self):
        from agentcost.heartbeat import HeartbeatTracker

        ht = HeartbeatTracker()
        ht.set_budget("a1", 1.00)

        ht.start_cycle("a1")
        ht.record_spend("a1", 1.50)
        ht.end_cycle("a1")
        assert ht.is_paused("a1")

        ht.resume_agent("a1")
        assert not ht.is_paused("a1")

    def test_pause_callback(self):
        from agentcost.heartbeat import HeartbeatTracker

        callbacks = []
        ht = HeartbeatTracker(
            pause_callback=lambda aid, data: callbacks.append((aid, data))
        )
        ht.set_budget("a1", 0.50)

        ht.start_cycle("a1")
        ht.record_spend("a1", 0.60)
        ht.end_cycle("a1")

        assert len(callbacks) == 1
        assert callbacks[0][0] == "a1"
        assert callbacks[0][1]["action"] == "pause"


class TestHeartbeatSummary:
    def test_agent_summary(self):
        from agentcost.heartbeat import HeartbeatTracker

        ht = HeartbeatTracker()
        ht.set_budget("a1", 10.0)

        for _ in range(3):
            ht.start_cycle("a1")
            ht.record_spend("a1", 0.10)
            ht.end_cycle("a1")

        summary = ht.get_agent_summary("a1")
        assert summary["total_cycles"] == 3
        assert summary["total_cost"] == pytest.approx(0.30)
        assert summary["total_calls"] == 3
        assert summary["budget"] == 10.0
        assert not summary["paused"]

    def test_get_all_agents(self):
        from agentcost.heartbeat import HeartbeatTracker

        ht = HeartbeatTracker()
        ht.start_cycle("a1")
        ht.start_cycle("a2")
        ht.start_cycle("a3")
        agents = ht.get_all_agents()
        assert len(agents) == 3

    def test_reset_agent(self):
        from agentcost.heartbeat import HeartbeatTracker

        ht = HeartbeatTracker()
        ht.start_cycle("a1")
        ht.record_spend("a1", 0.10)
        ht.end_cycle("a1")

        ht.reset("a1")
        assert ht.get_cumulative_spend("a1") == 0.0
        assert ht.get_agent_cycles("a1") == []

    def test_reset_all(self):
        from agentcost.heartbeat import HeartbeatTracker

        ht = HeartbeatTracker()
        ht.start_cycle("a1")
        ht.start_cycle("a2")
        ht.reset()
        assert ht.get_all_agents() == []

    def test_singleton(self):
        from agentcost.heartbeat import get_heartbeat_tracker

        h1 = get_heartbeat_tracker()
        h2 = get_heartbeat_tracker()
        assert h1 is h2


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Cross-Feature Integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossFeatureIntegration:
    def test_goal_with_heartbeat(self):
        """Goals + Heartbeat: track goal cost within heartbeat cycles."""
        from agentcost.goals import GoalService
        from agentcost.heartbeat import HeartbeatTracker

        goals = GoalService()
        goals.create_goal("sprint-1", "Sprint 1", budget=50.0)

        ht = HeartbeatTracker()
        ht.start_cycle("agent-a")

        # Simulate work: cost goes to both heartbeat and goal
        cost = 5.0
        ht.record_spend("agent-a", cost)
        goals.record_spend("sprint-1", cost)

        ht.end_cycle("agent-a")

        assert goals.get_goal_cost("sprint-1")["direct_cost"] == pytest.approx(5.0)
        assert ht.get_cumulative_spend("agent-a") == pytest.approx(5.0)

    def test_template_with_goals(self):
        """Templates can include goal definitions."""
        from agentcost.templates import Template

        t = Template.from_dict(
            {
                "name": "with-goals",
                "description": "Template with goals",
                "goals": [
                    {"id": "q1-okr", "name": "Q1 OKR", "budget": 5000},
                    {
                        "id": "launch",
                        "name": "Product Launch",
                        "parent_goal_id": "q1-okr",
                        "budget": 2000,
                    },
                ],
            }
        )
        assert len(t.goals) == 2
        assert t.goals[0]["id"] == "q1-okr"

    def test_heartbeat_budget_pause_flow(self):
        """Full flow: budget set → cycles accumulate → auto-pause."""
        from agentcost.heartbeat import HeartbeatTracker

        paused = []
        ht = HeartbeatTracker(pause_callback=lambda a, d: paused.append(a))
        ht.set_budget("worker", 0.20)

        # Cycle 1: $0.08
        ht.start_cycle("worker")
        ht.record_spend("worker", 0.08)
        ht.end_cycle("worker")
        assert not ht.is_paused("worker")

        # Cycle 2: $0.08 (cumulative $0.16 = 80%)
        ht.start_cycle("worker")
        ht.record_spend("worker", 0.08)
        ht.end_cycle("worker")
        assert not ht.is_paused("worker")

        # Cycle 3: $0.08 (cumulative $0.24 > 100%)
        ht.start_cycle("worker")
        ht.record_spend("worker", 0.08)
        ht.end_cycle("worker")
        assert ht.is_paused("worker")
        assert "worker" in paused
