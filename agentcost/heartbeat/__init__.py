"""
AgentCost Heartbeat Tracker — per-cycle cost monitoring for agent orchestrators.

Tracks costs per heartbeat cycle (not just per-call), detects anomalies
between cycles, and auto-pauses agents when budgets are hit.

Now persisted to database — cycle history and budgets survive restarts.
Active cycles are still in-memory (they're transient by nature).

Usage:
    from agentcost.heartbeat import HeartbeatTracker, get_heartbeat_tracker

    tracker = get_heartbeat_tracker()
    cycle_id = tracker.start_cycle("agent-123")
    tracker.record_spend("agent-123", 0.05)
    summary = tracker.end_cycle("agent-123")
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Callable, Any

logger = logging.getLogger("agentcost.heartbeat")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS heartbeat_cycles (
    id              TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    started_at      REAL NOT NULL,
    ended_at        REAL DEFAULT 0,
    cost            REAL DEFAULT 0,
    calls           INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'active',
    anomaly_reason  TEXT DEFAULT '',
    org_id          TEXT DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_hb_agent ON heartbeat_cycles(agent_id);
CREATE INDEX IF NOT EXISTS idx_hb_status ON heartbeat_cycles(status);
CREATE INDEX IF NOT EXISTS idx_hb_started ON heartbeat_cycles(started_at);

CREATE TABLE IF NOT EXISTS heartbeat_budgets (
    agent_id        TEXT PRIMARY KEY,
    budget_limit    REAL NOT NULL,
    warning_pct     REAL DEFAULT 0.8,
    pause_pct       REAL DEFAULT 1.0,
    org_id          TEXT DEFAULT 'default',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
"""


@dataclass
class HeartbeatCycle:
    """A single heartbeat cycle for an agent."""

    cycle_id: str
    agent_id: str
    started_at: float
    ended_at: float = 0.0
    cost: float = 0.0
    calls: int = 0
    status: str = "active"
    anomaly_reason: str = ""

    @property
    def duration_s(self) -> float:
        end = self.ended_at or time.time()
        return round(end - self.started_at, 2)

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "agent_id": self.agent_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "cost": round(self.cost, 6),
            "calls": self.calls,
            "duration_s": self.duration_s,
            "status": self.status,
            "anomaly_reason": self.anomaly_reason,
        }


class HeartbeatTracker:
    """Tracks costs per heartbeat cycle for each agent.

    Active cycles live in memory (transient). Completed cycles persist to DB.
    """

    def __init__(
        self,
        db=None,
        anomaly_multiplier: float = 2.0,
        pause_callback: Callable[[str, dict], None] | None = None,
    ):
        from ..data.connection import get_db

        self.db = db or get_db()
        self._init()
        self._active_cycles: dict[str, HeartbeatCycle] = {}
        self._anomaly_multiplier = anomaly_multiplier
        self._pause_callback = pause_callback
        self._paused_agents: set[str] = set()

    def _init(self):
        self.db.executescript(_SCHEMA)

    def start_cycle(self, agent_id: str) -> str:
        if agent_id in self._active_cycles:
            self.end_cycle(agent_id)

        if agent_id in self._paused_agents:
            logger.warning(
                "Agent %s is paused — cycle started but spend blocked", agent_id
            )

        cycle = HeartbeatCycle(
            cycle_id=uuid.uuid4().hex[:12],
            agent_id=agent_id,
            started_at=time.time(),
        )
        self._active_cycles[agent_id] = cycle
        # Write active cycle to DB
        self.db.execute(
            """INSERT INTO heartbeat_cycles (id, agent_id, started_at, ended_at,
               cost, calls, status, anomaly_reason, org_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cycle.cycle_id,
                agent_id,
                cycle.started_at,
                0,
                0,
                0,
                "active",
                "",
                "default",
            ),
        )
        return cycle.cycle_id

    def record_spend(self, agent_id: str, cost: float) -> None:
        cycle = self._active_cycles.get(agent_id)
        if cycle and cycle.is_active:
            cycle.cost += cost
            cycle.calls += 1
            # Update in DB
            self.db.execute(
                "UPDATE heartbeat_cycles SET cost=?, calls=? WHERE id=?",
                (cycle.cost, cycle.calls, cycle.cycle_id),
            )

    def end_cycle(self, agent_id: str) -> dict | None:
        cycle = self._active_cycles.pop(agent_id, None)
        if not cycle:
            return None

        cycle.ended_at = time.time()
        cycle.status = "completed"

        # Check for cost anomaly
        avg = self._get_rolling_avg_cost(agent_id)
        if avg > 0 and cycle.cost > avg * self._anomaly_multiplier:
            cycle.status = "anomaly"
            cycle.anomaly_reason = (
                f"Cycle cost ${cycle.cost:.4f} is {cycle.cost / avg:.1f}x "
                f"the rolling average ${avg:.4f}"
            )
            logger.warning("Anomaly: agent=%s %s", agent_id, cycle.anomaly_reason)
            self._emit_anomaly(agent_id, cycle)

        # Persist completed cycle
        self.db.execute(
            """UPDATE heartbeat_cycles SET ended_at=?, cost=?, calls=?,
               status=?, anomaly_reason=? WHERE id=?""",
            (
                cycle.ended_at,
                cycle.cost,
                cycle.calls,
                cycle.status,
                cycle.anomaly_reason,
                cycle.cycle_id,
            ),
        )

        self._check_budget(agent_id)
        return cycle.to_dict()

    def set_budget(self, agent_id: str, budget: float) -> None:
        now = time.time()
        # Upsert
        existing = self.db.fetch_one(
            "SELECT agent_id FROM heartbeat_budgets WHERE agent_id=?", (agent_id,)
        )
        if existing:
            self.db.execute(
                "UPDATE heartbeat_budgets SET budget_limit=?, updated_at=? WHERE agent_id=?",
                (budget, now, agent_id),
            )
        else:
            self.db.execute(
                """INSERT INTO heartbeat_budgets (agent_id, budget_limit, warning_pct,
                   pause_pct, org_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (agent_id, budget, 0.8, 1.0, "default", now, now),
            )

    def get_cumulative_spend(self, agent_id: str) -> float:
        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(cost), 0) as total FROM heartbeat_cycles WHERE agent_id=?",
            (agent_id,),
        )
        return row["total"] if row else 0.0

    def pause_agent(self, agent_id: str, reason: str = "") -> None:
        self._paused_agents.add(agent_id)
        logger.info("Agent paused: %s reason=%s", agent_id, reason)
        try:
            from ..plugins import registry

            registry.transition_agent(agent_id, "suspended", reason)
        except Exception:
            pass
        if self._pause_callback:
            try:
                self._pause_callback(
                    agent_id,
                    {
                        "action": "pause",
                        "reason": reason,
                        "cumulative_spend": self.get_cumulative_spend(agent_id),
                    },
                )
            except Exception as e:
                logger.error("Pause callback failed: %s", e)

    def resume_agent(self, agent_id: str) -> None:
        self._paused_agents.discard(agent_id)
        logger.info("Agent resumed: %s", agent_id)
        try:
            from ..plugins import registry

            registry.transition_agent(agent_id, "resumed", "budget reset")
        except Exception:
            pass

    def is_paused(self, agent_id: str) -> bool:
        return agent_id in self._paused_agents

    def get_agent_cycles(self, agent_id: str, limit: int = 20) -> list[dict]:
        rows = self.db.fetch_all(
            "SELECT * FROM heartbeat_cycles WHERE agent_id=? ORDER BY started_at DESC LIMIT ?",
            (agent_id, limit),
        )
        return [self._row_to_cycle(r).to_dict() for r in rows]

    def get_agent_summary(self, agent_id: str) -> dict:
        total_row = self.db.fetch_one(
            """SELECT COUNT(*) as total_cycles,
                      COALESCE(SUM(cost), 0) as total_cost,
                      COALESCE(SUM(calls), 0) as total_calls,
                      COALESCE(AVG(cost), 0) as avg_cost
               FROM heartbeat_cycles WHERE agent_id=? AND status != 'active'""",
            (agent_id,),
        )
        anomaly_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM heartbeat_cycles WHERE agent_id=? AND status='anomaly'",
            (agent_id,),
        )
        budget_row = self.db.fetch_one(
            "SELECT budget_limit FROM heartbeat_budgets WHERE agent_id=?", (agent_id,)
        )
        budget = budget_row["budget_limit"] if budget_row else 0
        cumulative = self.get_cumulative_spend(agent_id)

        return {
            "agent_id": agent_id,
            "total_cycles": total_row["total_cycles"] if total_row else 0,
            "total_cost": round(total_row["total_cost"], 6) if total_row else 0,
            "total_calls": total_row["total_calls"] if total_row else 0,
            "avg_cost_per_cycle": round(total_row["avg_cost"], 6) if total_row else 0,
            "anomaly_count": anomaly_row["cnt"] if anomaly_row else 0,
            "cumulative_spend": round(cumulative, 6),
            "budget": budget,
            "budget_used_pct": round(cumulative / budget * 100, 1) if budget > 0 else 0,
            "paused": agent_id in self._paused_agents,
            "active_cycle": agent_id in self._active_cycles,
        }

    def get_all_agents(self) -> list[str]:
        rows = self.db.fetch_all(
            "SELECT DISTINCT agent_id FROM heartbeat_cycles ORDER BY agent_id"
        )
        db_agents = {r["agent_id"] for r in rows}
        return sorted(db_agents | set(self._active_cycles.keys()))

    def reset(self, agent_id: str | None = None) -> None:
        if agent_id:
            self._active_cycles.pop(agent_id, None)
            self._paused_agents.discard(agent_id)
            self.db.execute(
                "DELETE FROM heartbeat_cycles WHERE agent_id=?", (agent_id,)
            )
            self.db.execute(
                "DELETE FROM heartbeat_budgets WHERE agent_id=?", (agent_id,)
            )
        else:
            self._active_cycles.clear()
            self._paused_agents.clear()
            self.db.execute("DELETE FROM heartbeat_cycles")
            self.db.execute("DELETE FROM heartbeat_budgets")

    # ── Internal ──────────────────────────────────────────────────

    def _get_rolling_avg_cost(self, agent_id: str, window: int = 10) -> float:
        rows = self.db.fetch_all(
            """SELECT cost FROM heartbeat_cycles
               WHERE agent_id=? AND status='completed'
               ORDER BY started_at DESC LIMIT ?""",
            (agent_id, window),
        )
        if not rows:
            return 0.0
        return sum(r["cost"] for r in rows) / len(rows)

    def _check_budget(self, agent_id: str) -> None:
        budget_row = self.db.fetch_one(
            "SELECT budget_limit FROM heartbeat_budgets WHERE agent_id=?", (agent_id,)
        )
        if not budget_row or budget_row["budget_limit"] <= 0:
            return
        budget = budget_row["budget_limit"]
        spend = self.get_cumulative_spend(agent_id)
        pct = spend / budget * 100
        if pct >= 100 and agent_id not in self._paused_agents:
            self.pause_agent(agent_id, f"Budget exceeded: ${spend:.2f} / ${budget:.2f}")
            self._emit_budget_event("budget.exceeded", agent_id, spend, budget)
        elif pct >= 80:
            self._emit_budget_event("budget.warning", agent_id, spend, budget)

    def _emit_budget_event(
        self, event_type: str, agent_id: str, spend: float, budget: float
    ):
        try:
            from ..events import get_event_bus

            get_event_bus().emit(
                event_type,
                {
                    "agent_id": agent_id,
                    "spend": round(spend, 4),
                    "budget": round(budget, 4),
                    "usage_pct": round(spend / budget * 100, 1),
                    "source": "heartbeat",
                },
            )
        except Exception:
            pass

    def _emit_anomaly(self, agent_id: str, cycle: HeartbeatCycle):
        try:
            from ..events import get_event_bus

            get_event_bus().emit(
                "anomaly.cost_spike",
                {
                    "agent_id": agent_id,
                    "cycle_id": cycle.cycle_id,
                    "cost": round(cycle.cost, 6),
                    "reason": cycle.anomaly_reason,
                    "source": "heartbeat",
                },
            )
        except Exception:
            pass

    def _row_to_cycle(self, row) -> HeartbeatCycle:
        return HeartbeatCycle(
            cycle_id=row["id"],
            agent_id=row["agent_id"],
            started_at=row["started_at"],
            ended_at=row.get("ended_at", 0),
            cost=row.get("cost", 0),
            calls=row.get("calls", 0),
            status=row.get("status", "active"),
            anomaly_reason=row.get("anomaly_reason", ""),
        )


_global_tracker: Optional[HeartbeatTracker] = None


def get_heartbeat_tracker(db=None) -> HeartbeatTracker:
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = HeartbeatTracker(db=db)
    return _global_tracker


def reset_heartbeat_tracker() -> None:
    global _global_tracker
    _global_tracker = None
