# Dashboard Guide

The AgentCost dashboard provides seven intelligence views for understanding and controlling your AI costs.

## Launching the Dashboard

```bash
agentcost dashboard
# → http://localhost:8500
```

Or with custom port:

```bash
AGENTCOST_PORT=8100 agentcost dashboard
```

## Seeding Demo Data

To explore the dashboard immediately:

```bash
curl -X POST http://localhost:8500/api/seed \
  -H "Content-Type: application/json" \
  -d '{"days": 14, "clear": true}'
```

Or use the script:

```bash
python scripts/seed_sample_data.py --days 14 --clear
```

## Views

### Overview

The landing page shows key metrics at a glance: total spend, call volume, error rate, and cost-over-time charts. Use the project filter to drill into specific applications.

### Cost Breakdown

Detailed spend analysis by model, project, and provider. Shows which models consume the most budget and identifies cost trends over time.

### Forecasting

Predicts future costs using three methods:

- **Linear** — Simple trend extrapolation
- **EMA** — Exponential moving average (adapts to recent changes faster)
- **Ensemble** — Weighted combination (recommended)

Includes budget exhaustion prediction: "At current rates, your $1,000 monthly budget will be exhausted by March 15th."

### Optimizer

Analyzes your usage patterns and recommends model substitutions:

- Which calls use expensive models for simple tasks?
- What savings would you get from switching `gpt-4o` → `gpt-4o-mini` for classification?
- Overall efficiency score for each project

### Analytics

Deep-dive analysis:

- **Token efficiency** — Cost per 1K tokens by model
- **Top spenders** — Highest-cost agents, projects, or models
- **Error analysis** — Error rates by model and type
- **Chargeback reports** — Cost allocation by team/project

### Estimator

Pre-call cost estimation. Enter a prompt and compare estimated costs across 2,610+ models before making expensive API calls.

### Models Explorer

Search and filter the full model pricing database:

- **Real-time search** by model name across 2,610+ models
- **Filter by provider** — OpenAI, Anthropic, Google, Groq, DeepSeek, Bedrock, Azure, and 30+ more
- **Filter by tier** — Economy, Standard, Premium, Free
- **Filter by cost range** — Set max input cost per 1M tokens
- **Filter by context window** — Minimum context size
- **Click any model** for detailed pricing, tier classification, and capability info (vision, tools)

The Models Explorer is powered by the vendored pricing API at `/api/models`, which serves data from the same 2,610-model database used for cost calculation.

## API Endpoints

All dashboard views are powered by REST endpoints you can use directly:

| Endpoint | Description |
|----------|-------------|
| `GET /api/summary` | Overview metrics |
| `GET /api/cost/by-model` | Cost breakdown by model |
| `GET /api/cost/over-time` | Time-series cost data |
| `GET /api/forecast/{project}` | Cost predictions |
| `GET /api/optimizer/{project}` | Optimization recommendations |
| `GET /api/analytics/{project}/summary` | Usage analytics |
| `POST /api/estimate` | Cost estimation |

See the [API Reference](../reference/api.md) for full documentation.
