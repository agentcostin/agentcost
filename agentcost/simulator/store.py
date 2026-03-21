"""
Simulator Store — CRUD for saved chaos simulation scenarios.

Uses the shared DatabaseAdapter (SQLite or PostgreSQL).
"""

from __future__ import annotations

import json
from datetime import datetime

from ..data.connection import get_db


# ── Schema (applied at import if table doesn't exist) ────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS simulator_scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL,
    description TEXT,
    architecture TEXT NOT NULL,
    chaos_events TEXT NOT NULL,
    traffic INTEGER NOT NULL DEFAULT 50,
    budget REAL NOT NULL DEFAULT 5000,
    results TEXT,
    tags TEXT,
    is_template BOOLEAN DEFAULT 0,
    created_by TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sim_scenarios_org ON simulator_scenarios(org_id);
"""


class SimulatorStore:
    """CRUD for simulator scenarios."""

    def __init__(self, db=None):
        self.db = db or get_db()
        self._ensure_table()

    def _ensure_table(self):
        try:
            self.db.executescript(_SCHEMA)
        except Exception:
            pass  # Table already exists

    # ── Create ────────────────────────────────────────────────────

    def save_scenario(
        self,
        name: str,
        chaos_events: list[str],
        traffic: int = 50,
        budget: float = 5000,
        description: str | None = None,
        architecture: dict | None = None,
        results: dict | None = None,
        tags: list[str] | None = None,
        org_id: str = "default",
        created_by: str | None = None,
    ) -> dict:
        now = datetime.now().isoformat()
        self.db.execute(
            """INSERT INTO simulator_scenarios
               (org_id, name, description, architecture, chaos_events,
                traffic, budget, results, tags, created_by, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                org_id,
                name,
                description,
                json.dumps(architecture or {}),
                json.dumps(chaos_events),
                traffic,
                budget,
                json.dumps(results) if results else None,
                json.dumps(tags) if tags else None,
                created_by,
                now,
                now,
            ),
        )
        # Return the created scenario
        row = self.db.fetch_one(
            "SELECT * FROM simulator_scenarios WHERE org_id=? ORDER BY id DESC LIMIT 1",
            (org_id,),
        )
        return self._row_to_dict(row) if row else {"name": name}

    # ── Read ──────────────────────────────────────────────────────

    def list_scenarios(self, org_id: str = "default") -> list[dict]:
        rows = self.db.fetch_all(
            """SELECT * FROM simulator_scenarios
               WHERE org_id=? OR is_template=1
               ORDER BY is_template DESC, updated_at DESC""",
            (org_id,),
        )
        return [self._row_to_dict(r) for r in rows]

    def get_scenario(self, scenario_id: int, org_id: str = "default") -> dict | None:
        row = self.db.fetch_one(
            "SELECT * FROM simulator_scenarios WHERE id=? AND (org_id=? OR is_template=1)",
            (scenario_id, org_id),
        )
        return self._row_to_dict(row) if row else None

    # ── Update ────────────────────────────────────────────────────

    def update_scenario(
        self,
        scenario_id: int,
        org_id: str = "default",
        **kwargs,
    ) -> dict | None:
        allowed = {"name", "description", "chaos_events", "traffic", "budget", "results", "tags", "architecture"}
        sets = []
        params = []
        for key, val in kwargs.items():
            if key not in allowed:
                continue
            if key in ("chaos_events", "results", "tags", "architecture"):
                val = json.dumps(val) if val is not None else None
            sets.append(f"{key}=?")
            params.append(val)

        if not sets:
            return self.get_scenario(scenario_id, org_id)

        sets.append("updated_at=?")
        params.append(datetime.now().isoformat())
        params.extend([scenario_id, org_id])

        self.db.execute(
            f"UPDATE simulator_scenarios SET {', '.join(sets)} WHERE id=? AND org_id=?",
            params,
        )
        return self.get_scenario(scenario_id, org_id)

    # ── Delete ────────────────────────────────────────────────────

    def delete_scenario(self, scenario_id: int, org_id: str = "default") -> bool:
        self.db.execute(
            "DELETE FROM simulator_scenarios WHERE id=? AND org_id=? AND is_template=0",
            (scenario_id, org_id),
        )
        return True

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row) -> dict:
        d = dict(row)
        for key in ("architecture", "chaos_events", "results", "tags"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d
