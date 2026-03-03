"""
CostCenterService — Cost center lifecycle and chargeback reporting.

Cost centers map to departments/teams in the customer's org (e.g., "Engineering",
"Marketing AI"). Each has an optional monthly budget and ERP code for finance
integration. Chargeback reports aggregate actual spend from trace_events via
cost_allocations rules.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from ..data.connection import get_db


class CostCenterService:
    def __init__(self, db=None):
        self._db = db or get_db()

    # ── Create ───────────────────────────────────────────────────

    def create(
        self,
        org_id: str,
        name: str,
        code: str = "",
        manager_email: str = "",
        monthly_budget: Optional[float] = None,
    ) -> dict:
        cc_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        self._db.execute(
            "INSERT INTO cost_centers (id, org_id, name, code, manager_email, monthly_budget, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cc_id, org_id, name, code, manager_email, monthly_budget, now, now),
        )
        return {
            "id": cc_id,
            "org_id": org_id,
            "name": name,
            "code": code,
            "manager_email": manager_email,
            "monthly_budget": monthly_budget,
        }

    # ── Read ─────────────────────────────────────────────────────

    def get(self, cc_id: str, org_id: str) -> Optional[dict]:
        row = self._db.fetch_one(
            "SELECT * FROM cost_centers WHERE id = ? AND org_id = ?", (cc_id, org_id)
        )
        return dict(row) if row else None

    def list(self, org_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        rows = self._db.fetch_all(
            "SELECT * FROM cost_centers WHERE org_id = ? ORDER BY name ASC LIMIT ? OFFSET ?",
            (org_id, limit, offset),
        )
        return [dict(r) for r in rows]

    def get_count(self, org_id: str) -> int:
        row = self._db.fetch_one(
            "SELECT COUNT(*) as count FROM cost_centers WHERE org_id = ?", (org_id,)
        )
        return row["count"] if row else 0

    # ── Update ───────────────────────────────────────────────────

    def update(self, cc_id: str, org_id: str, **kwargs) -> Optional[dict]:
        allowed = {"name", "code", "manager_email", "monthly_budget"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return self.get(cc_id, org_id)

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [datetime.utcnow().isoformat(), cc_id, org_id]
        self._db.execute(
            f"UPDATE cost_centers SET {set_clause}, updated_at = ? WHERE id = ? AND org_id = ?",
            params,
        )
        return self.get(cc_id, org_id)

    # ── Delete ───────────────────────────────────────────────────

    def delete(self, cc_id: str, org_id: str) -> dict:
        # Remove allocation rules first
        self._db.execute(
            "DELETE FROM cost_allocations WHERE cost_center_id = ? AND org_id = ?",
            (cc_id, org_id),
        )
        self._db.execute(
            "DELETE FROM cost_centers WHERE id = ? AND org_id = ?", (cc_id, org_id)
        )
        return {"status": "deleted", "id": cc_id}

    # ── Chargeback Report ────────────────────────────────────────

    def chargeback_report(
        self,
        org_id: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> list[dict]:
        """Generate a chargeback report: actual spend per cost center.

        Joins cost_allocations → trace_events to compute allocated costs.
        If a project has no allocation rule, its cost goes to 'Unallocated'.
        """
        # Get all cost centers for the org
        centers = self.list(org_id)
        center_map = {c["id"]: c for c in centers}

        # Build time filter
        time_filter = ""
        time_params: list = [org_id]
        if period_start:
            time_filter += " AND t.timestamp >= ?"
            time_params.append(period_start)
        if period_end:
            time_filter += " AND t.timestamp < ?"
            time_params.append(period_end)

        # Get allocated spend
        rows = self._db.fetch_all(
            f"""SELECT ca.cost_center_id,
                       COALESCE(SUM(t.cost * ca.allocation_pct / 100.0), 0) as allocated_cost,
                       COUNT(t.id) as trace_count
                FROM cost_allocations ca
                JOIN trace_events t ON (
                    (ca.project IS NOT NULL AND t.project = ca.project)
                    OR (ca.agent_id IS NOT NULL AND t.agent_id = ca.agent_id)
                )
                WHERE ca.org_id = ? {time_filter}
                GROUP BY ca.cost_center_id""",
            time_params,
        )

        # Build report
        allocated_ids = set()
        report = []
        for r in rows:
            row = dict(r)
            cc_id = row["cost_center_id"]
            allocated_ids.add(cc_id)
            cc = center_map.get(cc_id, {})
            monthly_budget = cc.get("monthly_budget")
            allocated = round(row["allocated_cost"], 6)
            report.append(
                {
                    "cost_center_id": cc_id,
                    "cost_center_name": cc.get("name", "Unknown"),
                    "code": cc.get("code", ""),
                    "allocated_cost": allocated,
                    "trace_count": row["trace_count"],
                    "monthly_budget": monthly_budget,
                    "budget_pct": round(allocated / monthly_budget * 100, 1)
                    if monthly_budget
                    else None,
                }
            )

        # Add centers with zero spend
        for cc_id, cc in center_map.items():
            if cc_id not in allocated_ids:
                report.append(
                    {
                        "cost_center_id": cc_id,
                        "cost_center_name": cc["name"],
                        "code": cc.get("code", ""),
                        "allocated_cost": 0.0,
                        "trace_count": 0,
                        "monthly_budget": cc.get("monthly_budget"),
                        "budget_pct": 0.0 if cc.get("monthly_budget") else None,
                    }
                )

        # Get unallocated spend
        unallocated_row = self._db.fetch_one(
            f"""SELECT COALESCE(SUM(t.cost), 0) as unallocated_cost, COUNT(t.id) as trace_count
                FROM trace_events t
                WHERE t.org_id = ?
                  AND t.project NOT IN (
                      SELECT DISTINCT project FROM cost_allocations WHERE org_id = ? AND project IS NOT NULL
                  )
                  AND (t.agent_id IS NULL OR t.agent_id NOT IN (
                      SELECT DISTINCT agent_id FROM cost_allocations WHERE org_id = ? AND agent_id IS NOT NULL
                  ))
                  {time_filter.replace("t.timestamp", "t.timestamp")}""",
            [org_id, org_id, org_id] + time_params[1:],
        )
        if unallocated_row:
            ur = dict(unallocated_row)
            if ur["unallocated_cost"] > 0 or ur["trace_count"] > 0:
                report.append(
                    {
                        "cost_center_id": None,
                        "cost_center_name": "Unallocated",
                        "code": "",
                        "allocated_cost": round(ur["unallocated_cost"], 6),
                        "trace_count": ur["trace_count"],
                        "monthly_budget": None,
                        "budget_pct": None,
                    }
                )

        return sorted(report, key=lambda x: x["allocated_cost"], reverse=True)
