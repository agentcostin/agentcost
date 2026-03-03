# CLI Reference

```bash
pip install agentcostin
agentcost --help
```

## Commands

### benchmark

Run a single-model benchmark on real professional tasks.

```bash
agentcost benchmark --model gpt-4o --tasks 10
agentcost benchmark --model llama3:8b --provider ollama --tasks 5
agentcost benchmark --model gpt-4o --tasks 10 --output report.md
```

| Flag | Default | Description |
|------|---------|-------------|
| `--model` | required | Model name |
| `--provider` | `openai` | Provider (openai, anthropic, ollama) |
| `--tasks` | `5` | Number of tasks to run |
| `--output` | — | Save report to file |
| `--ollama-url` | — | Ollama server URL |

### compare

Compare multiple models head-to-head.

```bash
agentcost compare --models "gpt-4o,gpt-4o-mini,claude-sonnet-4-6" --tasks 5
```

| Flag | Default | Description |
|------|---------|-------------|
| `--models` | required | Comma-separated model names |
| `--tasks` | `5` | Tasks per model |

### leaderboard

Show the all-time model leaderboard.

```bash
agentcost leaderboard
```

### dashboard

Launch the cost dashboard web UI.

```bash
agentcost dashboard
agentcost dashboard --port 8100
```

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `0.0.0.0` | Host |
| `--port` | `8500` / `AGENTCOST_PORT` | Port |

### traces

View SDK trace events.

```bash
agentcost traces
agentcost traces --project my-app --summary
agentcost traces --project my-app --model gpt-4o --limit 20
```

| Flag | Default | Description |
|------|---------|-------------|
| `--project` | — | Filter by project |
| `--model` | — | Filter by model |
| `--limit` | `50` | Max traces |
| `--summary` | — | Show summary stats |

### budget

View or set project budgets.

```bash
agentcost budget --project my-app
agentcost budget --project my-app --daily 50 --monthly 1000
```

### plugin

Manage AgentCost plugins.

```bash
agentcost plugin list                    # List installed plugins
agentcost plugin install agentcost-slack-alerts  # Install from PyPI
agentcost plugin create my-plugin        # Scaffold a new plugin
agentcost plugin test                    # Run health checks
```

### gateway

Start the AI Gateway proxy (enterprise).

```bash
agentcost gateway
agentcost gateway --port 8200
```

### info

Show edition, features, and version info.

```bash
agentcost info
```

```
🧮 AgentCost v1.0.0
   Edition: 🌐 Community

   Core Features (MIT):
     ✅ tracing
     ✅ dashboard
     ...

   Enterprise Features (BSL 1.1):
     🔒 auth
     🔒 org
     ...
```
