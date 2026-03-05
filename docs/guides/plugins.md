# Plugin Development

AgentCost uses an 8-slot plugin architecture. Every integration point is swappable via ABC-based plugin classes.

## Plugin Slots

| Slot | Class | Purpose |
|------|-------|---------|
| 1. Notifier | `NotifierPlugin` | Send alerts (Slack, email, webhook, PagerDuty) |
| 2. Policy | `PolicyPlugin` | Custom policy evaluation rules |
| 3. Exporter | `ExporterPlugin` | Export traces to external systems (S3, Snowflake) |
| 4. Provider | `ProviderPlugin` | Cost calculation for custom/new LLM providers |
| 5. Tracker | `TrackerPlugin` | Cost tracking backends (in-memory, DB, Langfuse) |
| 6. Reactor | `ReactorPlugin` | Custom reaction actions (PagerDuty, Jira, Lambda) |
| 7. Runtime | `RuntimePlugin` | Model routing, rate limiting, feature flags |
| 8. Agent | `AgentPlugin` | Agent lifecycle management, workspace config |

## Quick Start

```bash
# Scaffold a new plugin (any of the 8 types)
agentcost plugin create my-slack-alerts --type notifier
agentcost plugin create my-tracker --type tracker
agentcost plugin create budget-router --type runtime
agentcost plugin create lifecycle-manager --type agent
```

This creates a ready-to-develop plugin:

```
agentcost-my-slack-alerts/
├── my_slack_alerts/
│   ├── __init__.py
│   └── plugin.py       # Your plugin class (ABC implementation)
├── pyproject.toml
└── README.md
```

## Writing a Plugin

### Notifier Plugin

```python
from agentcost.plugins import (
    NotifierPlugin, NotifyEvent, SendResult,
    PluginMeta, PluginType, HealthStatus,
)

class SlackNotifier(NotifierPlugin):
    meta = PluginMeta(
        name="my-slack",
        version="1.0.0",
        plugin_type=PluginType.NOTIFIER,
        description="Slack webhook notifications",
    )

    def __init__(self):
        self.webhook_url = ""

    def configure(self, config: dict) -> None:
        self.webhook_url = config.get("webhook_url", "")

    def send(self, event: NotifyEvent) -> SendResult:
        # POST to Slack webhook
        import urllib.request, json
        data = json.dumps({"text": f"[{event.severity}] {event.message}"}).encode()
        req = urllib.request.Request(self.webhook_url, data=data,
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        return SendResult(success=True)

    def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=bool(self.webhook_url))
```

### Tracker Plugin

```python
from agentcost.plugins import TrackerPlugin, PluginMeta, PluginType

class LangfuseTracker(TrackerPlugin):
    meta = PluginMeta(
        name="langfuse-tracker",
        version="1.0.0",
        plugin_type=PluginType.TRACKER,
    )

    def record_trace(self, event: dict) -> None:
        # Send to Langfuse API
        pass

    def get_spend(self, scope: str, scope_id: str, period: str = "month") -> float:
        # Query Langfuse for spend data
        return 0.0
```

### Runtime Plugin

```python
from agentcost.plugins import RuntimePlugin, PluginMeta, PluginType

class BudgetAwareRouter(RuntimePlugin):
    meta = PluginMeta(
        name="budget-router",
        version="1.0.0",
        plugin_type=PluginType.RUNTIME,
    )

    def get_model_override(self, requested_model: str, context: dict) -> str | None:
        # Downgrade to cheaper model when budget is tight
        if context.get("budget_pressure") and requested_model == "gpt-4o":
            return "gpt-4o-mini"
        return None

    def check_rate_limit(self, scope: str, scope_id: str) -> bool:
        return True  # No rate limiting
```

### Agent Plugin

```python
from agentcost.plugins import AgentPlugin, PluginMeta, PluginType

class MyLifecycleManager(AgentPlugin):
    meta = PluginMeta(
        name="my-lifecycle",
        version="1.0.0",
        plugin_type=PluginType.AGENT,
    )

    def __init__(self):
        self._states = {}

    def get_agent_state(self, agent_id: str) -> str:
        return self._states.get(agent_id, "registered")

    def transition(self, agent_id: str, new_state: str, reason: str = "") -> bool:
        self._states[agent_id] = new_state
        return True
```

## Registration

Register your plugin in `pyproject.toml`:

```toml
[project.entry-points."agentcost.plugins"]
my-slack = "my_slack_alerts.plugin:SlackNotifier"
```

## Built-in Plugins

AgentCost ships with 7 built-in plugins that work out of the box:

| Plugin | Slot | Description |
|--------|------|-------------|
| `builtin-slack` | Notifier | Slack webhook notifications |
| `builtin-webhook` | Notifier | Generic HTTP webhook |
| `builtin-email` | Notifier | Email (SMTP stub) |
| `builtin-pagerduty` | Notifier | PagerDuty Events API |
| `builtin-memory-tracker` | Tracker | In-memory cost tracking |
| `builtin-agent-lifecycle` | Agent | Agent state machine |
| `example-pagerduty-reactor` | Reactor | PagerDuty incident management |

## Plugin Module Pattern

For distributing multiple plugins in one package, use `PluginModule`:

```python
from agentcost.plugins import PluginModule

module = PluginModule(
    name="agentcost-my-suite",
    version="1.0.0",
    plugins=[SlackNotifier, PagerDutyNotifier],
    default_config={"webhook_url": ""},
    slot="notifier",
)
```

## Testing & Publishing

```bash
# Health check
agentcost plugin test

# Build and publish
cd agentcost-my-plugin
python -m build
twine upload dist/*
```

Convention: Name your package `agentcost-<name>` on PyPI.
