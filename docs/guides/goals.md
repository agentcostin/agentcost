# Goal-Aware Cost Attribution

Track LLM spending per business objective. Answer "how much did achieving Goal X cost?" with hierarchical cost rollup.

## Creating Goals

Goals form a tree — child goals roll up costs to their parents:

```python
from agentcost.goals import GoalService

svc = GoalService()

# Top-level OKR
svc.create_goal("q1-okr", "Q1 Revenue Target", budget=5000.0)

# Sub-goals
svc.create_goal("launch-v2", "Launch Product V2", parent_goal_id="q1-okr", budget=2000.0)
svc.create_goal("build-api", "Build API Layer", parent_goal_id="launch-v2")
svc.create_goal("marketing", "Marketing Campaign", parent_goal_id="q1-okr", budget=1000.0)
```

## Tracking Costs Against Goals

Pass `goal_id` to the SDK trace wrapper:

```python
from agentcost.sdk import trace
from openai import OpenAI

# All costs from this client are attributed to "build-api"
client = trace(OpenAI(), project="my-app", goal_id="build-api")

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Design the REST API schema"}]
)
```

## Querying Cost Attribution

```python
# Direct cost of a goal
cost = svc.get_goal_cost("build-api")
# {'direct_cost': 12.50, 'children_cost': 0.0, 'total_cost': 12.50, ...}

# Total cost including all sub-goals
cost = svc.get_goal_cost("q1-okr", include_children=True)
# {'direct_cost': 5.00, 'children_cost': 45.00, 'total_cost': 50.00, 'budget_used_pct': 1.0}

# Goal ancestry chain
chain = svc.get_ancestry("build-api")
# [build-api, launch-v2, q1-okr]
```

## Budget Checks

Goals can have budgets that are checked before expensive operations:

```python
check = svc.check_goal_budget("launch-v2")
if not check["allowed"]:
    print(f"Goal over budget: {check['reason']}")
```

## Goal Lifecycle

```python
# Mark a goal as completed
svc.update_goal("build-api", status="completed")

# List active goals for a project
active = svc.list_goals(project="my-app", status="active")

# Get all goals in summary
summary = svc.get_summary()
```
