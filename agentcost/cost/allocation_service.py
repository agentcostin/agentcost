"""
AllocationService — Cost allocation rules management.

Maps projects and agents to cost centers with split allocation percentages.
A project can be split across multiple cost centers (e.g., 60% Engineering,
40% Data Science). Total allocation per project should sum to 100% but
the system doesn't enforce this — it's the admin's responsibility.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..data.connection import get_db


class AllocationService:

    def __init__(self, db=None):
        self._db = db or get_db()

    # ── Create ───────────────────────────────────────────────────

    def create(
        self,
        org_id: str,
        cost_center_id: str,
        project: Optional[str] = None,
        agent_id: Optional[str] = None,
        allocation_pct: float = 100.0,
    ) -> dict:
        """Create an allocation rule.

        Either project or agent_id must be provided (or both for specificity).
        """
        if not project and not agent_id:
            return {"error": "Must provide either project or agent_id"}

        if allocation_pct <= 0 or allocation_pct > 100:
            return {"error": "allocation_pct must be between 0 and 100"}

        # Verify cost center exists
        cc = self._db.fetch_one(
            "SELECT id FROM cost_centers WHERE id = ? AND org_id = ?",
            (cost_center_id, org_id),
        )
        if not cc:
            return {"error": "Cost center not found"}

        now = datetime.utcnow().isoformat()
        self._db.execute(
            "INSERT INTO cost_allocations (org_id, project, agent_id, cost_center_id, allocation_pct, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (org_id, project, agent_id, cost_center_id, allocation_pct, now),
        )

        # Get the auto-generated ID
        row = self._db.fetch_one(
            "SELECT id FROM cost_allocations WHERE org_id = ? AND cost_center_id = ? "
            "AND created_at = ? ORDER BY id DESC LIMIT 1",
            (org_id, cost_center_id, now),
        )
        alloc_id = row["id"] if row else None

        return {
            "id": alloc_id,
            "org_id": org_id,
            "project": project,
            "agent_id": agent_id,
            "cost_center_id": cost_center_id,
            "allocation_pct": allocation_pct,
        }

    # ── Read ─────────────────────────────────────────────────────

    def list(self, org_id: str, cost_center_id: Optional[str] = None,
             project: Optional[str] = None) -> list[dict]:
        """List allocation rules, optionally filtered."""
        sql = ("SELECT ca.*, cc.name as cost_center_name, cc.code as cost_center_code "
               "FROM cost_allocations ca "
               "LEFT JOIN cost_centers cc ON ca.cost_center_id = cc.id "
               "WHERE ca.org_id = ?")
        params: list = [org_id]

        if cost_center_id:
            sql += " AND ca.cost_center_id = ?"
            params.append(cost_center_id)
        if project:
            sql += " AND ca.project = ?"
            params.append(project)

        sql += " ORDER BY ca.project, ca.agent_id"
        rows = self._db.fetch_all(sql, params)
        return [dict(r) for r in rows]

    def get_allocation_summary(self, org_id: str, project: str) -> dict:
        """Get total allocation % for a project across all cost centers.

        Useful for validation — admin can check if allocations sum to 100%.
        """
        rows = self._db.fetch_all(
            "SELECT ca.cost_center_id, cc.name, ca.allocation_pct "
            "FROM cost_allocations ca "
            "LEFT JOIN cost_centers cc ON ca.cost_center_id = cc.id "
            "WHERE ca.org_id = ? AND ca.project = ?",
            (org_id, project),
        )
        allocations = [dict(r) for r in rows]
        total_pct = sum(a["allocation_pct"] for a in allocations)
        return {
            "project": project,
            "allocations": allocations,
            "total_pct": round(total_pct, 2),
            "fully_allocated": abs(total_pct - 100.0) < 0.01,
        }

    # ── Update ───────────────────────────────────────────────────

    def update(self, alloc_id: int, org_id: str, **kwargs) -> Optional[dict]:
        allowed = {"cost_center_id", "allocation_pct", "project", "agent_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return None

        if "allocation_pct" in updates:
            pct = updates["allocation_pct"]
            if pct <= 0 or pct > 100:
                return {"error": "allocation_pct must be between 0 and 100"}

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [alloc_id, org_id]
        self._db.execute(
            f"UPDATE cost_allocations SET {set_clause} WHERE id = ? AND org_id = ?",
            params,
        )
        row = self._db.fetch_one(
            "SELECT * FROM cost_allocations WHERE id = ? AND org_id = ?",
            (alloc_id, org_id),
        )
        return dict(row) if row else None

    # ── Delete ───────────────────────────────────────────────────

    def delete(self, alloc_id: int, org_id: str) -> dict:
        self._db.execute(
            "DELETE FROM cost_allocations WHERE id = ? AND org_id = ?",
            (alloc_id, org_id),
        )
        return {"status": "deleted", "id": alloc_id}

    def delete_for_project(self, org_id: str, project: str) -> dict:
        """Remove all allocation rules for a project."""
        self._db.execute(
            "DELETE FROM cost_allocations WHERE org_id = ? AND project = ?",
            (org_id, project),
        )
        return {"status": "deleted", "project": project}
