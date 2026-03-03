# Python SDK Reference

## trace()

The primary way to integrate AgentCost. Wraps an OpenAI, Anthropic, or LiteLLM client to automatically track costs.

```python
from agentcost.sdk import trace

client = trace(openai_client, project="my-app", agent_id="chatbot", session_id="conv-123")
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `client` | `OpenAI \| Anthropic \| Any` | required | The LLM client to wrap |
| `project` | `str` | `"default"` | Project name for grouping |
| `agent_id` | `str \| None` | `None` | Agent identifier |
| `session_id` | `str \| None` | `None` | Session identifier |

**Returns:** A wrapped client with the same interface as the original.

## get_tracker()

Retrieve the cost tracker for a project to check accumulated costs.

```python
from agentcost.sdk import get_tracker

tracker = get_tracker("my-app")
summary = tracker.summary()
```

**Returns:** `CostTracker` instance.

## CostTracker

Tracks costs for a specific project.

### .summary() → dict

```python
{
    "project": "my-app",
    "total_cost": 0.0523,
    "total_calls": 15,
    "total_input_tokens": 4500,
    "total_output_tokens": 2100,
    "cost_by_model": {"gpt-4o": 0.0450, "gpt-4o-mini": 0.0073},
    "error_count": 0,
}
```

### .reset()

Clear accumulated cost data for this project.

## TraceEvent

Data class representing a single traced LLM call.

```python
from agentcost.sdk.trace import TraceEvent

event = TraceEvent(
    trace_id="abc123",
    project="my-app",
    model="gpt-4o",
    provider="openai",
    input_tokens=150,
    output_tokens=80,
    cost=0.0035,
    latency_ms=450,
    status="success",
    error=None,
    agent_id="chatbot",
    session_id="conv-123",
    timestamp="2026-03-01T10:30:00",
    metadata={"custom": "data"},
)
```

## CostForecaster

```python
from agentcost.forecast import CostForecaster

forecaster = CostForecaster()
forecaster.add_from_traces(traces)  # list of trace dicts
prediction = forecaster.predict(days_ahead=30, method="ensemble")
```

**Methods:**

| Method | Description |
|--------|-------------|
| `add_from_traces(traces)` | Load historical traces |
| `add_daily_cost(cost)` | Add a single daily cost value |
| `predict(days_ahead, method)` | Forecast future costs |
| `predict_budget_exhaustion(budget)` | Estimate when budget runs out |

**Methods for `method` parameter:** `"linear"`, `"ema"`, `"ensemble"` (default)

## CostEstimator

```python
from agentcost.estimator import CostEstimator

estimator = CostEstimator()
est = estimator.estimate("gpt-4o", "Hello world", task_type="chat")
```

**Methods:**

| Method | Description |
|--------|-------------|
| `estimate(model, prompt, task_type, max_output_tokens)` | Estimate cost for a prompt |
| `estimate_messages(model, messages, task_type, max_output_tokens)` | Estimate cost for chat messages |
| `compare_models(prompt, models, task_type)` | Compare costs across models |

## CostOptimizer

```python
from agentcost.optimizer import CostOptimizer

optimizer = CostOptimizer()
optimizer.add_traces(traces)
report = optimizer.analyze()
```

## UsageAnalytics

```python
from agentcost.analytics import UsageAnalytics

analytics = UsageAnalytics()
analytics.add_traces(traces)
analytics.summary()
analytics.top_spenders(by="model", limit=10)
analytics.token_efficiency()
analytics.chargeback_report(group_by="project")
```
