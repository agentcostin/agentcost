"""
ScorecardService — Agent scorecard generation, comparison, and recommendations.

Scorecards aggregate monthly agent performance from trace_events:
  - total_cost, total_tasks, error_rate
  - cost_efficiency (cost per task)
  - quality_score (success rate)
  - grade (A-F based on composite score)
  - recommendations (auto-generated optimization suggestions)

Scorecards are generated on-demand for any period and cached in the
agent_scorecards table with a UNIQUE(org_id, agent_id, period) constraint.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional

from ..data.connection import get_db


class ScorecardService:
    def __init__(self, db=None):
        self._db = db or get_db()

    # ── Generate ─────────────────────────────────────────────────

    def generate(
        self, org_id: str, agent_id: str, period: Optional[str] = None
    ) -> dict:
        """Generate or refresh a scorecard for an agent for a given period.

        Args:
            org_id: Organization ID
            agent_id: Agent identifier
            period: 'YYYY-MM' format (default: current month)
        """
        if not period:
            period = datetime.utcnow().strftime("%Y-%m")

        # Get period boundaries
        year, month = int(period[:4]), int(period[5:7])
        period_start = f"{year}-{month:02d}-01T00:00:00"
        if month == 12:
            period_end = f"{year + 1}-01-01T00:00:00"
        else:
            period_end = f"{year}-{month + 1:02d}-01T00:00:00"

        # Aggregate trace data
        stats = self._db.fetch_one(
            "SELECT COUNT(*) as total_tasks, "
            "COALESCE(SUM(cost), 0) as total_cost, "
            "COALESCE(AVG(cost), 0) as avg_cost, "
            "COALESCE(AVG(latency_ms), 0) as avg_latency, "
            "SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count, "
            "SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count, "
            "COUNT(DISTINCT model) as models_used, "
            "COUNT(DISTINCT project) as projects_used "
            "FROM trace_events WHERE agent_id = ? AND org_id = ? "
            "AND timestamp >= ? AND timestamp < ?",
            (agent_id, org_id, period_start, period_end),
        )

        if not stats or stats["total_tasks"] == 0:
            return {
                "agent_id": agent_id,
                "period": period,
                "org_id": org_id,
                "total_tasks": 0,
                "message": "No data for this agent in this period",
            }

        s = dict(stats)
        total = s["total_tasks"]
        errors = s["error_count"] or 0
        successes = s["success_count"] or 0
        total_cost = round(s["total_cost"], 6)

        error_rate = round(errors / total, 4) if total > 0 else 0
        quality_score = round(successes / total * 100, 1) if total > 0 else 0
        cost_efficiency = round(total_cost / total, 6) if total > 0 else 0

        # Grade calculation
        grade = self._compute_grade(quality_score, error_rate, cost_efficiency)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            quality_score, error_rate, cost_efficiency, total_cost, total, s
        )

        # Upsert scorecard
        sc_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        recs_json = json.dumps(recommendations)

        # Check existing
        existing = self._db.fetch_one(
            "SELECT id FROM agent_scorecards WHERE org_id = ? AND agent_id = ? AND period = ?",
            (org_id, agent_id, period),
        )
        if existing:
            self._db.execute(
                "UPDATE agent_scorecards SET quality_score = ?, cost_efficiency = ?, "
                "total_cost = ?, total_tasks = ?, error_rate = ?, grade = ?, "
                "recommendations = ?, created_at = ? "
                "WHERE org_id = ? AND agent_id = ? AND period = ?",
                (
                    quality_score,
                    cost_efficiency,
                    total_cost,
                    total,
                    error_rate,
                    grade,
                    recs_json,
                    now,
                    org_id,
                    agent_id,
                    period,
                ),
            )
            sc_id = existing["id"]
        else:
            self._db.execute(
                "INSERT INTO agent_scorecards (id, org_id, agent_id, period, quality_score, "
                "cost_efficiency, total_cost, total_tasks, error_rate, grade, "
                "recommendations, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sc_id,
                    org_id,
                    agent_id,
                    period,
                    quality_score,
                    cost_efficiency,
                    total_cost,
                    total,
                    error_rate,
                    grade,
                    recs_json,
                    now,
                ),
            )

        return {
            "id": sc_id,
            "org_id": org_id,
            "agent_id": agent_id,
            "period": period,
            "quality_score": quality_score,
            "cost_efficiency": cost_efficiency,
            "total_cost": total_cost,
            "total_tasks": total,
            "error_rate": error_rate,
            "grade": grade,
            "recommendations": recommendations,
        }

    # ── Read ─────────────────────────────────────────────────────

    def get(self, org_id: str, agent_id: str, period: str) -> Optional[dict]:
        row = self._db.fetch_one(
            "SELECT * FROM agent_scorecards WHERE org_id = ? AND agent_id = ? AND period = ?",
            (org_id, agent_id, period),
        )
        return self._parse_row(row) if row else None

    def list_for_agent(self, org_id: str, agent_id: str, limit: int = 12) -> list[dict]:
        """Get scorecard history for an agent (most recent first)."""
        rows = self._db.fetch_all(
            "SELECT * FROM agent_scorecards WHERE org_id = ? AND agent_id = ? "
            "ORDER BY period DESC LIMIT ?",
            (org_id, agent_id, limit),
        )
        return [self._parse_row(r) for r in rows]

    def list_for_period(self, org_id: str, period: Optional[str] = None) -> list[dict]:
        """Get all agent scorecards for a period (leaderboard view)."""
        if not period:
            period = datetime.utcnow().strftime("%Y-%m")
        rows = self._db.fetch_all(
            "SELECT * FROM agent_scorecards WHERE org_id = ? AND period = ? "
            "ORDER BY grade ASC, quality_score DESC",
            (org_id, period),
        )
        return [self._parse_row(r) for r in rows]

    def get_agents(self, org_id: str) -> list[str]:
        """Get all distinct agent IDs that have trace data."""
        rows = self._db.fetch_all(
            "SELECT DISTINCT agent_id FROM trace_events WHERE org_id = ? AND agent_id IS NOT NULL "
            "ORDER BY agent_id",
            (org_id,),
        )
        return [r["agent_id"] for r in rows]

    # ── Compare ──────────────────────────────────────────────────

    def compare(
        self, org_id: str, agent_ids: list[str], period: Optional[str] = None
    ) -> dict:
        """Compare multiple agents side-by-side for a period."""
        if not period:
            period = datetime.utcnow().strftime("%Y-%m")

        scorecards = []
        for aid in agent_ids:
            sc = self.get(org_id, aid, period)
            if not sc:
                sc = self.generate(org_id, aid, period)
            scorecards.append(sc)

        # Rank by grade then quality
        scorecards.sort(key=lambda x: (x.get("grade", "F"), -x.get("quality_score", 0)))

        return {
            "period": period,
            "agents": scorecards,
            "best_quality": max(
                scorecards, key=lambda x: x.get("quality_score", 0)
            ).get("agent_id")
            if scorecards
            else None,
            "most_efficient": min(
                [s for s in scorecards if s.get("cost_efficiency", 0) > 0],
                key=lambda x: x.get("cost_efficiency", float("inf")),
                default={},
            ).get("agent_id"),
            "lowest_error": min(scorecards, key=lambda x: x.get("error_rate", 1)).get(
                "agent_id"
            )
            if scorecards
            else None,
        }

    # ── Generate All ─────────────────────────────────────────────

    def generate_all(self, org_id: str, period: Optional[str] = None) -> dict:
        """Generate scorecards for ALL agents in the org."""
        agents = self.get_agents(org_id)
        results = []
        for aid in agents:
            sc = self.generate(org_id, aid, period)
            results.append(sc)
        return {
            "period": period or datetime.utcnow().strftime("%Y-%m"),
            "agents_processed": len(results),
            "scorecards": results,
        }

    # ── Internal ─────────────────────────────────────────────────

    def _compute_grade(self, quality: float, error_rate: float, cost_eff: float) -> str:
        """Compute letter grade from composite metrics.

        Scoring:
          quality_score (0-100): 50% weight
          error_rate (0-1): 30% weight (inverted — lower is better)
          cost_efficiency: 20% weight (contextual, lower is better)
        """
        # Normalize to 0-100 scale
        q_score = quality  # Already 0-100
        e_score = (1 - error_rate) * 100  # 0% errors = 100
        # Cost efficiency is relative — hard to normalize without benchmarks,
        # so we use a simple heuristic: <$0.01/task = excellent, >$1/task = poor
        if cost_eff <= 0.001:
            c_score = 100
        elif cost_eff <= 0.01:
            c_score = 90
        elif cost_eff <= 0.05:
            c_score = 75
        elif cost_eff <= 0.1:
            c_score = 60
        elif cost_eff <= 0.5:
            c_score = 40
        elif cost_eff <= 1.0:
            c_score = 20
        else:
            c_score = 10

        composite = q_score * 0.5 + e_score * 0.3 + c_score * 0.2

        if composite >= 90:
            return "A"
        elif composite >= 80:
            return "B"
        elif composite >= 70:
            return "C"
        elif composite >= 60:
            return "D"
        else:
            return "F"

    def _generate_recommendations(
        self,
        quality: float,
        error_rate: float,
        cost_eff: float,
        total_cost: float,
        total_tasks: int,
        stats: dict,
    ) -> list[str]:
        """Auto-generate optimization suggestions based on metrics."""
        recs = []

        if error_rate > 0.1:
            recs.append(
                f"High error rate ({error_rate:.1%}). Review error logs and add retry logic or fallback models."
            )
        if error_rate > 0.25:
            recs.append(
                "Critical: >25% error rate. Consider pausing this agent for investigation."
            )

        if cost_eff > 0.5:
            recs.append(
                f"High cost per task (${cost_eff:.4f}). Consider switching to a cheaper model for routine tasks."
            )
        if cost_eff > 0.1:
            recs.append(
                "Evaluate whether this agent can use a smaller/faster model without quality loss."
            )

        if quality < 70:
            recs.append(
                f"Quality score below threshold ({quality:.0f}%). Review prompt engineering and output validation."
            )

        if total_cost > 100:
            recs.append(
                f"Total spend ${total_cost:.2f} is significant. Set a budget alert if not already configured."
            )

        models_used = stats.get("models_used", 0)
        if models_used and models_used > 3:
            recs.append(
                f"Using {models_used} different models. Consider standardizing to reduce complexity."
            )

        if not recs:
            recs.append("Agent is performing well. No immediate optimization needed.")

        return recs

    def _parse_row(self, row) -> dict:
        d = dict(row)
        if d.get("recommendations") and isinstance(d["recommendations"], str):
            try:
                d["recommendations"] = json.loads(d["recommendations"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d
