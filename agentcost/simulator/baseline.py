"""
Simulator Baseline — Compute real metrics from AgentCost trace data.

Provides the bridge between real historical data and the simulator's
configuration, so simulations are grounded in reality.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from ..data.connection import get_db
from ..data.events import EventStore


def get_baseline_metrics(project: str | None = None, hours: int = 24) -> dict:
    """
    Compute baseline metrics from real trace data for the last N hours.
    
    Returns a dict that the simulator frontend uses to seed realistic defaults:
    - avg_rps, avg_cost_per_hour, avg_tokens_per_request
    - cache_hit_rate (from gateway if available)
    - model_distribution (% of requests per model)
    - agent_distribution (% of requests per agent)
    - peak_hour_multiplier (max hour / avg hour)
    - hourly_pattern (24 values for typical daily traffic shape)
    """
    db = get_db()
    since = (datetime.now() - timedelta(hours=hours)).isoformat()

    # Build WHERE clause
    conditions = ["timestamp >= ?"]
    params: list = [since]
    if project:
        conditions.append("project = ?")
        params.append(project)
    where = "WHERE " + " AND ".join(conditions)

    # ── Core aggregates ──────────────────────────────────────────
    agg = db.fetch_one(
        f"""SELECT
            COUNT(*) as total_calls,
            COALESCE(SUM(cost), 0) as total_cost,
            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(AVG(latency_ms), 0) as avg_latency,
            COALESCE(AVG(input_tokens + output_tokens), 0) as avg_tokens_per_request,
            COUNT(DISTINCT model) as model_count,
            COUNT(DISTINCT project) as project_count,
            COUNT(DISTINCT agent_id) as agent_count
        FROM trace_events {where}""",
        params,
    )
    agg = dict(agg) if agg else {}

    total_calls = agg.get("total_calls", 0)
    total_cost = agg.get("total_cost", 0)

    # Compute rates
    avg_rps = total_calls / max(hours * 3600, 1)
    avg_cost_per_hour = total_cost / max(hours, 1)
    avg_tokens = agg.get("avg_tokens_per_request", 850)

    # ── Model distribution ────────────────────────────────────────
    model_rows = db.fetch_all(
        f"""SELECT model,
            COUNT(*) as calls,
            COALESCE(SUM(cost), 0) as cost,
            COALESCE(AVG(latency_ms), 0) as avg_latency
        FROM trace_events {where}
        GROUP BY model ORDER BY calls DESC""",
        params,
    )
    model_dist = []
    for r in model_rows:
        r = dict(r)
        r["pct"] = round(r["calls"] / max(total_calls, 1) * 100, 1)
        model_dist.append(r)

    # ── Agent distribution ────────────────────────────────────────
    agent_rows = db.fetch_all(
        f"""SELECT COALESCE(agent_id, 'unknown') as agent_id,
            COUNT(*) as calls,
            COALESCE(SUM(cost), 0) as cost
        FROM trace_events {where}
        GROUP BY agent_id ORDER BY cost DESC
        LIMIT 20""",
        params,
    )
    agent_dist = [dict(r) for r in agent_rows]

    # ── Hourly pattern (for peak detection) ───────────────────────
    # Extract hour from timestamp and compute call distribution
    hourly_rows = db.fetch_all(
        f"""SELECT
            CAST(SUBSTR(timestamp, 12, 2) AS INTEGER) as hour,
            COUNT(*) as calls,
            COALESCE(SUM(cost), 0) as cost
        FROM trace_events {where}
        GROUP BY hour ORDER BY hour""",
        params,
    )
    hourly = {int(r["hour"]): {"calls": r["calls"], "cost": r["cost"]} for r in hourly_rows}
    hourly_calls = [hourly.get(h, {}).get("calls", 0) for h in range(24)]
    avg_hourly = max(sum(hourly_calls) / max(len([x for x in hourly_calls if x > 0]), 1), 1)
    peak_calls = max(hourly_calls) if hourly_calls else 0
    peak_multiplier = round(peak_calls / avg_hourly, 2) if avg_hourly > 0 else 1.0

    # ── Budget info ───────────────────────────────────────────────
    budgets = db.fetch_all(
        "SELECT project, daily_limit, monthly_limit, total_limit, alert_threshold FROM budgets"
    )
    budget_config = [dict(b) for b in budgets]

    # ── Cache stats (from gateway if available) ───────────────────
    cache_stats = _get_cache_stats()

    # ── Error rate ────────────────────────────────────────────────
    error_row = db.fetch_one(
        f"""SELECT
            COUNT(CASE WHEN status != 'success' THEN 1 END) as errors,
            COUNT(*) as total
        FROM trace_events {where}""",
        params,
    )
    error_rate = 0
    if error_row and error_row["total"] > 0:
        error_rate = round(error_row["errors"] / error_row["total"] * 100, 2)

    return {
        # Core metrics
        "total_calls": total_calls,
        "total_cost": round(total_cost, 4),
        "avg_rps": round(avg_rps, 2),
        "avg_cost_per_hour": round(avg_cost_per_hour, 4),
        "avg_tokens_per_request": round(avg_tokens, 0),
        "avg_latency_ms": round(agg.get("avg_latency", 0), 1),
        "error_rate_pct": error_rate,
        "hours_analyzed": hours,

        # Distributions
        "model_count": agg.get("model_count", 0),
        "model_distribution": model_dist,
        "agent_count": agg.get("agent_count", 0),
        "agent_distribution": agent_dist,

        # Traffic patterns
        "hourly_pattern": hourly_calls,
        "peak_hour_multiplier": peak_multiplier,

        # Configuration
        "budget_config": budget_config,
        "cache_stats": cache_stats,

        # Simulator-ready defaults (mapped to engine/constants.js names)
        "simulator_defaults": {
            "traffic": min(100, max(10, int(avg_rps / 22 * 50))),  # Map RPS to traffic slider
            "avgTokensPerRequest": int(avg_tokens) if avg_tokens > 0 else 850,
            "budget": budget_config[0]["monthly_limit"] if budget_config and budget_config[0].get("monthly_limit") else 5000,
            "baseCacheHitRate": cache_stats.get("hit_rate_pct", 0) / 100 if cache_stats.get("hit_rate_pct") else 0.72,
            "models_in_use": [m["model"] for m in model_dist[:5]],
            "active_agents": [a["agent_id"] for a in agent_dist if a["agent_id"] != "unknown"][:10],
        },
    }


def get_architecture_config() -> dict:
    """
    Auto-detect the user's AI agent architecture from existing data.
    
    Scans trace data, budgets, gateway config, and models to build
    a realistic architecture diagram for the simulator.
    """
    db = get_db()

    # What models are in use?
    models = db.fetch_all(
        """SELECT DISTINCT model, provider,
           COUNT(*) as calls, COALESCE(SUM(cost), 0) as total_cost
        FROM trace_events
        WHERE timestamp >= datetime('now', '-7 days')
        GROUP BY model, provider ORDER BY calls DESC LIMIT 10"""
    )
    models_in_use = [dict(m) for m in models]

    # What agents are active?
    agents = db.fetch_all(
        """SELECT DISTINCT agent_id, COUNT(*) as calls
        FROM trace_events
        WHERE agent_id IS NOT NULL AND timestamp >= datetime('now', '-7 days')
        GROUP BY agent_id ORDER BY calls DESC LIMIT 10"""
    )
    active_agents = [dict(a) for a in agents]

    # Cache enabled?
    cache_stats = _get_cache_stats()
    cache_enabled = cache_stats.get("enabled", False)

    # Gateway running?
    gateway_url = os.getenv("AGENTCOST_GATEWAY_URL", "http://localhost:8200")
    gateway_enabled = False
    try:
        import urllib.request
        req = urllib.request.Request(f"{gateway_url}/health", method="GET")
        resp = urllib.request.urlopen(req, timeout=2)
        gateway_enabled = resp.status == 200
    except Exception:
        pass

    # Budget enforcement configured?
    budgets = db.fetch_all("SELECT project, monthly_limit FROM budgets WHERE monthly_limit > 0")
    budget_enforcement = len(budgets) > 0

    # Build node tags from real data
    model_tags = [m["model"].split("/")[-1][:12] for m in models_in_use[:2]] or ["GPT-4o", "Sonnet"]
    agent_tags = [a["agent_id"][:8] for a in active_agents[:2]] or ["CrewAI", "LC"]

    return {
        "models_in_use": models_in_use,
        "active_agents": active_agents,
        "cache_enabled": cache_enabled,
        "cache_stats": cache_stats,
        "gateway_enabled": gateway_enabled,
        "budget_enforcement": budget_enforcement,
        "budget_count": len(budgets),

        # Suggested node customizations for the simulator
        "node_overrides": {
            "llm": {"tags": model_tags},
            "ag": {"tags": agent_tags},
            "ch": {"tags": ["Redis", f"{cache_stats.get('hit_rate_pct', 0):.0f}% hit"] if cache_enabled else ["disabled"]},
            "gw": {"tags": ["gateway" if gateway_enabled else "direct", "REST"]},
            "db": {"tags": ["PG" if db.is_postgres() else "SQLite", "OLTP"]},
        },
    }


def compute_whatif_projection(
    baseline: dict,
    changes: dict,
    days: int = 30,
) -> dict:
    """
    Run a what-if cost projection.
    
    Takes baseline metrics and a dict of changes, then projects
    costs forward for N days.
    
    changes can include:
    - price_multiplier: float (e.g., 2.0 for 2× price increase)
    - cache_hit_rate: float (e.g., 0.85 for 85% hit rate)
    - traffic_multiplier: float (e.g., 1.5 for 50% more traffic)
    - tokens_per_request: int (override avg tokens)
    - add_model: str (add a cheaper/more expensive model)
    """
    base_cost_per_hour = baseline.get("avg_cost_per_hour", 0)
    base_rps = baseline.get("avg_rps", 0)
    base_tokens = baseline.get("avg_tokens_per_request", 850)
    base_cache = baseline.get("simulator_defaults", {}).get("baseCacheHitRate", 0.72)

    # Apply changes
    price_mult = changes.get("price_multiplier", 1.0)
    traffic_mult = changes.get("traffic_multiplier", 1.0)
    new_cache = changes.get("cache_hit_rate", base_cache)
    new_tokens = changes.get("tokens_per_request", base_tokens)

    # Calculate cost impact
    # Cost ~ (RPS × (1 - cache_hit_rate) × tokens × price)
    base_effective = base_rps * (1 - base_cache) * base_tokens
    new_effective = (base_rps * traffic_mult) * (1 - new_cache) * new_tokens * price_mult

    ratio = new_effective / max(base_effective, 0.001) if base_effective > 0 else 1.0
    new_cost_per_hour = base_cost_per_hour * ratio

    # Project daily
    base_daily = base_cost_per_hour * 24
    new_daily = new_cost_per_hour * 24

    daily_breakdown = []
    for day in range(1, days + 1):
        # Apply hourly pattern variation (±15% random for realism)
        import random
        variance = 1.0 + (random.random() - 0.5) * 0.3
        daily_breakdown.append({
            "day": day,
            "baseline_cost": round(base_daily * variance, 2),
            "projected_cost": round(new_daily * variance, 2),
        })

    base_monthly = base_daily * 30
    new_monthly = new_daily * 30
    delta = new_monthly - base_monthly

    # Risk assessment
    risk_events = []
    budget = baseline.get("simulator_defaults", {}).get("budget", 5000)
    if new_monthly > budget:
        risk_events.append({
            "type": "budget_breach",
            "severity": "critical",
            "message": f"Projected monthly cost ${new_monthly:.0f} exceeds budget ${budget:.0f}",
            "day_of_breach": max(1, int(budget / max(new_daily, 0.01))),
        })
    if new_monthly > base_monthly * 2:
        risk_events.append({
            "type": "cost_spike",
            "severity": "warning",
            "message": f"Cost increase of {((new_monthly / max(base_monthly, 0.01)) - 1) * 100:.0f}% projected",
        })
    if new_cache < 0.1 and base_cache > 0.5:
        risk_events.append({
            "type": "cache_degradation",
            "severity": "warning",
            "message": f"Cache hit rate dropping from {base_cache*100:.0f}% to {new_cache*100:.0f}%",
        })

    # Recommendations
    recommendations = []
    if new_monthly > budget:
        savings_with_cache = new_daily * 24 * 0.7 * 30  # assume 70% cache hit saves 70%
        recommendations.append(f"Enable semantic caching to potentially save ~${base_monthly - savings_with_cache:.0f}/mo")
    if len(baseline.get("model_distribution", [])) == 1:
        recommendations.append("Consider multi-model routing to reduce single-provider risk")
    if not baseline.get("budget_config"):
        recommendations.append("Set up budget alerts to catch cost spikes before they exceed limits")

    return {
        "baseline": {
            "cost_per_hour": round(base_cost_per_hour, 4),
            "cost_per_day": round(base_daily, 2),
            "cost_per_month": round(base_monthly, 2),
        },
        "projected": {
            "cost_per_hour": round(new_cost_per_hour, 4),
            "cost_per_day": round(new_daily, 2),
            "cost_per_month": round(new_monthly, 2),
        },
        "delta": round(delta, 2),
        "delta_pct": round((ratio - 1) * 100, 1),
        "changes_applied": changes,
        "daily_breakdown": daily_breakdown,
        "risk_events": risk_events,
        "recommendations": recommendations,
    }


def _get_cache_stats() -> dict:
    """Fetch cache stats from gateway, return empty dict on failure."""
    gateway_url = os.getenv("AGENTCOST_GATEWAY_URL", "http://localhost:8200")
    try:
        import urllib.request
        import json as _json
        req = urllib.request.Request(f"{gateway_url}/v1/gateway/cache/stats", method="GET")
        resp = urllib.request.urlopen(req, timeout=2)
        return _json.loads(resp.read().decode())
    except Exception:
        return {"enabled": False, "hit_rate_pct": 0, "entries": 0}
