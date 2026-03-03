# Plugin Development

Extend AgentCost with custom plugins for exporters, alerting, analytics, and more.

## Quick Start

```bash
# Scaffold a new plugin
agentcost plugin create my-plugin
cd agentcost-my-plugin
```

This creates a ready-to-develop plugin structure:

```
agentcost-my-plugin/
├── agentcost_my_plugin/
│   ├── __init__.py
│   └── plugin.py       # Your plugin class
├── pyproject.toml
├── README.md
└── tests/
```

## Plugin Interface

Every plugin implements the `AgentCostPlugin` interface:

```python
from agentcost.plugins import AgentCostPlugin, TraceEvent

class MyPlugin(AgentCostPlugin):
    """My custom AgentCost plugin."""

    name = "my-plugin"
    version = "1.0.0"

    def on_trace(self, event: TraceEvent) -> None:
        """Called for every trace event."""
        if event.cost > 1.0:
            print(f"⚠️ High cost alert: ${event.cost:.4f} on {event.model}")

    def on_startup(self) -> None:
        """Called when the server starts."""
        print(f"🔌 {self.name} plugin loaded")

    def on_shutdown(self) -> None:
        """Called when the server stops."""
        pass
```

## Registration

Register your plugin in `pyproject.toml`:

```toml
[project.entry-points."agentcost.plugins"]
my-plugin = "agentcost_my_plugin.plugin:MyPlugin"
```

## Installation

```bash
# Install from local directory
pip install -e ./agentcost-my-plugin

# Or from PyPI
pip install agentcostin-my-plugin

# Verify
agentcost plugin list
```

## Example: Slack Alerts

```python
from agentcost.plugins import AgentCostPlugin, TraceEvent
import requests

class SlackAlertPlugin(AgentCostPlugin):
    name = "slack-alerts"
    version = "1.0.0"

    def __init__(self):
        self.webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
        self.threshold = float(os.environ.get("COST_ALERT_THRESHOLD", "5.0"))

    def on_trace(self, event: TraceEvent) -> None:
        if event.cost > self.threshold:
            requests.post(self.webhook_url, json={
                "text": f"🚨 High cost alert: ${event.cost:.2f} on {event.model} ({event.project})"
            })
```

## Testing

```bash
# Run plugin health checks
agentcost plugin test

# Run plugin tests
cd agentcost-my-plugin
pytest tests/ -v
```

## Publishing

```bash
cd agentcost-my-plugin
python -m build
twine upload dist/*
```

Convention: Name your package `agentcost-<name>` on PyPI.

## Community Plugins

| Plugin | Description |
|--------|-------------|
| `agentcost-slack-alerts` | Slack notifications for cost anomalies |
| `agentcost-s3-archive` | Archive traces to AWS S3 |
| `agentcost-cost-limiter` | Hard cost limits per project |

Want to add yours? Open a [Plugin Request](https://github.com/agentcostin/agentcost/issues/new?template=plugin_request.yml).
