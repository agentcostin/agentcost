<p align="center">
  <h1 align="center">🧮 AgentCost</h1>
  <p align="center">
    <strong>Track, control, and optimize your AI spending.</strong>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/agentcostin/"><img src="https://img.shields.io/pypi/v/agentcostin?color=blue" alt="PyPI"></a>
    <a href="https://www.npmjs.com/package/@agentcost/sdk"><img src="https://img.shields.io/npm/v/@agentcost/sdk?color=green" alt="npm"></a>
    <a href="https://github.com/agentcostin/agentcost/actions"><img src="https://img.shields.io/github/actions/workflow/status/agentcostin/agentcost/ci.yml?branch=main" alt="CI"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="License"></a>
    <a href="https://discord.gg/agentcost"><img src="https://img.shields.io/discord/000000000?color=7289da&label=discord" alt="Discord"></a>
  </p>
</p>

---

**AI costs are invisible, unpredictable, and uncontrolled.** Teams deploy agents across OpenAI, Anthropic, Google, and open-source models with no idea what they're actually spending — or whether cheaper models would work just as well. AgentCost fixes that with a vendored pricing database of **2,610+ models from 40+ providers**, automatic cost-tier classification, and intelligent model routing.

## Quickstart

```bash
pip install agentcostin
```

```python
from agentcost.sdk import trace
from openai import OpenAI

client = trace(OpenAI(), project="my-app")

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)

# Every call is now tracked. Open the dashboard:
# agentcost dashboard
# → http://localhost:8500
```

That's it. **One line** wraps your client, and every LLM call is tracked with model, tokens, cost, latency, and status.

## Dashboard

```bash
# Seed demo data and launch
curl -X POST http://localhost:8500/api/seed -H "Content-Type: application/json" -d '{"days": 14}'
agentcost dashboard
```

The dashboard gives you seven intelligence views:

| View | What it shows |
|------|---------------|
| **Overview** | Total spend, call volume, error rate, cost-over-time charts |
| **Cost Breakdown** | Spend by model, project, and provider with trend analysis |
| **Forecasting** | Predicted costs for next 7/14/30 days, budget exhaustion alerts |
| **Optimizer** | Model downgrade recommendations with estimated savings |
| **Analytics** | Token efficiency, top spenders, chargeback reports |
| **Estimator** | Pre-call cost estimation across 2,610+ models |
| **Models** | Search/filter all models by provider, tier, cost range, context window |

## Framework Support

AgentCost integrates with the frameworks you already use:

```python
# LangChain
from agentcost.sdk.integrations import langchain_callback
chain.invoke(input, config={"callbacks": [langchain_callback("my-project")]})

# CrewAI
from agentcost.sdk.integrations import crewai_callback
crew = Crew(agents=[...], callbacks=[crewai_callback("my-project")])

# AutoGen
from agentcost.sdk.integrations import autogen_callback
agent = AssistantAgent("assistant", llm_config={..., "callbacks": [autogen_callback("my-project")]})

# LlamaIndex
from agentcost.sdk.integrations import llamaindex_callback
service_context = ServiceContext.from_defaults(callback_manager=llamaindex_callback("my-project"))
```

## CLI

```bash
# Benchmark models on real professional tasks
agentcost benchmark --model gpt-4o --tasks 10

# Compare models head-to-head
agentcost compare --models "gpt-4o,gpt-4o-mini,claude-sonnet-4-6" --tasks 5

# View the leaderboard
agentcost leaderboard

# Check traces and budgets
agentcost traces --project my-app --summary
agentcost budget --project my-app --daily 50 --monthly 1000

# Manage plugins
agentcost plugin list
agentcost plugin install agentcost-slack-alerts
```

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │              Your Application               │
                    └─────┬──────────┬──────────┬────────────────┘
                          │          │          │
                    ┌─────▼──┐ ┌─────▼──┐ ┌────▼───┐
                    │ Python │ │ Node.js│ │ Proxy  │
                    │  SDK   │ │  SDK   │ │Gateway │
                    └───┬────┘ └───┬────┘ └───┬────┘
                        │          │          │
                        └──────────┼──────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │     AgentCost API Server     │
                    │         (FastAPI)            │
                    ├─────────────────────────────┤
                    │  Traces │ Forecasts │ Optim  │
                    │  Budget │ Analytics │ Estim  │
                    ├─────────────────────────────┤
                    │   SQLite / PostgreSQL        │
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
        ┌─────▼─────┐     ┌──────▼──────┐     ┌──────▼──────┐
        │ Dashboard  │     │   OTel /    │     │  Prometheus │
        │  (React)   │     │   Grafana   │     │   /metrics  │
        └────────────┘     └─────────────┘     └─────────────┘
```

## Exporters

Send cost data to your existing observability stack:

```python
# OpenTelemetry (Datadog, Jaeger, Grafana Tempo)
from agentcost.otel import install_otel_exporter
install_otel_exporter(endpoint="http://localhost:4317")

# Prometheus (Grafana, AlertManager)
# Enabled automatically at /metrics when server is running
```

## Plugin System

Extend AgentCost with plugins:

```bash
# Install community plugins
agentcost plugin install agentcost-slack-alerts
agentcost plugin install agentcost-s3-archive

# Create your own plugin
agentcost plugin create my-plugin
```

Plugins can export data, add alerting, create custom views, and more. See the [Plugin Development Guide](https://docs.agentcost.in/plugins/).

## TypeScript SDK

```bash
npm install @agentcost/sdk
```

```typescript
import { AgentCost } from "@agentcost/sdk";

const ac = new AgentCost({ project: "my-app", apiUrl: "http://localhost:8500" });

// Trace any LLM call
const traced = await ac.trace({
  model: "gpt-4o",
  inputTokens: 150,
  outputTokens: 80,
  cost: 0.0035,
  latencyMs: 450,
});
```

## Self-Hosting

### Community Edition (Quick Start)

```bash
git clone https://github.com/agentcostin/agentcost.git
cd agentcost
docker compose -f docker-compose.dev.yml up
# → http://localhost:8100
```

### Enterprise Edition

```bash
# Full stack: PostgreSQL + SSO + API
docker compose up -d

# Configure SSO
export AGENTCOST_EDITION=enterprise
export AGENTCOST_AUTH_ENABLED=true
export KEYCLOAK_URL=http://localhost:8180
```

## Enterprise Features

For teams and organizations that need governance:

| Feature | Description |
|---------|-------------|
| **SSO/SAML** | Any OIDC/SAML provider (Okta, Auth0, Azure AD, Keycloak) |
| **Organizations** | Multi-tenant team management with roles |
| **Budget Enforcement** | Cost centers, allocations, pre-call validation |
| **Policy Engine** | JSON rules: block models, cap costs, require approval |
| **Approval Workflows** | Human-in-the-loop for policy exceptions |
| **Notifications** | Slack, email, webhook, PagerDuty alerts |
| **Agent Scorecards** | Monthly agent grading (A–F) with recommendations |
| **Audit Log** | Hash-chained compliance trail |
| **Anomaly Detection** | ML-based cost/latency spike detection |
| **AI Gateway** | Transparent LLM proxy with policy enforcement |

Enterprise features are source-available under BSL 1.1. See [enterprise/LICENSE](enterprise/LICENSE).

→ [Contact us](mailto:open@agentcost.in) or [read the docs](https://docs.agentcost.in/enterprise/)

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTCOST_PORT` | `8500` | Server port |
| `AGENTCOST_EDITION` | `auto` | `community`, `enterprise`, or `auto` |
| `AGENTCOST_AUTH_ENABLED` | `false` | Enable SSO (enterprise) |
| `AGENTCOST_DB_URL` | SQLite | PostgreSQL connection string |
| `OIDC_ISSUER_URL` | — | OIDC provider URL (e.g., https://auth.example.com/realms/app) |
| `OIDC_CLIENT_ID` | agentcost-api | OIDC client ID |
| `OIDC_CLIENT_SECRET` | — | OIDC client secret |

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions.

```bash
git clone https://github.com/agentcostin/agentcost.git
cd agentcost
pip install -e ".[dev,server]"
pytest tests/ -v
```

## License

- **Core** (agentcost SDK, dashboard, CLI, forecasting, optimizer, analytics, estimator, plugins): [MIT](LICENSE)
- **Enterprise** (auth, org, budgets, policies, notifications, anomaly, gateway): [BSL 1.1](enterprise/LICENSE) — converts to Apache 2.0 after 3 years

---

<p align="center">
  <a href="https://docs.agentcost.in">Documentation</a> ·
  <a href="https://github.com/agentcostin/agentcost/issues">Issues</a> ·
  <a href="https://discord.gg/agentcost">Discord</a> ·
  <a href="https://twitter.com/agentcost">Twitter</a>
</p>
