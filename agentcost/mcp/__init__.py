"""
AgentCost MCP Server — Expose cost governance tools via Model Context Protocol.

Allows Claude Desktop, Cursor, VS Code, and any MCP-compatible agent to:
- Query cost analytics (total spend, per-model breakdown, trends)
- Check and set budgets
- Search traces
- Get optimization recommendations
- Submit and query feedback
- Resolve prompts

Run standalone:
    python -m agentcost.mcp.server

Or configure in Claude Desktop / Cursor:
    {
      "mcpServers": {
        "agentcost": {
          "command": "python",
          "args": ["-m", "agentcost.mcp.server"]
        }
      }
    }

Or via SSE transport for remote access:
    python -m agentcost.mcp.server --transport sse --port 8300
"""

from __future__ import annotations

import json
import logging
import os
import sys

logger = logging.getLogger("agentcost.mcp")


def create_mcp_server():
    """Create and configure the AgentCost MCP server with all tools."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("AgentCost")

    # ── Cost Analytics Tools ─────────────────────────────────────

    @mcp.tool()
    def get_cost_summary(project: str = "") -> dict:
        """Get overall cost summary — total spend, calls, tokens, model count.

        Args:
            project: Filter by project name. Leave empty for all projects.
        """
        from ..data.events import EventStore

        store = EventStore()
        return store.get_cost_summary(project or None)

    @mcp.tool()
    def get_cost_by_model(project: str = "") -> list[dict]:
        """Get cost breakdown per model — calls, cost, tokens, latency.

        Args:
            project: Filter by project name. Leave empty for all projects.
        """
        from ..data.events import EventStore

        store = EventStore()
        return store.get_cost_by_model(project or None)

    @mcp.tool()
    def get_cost_by_project() -> list[dict]:
        """Get cost breakdown per project — calls, cost, tokens."""
        from ..data.events import EventStore

        store = EventStore()
        return store.get_cost_by_project()

    @mcp.tool()
    def list_projects() -> list[str]:
        """List all projects that have trace data."""
        from ..data.events import EventStore

        store = EventStore()
        return store.get_projects()

    # ── Trace Tools ──────────────────────────────────────────────

    @mcp.tool()
    def search_traces(
        project: str = "",
        model: str = "",
        limit: int = 50,
    ) -> list[dict]:
        """Search recent LLM traces with optional filters.

        Args:
            project: Filter by project name.
            model: Filter by model name (e.g. 'gpt-4o', 'claude-sonnet-4-6').
            limit: Max number of traces to return (default 50).
        """
        from ..data.events import EventStore

        store = EventStore()
        return store.get_traces(
            project=project or None,
            model=model or None,
            limit=min(limit, 200),
        )

    @mcp.tool()
    def get_trace_count(project: str = "") -> dict:
        """Get total trace count, optionally filtered by project."""
        from ..data.events import EventStore

        store = EventStore()
        count = store.get_event_count(project or None)
        return {"project": project or "all", "count": count}

    # ── Budget Tools ─────────────────────────────────────────────

    @mcp.tool()
    def check_budget(project: str) -> dict:
        """Check budget status for a project — spend, limits, utilization.

        Args:
            project: The project to check budget for.
        """
        from ..data.events import EventStore

        store = EventStore()
        summary = store.get_cost_summary(project)
        budget = store.db.fetch_one("SELECT * FROM budgets WHERE project=?", (project,))
        if not budget:
            return {
                "project": project,
                "total_spend": summary.get("total_cost", 0),
                "budget_set": False,
                "message": f"No budget configured for '{project}'",
            }

        total_spend = summary.get("total_cost", 0)
        monthly = budget.get("monthly_limit", 0) or 0
        daily = budget.get("daily_limit", 0) or 0
        return {
            "project": project,
            "total_spend": round(total_spend, 4),
            "daily_limit": daily,
            "monthly_limit": monthly,
            "monthly_utilization_pct": round(total_spend / monthly * 100, 1)
            if monthly > 0
            else 0,
            "budget_set": True,
        }

    @mcp.tool()
    def set_budget(
        project: str,
        daily_limit: float = 0,
        monthly_limit: float = 0,
    ) -> dict:
        """Set or update budget limits for a project.

        Args:
            project: The project to set budget for.
            daily_limit: Daily spending limit in USD (0 = no limit).
            monthly_limit: Monthly spending limit in USD (0 = no limit).
        """
        from ..data.events import EventStore
        import time

        store = EventStore()
        existing = store.db.fetch_one(
            "SELECT * FROM budgets WHERE project=?", (project,)
        )
        now = str(time.time())
        if existing:
            store.db.execute(
                "UPDATE budgets SET daily_limit=?, monthly_limit=?, updated_at=? WHERE project=?",
                (daily_limit or None, monthly_limit or None, now, project),
            )
        else:
            store.db.execute(
                """INSERT INTO budgets (project, daily_limit, monthly_limit,
                   alert_threshold, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (project, daily_limit or None, monthly_limit or None, 0.8, now, now),
            )
        return {
            "status": "ok",
            "project": project,
            "daily_limit": daily_limit,
            "monthly_limit": monthly_limit,
        }

    # ── Optimizer Tools ──────────────────────────────────────────

    @mcp.tool()
    def get_optimization_recommendations(project: str = "default") -> dict:
        """Get model optimization recommendations — which models to downgrade for savings.

        Args:
            project: The project to analyze.
        """
        try:
            from ..optimizer import get_optimizer_report

            return get_optimizer_report(project)
        except Exception as e:
            return {"error": str(e), "project": project}

    @mcp.tool()
    def estimate_cost(
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> dict:
        """Estimate the cost of an LLM call before making it.

        Args:
            model: Model name (e.g. 'gpt-4o', 'claude-sonnet-4-6').
            input_tokens: Number of input/prompt tokens.
            output_tokens: Number of output/completion tokens.
        """
        from ..providers.tracked import calculate_cost

        cost = calculate_cost(model, input_tokens, output_tokens)
        return {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": round(cost, 8),
        }

    # ── Feedback Tools ───────────────────────────────────────────

    @mcp.tool()
    def submit_feedback(
        trace_id: str,
        score: int,
        comment: str = "",
    ) -> dict:
        """Submit quality feedback on an LLM trace.

        Args:
            trace_id: The trace ID to rate.
            score: 1 for thumbs up, -1 for thumbs down, 0 for neutral.
            comment: Optional text comment.
        """
        from ..feedback import get_feedback_service

        svc = get_feedback_service()
        return svc.submit(trace_id, score=score, comment=comment, source="mcp")

    @mcp.tool()
    def get_quality_by_model(project: str = "") -> list[dict]:
        """Get quality ratings breakdown per model — positive %, cost per positive.

        Args:
            project: Filter by project. Leave empty for all.
        """
        from ..feedback import get_feedback_service

        svc = get_feedback_service()
        return svc.get_quality_by_model(project=project or None)

    # ── Prompt Tools ─────────────────────────────────────────────

    @mcp.tool()
    def resolve_prompt(
        name: str,
        environment: str = "production",
        variables: str = "{}",
    ) -> dict:
        """Resolve a managed prompt — returns the deployed content with variables filled.

        Args:
            name: Prompt name or ID.
            environment: Deployment environment (production, staging, dev).
            variables: JSON string of variable values, e.g. '{"product": "AgentCost"}'.
        """
        from ..prompts import get_prompt_service

        svc = get_prompt_service()
        try:
            vars_dict = json.loads(variables) if variables else {}
        except json.JSONDecodeError:
            vars_dict = {}
        return svc.resolve(name, environment=environment, variables=vars_dict)

    @mcp.tool()
    def list_prompts(project: str = "") -> list[dict]:
        """List all managed prompts with their latest version and deployments.

        Args:
            project: Filter by project. Leave empty for all.
        """
        from ..prompts import get_prompt_service

        svc = get_prompt_service()
        return svc.list_prompts(project=project or None)

    # ── Resources ────────────────────────────────────────────────

    @mcp.resource("agentcost://status")
    def server_status() -> str:
        """AgentCost server status and feature summary."""
        from ..data.events import EventStore

        store = EventStore()
        summary = store.get_cost_summary()
        projects = store.get_projects()
        return json.dumps(
            {
                "status": "running",
                "total_traces": summary.get("total_calls", 0),
                "total_cost": round(summary.get("total_cost", 0), 4),
                "projects": projects,
                "models_in_db": summary.get("model_count", 0),
                "features": [
                    "cost_tracking",
                    "budgets",
                    "forecasting",
                    "optimization",
                    "prompt_management",
                    "feedback",
                    "otel_collector",
                    "semantic_caching",
                ],
            },
            indent=2,
        )

    return mcp


def main():
    """Run the AgentCost MCP server."""
    import argparse

    parser = argparse.ArgumentParser(description="AgentCost MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8300,
        help="Port for SSE transport (default: 8300)",
    )
    args = parser.parse_args()

    mcp = create_mcp_server()

    if args.transport == "sse":
        mcp.run(transport="sse", sse_port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
