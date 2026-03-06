"""
AgentCost Goals — Cost attribution by business objective.

Tracks spend per goal with hierarchical goal ancestry, enabling
"how much did achieving Goal X cost?" reporting.

Goals form a tree: goal → parent → grandparent. Cost rolls up
through the hierarchy so top-level OKRs show total cost including
all sub-goals.

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
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("agentcost.goals")


@dataclass
class Goal:
    """A business objective with cost tracking."""

    id: str
    name: str
    description: str = ""
    project: str = ""
    parent_goal_id: str = ""
    status: str = "active"  # active, completed, cancelled
    budget: float = 0.0  # 0 = no limit
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
    """Manages goals and cost attribution.

    Stores goals in memory (production: backed by DB via GoalStore).
    Tracks spend per goal via trace events tagged with goal_id.
    """

    def __init__(self):
        self._goals: dict[str, Goal] = {}
        self._spend: dict[str, float] = {}  # goal_id → total spend
        self._call_counts: dict[str, int] = {}  # goal_id → call count

    def create_goal(
        self,
        goal_id: str,
        name: str,
        description: str = "",
        project: str = "",
        parent_goal_id: str = "",
        budget: float = 0.0,
    ) -> Goal:
        """Create a new goal."""
        if goal_id in self._goals:
            raise ValueError(f"Goal '{goal_id}' already exists")
        if parent_goal_id and parent_goal_id not in self._goals:
            raise ValueError(f"Parent goal '{parent_goal_id}' not found")

        goal = Goal(
            id=goal_id,
            name=name,
            description=description,
            project=project,
            parent_goal_id=parent_goal_id,
            budget=budget,
        )
        self._goals[goal_id] = goal
        self._spend[goal_id] = 0.0
        self._call_counts[goal_id] = 0
        logger.info("Created goal: %s (%s)", goal_id, name)
        return goal

    def get_goal(self, goal_id: str) -> Goal | None:
        return self._goals.get(goal_id)

    def list_goals(
        self, project: str = "", status: str = "", parent_goal_id: str | None = None
    ) -> list[Goal]:
        """List goals with optional filters."""
        goals = list(self._goals.values())
        if project:
            goals = [g for g in goals if g.project == project]
        if status:
            goals = [g for g in goals if g.status == status]
        if parent_goal_id is not None:
            goals = [g for g in goals if g.parent_goal_id == parent_goal_id]
        return goals

    def update_goal(self, goal_id: str, **kwargs) -> Goal | None:
        """Update goal fields."""
        goal = self._goals.get(goal_id)
        if not goal:
            return None
        for key, val in kwargs.items():
            if hasattr(goal, key) and key not in ("id", "created_at"):
                setattr(goal, key, val)
        goal.updated_at = time.time()
        return goal

    def delete_goal(self, goal_id: str) -> bool:
        if goal_id in self._goals:
            del self._goals[goal_id]
            self._spend.pop(goal_id, None)
            self._call_counts.pop(goal_id, None)
            return True
        return False

    # ── Cost Attribution ──────────────────────────────────────────

    def record_spend(self, goal_id: str, cost: float) -> None:
        """Record spend against a goal. Called by SDK on each trace."""
        if goal_id in self._spend:
            self._spend[goal_id] += cost
            self._call_counts[goal_id] = self._call_counts.get(goal_id, 0) + 1

    def get_goal_cost(
        self, goal_id: str, include_children: bool = True
    ) -> dict:
        """Get cost for a goal, optionally including all sub-goals.

        Returns:
            {
                "goal_id": str,
                "direct_cost": float,
                "children_cost": float,
                "total_cost": float,
                "call_count": int,
                "budget": float,
                "budget_used_pct": float,
            }
        """
        direct = self._spend.get(goal_id, 0.0)
        calls = self._call_counts.get(goal_id, 0)
        children_cost = 0.0
        children_calls = 0

        if include_children:
            for child in self._get_all_descendants(goal_id):
                children_cost += self._spend.get(child.id, 0.0)
                children_calls += self._call_counts.get(child.id, 0)

        total = direct + children_cost
        goal = self._goals.get(goal_id)
        budget = goal.budget if goal else 0.0
        used_pct = (total / budget * 100) if budget > 0 else 0.0

        return {
            "goal_id": goal_id,
            "direct_cost": round(direct, 6),
            "children_cost": round(children_cost, 6),
            "total_cost": round(total, 6),
            "call_count": calls + children_calls,
            "budget": budget,
            "budget_used_pct": round(used_pct, 1),
        }

    def get_ancestry(self, goal_id: str) -> list[Goal]:
        """Get the full ancestry chain: goal → parent → grandparent → ..."""
        chain = []
        current = goal_id
        visited = set()
        while current and current not in visited:
            visited.add(current)
            goal = self._goals.get(current)
            if not goal:
                break
            chain.append(goal)
            current = goal.parent_goal_id
        return chain

    def get_children(self, goal_id: str) -> list[Goal]:
        """Get direct children of a goal."""
        return [g for g in self._goals.values() if g.parent_goal_id == goal_id]

    def _get_all_descendants(self, goal_id: str) -> list[Goal]:
        """Recursively get all descendants."""
        descendants = []
        stack = [goal_id]
        while stack:
            parent = stack.pop()
            children = self.get_children(parent)
            descendants.extend(children)
            stack.extend(c.id for c in children)
        return descendants

    def check_goal_budget(self, goal_id: str) -> dict:
        """Check if goal spend is within budget.

        Returns:
            {"allowed": bool, "reason": str, "budget_used_pct": float}
        """
        cost_data = self.get_goal_cost(goal_id, include_children=True)
        goal = self._goals.get(goal_id)
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
        """Summary of all goals with costs."""
        result = []
        for goal in self._goals.values():
            cost_data = self.get_goal_cost(goal.id)
            result.append({
                **goal.to_dict(),
                **cost_data,
            })
        return result


# ── Singleton ─────────────────────────────────────────────────────────────────

_global_service: Optional[GoalService] = None


def get_goal_service() -> GoalService:
    global _global_service
    if _global_service is None:
        _global_service = GoalService()
    return _global_service
