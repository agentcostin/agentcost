# User Feedback on Traces

AgentCost lets you attach thumbs-up/down feedback to any LLM trace. This connects cost data to quality data — the missing link for knowing whether a cheaper model actually works well enough.

## Why Feedback Matters for Cost Governance

Cost optimization without quality signals is dangerous. If you switch from GPT-4.1 to GPT-4.1-mini to save money, you need to know whether users notice the difference. Feedback gives you that signal:

- **Per-model quality**: "GPT-4.1 gets 92% positive, GPT-4.1-mini gets 78% — the 80% cost savings come with a 14% quality drop"
- **Per-prompt-version quality**: "V3 of support-bot gets 95% positive vs V2's 82%"
- **Cost-per-positive response**: "GPT-4.1-mini costs $0.002 per positive-rated response vs $0.008 for GPT-4.1 — 4x more cost-efficient despite the quality gap"

## Quick Start

### Submit feedback via API

```bash
# Thumbs up
curl -X POST http://localhost:8100/api/feedback \
  -H "Content-Type: application/json" \
  -d '{"trace_id": "abc-123", "score": 1, "comment": "Accurate and helpful"}'

# Thumbs down
curl -X POST http://localhost:8100/api/feedback \
  -H "Content-Type: application/json" \
  -d '{"trace_id": "abc-123", "score": -1, "comment": "Hallucinated a date", "tags": ["hallucination"]}'
```

### Submit feedback via Python

```python
from agentcost.feedback import get_feedback_service

svc = get_feedback_service()

# Simple thumbs up
svc.submit("trace-abc-123", score=1)

# Detailed feedback
svc.submit(
    "trace-abc-123",
    score=-1,
    comment="Response was too long and included incorrect pricing",
    source="human-review",
    user_id="reviewer-jane",
    tags=["verbose", "inaccurate"],
)
```

### Score values

| Score | Meaning | Use when |
|:-----:|---------|----------|
| **1** | Positive / thumbs up | Response was correct, helpful, or met expectations |
| **0** | Neutral | Response was acceptable but not noteworthy |
| **-1** | Negative / thumbs down | Response was wrong, unhelpful, or harmful |

## Analytics

### Quality by model

See which models produce the best results in your application:

```bash
curl http://localhost:8100/api/feedback/quality/models
```

```json
[
  {
    "model": "gpt-4.1",
    "total_feedback": 240,
    "positive_pct": 92.1,
    "negative_pct": 4.2,
    "avg_score": 0.879,
    "avg_cost": 0.0034,
    "cost_per_positive": 0.00369
  },
  {
    "model": "gpt-4.1-mini",
    "total_feedback": 180,
    "positive_pct": 78.3,
    "negative_pct": 12.2,
    "avg_score": 0.661,
    "avg_cost": 0.0006,
    "cost_per_positive": 0.000766
  }
]
```

The `cost_per_positive` metric tells you the real efficiency story: GPT-4.1-mini costs 5x less per positive-rated response despite the lower quality percentage.

### Quality by prompt version

Track whether prompt changes improve or degrade quality:

```bash
curl http://localhost:8100/api/feedback/quality/prompt/support-bot
```

```json
[
  {"version": 1, "total_feedback": 50, "positive_pct": 82.0, "avg_score": 0.64},
  {"version": 2, "total_feedback": 120, "positive_pct": 91.7, "avg_score": 0.833},
  {"version": 3, "total_feedback": 30, "positive_pct": 96.7, "avg_score": 0.933}
]
```

### Trace-level score

Get the aggregated score for a single trace:

```bash
curl http://localhost:8100/api/feedback/trace/abc-123/score
```

```json
{
  "trace_id": "abc-123",
  "total": 5,
  "positive": 4,
  "negative": 1,
  "neutral": 0,
  "score": 0.6
}
```

## Feedback Sources

Use the `source` field to distinguish where feedback comes from:

| Source | Description |
|--------|-------------|
| `user` | End-user thumbs up/down in your application |
| `human-review` | Manual review by a team member |
| `automated` | Automated quality checks (regex, format validation) |
| `eval` | LLM-as-judge or evaluation pipeline |

```python
# Automated quality check
if "I don't know" in response.content:
    svc.submit(trace_id, score=-1, source="automated", tags=["refusal"])
```

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/feedback` | Submit feedback on a trace |
| `GET` | `/api/feedback` | List feedback (filter by project, model, score, source) |
| `GET` | `/api/feedback/summary` | Overall feedback stats |
| `GET` | `/api/feedback/quality/models` | Quality breakdown by model |
| `GET` | `/api/feedback/quality/model/{model}` | Quality for a specific model |
| `GET` | `/api/feedback/quality/prompt/{prompt_id}` | Quality per prompt version |
| `GET` | `/api/feedback/trace/{trace_id}` | All feedback for a trace |
| `GET` | `/api/feedback/trace/{trace_id}/score` | Aggregated score |
| `DELETE` | `/api/feedback/{id}` | Delete feedback |

## Best Practices

**Collect feedback close to the user.** Add a thumbs up/down button next to every LLM response in your UI. The closer to the interaction, the higher the response rate.

**Use tags to categorize failures.** Tags like `hallucination`, `too-long`, `off-topic`, `formatting` help you identify patterns in negative feedback.

**Combine with prompt versioning.** When you deploy a new prompt version, monitor the `quality/prompt/{id}` endpoint to catch quality regressions before they accumulate.

**Set up automated feedback for known failure patterns.** If a response matches a known bad pattern (refusal, empty response, format violation), submit automated negative feedback so it shows up in quality metrics immediately.

**Review cost-per-positive regularly.** The cheapest model isn't always the most cost-efficient — a slightly more expensive model with much higher quality can have a lower cost per successful response.
