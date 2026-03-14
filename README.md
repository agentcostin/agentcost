<p align="center">
  <h1 align="center">🧮 AgentCost</h1>
  <p align="center">
    <strong>Track, control, and optimize your AI spending.</strong>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/agentcostin/"><img src="https://img.shields.io/pypi/v/agentcostin?color=blue" alt="PyPI"></a>
    <a href="https://www.npmjs.com/package/@agentcost/sdk"><img src="https://img.shields.io/npm/v/@agentcost/sdk?color=green" alt="npm"></a>
    <a href="https://hub.docker.com/r/agentcost/agentcost"><img src="https://img.shields.io/docker/pulls/agentcost/agentcost?color=blue&label=docker%20pulls" alt="Docker Hub"></a>
    <a href="https://github.com/agentcost/agentcost/actions"><img src="https://img.shields.io/github/actions/workflow/status/agentcost/agentcost/ci.yml?branch=main" alt="CI"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="License"></a>
    <a href="https://discord.gg/agentcost"><img src="https://img.shields.io/discord/000000000?color=7289da&label=discord" alt="Discord"></a>
  </p>
</p>

> **[Watch the 2-min demo →](https://www.youtube.com/watch?v=T1i2aFB5New)** | **[Live demo →](https://demo.agentcost.in)**

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

The dashboard gives you nine intelligence views:

| View               | What it shows                                                          |
| ------------------ | ---------------------------------------------------------------------- |
| **Overview**       | Total spend, call volume, error rate, cost-over-time charts            |
| **Cost Breakdown** | Spend by model, project, and provider with trend analysis              |
| **Forecasting**    | Predicted costs for next 7/14/30 days, budget exhaustion alerts        |
| **Optimizer**      | Model downgrade recommendations with estimated savings                 |
| **Analytics**      | Token efficiency, top spenders, chargeback reports                     |
| **Estimator**      | Pre-call cost estimation across 2,610+ models                          |
| **Models**         | Search/filter all models by provider, tier, cost range, context window |
| **Prompts**        | Version, deploy, and track cost of system prompts per version          |
| **Feedback**       | User thumbs up/down on traces, quality per model and prompt version    |

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

## Prompt Management

Store, version, deploy, and track the cost of your system prompts — with automatic cost analytics per version.

```python
from agentcost.sdk import get_prompt, trace
from openai import OpenAI

# Create and version prompts
from agentcost.prompts import get_prompt_service
svc = get_prompt_service()
svc.create_prompt("support-bot", content="You are a helpful agent for {{product}}.")
svc.create_version("support-bot", content="You are a concise agent for {{product}}. Be brief.")
svc.deploy("support-bot", version=2, environment="production")

# Use in your app — prompt version is tagged on every trace
prompt = get_prompt("support-bot", environment="production", variables={"product": "AgentCost"})

client = trace(OpenAI(), project="support",
               prompt_id=prompt["prompt_id"], prompt_version=prompt["version"])
response = client.chat.completions.create(
    model=prompt.get("model") or "gpt-4.1",
    messages=[{"role": "system", "content": prompt["content"]},
              {"role": "user", "content": "How do I set a budget?"}]
)
```

Every prompt change creates an immutable version. Deploy V2 to staging while V1 runs in production. Compare cost per call between versions to answer *"did the new prompt cost more or less?"* See the [Prompt Management Guide](https://agentcost.in/docs/guides/prompts/).

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
                    └─────┬──────────┬──────────┬───────┬────────┘
                          │          │          │       │
                    ┌─────▼──┐ ┌─────▼──┐ ┌────▼───┐ ┌─▼──────┐
                    │ Python │ │ Node.js│ │ Proxy  │ │  OTel  │
                    │  SDK   │ │  SDK   │ │Gateway │ │Ingest  │
                    └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘
                        │          │          │          │
                        └──────────┼──────────┼──────────┘
                                   │          │
                    ┌──────────────▼──────────▼───────┐
                    │     AgentCost API Server         │
                    │         (FastAPI)                │
                    ├──────────────────────────────────┤
                    │  Traces │ Prompts  │ Feedback    │
                    │  Budget │ Forecast │ Optimizer   │
                    ├──────────────────────────────────┤
                    │   SQLite / PostgreSQL             │
                    └──────────────┬───────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
        ┌─────▼─────┐     ┌──────▼──────┐     ┌──────▼──────┐
        │ Dashboard  │     │   OTel /    │     │  Prometheus │
        │  (React)   │     │   Grafana   │     │   /metrics  │
        └────────────┘     └─────────────┘     └─────────────┘
```

## AI Gateway (with Semantic Caching)

Zero-instrumentation cost tracking. Point your agents at the gateway instead of the provider:

```python
from openai import OpenAI

# Just change the base URL — zero code changes to your agent
client = OpenAI(
    base_url="http://localhost:8200/v1",
    api_key="ac_myproject_xxx",
)

# Every call is tracked, policy-checked, and cached automatically
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
    temperature=0,  # deterministic calls are cached
)
```

The gateway provides automatic **response caching** for deterministic requests (temperature ≤ 0.2), with full cost savings tracking visible in the dashboard. Cache stats include hit rate, total cost saved, per-project and per-model breakdown.

```bash
# Start the gateway
python -m agentcost.gateway --port 8200

# Check cache performance
curl http://localhost:8200/v1/gateway/cache/stats
```

| Feature                   | Description                                                                       |
| ------------------------- | --------------------------------------------------------------------------------- |
| **Response Caching**      | Exact-match + semantic caching — similar prompts hit the cache, not just identical ones |
| **Cost Savings Tracking** | Per-request cost saved, aggregated by project and model                           |
| **Policy Enforcement**    | Pre-call policy checks before forwarding to providers                             |
| **Provider Failover**     | Automatic routing across OpenAI, Anthropic, Ollama                                |
| **Rate Limiting**         | Per-project RPM limits with token-bucket algorithm                                |

## Exporters

## Exporters & OTel Collector

Send cost data **out** to your observability stack, or receive spans **in** from your existing OTel instrumentation:

```python
# Export to OpenTelemetry (Datadog, Jaeger, Grafana Tempo)
from agentcost.otel import install_otel_exporter
install_otel_exporter(endpoint="http://localhost:4317")

# Prometheus (Grafana, AlertManager)
# Enabled automatically at /metrics when server is running
```

**Already using Traceloop, OpenLLMetry, or OpenInference?** Just point your OTel exporter at AgentCost — no re-instrumentation needed:

```bash
# Zero code changes — just set the endpoint
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8100

# AgentCost accepts OTLP/HTTP spans on POST /v1/traces
# LLM spans are auto-detected, cost is auto-calculated from 2,610+ model pricing
# Non-LLM spans (HTTP, DB, etc.) are silently skipped
```

## MCP Server (Model Context Protocol)

AgentCost runs as an MCP server — Claude Desktop, Cursor, VS Code, and any MCP-compatible agent can query your cost data, check budgets, get optimization recommendations, and manage prompts directly.

```json
// Claude Desktop or Cursor config
{
  "mcpServers": {
    "agentcost": {
      "command": "python",
      "args": ["-m", "agentcost.mcp"]
    }
  }
}
```

14 tools available: cost summary, cost by model/project, search traces, check/set budgets, optimization recommendations, cost estimation, feedback, prompt resolution, and more. See the [MCP Server Guide](https://agentcost.in/docs/guides/mcp-server/).

## Plugin System

Extend AgentCost with plugins:

```bash
# Install community plugins
agentcost plugin install agentcost-slack-alerts
agentcost plugin install agentcost-s3-archive

# Create your own plugin
agentcost plugin create my-plugin
```

Plugins can export data, add alerting, create custom views, and more. See the [Plugin Development Guide](https://agentcost.in/docs/guides/plugins/).

## TypeScript SDK

```bash
npm install @agentcost/sdk
```

```typescript
import { AgentCost } from "@agentcost/sdk";

const ac = new AgentCost({
    project: "my-app",
    apiUrl: "http://localhost:8500",
});

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

### Docker Hub (Quickest)

```bash
# One command — pulls from Docker Hub, runs with SQLite, dashboard on :8100
docker run -d -p 8100:8100 -v agentcost_data:/data agentcost/agentcost:latest

# Seed demo data
curl -X POST http://localhost:8100/api/seed -H "Content-Type: application/json" -d '{"days": 14}'

# → Open http://localhost:8100
```

> **Live Demo**: See AgentCost in action at [demo.agentcost.in](https://demo.agentcost.in) — no install required.

### Community Edition (From Source)

```bash
git clone https://github.com/agentcost/agentcost.git
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

| Feature                | Description                                              |
| ---------------------- | -------------------------------------------------------- |
| **SSO/SAML**           | Any OIDC/SAML provider (Okta, Auth0, Azure AD, Keycloak) |
| **Organizations**      | Multi-tenant team management with roles                  |
| **Budget Enforcement** | Cost centers, allocations, pre-call validation           |
| **Policy Engine**      | JSON rules: block models, cap costs, require approval    |
| **Approval Workflows** | Human-in-the-loop for policy exceptions                  |
| **Notifications**      | Slack, email, webhook, PagerDuty alerts                  |
| **Agent Scorecards**   | Monthly agent grading (A–F) with recommendations         |
| **Audit Log**          | Hash-chained compliance trail                            |
| **Anomaly Detection**  | ML-based cost/latency spike detection                    |
| **AI Gateway**         | Transparent LLM proxy with policy enforcement            |

Enterprise features are source-available under BSL 1.1. See [enterprise/LICENSE](enterprise/LICENSE).

→ [Contact us](mailto:open@agentcost.in) or [read the docs](https://agentcost.in/docs/enterprise/overview/)

## Configuration

| Variable                 | Default       | Description                                                   |
| ------------------------ | ------------- | ------------------------------------------------------------- |
| `AGENTCOST_PORT`         | `8500`        | Server port                                                   |
| `AGENTCOST_EDITION`      | `auto`        | `community`, `enterprise`, or `auto`                          |
| `AGENTCOST_AUTH_ENABLED` | `false`       | Enable SSO (enterprise)                                       |
| `AGENTCOST_DB_URL`       | SQLite        | PostgreSQL connection string                                  |
| `OIDC_ISSUER_URL`        | —             | OIDC provider URL (e.g., https://auth.example.com/realms/app) |
| `OIDC_CLIENT_ID`         | agentcost-api | OIDC client ID                                                |
| `OIDC_CLIENT_SECRET`     | —             | OIDC client secret                                            |

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions.

```bash
git clone https://github.com/agentcost/agentcost.git
cd agentcost
pip install -e ".[dev,server]"
pytest tests/ -v
```

## License

- **Core** (agentcost SDK, dashboard, CLI, forecasting, optimizer, analytics, estimator, plugins): [MIT](LICENSE)
- **Enterprise** (auth, org, budgets, policies, notifications, anomaly, gateway): [BSL 1.1](enterprise/LICENSE) — converts to Apache 2.0 after 3 years

---

<p align="center">
  <a href="https://agentcost.in/docs/">Documentation</a> ·
  <a href="https://github.com/agentcost/agentcost/issues">Issues</a> ·
  <a href="https://discord.gg/agentcost">Discord</a> ·
  <a href="https://twitter.com/agentcost">Twitter</a>
</p>
