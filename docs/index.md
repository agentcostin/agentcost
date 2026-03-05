# AgentCost

**Track, control, and optimize your AI spending.**

AgentCost is an open-source cost governance platform for AI agents. It gives you visibility into what your LLM calls actually cost, forecasts future spending, and recommends cheaper models that deliver equivalent quality.

## Why AgentCost?

Teams deploying AI agents across OpenAI, Anthropic, Google, and open-source providers face three problems:

1. **Invisible costs** — No centralized view of what each model, project, or agent is spending
2. **Unpredictable growth** — Costs spike with no warning as usage scales
3. **No optimization signal** — No way to know if a cheaper model would work just as well

AgentCost solves all three with a single `pip install`.

## Quick Start

```bash
pip install agentcostin
```

```python
from agentcost.sdk import trace
from openai import OpenAI

# One line wraps your client
client = trace(OpenAI(), project="my-app")

# Use it exactly as before — costs are tracked automatically
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

```bash
# Launch the dashboard
agentcost dashboard
# → http://localhost:8500
```

That's it. Every LLM call is now tracked with model, tokens, cost, latency, and status.

## What You Get

| Feature | Description |
|---------|-------------|
| **Tracing SDK** | Wrap any OpenAI/Anthropic/LiteLLM client in one line |
| **2,610+ Model Pricing** | Vendored pricing from 40+ providers, auto-synced weekly |
| **Dashboard** | 7-tab web UI with real-time model search across all providers |
| **Cost Intelligence** | Tier classification, complexity routing, budget gates, token analysis |
| **Cost Forecasting** | Predict next 7/14/30 days of spending |
| **Cost Optimizer** | Model downgrade recommendations with savings estimates |
| **Prompt Estimator** | Pre-call cost estimation across 2,610+ models |
| **Reactions Engine** | YAML-driven event reactions (budget alerts, auto-suspend, webhooks) |
| **8-Slot Plugin System** | Notifier, Policy, Exporter, Provider, Tracker, Reactor, Runtime, Agent |
| **Framework Integrations** | LangChain, CrewAI, AutoGen, LlamaIndex |
| **Exporters** | OpenTelemetry, Prometheus, Grafana |
| **CLI** | Benchmark, compare, trace, budget management |
| **TypeScript SDK** | Full Node.js/Deno/Bun support |

## Editions

AgentCost comes in two editions:

**Community (MIT)** — Everything a developer or small team needs. SDK, dashboard, forecasting, optimizer, analytics, estimator, plugins, CLI, exporters.

**Enterprise (BSL 1.1)** — Adds governance for organizations: SSO/SAML, multi-tenant orgs, budget enforcement, policy engine, approval workflows, notifications, agent scorecards, audit logs, anomaly detection, AI gateway.

See [Enterprise Features](enterprise/overview.md) for details.

## Next Steps

- [Installation & Configuration](getting-started.md)
- [Core Concepts](concepts.md)
- [Dashboard Guide](guides/dashboard.md)
- [Python SDK Reference](reference/python-sdk.md)
- [REST API Reference](reference/api.md)
