"""
AgentCost Plugin SDK — extend AgentCost with custom notifiers, policies, exporters, and providers.

Plugin Types:
    NotifierPlugin  — send alerts to custom channels (Teams, Discord, SMS)
    PolicyPlugin    — custom policy evaluation rules
    ExporterPlugin  — export trace data to external systems (S3, Snowflake)
    ProviderPlugin  — add cost calculation for custom/new LLM providers

Discovery:
    Plugins are discovered via Python entry_points group "agentcost.plugins".
    In your plugin's pyproject.toml:

        [project.entry-points."agentcost.plugins"]
        my_plugin = "my_package.plugin:MyPlugin"

CLI:
    agentcost plugin list           # list installed plugins
    agentcost plugin install NAME   # pip install agentcost-NAME
    agentcost plugin create NAME    # scaffold a new plugin project
    agentcost plugin test NAME      # run plugin health check
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("agentcost.plugins")


# ── Plugin Types ──────────────────────────────────────────────────────────────

class PluginType(str, Enum):
    NOTIFIER = "notifier"
    POLICY = "policy"
    EXPORTER = "exporter"
    PROVIDER = "provider"


@dataclass
class PluginMeta:
    """Metadata about a plugin."""
    name: str
    version: str
    plugin_type: PluginType
    description: str = ""
    author: str = ""
    config_schema: dict = field(default_factory=dict)


@dataclass
class PluginContext:
    """Runtime context passed to plugins during lifecycle events."""
    config: dict = field(default_factory=dict)
    db_url: str | None = None
    server_url: str | None = None


@dataclass
class HealthStatus:
    healthy: bool
    message: str = "ok"
    details: dict = field(default_factory=dict)


# ── Notifier Types ────────────────────────────────────────────────────────────

@dataclass
class NotifyEvent:
    """Event payload sent to notifier plugins."""
    event_type: str  # "budget.warning", "policy.violation", etc.
    severity: str  # "info", "warning", "critical"
    title: str
    message: str
    project: str | None = None
    agent_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class SendResult:
    success: bool
    message: str = ""
    provider_response: Any = None


# ── Policy Types ──────────────────────────────────────────────────────────────

@dataclass
class PolicyContext:
    """Context for policy evaluation."""
    model: str
    provider: str
    estimated_cost: float
    project: str | None = None
    agent_id: str | None = None
    input_tokens: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str = ""
    action: str = "allow"  # "allow", "deny", "require_approval"


# ── Base Plugin Classes ───────────────────────────────────────────────────────

class AgentCostPlugin(ABC):
    """Base class for all AgentCost plugins."""

    meta: PluginMeta

    def on_install(self, ctx: PluginContext) -> None:
        """Called when the plugin is installed/loaded."""
        pass

    def on_uninstall(self, ctx: PluginContext) -> None:
        """Called when the plugin is removed."""
        pass

    def configure(self, config: dict) -> None:
        """Update plugin configuration at runtime."""
        pass

    def health_check(self) -> HealthStatus:
        """Check plugin health status."""
        return HealthStatus(healthy=True)


class NotifierPlugin(AgentCostPlugin):
    """Plugin that sends alerts/notifications to external channels."""

    @abstractmethod
    def send(self, event: NotifyEvent) -> SendResult:
        """Send a notification. Must be implemented by subclass."""
        ...

    def send_batch(self, events: list[NotifyEvent]) -> list[SendResult]:
        """Send multiple notifications. Override for batch-optimized delivery."""
        return [self.send(e) for e in events]


class PolicyPlugin(AgentCostPlugin):
    """Plugin that provides custom policy evaluation rules."""

    @abstractmethod
    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        """Evaluate a policy against the given context."""
        ...


class ExporterPlugin(AgentCostPlugin):
    """Plugin that exports trace data to external systems."""

    @abstractmethod
    def export(self, traces: list[dict], fmt: str = "json") -> bytes | str:
        """Export trace events in the specified format."""
        ...

    def supported_formats(self) -> list[str]:
        """List of supported export formats."""
        return ["json"]


class ProviderPlugin(AgentCostPlugin):
    """Plugin that adds cost calculation for custom/new LLM providers."""

    @abstractmethod
    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float | None:
        """Calculate cost for a model. Return None if model not supported."""
        ...

    @abstractmethod
    def supported_models(self) -> list[str]:
        """List of model names this provider supports."""
        ...


# ── Plugin Registry ───────────────────────────────────────────────────────────

class PluginRegistry:
    """Discovers, loads, and manages AgentCost plugins."""

    def __init__(self):
        self._plugins: dict[str, AgentCostPlugin] = {}
        self._notifiers: list[NotifierPlugin] = []
        self._policies: list[PolicyPlugin] = []
        self._exporters: list[ExporterPlugin] = []
        self._providers: list[ProviderPlugin] = []

    def discover(self) -> list[PluginMeta]:
        """Discover plugins via Python entry_points."""
        found: list[PluginMeta] = []
        try:
            from importlib.metadata import entry_points
            eps = entry_points()
            # Python 3.12+ returns a SelectableGroups dict
            if hasattr(eps, "select"):
                group = eps.select(group="agentcost.plugins")
            elif isinstance(eps, dict):
                group = eps.get("agentcost.plugins", [])
            else:
                group = [ep for ep in eps if ep.group == "agentcost.plugins"]

            for ep in group:
                try:
                    plugin_cls = ep.load()
                    if isinstance(plugin_cls, type) and issubclass(plugin_cls, AgentCostPlugin):
                        instance = plugin_cls()
                        found.append(instance.meta)
                        logger.info(f"Discovered plugin: {instance.meta.name} v{instance.meta.version}")
                except Exception as e:
                    logger.warning(f"Failed to load plugin {ep.name}: {e}")
        except Exception as e:
            logger.warning(f"Plugin discovery failed: {e}")
        return found

    def load(self, plugin: AgentCostPlugin, config: dict | None = None):
        """Register and initialize a plugin."""
        ctx = PluginContext(config=config or {})
        plugin.on_install(ctx)
        if config:
            plugin.configure(config)
        name = plugin.meta.name
        self._plugins[name] = plugin

        if isinstance(plugin, NotifierPlugin):
            self._notifiers.append(plugin)
        elif isinstance(plugin, PolicyPlugin):
            self._policies.append(plugin)
        elif isinstance(plugin, ExporterPlugin):
            self._exporters.append(plugin)
        elif isinstance(plugin, ProviderPlugin):
            self._providers.append(plugin)

        logger.info(f"Loaded plugin: {name} ({plugin.meta.plugin_type.value})")

    def unload(self, name: str):
        """Remove a plugin."""
        plugin = self._plugins.pop(name, None)
        if plugin:
            plugin.on_uninstall(PluginContext())
            self._notifiers = [p for p in self._notifiers if p.meta.name != name]
            self._policies = [p for p in self._policies if p.meta.name != name]
            self._exporters = [p for p in self._exporters if p.meta.name != name]
            self._providers = [p for p in self._providers if p.meta.name != name]

    def get(self, name: str) -> AgentCostPlugin | None:
        return self._plugins.get(name)

    @property
    def notifiers(self) -> list[NotifierPlugin]:
        return self._notifiers

    @property
    def policies(self) -> list[PolicyPlugin]:
        return self._policies

    @property
    def exporters(self) -> list[ExporterPlugin]:
        return self._exporters

    @property
    def providers(self) -> list[ProviderPlugin]:
        return self._providers

    def list_plugins(self) -> list[dict]:
        """List all loaded plugins."""
        return [
            {
                "name": p.meta.name,
                "version": p.meta.version,
                "type": p.meta.plugin_type.value,
                "description": p.meta.description,
                "healthy": p.health_check().healthy,
            }
            for p in self._plugins.values()
        ]

    def calculate_cost_with_plugins(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float | None:
        """Try each provider plugin; return first match."""
        for pp in self._providers:
            cost = pp.calculate_cost(model, input_tokens, output_tokens)
            if cost is not None:
                return cost
        return None


# Global registry instance
registry = PluginRegistry()
