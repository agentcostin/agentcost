"""
BudgetService — Enterprise budget enforcement.

Upgrades the basic Phase 2 budget system with:
  - Org-scoped budgets (each org's budgets are isolated)
  - Daily + monthly + total limit enforcement
  - Pre-call budget check (can this call proceed?)
  - Alert thresholds with overage detection
  - Budget utilization reports across all projects
  - Cost center budget validation

The budget check is designed to be called by the SDK/trace ingestion
layer BEFORE recording an LLM call. If the budget would be exceeded,
the call can be blocked or flagged for approval.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..data.connection import get_db


class BudgetService:

    def __init__(self, db=None):
        self._db = db or get_db()

    # ── Set Budget ───────────────────────────────────────────────

    def set_budget(
        self,
        org_id: str,
        project: str,
        daily_limit: Optional[float] = None,
        monthly_limit: Optional[float] = None,
        total_limit: Optional[float] = None,
        alert_threshold: float = 0.8,
    ) -> dict:
        """Create or update a budget for a project within an org."""
        now = datetime.utcnow().isoformat()
        # Check if budget exists
        existing = self._db.fetch_one(
            "SELECT id FROM budgets WHERE project = ? AND org_id = ?",
            (project, org_id),
        )
        if existing:
            self._db.execute(
                "UPDATE budgets SET daily_limit = ?, monthly_limit = ?, total_limit = ?, "
                "alert_threshold = ?, updated_at = ? WHERE project = ? AND org_id = ?",
                (daily_limit, monthly_limit, total_limit, alert_threshold, now, project, org_id),
            )
        else:
            self._db.execute(
                "INSERT INTO budgets (project, daily_limit, monthly_limit, total_limit, "
                "alert_threshold, created_at, updated_at, org_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (project, daily_limit, monthly_limit, total_limit, alert_threshold, now, now, org_id),
            )
        return self.get_budget(org_id, project)

    # ── Get Budget ───────────────────────────────────────────────

    def get_budget(self, org_id: str, project: str) -> Optional[dict]:
        """Get budget for a project with current spend calculations."""
        row = self._db.fetch_one(
            "SELECT * FROM budgets WHERE project = ? AND org_id = ?",
            (project, org_id),
        )
        if not row:
            return None

        b = dict(row)
        spend = self._get_spend(org_id, project)
        b.update(spend)
        b["alerts"] = self._check_alerts(b)
        return b

    def list_budgets(self, org_id: str) -> list[dict]:
        """List all budgets for an org with current spend."""
        rows = self._db.fetch_all(
            "SELECT * FROM budgets WHERE org_id = ? ORDER BY project",
            (org_id,),
        )
        result = []
        for r in rows:
            b = dict(r)
            spend = self._get_spend(org_id, b["project"])
            b.update(spend)
            b["alerts"] = self._check_alerts(b)
            result.append(b)
        return result

    # ── Delete Budget ────────────────────────────────────────────

    def delete_budget(self, org_id: str, project: str) -> dict:
        self._db.execute(
            "DELETE FROM budgets WHERE project = ? AND org_id = ?",
            (project, org_id),
        )
        return {"status": "deleted", "project": project}

    # ── Pre-Call Check ───────────────────────────────────────────

    def check_can_proceed(
        self,
        org_id: str,
        project: str,
        estimated_cost: float = 0.0,
    ) -> dict:
        """Check if an LLM call can proceed within budget.

        Called by SDK/trace ingestion BEFORE the LLM call.
        Returns allow/deny/warn with reason.

        Args:
            org_id: Organization ID
            project: Project name
            estimated_cost: Estimated cost of the upcoming call

        Returns:
            {"allowed": bool, "reason": str, "budget": dict}
        """
        budget = self.get_budget(org_id, project)
        if not budget:
            return {"allowed": True, "reason": "no_budget_set", "budget": None}

        # Check total limit
        if budget.get("total_limit"):
            if budget["total_spend"] + estimated_cost > budget["total_limit"]:
                return {
                    "allowed": False,
                    "reason": "total_limit_exceeded",
                    "budget": budget,
                    "current": budget["total_spend"],
                    "limit": budget["total_limit"],
                }

        # Check daily limit
        if budget.get("daily_limit"):
            if budget["daily_spend"] + estimated_cost > budget["daily_limit"]:
                return {
                    "allowed": False,
                    "reason": "daily_limit_exceeded",
                    "budget": budget,
                    "current": budget["daily_spend"],
                    "limit": budget["daily_limit"],
                }

        # Check monthly limit
        if budget.get("monthly_limit"):
            if budget["monthly_spend"] + estimated_cost > budget["monthly_limit"]:
                return {
                    "allowed": False,
                    "reason": "monthly_limit_exceeded",
                    "budget": budget,
                    "current": budget["monthly_spend"],
                    "limit": budget["monthly_limit"],
                }

        return {"allowed": True, "reason": "within_budget", "budget": budget}

    # ── Utilization Report ───────────────────────────────────────

    def utilization_report(self, org_id: str) -> dict:
        """Generate a budget utilization report across all projects."""
        budgets = self.list_budgets(org_id)

        total_budget = sum(b.get("monthly_limit") or 0 for b in budgets)
        total_spend = sum(b.get("monthly_spend") or 0 for b in budgets)

        # Get total org spend (including unbudgeted projects)
        org_total = self._db.fetch_one(
            "SELECT COALESCE(SUM(cost), 0) as total FROM trace_events WHERE org_id = ?",
            (org_id,),
        )
        org_spend = org_total["total"] if org_total else 0

        # Projects without budgets
        budgeted_projects = {b["project"] for b in budgets}
        unbudgeted_rows = self._db.fetch_all(
            "SELECT project, COALESCE(SUM(cost), 0) as spend, COUNT(*) as calls "
            "FROM trace_events WHERE org_id = ? "
            "GROUP BY project ORDER BY spend DESC",
            (org_id,),
        )
        unbudgeted = [
            dict(r) for r in unbudgeted_rows
            if r["project"] not in budgeted_projects
        ]

        return {
            "org_id": org_id,
            "total_monthly_budget": round(total_budget, 4),
            "total_monthly_spend": round(total_spend, 4),
            "total_org_spend": round(org_spend, 4),
            "budget_utilization_pct": round(total_spend / total_budget * 100, 1) if total_budget > 0 else None,
            "budgeted_projects": len(budgets),
            "unbudgeted_projects": unbudgeted,
            "projects": budgets,
        }

    # ── Internal Helpers ─────────────────────────────────────────

    def _get_spend(self, org_id: str, project: str) -> dict:
        """Calculate current spend for a project across time windows."""
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

        # Total spend
        total = self._db.fetch_one(
            "SELECT COALESCE(SUM(cost), 0) as spend FROM trace_events "
            "WHERE project = ? AND org_id = ?",
            (project, org_id),
        )
        # Daily spend
        daily = self._db.fetch_one(
            "SELECT COALESCE(SUM(cost), 0) as spend FROM trace_events "
            "WHERE project = ? AND org_id = ? AND timestamp >= ?",
            (project, org_id, today_start),
        )
        # Monthly spend
        monthly = self._db.fetch_one(
            "SELECT COALESCE(SUM(cost), 0) as spend FROM trace_events "
            "WHERE project = ? AND org_id = ? AND timestamp >= ?",
            (project, org_id, month_start),
        )

        return {
            "total_spend": round(total["spend"], 6) if total else 0,
            "daily_spend": round(daily["spend"], 6) if daily else 0,
            "monthly_spend": round(monthly["spend"], 6) if monthly else 0,
        }

    def _check_alerts(self, budget: dict) -> list[dict]:
        """Generate alerts for a budget based on current spend."""
        alerts = []
        threshold = budget.get("alert_threshold", 0.8)

        for limit_type in ["daily", "monthly", "total"]:
            limit_val = budget.get(f"{limit_type}_limit")
            spend_val = budget.get(f"{limit_type}_spend")
            if limit_val and spend_val is not None:
                pct = spend_val / limit_val
                if pct >= 1.0:
                    alerts.append({
                        "type": f"{limit_type}_exceeded",
                        "pct": round(pct * 100, 1),
                        "spend": round(spend_val, 6),
                        "limit": limit_val,
                    })
                elif pct >= threshold:
                    alerts.append({
                        "type": f"{limit_type}_warning",
                        "pct": round(pct * 100, 1),
                        "spend": round(spend_val, 6),
                        "limit": limit_val,
                    })
        return alerts
