"""
AgentCost Goals — Cost attribution by business objective.

Tracks spend per goal with hierarchical goal ancestry, enabling
"how much did achieving Goal X cost?" reporting.

Goals form a tree: goal → parent → grandparent. Cost rolls up
through the hierarchy so top-level OKRs show total cost including
all sub-goals.

Now persisted to database (SQLite/PostgreSQL) — survives restarts.

Usage:
    from agentcost.goals import GoalService, Goal

    svc = GoalService()
    svc.create_goal("launch-v2", "Launch Product V2", project="my-app", budget=500.0)
    svc.create_goal("build-api", "Build API Layer", parent_goal_id="launch-v2")

    # Track costs against a goal via SDK:
    client = trace(OpenAI(), project="my-app", goal_id="build-api")

    # Query cost attribution:
    cost = svc.get_goal_cost("launch-v2", include_children=True)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("agentcost.goals")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    project         TEXT DEFAULT '',
    parent_goal_id  TEXT DEFAULT '',
    status          TEXT DEFAULT 'active',
    budget          REAL DEFAULT 0,
    org_id          TEXT DEFAULT 'default',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_goals_project ON goals(project);
CREATE INDEX IF NOT EXISTS idx_goals_parent ON goals(parent_goal_id);
CREATE INDEX IF NOT EXISTS idx_goals_org ON goals(org_id);

CREATE TABLE IF NOT EXISTS goal_spend (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id         TEXT NOT NULL,
    cost            REAL NOT NULL DEFAULT 0,
    trace_id        TEXT,
    timestamp       REAL NOT NULL,
    org_id          TEXT DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_gs_goal ON goal_spend(goal_id);
"""


@dataclass
class Goal:
    """A business objective with cost tracking."""

    id: str
    name: str
    description: str = ""
    project: str = ""
    parent_goal_id: str = ""
    status: str = "active"
    budget: float = 0.0
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "project": self.project,
            "parent_goal_id": self.parent_goal_id,
            "status": self.status,
            "budget": self.budget,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class GoalService:
    """Manages goals and cost attribution. Persisted to database."""

    def __init__(self, db=None):
        from ..data.connection import get_db

        self.db = db or get_db()
        self._init()

    def _init(self):
        self.db.executescript(_SCHEMA)

    def create_goal(
        self,
        goal_id: str,
        name: str,
        description: str = "",
        project: str = "",
        parent_goal_id: str = "",
        budget: float = 0.0,
    ) -> Goal:
        existing = self.db.fetch_one("SELECT id FROM goals WHERE id=?", (goal_id,))
        if existing:
            raise ValueError(f"Goal '{goal_id}' already exists")
        if parent_goal_id:
            parent = self.db.fetch_one(
                "SELECT id FROM goals WHERE id=?", (parent_goal_id,)
            )
            if not parent:
                raise ValueError(f"Parent goal '{parent_goal_id}' not found")

        goal = Goal(
            id=goal_id,
            name=name,
            description=description,
            project=project,
            parent_goal_id=parent_goal_id,
            budget=budget,
        )
        self.db.execute(
            """INSERT INTO goals (id, name, description, project, parent_goal_id,
               status, budget, org_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                goal.id,
                goal.name,
                goal.description,
                goal.project,
                goal.parent_goal_id,
                goal.status,
                goal.budget,
                "default",
                goal.created_at,
                goal.updated_at,
            ),
        )
        logger.info("Created goal: %s (%s)", goal_id, name)
        return goal

    def get_goal(self, goal_id: str) -> Goal | None:
        row = self.db.fetch_one("SELECT * FROM goals WHERE id=?", (goal_id,))
        return self._row_to_goal(row) if row else None

    def list_goals(
        self, project: str = "", status: str = "", parent_goal_id: str | None = None
    ) -> list[Goal]:
        sql = "SELECT * FROM goals WHERE 1=1"
        params: list = []
        if project:
            sql += " AND project=?"
            params.append(project)
        if status:
            sql += " AND status=?"
            params.append(status)
        if parent_goal_id is not None:
            sql += " AND parent_goal_id=?"
            params.append(parent_goal_id)
        sql += " ORDER BY created_at DESC"
        return [self._row_to_goal(r) for r in self.db.fetch_all(sql, params)]

    def update_goal(self, goal_id: str, **kwargs) -> Goal | None:
        goal = self.get_goal(goal_id)
        if not goal:
            return None
        for key, val in kwargs.items():
            if hasattr(goal, key) and key not in ("id", "created_at"):
                setattr(goal, key, val)
        goal.updated_at = time.time()
        self.db.execute(
            """UPDATE goals SET name=?, description=?, project=?, parent_goal_id=?,
               status=?, budget=?, updated_at=? WHERE id=?""",
            (
                goal.name,
                goal.description,
                goal.project,
                goal.parent_goal_id,
                goal.status,
                goal.budget,
                goal.updated_at,
                goal.id,
            ),
        )
        return goal

    def delete_goal(self, goal_id: str) -> bool:
        existing = self.db.fetch_one("SELECT id FROM goals WHERE id=?", (goal_id,))
        if not existing:
            return False
        self.db.execute("DELETE FROM goal_spend WHERE goal_id=?", (goal_id,))
        self.db.execute("DELETE FROM goals WHERE id=?", (goal_id,))
        return True

    def record_spend(self, goal_id: str, cost: float, trace_id: str = "") -> None:
        existing = self.db.fetch_one("SELECT id FROM goals WHERE id=?", (goal_id,))
        if existing:
            self.db.execute(
                "INSERT INTO goal_spend (goal_id, cost, trace_id, timestamp, org_id) VALUES (?, ?, ?, ?, ?)",
                (goal_id, cost, trace_id, time.time(), "default"),
            )

    def get_goal_cost(self, goal_id: str, include_children: bool = True) -> dict:
        direct = self._get_direct_cost(goal_id)
        direct_calls = self._get_call_count(goal_id)
        children_cost = 0.0
        children_calls = 0
        if include_children:
            for child in self._get_all_descendants(goal_id):
                children_cost += self._get_direct_cost(child.id)
                children_calls += self._get_call_count(child.id)
        total = direct + children_cost
        goal = self.get_goal(goal_id)
        budget = goal.budget if goal else 0.0
        used_pct = (total / budget * 100) if budget > 0 else 0.0
        return {
            "goal_id": goal_id,
            "direct_cost": round(direct, 6),
            "children_cost": round(children_cost, 6),
            "total_cost": round(total, 6),
            "call_count": direct_calls + children_calls,
            "budget": budget,
            "budget_used_pct": round(used_pct, 1),
        }

    def get_ancestry(self, goal_id: str) -> list[Goal]:
        chain, current, visited = [], goal_id, set()
        while current and current not in visited:
            visited.add(current)
            goal = self.get_goal(current)
            if not goal:
                break
            chain.append(goal)
            current = goal.parent_goal_id
        return chain

    def get_children(self, goal_id: str) -> list[Goal]:
        rows = self.db.fetch_all(
            "SELECT * FROM goals WHERE parent_goal_id=?", (goal_id,)
        )
        return [self._row_to_goal(r) for r in rows]

    def _get_all_descendants(self, goal_id: str) -> list[Goal]:
        descendants, stack = [], [goal_id]
        while stack:
            children = self.get_children(stack.pop())
            descendants.extend(children)
            stack.extend(c.id for c in children)
        return descendants

    def check_goal_budget(self, goal_id: str) -> dict:
        cost_data = self.get_goal_cost(goal_id, include_children=True)
        goal = self.get_goal(goal_id)
        if not goal or goal.budget <= 0:
            return {"allowed": True, "reason": "no budget set", "budget_used_pct": 0.0}
        if cost_data["total_cost"] >= goal.budget:
            return {
                "allowed": False,
                "reason": f"Goal budget exceeded: ${cost_data['total_cost']:.2f} / ${goal.budget:.2f}",
                "budget_used_pct": cost_data["budget_used_pct"],
            }
        return {
            "allowed": True,
            "reason": "within budget",
            "budget_used_pct": cost_data["budget_used_pct"],
        }

    def get_summary(self) -> list[dict]:
        return [{**g.to_dict(), **self.get_goal_cost(g.id)} for g in self.list_goals()]

    def _get_direct_cost(self, goal_id: str) -> float:
        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(cost), 0) as total FROM goal_spend WHERE goal_id=?",
            (goal_id,),
        )
        return row["total"] if row else 0.0

    def _get_call_count(self, goal_id: str) -> int:
        row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM goal_spend WHERE goal_id=?", (goal_id,)
        )
        return row["cnt"] if row else 0

    def _row_to_goal(self, row) -> Goal:
        return Goal(
            id=row["id"],
            name=row["name"],
            description=row.get("description", ""),
            project=row.get("project", ""),
            parent_goal_id=row.get("parent_goal_id", ""),
            status=row.get("status", "active"),
            budget=row.get("budget", 0.0),
            created_at=row.get("created_at", 0),
            updated_at=row.get("updated_at", 0),
        )


_global_service: Optional[GoalService] = None


def get_goal_service(db=None) -> GoalService:
    global _global_service
    if _global_service is None:
        _global_service = GoalService(db=db)
    return _global_service


def reset_goal_service() -> None:
    global _global_service
    _global_service = None
