# Heartbeat-Based Cost Monitoring

Track costs per agent heartbeat cycle, detect anomalies between cycles, and auto-pause agents when budgets are hit. Designed to integrate with orchestrators like Paperclip, CrewAI, and AutoGen.

## Concept

Agents in orchestration systems run on scheduled heartbeat intervals — periodic cycles where they check for work, execute tasks, and go idle. The HeartbeatTracker wraps these cycles with cost monitoring:

```
start_cycle → [agent makes LLM calls] → end_cycle
              ↓ cost recorded per call ↓
              → anomaly check → budget check → auto-pause if needed
```

## Basic Usage

```python
from agentcost.heartbeat import HeartbeatTracker

tracker = HeartbeatTracker()

# Set a budget for the agent
tracker.set_budget("agent-123", budget=10.00)

# --- Agent heartbeat cycle begins ---
cycle_id = tracker.start_cycle("agent-123")

# Agent makes LLM calls — record each cost
tracker.record_spend("agent-123", 0.05)
tracker.record_spend("agent-123", 0.03)

# --- Agent heartbeat cycle ends ---
summary = tracker.end_cycle("agent-123")
# {'cycle_id': '...', 'cost': 0.08, 'calls': 2, 'duration_s': 30.5, 'status': 'completed'}
```

## Anomaly Detection

The tracker maintains a rolling average of cycle costs. If a cycle's cost exceeds 2x the average, it's flagged as an anomaly:

```python
tracker = HeartbeatTracker(anomaly_multiplier=2.0)

# After 5 normal cycles at ~$0.10 each:
tracker.start_cycle("agent-1")
tracker.record_spend("agent-1", 0.50)  # 5x the average!
summary = tracker.end_cycle("agent-1")

print(summary["status"])          # "anomaly"
print(summary["anomaly_reason"])  # "Cycle cost $0.50 is 5.0x the rolling average $0.10"
```

## Auto-Pause on Budget

When cumulative spend hits the budget limit, the agent is automatically paused:

```python
tracker = HeartbeatTracker()
tracker.set_budget("agent-1", budget=1.00)

# After several cycles totaling > $1.00:
print(tracker.is_paused("agent-1"))  # True

# Resume when budget is replenished
tracker.resume_agent("agent-1")
```

## Orchestrator Webhook Integration

For external orchestrators (Paperclip, CrewAI), set a callback that fires when an agent is paused:

```python
import requests

def notify_orchestrator(agent_id: str, data: dict):
    """POST to Paperclip's agent pause endpoint."""
    requests.post(
        f"http://paperclip:3100/api/agents/{agent_id}/pause",
        json=data,
    )

tracker = HeartbeatTracker(pause_callback=notify_orchestrator)
tracker.set_budget("agent-1", budget=5.00)
```

When the agent exceeds its budget, the callback fires with:

```json
{
  "action": "pause",
  "reason": "Budget exceeded: $5.12 / $5.00",
  "cumulative_spend": 5.12
}
```

## Agent Summary

```python
summary = tracker.get_agent_summary("agent-123")
# {
#   "agent_id": "agent-123",
#   "total_cycles": 42,
#   "total_cost": 3.75,
#   "total_calls": 156,
#   "avg_cost_per_cycle": 0.089,
#   "anomaly_count": 1,
#   "budget": 10.0,
#   "budget_used_pct": 37.5,
#   "paused": false,
# }

# Get cycle history
cycles = tracker.get_agent_cycles("agent-123", limit=10)

# List all tracked agents
agents = tracker.get_all_agents()
```

## Combining with Goals

Track goal attribution within heartbeat cycles:

```python
from agentcost.heartbeat import HeartbeatTracker
from agentcost.goals import GoalService

tracker = HeartbeatTracker()
goals = GoalService()
goals.create_goal("feature-x", "Build Feature X", budget=50.0)

tracker.start_cycle("agent-1")

# Each LLM call records cost to both heartbeat and goal
cost = 0.15
tracker.record_spend("agent-1", cost)
goals.record_spend("feature-x", cost)

tracker.end_cycle("agent-1")

# Query both
print(tracker.get_cumulative_spend("agent-1"))    # 0.15
print(goals.get_goal_cost("feature-x"))           # {'direct_cost': 0.15, ...}
```
