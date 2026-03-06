"""
AgentCost Heartbeat Tracker — per-cycle cost monitoring for agent orchestrators.

Tracks costs per heartbeat cycle (not just per-call), detects anomalies
between cycles, and auto-pauses agents when budgets are hit.

Designed to integrate with orchestrators like Paperclip, CrewAI, and AutoGen
that run agents on scheduled heartbeat intervals.

Lifecycle:
    start_cycle(agent_id) → record_spend(agent_id, cost) → end_cycle(agent_id)
    Each cycle captures: total cost, call count, duration, and anomaly status.

Usage:
    from agentcost.heartbeat import HeartbeatTracker, get_heartbeat_tracker

    tracker = get_heartbeat_tracker()

    # Start a cycle (agent begins work)
    cycle_id = tracker.start_cycle("agent-123")

    # ... agent makes LLM calls, costs are recorded ...
    tracker.record_spend("agent-123", 0.05)
    tracker.record_spend("agent-123", 0.03)

    # End cycle (agent goes idle)
    summary = tracker.end_cycle("agent-123")
    # {'cycle_id': '...', 'cost': 0.08, 'calls': 2, 'duration_s': 30.5}
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Callable, Any

logger = logging.getLogger("agentcost.heartbeat")


@dataclass
class HeartbeatCycle:
    """A single heartbeat cycle for an agent."""

    cycle_id: str
    agent_id: str
    started_at: float
    ended_at: float = 0.0
    cost: float = 0.0
    calls: int = 0
    status: str = "active"  # active, completed, anomaly
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

    Features:
        - Per-cycle cost/call tracking
        - Rolling average for anomaly detection (cost > 2x avg triggers alert)
        - Auto-pause agents at budget thresholds
        - Webhook callback when agent is paused
    """

    def __init__(
        self,
        anomaly_multiplier: float = 2.0,
        pause_callback: Callable[[str, dict], None] | None = None,
    ):
        self._active_cycles: dict[str, HeartbeatCycle] = {}  # agent_id → current cycle
        self._history: dict[str, list[HeartbeatCycle]] = defaultdict(list)
        self._cumulative_spend: dict[str, float] = defaultdict(float)
        self._budgets: dict[str, float] = {}  # agent_id → budget limit
        self._anomaly_multiplier = anomaly_multiplier
        self._pause_callback = pause_callback
        self._paused_agents: set[str] = set()
        self._max_history = 100  # per agent

    def start_cycle(self, agent_id: str) -> str:
        """Start a new heartbeat cycle for an agent.

        Returns the cycle_id. If a cycle is already active, ends it first.
        """
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
        logger.debug("Cycle started: agent=%s cycle=%s", agent_id, cycle.cycle_id)
        return cycle.cycle_id

    def record_spend(self, agent_id: str, cost: float) -> None:
        """Record a cost event within the current cycle."""
        cycle = self._active_cycles.get(agent_id)
        if cycle and cycle.is_active:
            cycle.cost += cost
            cycle.calls += 1
        self._cumulative_spend[agent_id] += cost

    def end_cycle(self, agent_id: str) -> dict | None:
        """End the current cycle and return summary.

        Checks for anomalies and budget thresholds.
        """
        cycle = self._active_cycles.pop(agent_id, None)
        if not cycle:
            return None

        cycle.ended_at = time.time()
        cycle.status = "completed"

        # Check for cost anomaly (> 2x rolling average)
        avg = self._get_rolling_avg_cost(agent_id)
        if avg > 0 and cycle.cost > avg * self._anomaly_multiplier:
            cycle.status = "anomaly"
            cycle.anomaly_reason = (
                f"Cycle cost ${cycle.cost:.4f} is {cycle.cost / avg:.1f}x "
                f"the rolling average ${avg:.4f}"
            )
            logger.warning("Anomaly: agent=%s %s", agent_id, cycle.anomaly_reason)
            self._emit_anomaly(agent_id, cycle)

        # Store in history
        history = self._history[agent_id]
        history.append(cycle)
        if len(history) > self._max_history:
            self._history[agent_id] = history[-self._max_history :]

        # Check budget threshold
        self._check_budget(agent_id)

        summary = cycle.to_dict()
        logger.debug(
            "Cycle ended: agent=%s cost=$%.4f calls=%d duration=%.1fs",
            agent_id,
            cycle.cost,
            cycle.calls,
            cycle.duration_s,
        )
        return summary

    def set_budget(self, agent_id: str, budget: float) -> None:
        """Set a budget limit for an agent."""
        self._budgets[agent_id] = budget

    def get_cumulative_spend(self, agent_id: str) -> float:
        return self._cumulative_spend.get(agent_id, 0.0)

    def pause_agent(self, agent_id: str, reason: str = "") -> None:
        """Pause an agent (stop accepting spend)."""
        self._paused_agents.add(agent_id)
        logger.info("Agent paused: %s reason=%s", agent_id, reason)

        # Trigger lifecycle transition if agent plugin is loaded
        try:
            from ..plugins import registry

            registry.transition_agent(agent_id, "suspended", reason)
        except Exception:
            pass

        # Fire pause callback (for external orchestrators)
        if self._pause_callback:
            try:
                self._pause_callback(
                    agent_id,
                    {
                        "action": "pause",
                        "reason": reason,
                        "cumulative_spend": self._cumulative_spend.get(agent_id, 0),
                    },
                )
            except Exception as e:
                logger.error("Pause callback failed: %s", e)

    def resume_agent(self, agent_id: str) -> None:
        """Resume a paused agent."""
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
        """Get recent heartbeat cycles for an agent."""
        cycles = self._history.get(agent_id, [])
        return [c.to_dict() for c in cycles[-limit:]]

    def get_agent_summary(self, agent_id: str) -> dict:
        """Get summary stats for an agent."""
        cycles = self._history.get(agent_id, [])
        total_cost = sum(c.cost for c in cycles)
        total_calls = sum(c.calls for c in cycles)
        anomalies = sum(1 for c in cycles if c.status == "anomaly")
        avg_cost = total_cost / len(cycles) if cycles else 0
        budget = self._budgets.get(agent_id, 0)

        return {
            "agent_id": agent_id,
            "total_cycles": len(cycles),
            "total_cost": round(total_cost, 6),
            "total_calls": total_calls,
            "avg_cost_per_cycle": round(avg_cost, 6),
            "anomaly_count": anomalies,
            "cumulative_spend": round(self._cumulative_spend.get(agent_id, 0), 6),
            "budget": budget,
            "budget_used_pct": round(
                self._cumulative_spend.get(agent_id, 0) / budget * 100, 1
            )
            if budget > 0
            else 0,
            "paused": agent_id in self._paused_agents,
            "active_cycle": self._active_cycles.get(agent_id, None) is not None,
        }

    def get_all_agents(self) -> list[str]:
        """List all tracked agents."""
        agents = set(self._history.keys()) | set(self._active_cycles.keys())
        return sorted(agents)

    def reset(self, agent_id: str | None = None) -> None:
        """Reset tracking data for an agent (or all agents)."""
        if agent_id:
            self._history.pop(agent_id, None)
            self._active_cycles.pop(agent_id, None)
            self._cumulative_spend.pop(agent_id, None)
            self._paused_agents.discard(agent_id)
        else:
            self._history.clear()
            self._active_cycles.clear()
            self._cumulative_spend.clear()
            self._paused_agents.clear()

    # ── Internal ──────────────────────────────────────────────────

    def _get_rolling_avg_cost(self, agent_id: str, window: int = 10) -> float:
        """Rolling average cost over last N completed cycles."""
        cycles = self._history.get(agent_id, [])
        recent = [c for c in cycles[-window:] if c.status == "completed"]
        if not recent:
            return 0.0
        return sum(c.cost for c in recent) / len(recent)

    def _check_budget(self, agent_id: str) -> None:
        """Check if cumulative spend exceeds budget and auto-pause."""
        budget = self._budgets.get(agent_id, 0)
        if budget <= 0:
            return

        spend = self._cumulative_spend.get(agent_id, 0)
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

            bus = get_event_bus()
            bus.emit(
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

            bus = get_event_bus()
            bus.emit(
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


# ── Singleton ─────────────────────────────────────────────────────────────────

_global_tracker: Optional[HeartbeatTracker] = None


def get_heartbeat_tracker() -> HeartbeatTracker:
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = HeartbeatTracker()
    return _global_tracker
