"""
Event Store — Persistence for trace events with time-series queries.

Refactored to use DatabaseAdapter (supports both SQLite and PostgreSQL).
All SQL is written in portable syntax with `?` placeholders.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from .adapter import DatabaseAdapter
from .connection import get_db


# ── Schema DDL ───────────────────────────────────────────────────────────────
# Used by init() to create tables if they don't exist.
# This SQL is portable: works in SQLite as-is and gets auto-translated
# for Postgres by the adapter (AUTOINCREMENT → SERIAL, ? → %s).

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trace_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL, project TEXT DEFAULT 'default',
    agent_id TEXT, session_id TEXT, model TEXT NOT NULL,
    provider TEXT, input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0, cost REAL DEFAULT 0,
    latency_ms REAL DEFAULT 0, status TEXT DEFAULT 'success',
    error TEXT, metadata TEXT, timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_te_project ON trace_events(project);
CREATE INDEX IF NOT EXISTS idx_te_model ON trace_events(model);
CREATE INDEX IF NOT EXISTS idx_te_ts ON trace_events(timestamp);

CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT UNIQUE NOT NULL, daily_limit REAL,
    monthly_limit REAL, total_limit REAL,
    alert_threshold REAL DEFAULT 0.8,
    created_at TEXT, updated_at TEXT
);
"""

# Columns added in enterprise phase — applied after base schema
_MIGRATIONS = [
    ("trace_events", "org_id", "TEXT"),
    ("budgets", "org_id", "TEXT"),
]


class EventStore:
    """Trace event persistence with cost analytics queries.

    Works with any DatabaseAdapter backend (SQLite or PostgreSQL).
    """

    def __init__(self, db: DatabaseAdapter | None = None):
        self.db = db or get_db()
        self._init()

    def _init(self):
        self.db.executescript(_SCHEMA)
        # Add enterprise columns that may be missing on older databases
        for table, col, col_type in _MIGRATIONS:
            try:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            except Exception:
                pass  # Column already exists
        # Create index on org_id after ensuring column exists
        try:
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_te_org ON trace_events(org_id)")
        except Exception:
            pass

    # ── Write ────────────────────────────────────────────────────

    def log_trace(self, event):
        self.db.execute(
            """INSERT INTO trace_events
               (trace_id, project, agent_id, session_id, model, provider,
                input_tokens, output_tokens, cost, latency_ms, status,
                error, metadata, timestamp)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event.trace_id, event.project, event.agent_id, event.session_id,
                event.model, event.provider, event.input_tokens, event.output_tokens,
                event.cost, event.latency_ms, event.status, event.error,
                json.dumps(event.metadata) if event.metadata else None,
                event.timestamp or datetime.now().isoformat(),
            ),
        )

    # ── Read: traces ─────────────────────────────────────────────

    def get_traces(self, project=None, model=None, since=None, limit=100):
        q = "SELECT * FROM trace_events WHERE 1=1"
        p: list = []
        if project:
            q += " AND project=?"
            p.append(project)
        if model:
            q += " AND model=?"
            p.append(model)
        if since:
            q += " AND timestamp>=?"
            p.append(since)
        q += " ORDER BY timestamp DESC LIMIT ?"
        p.append(limit)
        return [dict(r) for r in self.db.fetch_all(q, p)]

    def get_event_count(self, project=None):
        w = "WHERE project=?" if project else ""
        p = [project] if project else []
        r = self.db.fetch_one(f"SELECT COUNT(*) as cnt FROM trace_events {w}", p)
        return r["cnt"] if r else 0

    def get_projects(self):
        rows = self.db.fetch_all(
            "SELECT DISTINCT project FROM trace_events ORDER BY project"
        )
        return [r["project"] for r in rows]

    # ── Read: cost analytics ─────────────────────────────────────

    def get_cost_summary(self, project=None):
        w = "WHERE project=?" if project else ""
        p = [project] if project else []
        r = self.db.fetch_one(
            f"""SELECT COUNT(*) as total_calls, COALESCE(SUM(cost),0) as total_cost,
                COALESCE(SUM(input_tokens),0) as total_input_tokens,
                COALESCE(SUM(output_tokens),0) as total_output_tokens,
                COALESCE(AVG(latency_ms),0) as avg_latency,
                COUNT(DISTINCT model) as model_count,
                COUNT(DISTINCT project) as project_count
                FROM trace_events {w}""",
            p,
        )
        return dict(r) if r else {}

    def get_cost_by_model(self, project=None):
        w = "WHERE project=?" if project else ""
        p = [project] if project else []
        return [
            dict(r) for r in self.db.fetch_all(
                f"""SELECT model, COUNT(*) as calls,
                    ROUND(CAST(SUM(cost) AS NUMERIC),6) as total_cost, SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens, ROUND(CAST(AVG(latency_ms) AS NUMERIC),0) as avg_latency_ms
                    FROM trace_events {w} GROUP BY model ORDER BY total_cost DESC""",
                p,
            )
        ]

    def get_cost_by_project(self):
        return [
            dict(r) for r in self.db.fetch_all(
                """SELECT project, COUNT(*) as calls,
                   ROUND(CAST(SUM(cost) AS NUMERIC),6) as total_cost, SUM(input_tokens) as input_tokens,
                   SUM(output_tokens) as output_tokens, MIN(timestamp) as first_call,
                   MAX(timestamp) as last_call FROM trace_events GROUP BY project
                   ORDER BY total_cost DESC"""
            )
        ]

    def get_cost_over_time(self, project=None, interval="hour", since_hours=24):
        since = (datetime.now() - timedelta(hours=since_hours)).isoformat()
        w = "WHERE timestamp>=?"
        p: list = [since]
        if project:
            w += " AND project=?"
            p.append(project)
        # SUBSTR works in both SQLite and PostgreSQL
        bkt = {
            "minute": "SUBSTR(timestamp,1,16)",
            "hour": "SUBSTR(timestamp,1,13)",
            "day": "SUBSTR(timestamp,1,10)",
        }.get(interval, "SUBSTR(timestamp,1,13)")
        return [
            dict(r) for r in self.db.fetch_all(
                f"""SELECT {bkt} as time_bucket, COUNT(*) as calls,
                    ROUND(CAST(SUM(cost) AS NUMERIC),6) as cost, SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens FROM trace_events {w}
                    GROUP BY time_bucket ORDER BY time_bucket ASC""",
                p,
            )
        ]

    # ── Budgets ──────────────────────────────────────────────────

    def set_budget(self, project, daily_limit=None, monthly_limit=None,
                   total_limit=None, alert_threshold=0.8):
        now = datetime.now().isoformat()
        self.db.execute(
            """INSERT INTO budgets
               (project, daily_limit, monthly_limit, total_limit, alert_threshold,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(project) DO UPDATE SET
                   daily_limit=excluded.daily_limit,
                   monthly_limit=excluded.monthly_limit,
                   total_limit=excluded.total_limit,
                   alert_threshold=excluded.alert_threshold,
                   updated_at=excluded.updated_at""",
            (project, daily_limit, monthly_limit, total_limit, alert_threshold, now, now),
        )

    def get_budget(self, project):
        r = self.db.fetch_one("SELECT * FROM budgets WHERE project=?", (project,))
        if not r:
            return None
        b = dict(r)
        s = self.get_cost_summary(project)
        b["current_spend"] = s.get("total_cost", 0)
        return b

    def check_budget(self, project):
        b = self.get_budget(project)
        if not b:
            return {"has_budget": False}
        cur = b["current_spend"]
        alerts = []
        if b.get("total_limit"):
            pct = cur / b["total_limit"]
            if pct >= 1.0:
                alerts.append({"type": "total_exceeded", "pct": pct})
            elif pct >= b.get("alert_threshold", 0.8):
                alerts.append({"type": "total_warning", "pct": pct})
        return {
            "has_budget": True,
            "current_spend": round(cur, 6),
            "total_limit": b.get("total_limit"),
            "pct_used": round(cur / b["total_limit"] * 100, 1) if b.get("total_limit") else None,
            "alerts": alerts,
        }
