"""
Plugin scaffolding generator — creates ready-to-develop plugin projects.

Usage: agentcost plugin create my-notifier --type notifier
"""
from __future__ import annotations

import os
from pathlib import Path


PLUGIN_TEMPLATES = {
    "notifier": '''"""
{name} — AgentCost Notifier Plugin

Sends notifications to {name}.
"""
from agentcost.plugins import (
    NotifierPlugin, NotifyEvent, SendResult, PluginMeta, PluginType, HealthStatus,
)


class {class_name}(NotifierPlugin):
    meta = PluginMeta(
        name="{pkg_name}",
        version="0.1.0",
        plugin_type=PluginType.NOTIFIER,
        description="Send AgentCost alerts to {name}",
        config_schema={{
            "webhook_url": {{"type": "string", "required": True}},
        }},
    )

    def __init__(self):
        self.webhook_url: str = ""

    def configure(self, config: dict) -> None:
        self.webhook_url = config.get("webhook_url", "")

    def send(self, event: NotifyEvent) -> SendResult:
        # TODO: Implement your notification logic here
        import urllib.request, json
        data = json.dumps({{
            "text": f"[{{event.severity.upper()}}] {{event.title}}\\n{{event.message}}"
        }}).encode()
        try:
            req = urllib.request.Request(self.webhook_url, data=data,
                headers={{"Content-Type": "application/json"}}, method="POST")
            urllib.request.urlopen(req, timeout=5)
            return SendResult(success=True)
        except Exception as e:
            return SendResult(success=False, message=str(e))

    def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=bool(self.webhook_url),
            message="ok" if self.webhook_url else "webhook_url not configured")
''',

    "policy": '''"""
{name} — AgentCost Policy Plugin
"""
from agentcost.plugins import (
    PolicyPlugin, PolicyContext, PolicyDecision, PluginMeta, PluginType,
)


class {class_name}(PolicyPlugin):
    meta = PluginMeta(
        name="{pkg_name}",
        version="0.1.0",
        plugin_type=PluginType.POLICY,
        description="Custom policy rule: {name}",
    )

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        # TODO: Implement your policy logic here
        if ctx.estimated_cost > 1.0:
            return PolicyDecision(allowed=False, reason="Cost exceeds $1.00 limit",
                action="require_approval")
        return PolicyDecision(allowed=True)
''',

    "exporter": '''"""
{name} — AgentCost Exporter Plugin
"""
import json
from agentcost.plugins import (
    ExporterPlugin, PluginMeta, PluginType,
)


class {class_name}(ExporterPlugin):
    meta = PluginMeta(
        name="{pkg_name}",
        version="0.1.0",
        plugin_type=PluginType.EXPORTER,
        description="Export traces to {name}",
    )

    def export(self, traces: list[dict], fmt: str = "json") -> bytes:
        # TODO: Implement your export logic (S3, Snowflake, CSV, etc.)
        if fmt == "csv":
            import csv, io
            buf = io.StringIO()
            if traces:
                w = csv.DictWriter(buf, fieldnames=traces[0].keys())
                w.writeheader()
                w.writerows(traces)
            return buf.getvalue().encode()
        return json.dumps(traces, indent=2).encode()

    def supported_formats(self) -> list[str]:
        return ["json", "csv"]
''',

    "provider": '''"""
{name} — AgentCost Provider Plugin
"""
from agentcost.plugins import (
    ProviderPlugin, PluginMeta, PluginType,
)


class {class_name}(ProviderPlugin):
    meta = PluginMeta(
        name="{pkg_name}",
        version="0.1.0",
        plugin_type=PluginType.PROVIDER,
        description="Cost calculation for {name} models",
    )

    # TODO: Add your model pricing
    PRICING = {{
        "my-model-large": {{"input": 1.00, "output": 3.00}},
        "my-model-small": {{"input": 0.10, "output": 0.30}},
    }}

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float | None:
        p = self.PRICING.get(model)
        if not p:
            return None
        return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000

    def supported_models(self) -> list[str]:
        return list(self.PRICING.keys())
''',
}


PYPROJECT_TEMPLATE = '''[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agentcost-{pkg_name}"
version = "0.1.0"
description = "{description}"
requires-python = ">=3.10"
dependencies = ["agentcost>=0.5.0"]

[project.entry-points."agentcost.plugins"]
{pkg_name} = "{module_name}.plugin:{class_name}"

[tool.hatch.build.targets.wheel]
packages = ["{module_name}"]
'''


def scaffold_plugin(name: str, plugin_type: str = "notifier", output_dir: str = "."):
    """Generate a plugin project skeleton."""
    pkg_name = name.lower().replace(" ", "-").replace("_", "-")
    module_name = pkg_name.replace("-", "_")
    class_name = "".join(w.capitalize() for w in pkg_name.split("-")) + "Plugin"

    template = PLUGIN_TEMPLATES.get(plugin_type)
    if not template:
        raise ValueError(f"Unknown plugin type: {plugin_type}. Use: {list(PLUGIN_TEMPLATES.keys())}")

    base = Path(output_dir) / f"agentcost-{pkg_name}"
    pkg_dir = base / module_name

    os.makedirs(pkg_dir, exist_ok=True)

    # plugin.py
    plugin_code = template.format(
        name=name, pkg_name=pkg_name, class_name=class_name, module_name=module_name
    )
    (pkg_dir / "plugin.py").write_text(plugin_code)
    (pkg_dir / "__init__.py").write_text(f'from .plugin import {class_name}\n')

    # pyproject.toml
    pyproject = PYPROJECT_TEMPLATE.format(
        pkg_name=pkg_name,
        module_name=module_name,
        class_name=class_name,
        description=f"AgentCost {plugin_type} plugin: {name}",
    )
    (base / "pyproject.toml").write_text(pyproject)

    # README
    (base / "README.md").write_text(
        f"# agentcost-{pkg_name}\n\n"
        f"AgentCost {plugin_type} plugin: {name}\n\n"
        f"## Install\n\n```bash\npip install agentcost-{pkg_name}\n```\n\n"
        f"## Usage\n\n```python\nfrom {module_name} import {class_name}\n```\n"
    )

    return str(base)
