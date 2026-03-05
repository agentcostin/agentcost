# Getting Started

Get AgentCost running in under 60 seconds.

## Installation

=== "pip"

    ```bash
    pip install agentcostin
    ```

=== "pip (with server)"

    ```bash
    pip install agentcostin[server]
    ```

=== "Docker"

    ```bash
    git clone https://github.com/agentcostin/agentcost.git
    cd agentcost
    docker compose -f docker-compose.dev.yml up
    ```

=== "From source"

    ```bash
    git clone https://github.com/agentcostin/agentcost.git
    cd agentcost
    pip install -e ".[dev,server]"
    ```

## First Trace

Wrap your OpenAI client with `trace()`:

```python
from agentcost.sdk import trace
from openai import OpenAI

client = trace(OpenAI(), project="my-app")

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

Every call through `client` is now tracked automatically.

## Launch the Dashboard

```bash
agentcost dashboard
```

Open [http://localhost:8500](http://localhost:8500) to see your cost data.

!!! tip "Seed demo data"
    To see the dashboard with data immediately:
    ```bash
    curl -X POST http://localhost:8500/api/seed \
      -H "Content-Type: application/json" \
      -d '{"days": 14, "clear": true}'
    ```

## Configuration

AgentCost is configured via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTCOST_PORT` | `8500` | Server port |
| `AGENTCOST_EDITION` | `auto` | `community`, `enterprise`, or `auto` |
| `AGENTCOST_DB_URL` | SQLite | PostgreSQL URL for enterprise |
| `AGENTCOST_AUTH_ENABLED` | `false` | Enable SSO (enterprise only) |

## Check Your Edition

```bash
agentcost info
```

```
🧮 AgentCost v1.0.0
   Edition: 🌐 Community

   Core Features (MIT):
     ✅ tracing
     ✅ dashboard
     ✅ forecasting
     ✅ optimizer
     ✅ analytics
     ✅ estimator
     ✅ plugins
     ✅ cli
     ✅ otel_export
```

## Next Steps

- [Core Concepts](concepts.md) — Understand traces, projects, agents, sessions
- [Dashboard Guide](guides/dashboard.md) — Tour of all 7 intelligence views
- [Python SDK Reference](reference/python-sdk.md) — Full API documentation
- [Framework Guides](guides/langchain.md) — LangChain, CrewAI, AutoGen, LlamaIndex
