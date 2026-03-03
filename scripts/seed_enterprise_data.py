#!/usr/bin/env python3
"""
AgentCost — Seed Enterprise Data (Governance & Operations)

Seeds: Orgs, Users, Cost Centers, Budgets, Policies, Approvals,
       Notification Channels, Scorecards, and Audit Log entries.

Usage:
    python scripts/seed_enterprise_data.py
    python scripts/seed_enterprise_data.py --clear   # wipe enterprise tables first
    python scripts/seed_enterprise_data.py --with-traces --days 14  # also seed traces

Requires the server to have run at least once (to auto-migrate tables),
or run after: docker compose up migrate
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentcost.data.connection import get_db


def _ensure_tables():
    """Apply enterprise schema to SQLite if tables don't exist."""
    from pathlib import Path
    db = get_db()
    # Check if tables exist
    try:
        db.fetch_one("SELECT 1 FROM orgs LIMIT 1")
        return  # tables exist
    except Exception:
        pass
    # Apply migrations
    mig_dir = Path(__file__).parent.parent / "agentcost" / "data" / "migrations"
    for sql_file in sorted(mig_dir.glob("*.sql")):
        sql = sql_file.read_text()
        sql = sql.replace("TIMESTAMPTZ", "TEXT")
        sql = sql.replace("JSONB", "TEXT")
        sql = sql.replace("DOUBLE PRECISION", "REAL")
        sql = sql.replace("BOOLEAN", "INTEGER")
        sql = sql.replace("DEFAULT NOW()", "DEFAULT (datetime('now'))")
        sql = sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        lines = [line for line in sql.split("\n") if "INSERT INTO schema_version" not in line and "ON CONFLICT" not in line]
        sql = "\n".join(lines)
        try:
            db.executescript(sql)
        except Exception:
            pass
    print("  📦 Enterprise tables created")


def _id():
    return str(uuid.uuid4())


def _now():
    return datetime.utcnow().isoformat()


def _ago(days=0, hours=0):
    return (datetime.utcnow() - timedelta(days=days, hours=hours)).isoformat()


def seed_enterprise(clear: bool = False, with_traces: bool = False, days: int = 14):
    _ensure_tables()
    db = get_db()

    # ── Clear if requested ──────────────────────────────────────────────
    if clear:
        for table in [
            "agent_scorecards", "notification_channels", "approval_requests",
            "policies", "cost_allocations", "cost_centers", "audit_log",
            "invites", "api_keys", "users", "orgs",
        ]:
            try:
                db.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        print("🗑️  Cleared enterprise tables")

    # ═══════════════════════════════════════════════════════════════════
    # ORGANIZATIONS
    # ═══════════════════════════════════════════════════════════════════
    org_id = _id()
    db.execute(
        "INSERT INTO orgs (id, name, slug, plan, sso_provider, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (org_id, "Acme AI Corp", "acme-ai", "enterprise", "keycloak", _ago(90))
    )
    print(f"  🏢 Org: Acme AI Corp ({org_id[:8]}…)")

    # ═══════════════════════════════════════════════════════════════════
    # USERS (Team Members)
    # ═══════════════════════════════════════════════════════════════════
    users = [
        (_id(), "open@agentcost.in", "Rajneesh Kumar", "admin", _ago(90)),
        (_id(), "care@agentcost.in", "Demo User", "viewer", _ago(85)),
        (_id(), "sarah.chen@acme.ai", "Sarah Chen", "manager", _ago(60)),
        (_id(), "mike.jones@acme.ai", "Mike Jones", "agent_dev", _ago(45)),
        (_id(), "priya.patel@acme.ai", "Priya Patel", "manager", _ago(30)),
        (_id(), "alex.kim@acme.ai", "Alex Kim", "agent_dev", _ago(20)),
        (_id(), "jordan.lee@acme.ai", "Jordan Lee", "viewer", _ago(10)),
    ]
    for uid, email, name, role, created in users:
        db.execute(
            "INSERT INTO users (id, email, name, org_id, role, created_at, last_login_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, email, name, org_id, role, created, _ago(0, hours=2))
        )
    admin_id = users[0][0]
    sarah_id = users[2][0]
    mike_id = users[3][0]
    priya_id = users[4][0]
    alex_id = users[5][0]
    print(f"  👥 Users: {len(users)} team members")

    # ═══════════════════════════════════════════════════════════════════
    # INVITES
    # ═══════════════════════════════════════════════════════════════════
    invites = [
        (_id(), "new.hire@acme.ai", "agent_dev", "pending", admin_id),
        (_id(), "contractor@external.com", "viewer", "pending", sarah_id),
        (_id(), "past.employee@acme.ai", "viewer", "expired", admin_id),
    ]
    for iid, email, role, status, invited_by in invites:
        db.execute(
            "INSERT INTO invites (id, org_id, email, role, invited_by, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (iid, org_id, email, role, invited_by, status, _ago(5))
        )
    print(f"  📧 Invites: {len(invites)} ({sum(1 for i in invites if i[3]=='pending')} pending)")

    # ═══════════════════════════════════════════════════════════════════
    # API KEYS
    # ═══════════════════════════════════════════════════════════════════
    import hashlib
    keys = [
        (_id(), "ac_live_prod", hashlib.sha256(b"ac_live_prod_key_123").hexdigest(), "Production SDK", "traces.write,traces.read", admin_id),
        (_id(), "ac_live_stag", hashlib.sha256(b"ac_live_staging_456").hexdigest(), "Staging SDK", "traces.write", mike_id),
        (_id(), "ac_test_dev1", hashlib.sha256(b"ac_test_dev_key_789").hexdigest(), "Dev Testing", "*", alex_id),
    ]
    for kid, prefix, khash, name, scopes, created_by in keys:
        db.execute(
            "INSERT INTO api_keys (id, org_id, key_prefix, key_hash, name, scopes, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (kid, org_id, prefix, khash, name, scopes, created_by, _ago(30))
        )
    print(f"  🔑 API Keys: {len(keys)}")

    # ═══════════════════════════════════════════════════════════════════
    # COST CENTERS
    # ═══════════════════════════════════════════════════════════════════
    cost_centers = [
        (_id(), "Engineering", "ENG-001", sarah_id, 15000.0),
        (_id(), "Customer Support", "CS-002", priya_id, 8000.0),
        (_id(), "Research", "RES-003", sarah_id, 25000.0),
        (_id(), "Marketing", "MKT-004", priya_id, 5000.0),
        (_id(), "Data Pipeline", "DATA-005", mike_id, 12000.0),
    ]
    for ccid, name, code, mgr, budget in cost_centers:
        db.execute(
            "INSERT INTO cost_centers (id, org_id, name, code, manager_email, monthly_budget, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ccid, org_id, name, code, mgr, budget, _ago(60))
        )
    eng_cc = cost_centers[0][0]
    cs_cc = cost_centers[1][0]
    res_cc = cost_centers[2][0]
    data_cc = cost_centers[4][0]
    print(f"  💰 Cost Centers: {len(cost_centers)} (total budget: ${sum(c[4] for c in cost_centers):,.0f}/mo)")

    # ═══════════════════════════════════════════════════════════════════
    # COST ALLOCATIONS (project → cost center)
    # ═══════════════════════════════════════════════════════════════════
    allocations = [
        (org_id, "default", None, eng_cc, 100.0),
        (org_id, "customer-support", None, cs_cc, 100.0),
        (org_id, "data-pipeline", None, data_cc, 100.0),
        (org_id, "code-review", None, eng_cc, 60.0),
        (org_id, "code-review", None, res_cc, 40.0),  # split allocation
        (org_id, "research", None, res_cc, 100.0),
    ]
    for oid, proj, agent, ccid, pct in allocations:
        db.execute(
            "INSERT INTO cost_allocations (org_id, project, agent_id, cost_center_id, allocation_pct, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (oid, proj, agent, ccid, pct, _ago(55))
        )
    print(f"  🔗 Allocations: {len(allocations)} rules")

    # ═══════════════════════════════════════════════════════════════════
    # BUDGETS (via BudgetService — uses budgets table from Phase 2)
    # ═══════════════════════════════════════════════════════════════════
    budgets = [
        (org_id, "default", 50.0, 1000.0),
        (org_id, "customer-support", 30.0, 600.0),
        (org_id, "data-pipeline", 80.0, 1500.0),
        (org_id, "research", 100.0, 2500.0),
        (org_id, "code-review", 40.0, 800.0),
    ]
    for oid, proj, daily, monthly in budgets:
        try:
            db.execute(
                "INSERT OR REPLACE INTO budgets (org_id, project, daily_limit, monthly_limit, created_at) VALUES (?, ?, ?, ?, ?)",
                (oid, proj, daily, monthly, _ago(50))
            )
        except Exception:
            # budgets table might have different schema
            from agentcost.cost import BudgetService
            BudgetService().set_budget(org_id=oid, project=proj, daily_limit=daily, monthly_limit=monthly)
    print(f"  📊 Budgets: {len(budgets)} project budgets")

    # ═══════════════════════════════════════════════════════════════════
    # POLICIES
    # ═══════════════════════════════════════════════════════════════════
    policies = [
        (_id(), "Block Premium Models in Staging", True, 10,
         json.dumps([{"field": "model", "op": "in", "value": ["gpt-5.2-pro", "claude-opus-4-6"]},
                     {"field": "project", "op": "eq", "value": "staging"}]),
         "deny", "Premium models are not allowed in staging environment"),

        (_id(), "Rate Limit Research Project", True, 20,
         json.dumps([{"field": "project", "op": "eq", "value": "research"},
                     {"field": "cost", "op": "gt", "value": 0.50}]),
         "require_approval", "High-cost research calls require manager approval"),

        (_id(), "Audit All GPT-5.2-Pro Usage", True, 50,
         json.dumps([{"field": "model", "op": "eq", "value": "gpt-5.2-pro"}]),
         "log_only", "All premium model usage is logged for review"),

        (_id(), "Block After Hours (Weekends)", True, 30,
         json.dumps([{"field": "day_of_week", "op": "in", "value": ["Saturday", "Sunday"]}]),
         "deny", "AI calls are restricted on weekends to control costs"),

        (_id(), "Cost Cap Per Call", True, 15,
         json.dumps([{"field": "estimated_cost", "op": "gt", "value": 5.00}]),
         "require_approval", "Individual calls exceeding $5 require approval"),

        (_id(), "Allow All for Data Pipeline", True, 5,
         json.dumps([{"field": "project", "op": "eq", "value": "data-pipeline"}]),
         "allow", "Data pipeline has pre-approved access to all models"),

        (_id(), "Deprecated: Block All External", False, 100,
         json.dumps([{"field": "provider", "op": "ne", "value": "internal"}]),
         "deny", "Legacy policy — disabled"),
    ]
    for pid, name, enabled, priority, conditions, action, message in policies:
        db.execute(
            "INSERT INTO policies (id, org_id, name, enabled, priority, conditions, action, message, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, org_id, name, 1 if enabled else 0, priority, conditions, action, message, admin_id, _ago(40))
        )
    active = sum(1 for p in policies if p[2])
    print(f"  📜 Policies: {len(policies)} ({active} active, {len(policies)-active} disabled)")

    # ═══════════════════════════════════════════════════════════════════
    # APPROVAL REQUESTS
    # ═══════════════════════════════════════════════════════════════════
    approvals = [
        (_id(), "agent", mike_id, "budget_overage",
         json.dumps({"model": "gpt-5.2-pro", "project": "research", "estimated_cost": 12.50, "reason": "Large document analysis"}),
         12.50, "approved", sarah_id, _ago(3), 50.0),

        (_id(), "agent", alex_id, "policy_override",
         json.dumps({"model": "claude-opus-4-6", "project": "code-review", "policy": "Block Premium Models in Staging"}),
         2.80, "approved", priya_id, _ago(2), None),

        (_id(), "agent", mike_id, "high_cost",
         json.dumps({"model": "gpt-5.2-pro", "project": "research", "estimated_cost": 8.75, "task": "Patent analysis"}),
         8.75, "pending", None, None, None),

        (_id(), "user", alex_id, "budget_overage",
         json.dumps({"model": "gpt-5.2", "project": "default", "daily_usage": 48.50, "daily_limit": 50.0}),
         15.00, "pending", None, None, 25.0),

        (_id(), "agent", mike_id, "policy_override",
         json.dumps({"model": "deepseek-reasoner", "project": "data-pipeline", "reason": "Weekend batch job"}),
         3.20, "denied", sarah_id, _ago(1), None),

        (_id(), "agent", alex_id, "high_cost",
         json.dumps({"model": "claude-opus-4-6", "project": "research", "estimated_cost": 6.40}),
         6.40, "expired", None, None, None),
    ]
    for aid, rtype, rid, atype, ctx, cost, status, decided_by, decided_at, unlock in approvals:
        db.execute(
            """INSERT INTO approval_requests
               (id, org_id, requester_type, requester_id, request_type, context, estimated_cost,
                status, decided_by, decided_at, unlock_amount, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (aid, org_id, rtype, rid, atype, ctx, cost, status, decided_by, decided_at, unlock,
             _ago(4), _ago(-1) if status == "pending" else None)
        )
    pending = sum(1 for a in approvals if a[6] == "pending")
    print(f"  ✋ Approvals: {len(approvals)} ({pending} pending)")

    # ═══════════════════════════════════════════════════════════════════
    # NOTIFICATION CHANNELS
    # ═══════════════════════════════════════════════════════════════════
    channels = [
        (_id(), "slack", "Engineering Alerts",
         json.dumps({"webhook_url": "https://hooks.example.com/services/REPLACE_WITH_SLACK_WEBHOOK", "channel": "#eng-ai-costs"}),
         "budget.exceeded,anomaly.detected,approval.requested", True),

        (_id(), "email", "Finance Weekly Report",
         json.dumps({"recipients": ["finance@acme.ai", "cto@acme.ai"], "subject_prefix": "[AgentCost]"}),
         "report.weekly,budget.warning", True),

        (_id(), "webhook", "PagerDuty Critical",
         json.dumps({"url": "https://events.pagerduty.com/v2/enqueue", "routing_key": "R000000000000000000000000000000000"}),
         "anomaly.critical,budget.exceeded", True),

        (_id(), "slack", "All Events (Debug)",
         json.dumps({"webhook_url": "https://hooks.example.com/services/REPLACE_WITH_SLACK_WEBHOOK", "channel": "#ai-debug"}),
         "*", False),
    ]
    for cid, ctype, name, config, events, enabled in channels:
        db.execute(
            "INSERT INTO notification_channels (id, org_id, channel_type, name, config, events, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, org_id, ctype, name, config, events, 1 if enabled else 0, _ago(35))
        )
    active_ch = sum(1 for c in channels if c[5])
    print(f"  🔔 Channels: {len(channels)} ({active_ch} active)")

    # ═══════════════════════════════════════════════════════════════════
    # AGENT SCORECARDS
    # ═══════════════════════════════════════════════════════════════════
    agents = ["chatbot", "assistant", "ticket-classifier", "response-drafter",
              "extractor", "transformer", "reviewer", "analyst"]
    periods = ["2025-12", "2026-01", "2026-02"]

    import random
    random.seed(42)
    sc_count = 0
    for agent in agents:
        for period in periods:
            quality = round(random.uniform(0.65, 0.98), 3)
            total_cost = round(random.uniform(50, 2000), 2)
            total_tasks = random.randint(100, 5000)
            cost_eff = round(total_cost / (quality * total_tasks + 1), 4)
            error_rate = round(random.uniform(0.005, 0.08), 4)
            uptime = round(random.uniform(0.95, 0.999), 4)

            if quality >= 0.90:
                grade = "A"
            elif quality >= 0.80:
                grade = "B"
            elif quality >= 0.70:
                grade = "C"
            else:
                grade = "D"

            recs = []
            if cost_eff > 0.05:
                recs.append("Consider switching to a cheaper model for routine tasks")
            if error_rate > 0.03:
                recs.append("High error rate — review prompt templates")
            if quality < 0.80:
                recs.append("Quality below threshold — consider model upgrade")
            if total_cost > 1000:
                recs.append("High monthly spend — evaluate caching opportunities")

            db.execute(
                """INSERT INTO agent_scorecards
                   (id, org_id, agent_id, period, quality_score, cost_efficiency,
                    total_cost, total_tasks, error_rate, uptime_pct, grade, recommendations, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (_id(), org_id, agent, period, quality, cost_eff, total_cost,
                 total_tasks, error_rate, uptime, grade, json.dumps(recs), _ago(5))
            )
            sc_count += 1
    print(f"  📋 Scorecards: {sc_count} ({len(agents)} agents × {len(periods)} periods)")

    # ═══════════════════════════════════════════════════════════════════
    # AUDIT LOG
    # ═══════════════════════════════════════════════════════════════════
    import hashlib

    audit_entries = [
        ("org.created", admin_id, "user", "org", org_id, "create",
         json.dumps({"name": "Acme AI Corp", "plan": "enterprise"}), _ago(90)),
        ("user.invited", admin_id, "user", "user", users[2][0], "create",
         json.dumps({"email": "sarah.chen@acme.ai", "role": "manager"}), _ago(60)),
        ("policy.created", admin_id, "user", "policy", policies[0][0], "create",
         json.dumps({"name": "Block Premium Models in Staging"}), _ago(40)),
        ("budget.set", sarah_id, "user", "budget", "default", "update",
         json.dumps({"project": "default", "daily_limit": 50, "monthly_limit": 1000}), _ago(50)),
        ("cost_center.created", admin_id, "user", "cost_center", eng_cc, "create",
         json.dumps({"name": "Engineering", "code": "ENG-001", "budget": 15000}), _ago(60)),
        ("approval.approved", sarah_id, "user", "approval", approvals[0][0], "update",
         json.dumps({"requester": mike_id, "amount": 12.50}), _ago(3)),
        ("approval.denied", sarah_id, "user", "approval", approvals[4][0], "update",
         json.dumps({"requester": mike_id, "reason": "Weekend batch job not pre-approved"}), _ago(1)),
        ("api_key.created", admin_id, "user", "api_key", keys[0][0], "create",
         json.dumps({"name": "Production SDK", "scopes": "traces.write,traces.read"}), _ago(30)),
        ("channel.created", admin_id, "user", "channel", channels[0][0], "create",
         json.dumps({"type": "slack", "name": "Engineering Alerts"}), _ago(35)),
        ("llm_call", mike_id, "agent", "trace", _id(), "execute",
         json.dumps({"model": "gpt-5.2-pro", "cost": 12.50, "project": "research"}), _ago(3)),
        ("budget.warning", "system", "system", "budget", "default", "alert",
         json.dumps({"project": "default", "usage_pct": 85, "daily_remaining": 7.50}), _ago(1)),
        ("anomaly.detected", "system", "system", "trace", _id(), "alert",
         json.dumps({"type": "cost_spike", "model": "gpt-5.2-pro", "cost": 15.00, "avg_cost": 0.50}), _ago(0, hours=6)),
    ]

    prev_hash = "genesis"
    for i, (etype, actor, atype, rtype, rid, action, details, ts) in enumerate(audit_entries):
        entry_data = f"{prev_hash}|{etype}|{actor}|{action}|{ts}"
        entry_hash = hashlib.sha256(entry_data.encode()).hexdigest()
        db.execute(
            """INSERT INTO audit_log
               (event_type, actor_id, actor_type, org_id, resource_type, resource_id,
                action, details, prev_hash, entry_hash, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (etype, actor, atype, org_id, rtype, rid, action, details, prev_hash, entry_hash, ts)
        )
        prev_hash = entry_hash
    print(f"  📝 Audit Log: {len(audit_entries)} entries (hash-chained)")

    # ═══════════════════════════════════════════════════════════════════
    # OPTIONAL: Seed traces too
    # ═══════════════════════════════════════════════════════════════════
    if with_traces:
        print()
        from seed_sample_data import seed
        seed(days=days, clear=clear)

    print(f"\n{'━'*60}")
    print("  ✅ Enterprise data seeded successfully!")
    print(f"{'━'*60}")
    print("  Org:            Acme AI Corp")
    print("  Admin login:    open@agentcost.in / admin123")
    print("  User login:     care@agentcost.in / user123")
    print("  Dashboard:      http://localhost:8100")
    print(f"{'━'*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed AgentCost enterprise data")
    parser.add_argument("--clear", action="store_true", help="Clear existing enterprise data first")
    parser.add_argument("--with-traces", action="store_true", help="Also seed trace data")
    parser.add_argument("--days", type=int, default=14, help="Days of trace history (default: 14)")
    args = parser.parse_args()
    seed_enterprise(clear=args.clear, with_traces=args.with_traces, days=args.days)