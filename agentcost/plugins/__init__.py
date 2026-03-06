"""
AgentCost Plugin SDK — 8-slot plugin architecture.

Inspired by ComposioHQ/agent-orchestrator's 8-slot pattern, adapted for
AI cost governance. Every integration point in AgentCost is swappable.

Plugin Slots (8):
    1. NotifierPlugin   — send alerts to custom channels (Slack, Teams, email)
    2. PolicyPlugin     — custom policy evaluation rules
    3. ExporterPlugin   — export trace data to external systems (S3, Snowflake)
    4. ProviderPlugin   — cost calculation for custom/new LLM providers
    5. TrackerPlugin    — cost tracking backends (in-memory, DB, Langfuse)
    6. ReactorPlugin    — custom reaction action handlers
    7. RuntimePlugin    — runtime config: model routing, rate limiting, feature flags
    8. AgentPlugin      — agent lifecycle management, workspace config

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
    TRACKER = "tracker"
    REACTOR = "reactor"
    RUNTIME = "runtime"
    AGENT = "agent"


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
    title: str = ""
    message: str = ""
    project: str | None = None
    agent_id: str | None = None
    metadata: dict = field(default_factory=dict)
    details: dict = field(default_factory=dict)


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
    def calculate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float | None:
        """Calculate cost for a model. Return None if model not supported."""
        ...

    @abstractmethod
    def supported_models(self) -> list[str]:
        """List of model names this provider supports."""
        ...


class TrackerPlugin(AgentCostPlugin):
    """Plugin that provides a cost tracking backend.

    Default: in-memory tracker (ships built-in). Alternatives: database-backed,
    remote API-backed, or third-party (e.g., Langfuse, Datadog).
    """

    @abstractmethod
    def record_trace(self, event: dict) -> None:
        """Record a trace event (LLM call with cost data)."""
        ...

    @abstractmethod
    def get_spend(self, scope: str, scope_id: str, period: str = "month") -> float:
        """Get total spend for a scope (project/agent/org) in a period."""
        ...

    def check_budget(self, scope: str, scope_id: str, budget: float) -> bool:
        """Check if spend is within budget. Returns True if OK."""
        return self.get_spend(scope, scope_id) < budget


class ReactorPlugin(AgentCostPlugin):
    """Plugin that handles custom reaction actions."""

    @abstractmethod
    def get_actions(self) -> dict[str, Any]:
        """Return a dict of action_name -> handler_callable."""
        ...

    def on_start(self, engine: Any) -> None:
        """Called when the reaction engine starts. Register actions here."""
        actions = self.get_actions()
        for name, handler in actions.items():
            engine.register_action(name, handler)


class RuntimePlugin(AgentCostPlugin):
    """Plugin that controls runtime configuration.

    Governs model routing rules, rate limits, feature flags, and
    global settings that affect how LLM calls are dispatched.

    Inspired by Agent Orchestrator's Runtime slot which controls
    execution environment and orchestration parameters.
    """

    @abstractmethod
    def get_model_override(self, requested_model: str, context: dict) -> str | None:
        """Override model selection at runtime.

        Returns overridden model name, or None to keep the original.
        """
        ...

    @abstractmethod
    def check_rate_limit(self, scope: str, scope_id: str) -> bool:
        """Check if a request should be allowed under rate limits.

        Returns True if within limits.
        """
        ...

    def get_feature_flags(self) -> dict[str, bool]:
        """Return feature flags for the runtime."""
        return {}


class AgentPlugin(AgentCostPlugin):
    """Plugin that manages agent lifecycle and workspace configuration.

    Provides the state machine for agent cost lifecycle:
        Registered -> Active -> BudgetWarning -> Suspended -> Resumed -> Active

    Also manages workspace-level config: project budgets, team assignments,
    default models, and context policies.

    Merges the Agent and Workspace slots from Agent Orchestrator into
    one cohesive plugin since they are tightly coupled in cost governance.
    """

    @abstractmethod
    def get_agent_state(self, agent_id: str) -> str:
        """Get the current lifecycle state of an agent.

        Returns one of: 'registered', 'active', 'budget_warning',
        'suspended', 'resumed', 'terminated'
        """
        ...

    @abstractmethod
    def transition(self, agent_id: str, new_state: str, reason: str = "") -> bool:
        """Transition an agent to a new lifecycle state.

        Returns True if the transition was valid and applied.
        """
        ...

    def get_workspace_config(self, project: str) -> dict:
        """Get workspace-level configuration for a project."""
        return {}

    def set_workspace_config(self, project: str, config: dict) -> None:
        """Update workspace configuration for a project."""
        pass


# ── Plugin Module ─────────────────────────────────────────────────────────────


@dataclass
class PluginModule:
    """A packaged plugin module — inspired by Agent Orchestrator's PluginModule pattern."""

    name: str
    version: str
    plugins: list  # list of AgentCostPlugin subclasses
    default_config: dict = field(default_factory=dict)
    slot: str = ""  # primary slot name
    description: str = ""
    author: str = ""

    def instantiate(self, config: dict | None = None) -> list[AgentCostPlugin]:
        """Create plugin instances with merged config."""
        merged = {**self.default_config, **(config or {})}
        instances = []
        for cls in self.plugins:
            instance = cls()
            instance.configure(merged)
            instances.append(instance)
        return instances


# ── Plugin Registry ───────────────────────────────────────────────────────────


class PluginRegistry:
    """Discovers, loads, and manages AgentCost plugins across 8 slots."""

    def __init__(self):
        self._plugins: dict[str, AgentCostPlugin] = {}
        self._notifiers: list[NotifierPlugin] = []
        self._policies: list[PolicyPlugin] = []
        self._exporters: list[ExporterPlugin] = []
        self._providers: list[ProviderPlugin] = []
        self._trackers: list[TrackerPlugin] = []
        self._reactors: list[ReactorPlugin] = []
        self._runtimes: list[RuntimePlugin] = []
        self._agents: list[AgentPlugin] = []

    def discover(self) -> list[PluginMeta]:
        """Discover plugins via Python entry_points."""
        found: list[PluginMeta] = []
        try:
            from importlib.metadata import entry_points

            eps = entry_points()
            if hasattr(eps, "select"):
                group = eps.select(group="agentcost.plugins")
            elif isinstance(eps, dict):
                group = eps.get("agentcost.plugins", [])
            else:
                group = [ep for ep in eps if ep.group == "agentcost.plugins"]
            for ep in group:
                try:
                    obj = ep.load()
                    if isinstance(obj, PluginModule):
                        for cls in obj.plugins:
                            instance = cls()
                            found.append(instance.meta)
                    elif isinstance(obj, type) and issubclass(obj, AgentCostPlugin):
                        instance = obj()
                        found.append(instance.meta)
                except Exception as e:
                    logger.warning("Failed to load plugin %s: %s", ep.name, e)
        except Exception as e:
            logger.warning("Plugin discovery failed: %s", e)
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
        elif isinstance(plugin, TrackerPlugin):
            self._trackers.append(plugin)
        elif isinstance(plugin, ReactorPlugin):
            self._reactors.append(plugin)
        elif isinstance(plugin, RuntimePlugin):
            self._runtimes.append(plugin)
        elif isinstance(plugin, AgentPlugin):
            self._agents.append(plugin)

        logger.info("Loaded plugin: %s (%s)", name, plugin.meta.plugin_type.value)

    def load_module(self, module: PluginModule, config: dict | None = None):
        """Load all plugins from a PluginModule."""
        instances = module.instantiate(config)
        for instance in instances:
            self.load(instance, config)

    def unload(self, name: str):
        """Remove a plugin."""
        plugin = self._plugins.pop(name, None)
        if plugin:
            plugin.on_uninstall(PluginContext())
            self._notifiers = [p for p in self._notifiers if p.meta.name != name]
            self._policies = [p for p in self._policies if p.meta.name != name]
            self._exporters = [p for p in self._exporters if p.meta.name != name]
            self._providers = [p for p in self._providers if p.meta.name != name]
            self._trackers = [p for p in self._trackers if p.meta.name != name]
            self._reactors = [p for p in self._reactors if p.meta.name != name]
            self._runtimes = [p for p in self._runtimes if p.meta.name != name]
            self._agents = [p for p in self._agents if p.meta.name != name]

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

    @property
    def trackers(self) -> list[TrackerPlugin]:
        return self._trackers

    @property
    def reactors(self) -> list[ReactorPlugin]:
        return self._reactors

    @property
    def runtimes(self) -> list[RuntimePlugin]:
        return self._runtimes

    @property
    def agents(self) -> list[AgentPlugin]:
        return self._agents

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

    @property
    def slots(self) -> dict:
        """Summary of all 8 plugin slots and what's loaded in each."""
        return {
            "notifier": [p.meta.name for p in self._notifiers],
            "policy": [p.meta.name for p in self._policies],
            "exporter": [p.meta.name for p in self._exporters],
            "provider": [p.meta.name for p in self._providers],
            "tracker": [p.meta.name for p in self._trackers],
            "reactor": [p.meta.name for p in self._reactors],
            "runtime": [p.meta.name for p in self._runtimes],
            "agent": [p.meta.name for p in self._agents],
        }

    def calculate_cost_with_plugins(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float | None:
        """Try each provider plugin; return first match."""
        for pp in self._providers:
            cost = pp.calculate_cost(model, input_tokens, output_tokens)
            if cost is not None:
                return cost
        return None

    def activate_reactors(self, engine=None) -> int:
        """Register all reactor plugin actions with the reaction engine."""
        if engine is None:
            from ..reactions import get_reaction_engine

            engine = get_reaction_engine()
        count = 0
        for reactor in self._reactors:
            try:
                reactor.on_start(engine)
                actions = reactor.get_actions()
                count += len(actions)
            except Exception as e:
                logger.error("Failed to activate reactor %s: %s", reactor.meta.name, e)
        return count

    def get_model_override(self, model: str, context: dict) -> str:
        """Check all runtime plugins for model overrides. Returns final model."""
        current = model
        for rt in self._runtimes:
            try:
                override = rt.get_model_override(current, context)
                if override:
                    current = override
            except Exception as e:
                logger.error("Runtime plugin %s error: %s", rt.meta.name, e)
        return current

    def check_rate_limits(self, scope: str, scope_id: str) -> bool:
        """Check all runtime plugins for rate limits. All must pass."""
        for rt in self._runtimes:
            try:
                if not rt.check_rate_limit(scope, scope_id):
                    return False
            except Exception as e:
                logger.error("Rate limit check failed: %s", e)
        return True

    def get_agent_state(self, agent_id: str) -> str | None:
        """Get agent state from the first agent plugin."""
        for ap in self._agents:
            try:
                return ap.get_agent_state(agent_id)
            except Exception:
                pass
        return None

    def transition_agent(self, agent_id: str, new_state: str, reason: str = "") -> bool:
        """Transition agent state via the first agent plugin."""
        for ap in self._agents:
            try:
                return ap.transition(agent_id, new_state, reason)
            except Exception as e:
                logger.error("Agent transition failed: %s", e)
        return False


# Global registry instance
registry = PluginRegistry()
