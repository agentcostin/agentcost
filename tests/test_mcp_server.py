"""Tests for AgentCost MCP Server tools.

Tests the tool functions directly (no MCP SDK transport needed).
"""

import json
import pytest

from agentcost.data.events import EventStore
from agentcost.sdk.trace import TraceEvent


@pytest.fixture
def seeded_db():
    """Seed trace data for testing."""
    store = EventStore()
    traces = [
        ("t-1", "support", "gpt-4o", "openai", 100, 50, 0.003, 200),
        ("t-2", "support", "gpt-4o", "openai", 150, 80, 0.005, 300),
        ("t-3", "support", "gpt-4o-mini", "openai", 80, 40, 0.0005, 100),
        ("t-4", "sales", "claude-sonnet-4-6", "anthropic", 200, 100, 0.006, 400),
        ("t-5", "sales", "claude-sonnet-4-6", "anthropic", 180, 90, 0.005, 350),
    ]
    for tid, proj, model, prov, inp, out, cost, lat in traces:
        event = TraceEvent(
            trace_id=tid,
            project=proj,
            model=model,
            provider=prov,
            input_tokens=inp,
            output_tokens=out,
            cost=cost,
            latency_ms=lat,
            status="success",
            timestamp="2026-03-14T10:00:00",
        )
        store.log_trace(event)
    return store


# ── Cost Analytics ───────────────────────────────────────────────────────────


class TestCostTools:
    def test_get_cost_summary_all(self, seeded_db):
        store = EventStore()
        summary = store.get_cost_summary()
        assert summary["total_calls"] == 5
        assert summary["total_cost"] > 0

    def test_get_cost_summary_by_project(self, seeded_db):
        store = EventStore()
        summary = store.get_cost_summary("support")
        assert summary["total_calls"] == 3

    def test_get_cost_by_model(self, seeded_db):
        store = EventStore()
        models = store.get_cost_by_model()
        assert len(models) >= 2
        model_names = {m["model"] for m in models}
        assert "gpt-4o" in model_names
        assert "claude-sonnet-4-6" in model_names

    def test_get_cost_by_project(self, seeded_db):
        store = EventStore()
        projects = store.get_cost_by_project()
        proj_names = {p["project"] for p in projects}
        assert "support" in proj_names
        assert "sales" in proj_names

    def test_list_projects(self, seeded_db):
        store = EventStore()
        projects = store.get_projects()
        assert "support" in projects
        assert "sales" in projects


# ── Trace Tools ──────────────────────────────────────────────────────────────


class TestTraceTools:
    def test_search_traces(self, seeded_db):
        store = EventStore()
        traces = store.get_traces(limit=50)
        assert len(traces) == 5

    def test_search_traces_by_project(self, seeded_db):
        store = EventStore()
        traces = store.get_traces(project="support")
        assert len(traces) == 3

    def test_search_traces_by_model(self, seeded_db):
        store = EventStore()
        traces = store.get_traces(model="claude-sonnet-4-6")
        assert len(traces) == 2

    def test_trace_count(self, seeded_db):
        store = EventStore()
        assert store.get_event_count() == 5
        assert store.get_event_count("sales") == 2


# ── Budget Tools ─────────────────────────────────────────────────────────────


class TestBudgetTools:
    def test_check_budget_no_budget(self, seeded_db):
        store = EventStore()
        budget = store.db.fetch_one(
            "SELECT * FROM budgets WHERE project=?", ("support",)
        )
        assert budget is None  # no budget set

    def test_set_and_check_budget(self, seeded_db):
        import time

        store = EventStore()
        now = str(time.time())
        store.db.execute(
            """INSERT INTO budgets (project, daily_limit, monthly_limit,
               alert_threshold, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("support", 10.0, 100.0, 0.8, now, now),
        )
        budget = store.db.fetch_one(
            "SELECT * FROM budgets WHERE project=?", ("support",)
        )
        assert budget is not None
        assert budget["monthly_limit"] == 100.0


# ── Estimator Tool ───────────────────────────────────────────────────────────


class TestEstimatorTool:
    def test_estimate_cost(self):
        from agentcost.providers.tracked import calculate_cost

        cost = calculate_cost("gpt-4o", 1000, 500)
        assert cost > 0

    def test_estimate_cost_unknown_model(self):
        from agentcost.providers.tracked import calculate_cost

        cost = calculate_cost("nonexistent-model-xyz", 1000, 500)
        # Should return 0 or a fallback, not crash
        assert cost >= 0


# ── Feedback Tools ───────────────────────────────────────────────────────────


class TestFeedbackTools:
    def test_submit_and_query_feedback(self, seeded_db):
        from agentcost.feedback import get_feedback_service

        svc = get_feedback_service()
        result = svc.submit("t-1", score=1, comment="Good", source="mcp")
        assert result["score"] == 1
        assert result["source"] == "mcp"

        feedback = svc.get_trace_feedback("t-1")
        assert len(feedback) == 1

    def test_quality_by_model(self, seeded_db):
        from agentcost.feedback import get_feedback_service

        svc = get_feedback_service()
        svc.submit("t-1", score=1, source="mcp")
        svc.submit("t-2", score=1, source="mcp")
        svc.submit("t-4", score=-1, source="mcp")

        quality = svc.get_quality_by_model()
        assert len(quality) >= 1


# ── Prompt Tools ─────────────────────────────────────────────────────────────


class TestPromptTools:
    def test_resolve_prompt(self):
        from agentcost.prompts import get_prompt_service

        svc = get_prompt_service()
        svc.create_prompt("mcp-test", content="Hello {{name}}, welcome to {{product}}.")
        result = svc.resolve(
            "mcp-test", variables={"name": "Agent", "product": "AgentCost"}
        )
        assert "Agent" in result["content"]
        assert "AgentCost" in result["content"]

    def test_list_prompts(self):
        from agentcost.prompts import get_prompt_service

        svc = get_prompt_service()
        svc.create_prompt("mcp-list-1", content="A")
        svc.create_prompt("mcp-list-2", content="B")
        prompts = svc.list_prompts()
        assert len(prompts) >= 2


# ── MCP Server Creation ─────────────────────────────────────────────────────


class TestMCPServerCreation:
    def test_create_server(self):
        """Verify the MCP server creates with all expected tools."""
        try:
            from agentcost.mcp import create_mcp_server

            mcp = create_mcp_server()
            tools = mcp._tool_manager.list_tools()
            tool_names = {t.name for t in tools}

            expected = {
                "get_cost_summary",
                "get_cost_by_model",
                "get_cost_by_project",
                "list_projects",
                "search_traces",
                "get_trace_count",
                "check_budget",
                "set_budget",
                "get_optimization_recommendations",
                "estimate_cost",
                "submit_feedback",
                "get_quality_by_model",
                "resolve_prompt",
                "list_prompts",
            }
            assert expected.issubset(tool_names), (
                f"Missing tools: {expected - tool_names}"
            )
        except ImportError:
            pytest.skip("mcp package not installed")
