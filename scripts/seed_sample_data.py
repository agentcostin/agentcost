#!/usr/bin/env python3
"""
AgentCost — Seed Sample Trace Data (7 days)

Generates realistic trace events across multiple models, projects,
and agents for testing Forecast, Optimizer, Analytics, and Anomaly
detection features.

Usage:
    python scripts/seed_sample_data.py              # default SQLite
    python scripts/seed_sample_data.py --project myapp
    python scripts/seed_sample_data.py --days 14    # 2 weeks
    python scripts/seed_sample_data.py --clear      # wipe first

The script can also be imported:
    from scripts.seed_sample_data import seed
    seed(project="demo", days=7)
"""
from __future__ import annotations

import argparse
import random
import uuid
from datetime import datetime, timedelta

# ── Pricing per 1M tokens (Feb 2026) ────────────────────────────────────────
MODEL_PROFILES = [
    # (model_id, provider, input_$/M, output_$/M, avg_input_tok, avg_output_tok, weight)
    # weight = relative frequency of use
    ("claude-sonnet-4-6",   "anthropic",  3.00,  15.00, 1200, 800, 30),
    ("claude-opus-4-6",     "anthropic",  5.00,  25.00, 2000, 1500, 8),
    ("claude-haiku-4-5",    "anthropic",  0.80,   4.00,  600, 400, 20),
    ("gpt-5.2",             "openai",     1.25,  10.00, 1500, 1000, 15),
    ("gpt-5.2-pro",         "openai",    21.00, 168.00, 3000, 2000, 2),
    ("gpt-4.1-mini",        "openai",     0.40,   1.60,  800, 500, 18),
    ("gpt-4.1-nano",        "openai",     0.10,   0.40,  500, 300, 10),
    ("gemini-3-pro",        "google",     2.00,  12.00, 1100, 900, 12),
    ("gemini-2.5-flash",    "google",     0.15,   0.60,  700, 500, 15),
    ("deepseek-chat",       "deepseek",   0.07,   1.10,  900, 700, 8),
    ("deepseek-reasoner",   "deepseek",   0.55,   2.19, 1800, 1200, 3),
]

PROJECTS = {
    "default":       {"agents": ["chatbot", "assistant"],  "weight": 35},
    "customer-support": {"agents": ["ticket-classifier", "response-drafter", "escalation-agent"], "weight": 25},
    "data-pipeline": {"agents": ["extractor", "transformer", "summarizer"], "weight": 20},
    "code-review":   {"agents": ["reviewer", "security-scan"], "weight": 15},
    "research":      {"agents": ["analyst"],  "weight": 5},
}

TASK_TYPES = ["chat", "code", "summary", "analysis", "classification", "translation", "creative"]

# ── Realistic daily patterns ─────────────────────────────────────────────────
# Hour-of-day activity weights (business hours peak)
HOURLY_WEIGHTS = [
    1, 1, 1, 1, 1, 2,       # 00-05: minimal
    4, 8, 12, 15, 14, 13,   # 06-11: ramp up
    10, 14, 15, 14, 12, 10, # 12-17: afternoon peak
    7, 5, 3, 2, 2, 1,       # 18-23: wind down
]

# Day-of-week multipliers (Mon=0)
DOW_MULTIPLIER = [1.0, 1.1, 1.15, 1.1, 0.95, 0.4, 0.25]

# Weekly growth trend (slight increase day over day)
DAILY_GROWTH_RATE = 1.03  # 3% daily growth to make forecast interesting


def _cost(input_tok: int, output_tok: int, in_price: float, out_price: float) -> float:
    return (input_tok * in_price + output_tok * out_price) / 1_000_000


def _pick_model(models=MODEL_PROFILES):
    weights = [m[6] for m in models]
    return random.choices(models, weights=weights, k=1)[0]


def _pick_project(projects=PROJECTS):
    names = list(projects.keys())
    weights = [projects[n]["weight"] for n in names]
    name = random.choices(names, weights=weights, k=1)[0]
    agent = random.choice(projects[name]["agents"])
    return name, agent


def _jitter(base: int, pct: float = 0.4) -> int:
    """Add random jitter to a base value."""
    lo = int(base * (1 - pct))
    hi = int(base * (1 + pct))
    return max(1, random.randint(lo, hi))


def generate_traces(
    days: int = 7,
    base_calls_per_day: int = 120,
    project_filter: str | None = None,
) -> list[dict]:
    """
    Generate realistic trace events.

    Args:
        days: Number of days of history to generate (ending today)
        base_calls_per_day: Approximate calls on day 1 (grows over time)
        project_filter: If set, only generate for this project

    Returns:
        List of trace event dicts ready for EventStore.log_trace()
    """
    traces = []
    now = datetime.now()
    start = now - timedelta(days=days)

    for day_offset in range(days):
        day = start + timedelta(days=day_offset)
        dow = day.weekday()

        # Scale calls: base × day-of-week × growth
        day_calls = int(
            base_calls_per_day
            * DOW_MULTIPLIER[dow]
            * (DAILY_GROWTH_RATE ** day_offset)
        )
        # Add some daily randomness
        day_calls = max(10, day_calls + random.randint(-15, 15))

        for _ in range(day_calls):
            # Pick hour weighted by business patterns
            hour = random.choices(range(24), weights=HOURLY_WEIGHTS, k=1)[0]
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            ts = day.replace(hour=hour, minute=minute, second=second)

            model_id, provider, in_price, out_price, avg_in, avg_out, _ = _pick_model()

            if project_filter:
                proj = project_filter
                agents = PROJECTS.get(proj, {"agents": ["agent"]})["agents"]
                agent = random.choice(agents)
            else:
                proj, agent = _pick_project()

            input_tok = _jitter(avg_in)
            output_tok = _jitter(avg_out)
            cost = _cost(input_tok, output_tok, in_price, out_price)

            # Latency correlates with tokens and model tier
            base_latency = 200 + output_tok * 0.5
            if "opus" in model_id or "pro" in model_id:
                base_latency *= 1.8
            elif "haiku" in model_id or "nano" in model_id or "flash" in model_id:
                base_latency *= 0.5
            latency = max(50, base_latency * random.uniform(0.6, 1.5))

            # ~3% error rate
            status = "error" if random.random() < 0.03 else "success"
            error = random.choice([
                "Rate limit exceeded", "Context length exceeded",
                "Connection timeout", "Internal server error",
            ]) if status == "error" else None

            if status == "error":
                cost = 0
                output_tok = 0

            session_id = f"sess-{day.strftime('%Y%m%d')}-{random.randint(1,50):03d}"

            traces.append({
                "trace_id": uuid.uuid4().hex[:12],
                "project": proj,
                "agent_id": agent,
                "session_id": session_id,
                "model": model_id,
                "provider": provider,
                "input_tokens": input_tok,
                "output_tokens": output_tok,
                "cost": round(cost, 8),
                "latency_ms": round(latency, 1),
                "status": status,
                "error": error,
                "metadata": None,
                "timestamp": ts.isoformat(),
            })

    # Sort by timestamp
    traces.sort(key=lambda t: t["timestamp"])
    return traces


def seed(project: str | None = None, days: int = 7, clear: bool = False):
    """Seed the database with sample traces."""
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from agentcost.data.events import EventStore
    from agentcost.sdk.trace import TraceEvent

    store = EventStore()

    if clear:
        store.db.execute("DELETE FROM trace_events")
        print("🗑️  Cleared existing trace data")

    traces = generate_traces(days=days, project_filter=project)

    for t in traces:
        event = TraceEvent(
            trace_id=t["trace_id"],
            project=t["project"],
            model=t["model"],
            provider=t["provider"],
            input_tokens=t["input_tokens"],
            output_tokens=t["output_tokens"],
            cost=t["cost"],
            latency_ms=t["latency_ms"],
            status=t["status"],
            error=t["error"],
            timestamp=t["timestamp"],
            metadata={},
            agent_id=t["agent_id"],
            session_id=t["session_id"],
        )
        store.log_trace(event)

    # Summary
    projects_seen = set(t["project"] for t in traces)
    models_seen = set(t["model"] for t in traces)
    total_cost = sum(t["cost"] for t in traces)
    errors = sum(1 for t in traces if t["status"] == "error")

    print(f"✅ Seeded {len(traces)} trace events over {days} days")
    print(f"   Projects: {', '.join(sorted(projects_seen))}")
    print(f"   Models:   {len(models_seen)} ({', '.join(sorted(models_seen)[:5])}…)")
    print(f"   Cost:     ${total_cost:.2f}")
    print(f"   Errors:   {errors} ({errors/len(traces)*100:.1f}%)")
    print()

    # Per-project breakdown
    from collections import Counter
    proj_counts = Counter(t["project"] for t in traces)
    proj_costs = {}
    for t in traces:
        proj_costs[t["project"]] = proj_costs.get(t["project"], 0) + t["cost"]

    print("   Per-project breakdown:")
    for p in sorted(proj_counts):
        print(f"     {p:25s} {proj_counts[p]:5d} calls  ${proj_costs[p]:8.2f}")

    # Per-day breakdown
    from collections import defaultdict
    daily = defaultdict(lambda: {"calls": 0, "cost": 0.0})
    for t in traces:
        d = t["timestamp"][:10]
        daily[d]["calls"] += 1
        daily[d]["cost"] += t["cost"]

    print()
    print("   Daily breakdown:")
    for d in sorted(daily):
        dow = datetime.fromisoformat(d).strftime("%a")
        print(f"     {d} ({dow})  {daily[d]['calls']:4d} calls  ${daily[d]['cost']:7.2f}")

    return traces


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed AgentCost with sample trace data")
    parser.add_argument("--project", help="Generate only for this project")
    parser.add_argument("--days", type=int, default=7, help="Days of history (default: 7)")
    parser.add_argument("--clear", action="store_true", help="Clear existing data first")
    args = parser.parse_args()

    seed(project=args.project, days=args.days, clear=args.clear)