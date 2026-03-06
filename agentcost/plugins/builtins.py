"""
AgentCost Built-in Plugins — ships out of the box.

Provides default implementations for key slots so AgentCost works
without any external plugin packages installed:

    1. SlackNotifierPlugin     — Slack webhook notifications
    2. WebhookNotifierPlugin   — generic webhook POST
    3. EmailNotifierPlugin     — SMTP email (stub, logs by default)
    4. PagerDutyNotifierPlugin — PagerDuty Events API v2 (stub)
    5. InMemoryTrackerPlugin   — in-memory cost tracking backend
    6. AgentLifecyclePlugin    — agent state machine (Registered → Active → ...)
    7. PagerDutyReactorPlugin  — example reactor that creates PagerDuty incidents
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from typing import Any

from . import (
    AgentPlugin,
    HealthStatus,
    NotifierPlugin,
    NotifyEvent,
    PluginMeta,
    PluginType,
    ReactorPlugin,
    SendResult,
    TrackerPlugin,
)

logger = logging.getLogger("agentcost.plugins.builtins")


# ═══════════════════════════════════════════════════════════════════════════════
# Notifier Plugins — converted from notify/dispatcher.py
# ═══════════════════════════════════════════════════════════════════════════════


class SlackNotifierPlugin(NotifierPlugin):
    """Send notifications to Slack via incoming webhooks."""

    meta = PluginMeta(
        name="builtin-slack",
        version="1.0.0",
        plugin_type=PluginType.NOTIFIER,
        description="Slack webhook notifications (built-in)",
        config_schema={"webhook_url": {"type": "string", "required": True}},
    )

    def __init__(self):
        self.webhook_url: str = ""
        self.channel: str = ""

    def configure(self, config: dict) -> None:
        self.webhook_url = config.get("webhook_url", "")
        self.channel = config.get("channel", "")

    def send(self, event: NotifyEvent) -> SendResult:
        if not self.webhook_url:
            return SendResult(success=False, message="No webhook_url configured")

        emoji = _event_emoji(event.event_type)
        text = f"{emoji} *AgentCost Alert* — `{event.event_type}`\n"
        if event.message:
            text += f">{event.message}\n"
        details = event.details or event.metadata
        if details:
            text += f"```{json.dumps(details, indent=2)[:500]}```"

        payload: dict[str, Any] = {"text": text}
        if self.channel:
            payload["channel"] = self.channel

        return _http_post(self.webhook_url, payload)

    def health_check(self) -> HealthStatus:
        ok = bool(self.webhook_url)
        return HealthStatus(
            healthy=ok,
            message="ok" if ok else "webhook_url not configured",
        )


class WebhookNotifierPlugin(NotifierPlugin):
    """Send notifications to any HTTP endpoint."""

    meta = PluginMeta(
        name="builtin-webhook",
        version="1.0.0",
        plugin_type=PluginType.NOTIFIER,
        description="Generic webhook notifications (built-in)",
        config_schema={"url": {"type": "string", "required": True}},
    )

    def __init__(self):
        self.url: str = ""
        self.headers: dict = {}
        self.method: str = "POST"

    def configure(self, config: dict) -> None:
        self.url = config.get("url", "")
        self.headers = config.get("headers", {})
        self.method = config.get("method", "POST").upper()

    def send(self, event: NotifyEvent) -> SendResult:
        if not self.url:
            return SendResult(success=False, message="No url configured")

        payload = {
            "event_type": event.event_type,
            "severity": event.severity,
            "title": event.title,
            "message": event.message,
            "project": event.project,
            "agent_id": event.agent_id,
            "metadata": event.metadata or event.details,
        }
        headers = {**self.headers}
        headers.setdefault("Content-Type", "application/json")
        return _http_post(self.url, payload, headers=headers)

    def health_check(self) -> HealthStatus:
        ok = bool(self.url)
        return HealthStatus(healthy=ok, message="ok" if ok else "url not configured")


class EmailNotifierPlugin(NotifierPlugin):
    """Send email notifications (stub — logs by default).

    In production, configure SMTP or integrate with SendGrid/SES.
    """

    meta = PluginMeta(
        name="builtin-email",
        version="1.0.0",
        plugin_type=PluginType.NOTIFIER,
        description="Email notifications (built-in, stub)",
        config_schema={"recipients": {"type": "array", "required": True}},
    )

    def __init__(self):
        self.recipients: list[str] = []

    def configure(self, config: dict) -> None:
        self.recipients = config.get("recipients", [])

    def send(self, event: NotifyEvent) -> SendResult:
        if not self.recipients:
            return SendResult(success=False, message="No recipients configured")

        subject = f"AgentCost Alert: {event.event_type}"
        body = event.message or json.dumps(event.metadata or event.details, indent=2)
        logger.info(
            "EMAIL [stub] to=%s subject='%s' body='%s'",
            self.recipients,
            subject,
            body[:200],
        )
        return SendResult(
            success=True,
            message="stub",
            provider_response={"recipients": self.recipients, "subject": subject},
        )

    def health_check(self) -> HealthStatus:
        ok = bool(self.recipients)
        return HealthStatus(healthy=ok, message="ok" if ok else "no recipients")


class PagerDutyNotifierPlugin(NotifierPlugin):
    """Send PagerDuty events (stub — logs by default).

    In production, POST to PagerDuty Events API v2.
    """

    meta = PluginMeta(
        name="builtin-pagerduty",
        version="1.0.0",
        plugin_type=PluginType.NOTIFIER,
        description="PagerDuty notifications (built-in, stub)",
        config_schema={"routing_key": {"type": "string", "required": True}},
    )

    def __init__(self):
        self.routing_key: str = ""
        self.default_severity: str = "warning"

    def configure(self, config: dict) -> None:
        self.routing_key = config.get("routing_key", "")
        self.default_severity = config.get("severity", "warning")

    def send(self, event: NotifyEvent) -> SendResult:
        if not self.routing_key:
            return SendResult(success=False, message="No routing_key configured")

        severity = event.severity or self.default_severity
        summary = f"AgentCost: {event.event_type} — {event.message}"
        logger.info(
            "PAGERDUTY [stub] routing_key=%s severity=%s summary='%s'",
            self.routing_key[:8] + "...",
            severity,
            summary[:200],
        )
        return SendResult(
            success=True,
            message="stub",
            provider_response={"severity": severity, "summary": summary[:200]},
        )

    def health_check(self) -> HealthStatus:
        ok = bool(self.routing_key)
        return HealthStatus(healthy=ok, message="ok" if ok else "no routing_key")


# ═══════════════════════════════════════════════════════════════════════════════
# Tracker Plugin — In-Memory (default)
# ═══════════════════════════════════════════════════════════════════════════════


class InMemoryTrackerPlugin(TrackerPlugin):
    """Default cost tracking backend — stores traces in memory.

    Ships as the built-in TrackerPlugin so reactions, budget alerts, and
    spend queries work out of the box without an external database.

    For production, replace with a DB-backed or third-party tracker.
    """

    meta = PluginMeta(
        name="builtin-memory-tracker",
        version="1.0.0",
        plugin_type=PluginType.TRACKER,
        description="In-memory cost tracker (built-in)",
    )

    def __init__(self):
        self._traces: list[dict] = []
        self._spend_by_scope: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._max_traces = 10_000

    def record_trace(self, event: dict) -> None:
        """Record a trace event and update running spend totals."""
        self._traces.append(event)
        if len(self._traces) > self._max_traces:
            self._traces = self._traces[-self._max_traces :]

        cost = event.get("cost", 0.0)
        # Update spend for every scope key present in the event
        for scope_key in ("project", "agent_id", "org_id"):
            scope_id = event.get(scope_key)
            if scope_id:
                self._spend_by_scope[scope_key][scope_id] += cost

    def get_spend(self, scope: str, scope_id: str, period: str = "month") -> float:
        """Get total spend for a scope. Period filtering is best-effort."""
        return self._spend_by_scope.get(scope, {}).get(scope_id, 0.0)

    def get_traces(self, limit: int = 100) -> list[dict]:
        """Return recent traces."""
        return self._traces[-limit:]

    def reset(self) -> None:
        """Clear all stored traces and spend data."""
        self._traces.clear()
        self._spend_by_scope.clear()

    def health_check(self) -> HealthStatus:
        return HealthStatus(
            healthy=True,
            details={"trace_count": len(self._traces)},
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Plugin — Lifecycle State Machine
# ═══════════════════════════════════════════════════════════════════════════════


# Valid state transitions for the agent cost lifecycle
VALID_TRANSITIONS: dict[str, set[str]] = {
    "registered": {"active"},
    "active": {"budget_warning", "suspended", "terminated"},
    "budget_warning": {"active", "suspended", "terminated"},
    "suspended": {"resumed", "terminated"},
    "resumed": {"active", "suspended", "terminated"},
    "terminated": set(),  # terminal state
}

ALL_STATES = set(VALID_TRANSITIONS.keys()) | {"terminated"}


class AgentLifecyclePlugin(AgentPlugin):
    """Built-in agent lifecycle manager.

    Implements the cost-event lifecycle state machine:
        Registered → Active → BudgetWarning → Suspended → Resumed → Active

    Emits events to EventBus on every state transition so the
    ReactionEngine can trigger actions (notify, block-calls, etc.).

    Also stores per-project workspace config (budget limits, default
    models, team assignments).
    """

    meta = PluginMeta(
        name="builtin-agent-lifecycle",
        version="1.0.0",
        plugin_type=PluginType.AGENT,
        description="Agent lifecycle state machine (built-in)",
    )

    def __init__(self):
        self._states: dict[str, str] = {}  # agent_id → state
        self._history: list[dict] = []  # transition audit log
        self._workspace_configs: dict[str, dict] = {}  # project → config

    def get_agent_state(self, agent_id: str) -> str:
        return self._states.get(agent_id, "registered")

    def transition(self, agent_id: str, new_state: str, reason: str = "") -> bool:
        """Transition an agent to a new state, validating the transition.

        Emits an event to the EventBus on successful transitions.
        """
        current = self.get_agent_state(agent_id)
        allowed = VALID_TRANSITIONS.get(current, set())

        if new_state not in allowed:
            logger.warning(
                "Invalid transition for agent %s: %s → %s (allowed: %s)",
                agent_id,
                current,
                new_state,
                allowed,
            )
            return False

        old_state = current
        self._states[agent_id] = new_state

        record = {
            "agent_id": agent_id,
            "from_state": old_state,
            "to_state": new_state,
            "reason": reason,
            "timestamp": time.time(),
        }
        self._history.append(record)
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

        # Emit event to EventBus for reaction engine
        _emit_lifecycle_event(agent_id, old_state, new_state, reason)

        logger.info(
            "Agent %s: %s → %s (reason: %s)",
            agent_id,
            old_state,
            new_state,
            reason or "none",
        )
        return True

    def register_agent(self, agent_id: str) -> bool:
        """Register a new agent (sets initial state)."""
        if agent_id in self._states:
            return False  # already registered
        self._states[agent_id] = "registered"
        return True

    def get_all_agents(self) -> dict[str, str]:
        """Return all agents and their states."""
        return dict(self._states)

    def get_transition_history(
        self, agent_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Get transition history, optionally filtered by agent."""
        if agent_id:
            filtered = [h for h in self._history if h["agent_id"] == agent_id]
            return filtered[-limit:]
        return self._history[-limit:]

    def get_workspace_config(self, project: str) -> dict:
        return self._workspace_configs.get(project, {})

    def set_workspace_config(self, project: str, config: dict) -> None:
        self._workspace_configs[project] = config


# ═══════════════════════════════════════════════════════════════════════════════
# Reactor Plugin — PagerDuty Example
# ═══════════════════════════════════════════════════════════════════════════════


class PagerDutyReactorPlugin(ReactorPlugin):
    """Example reactor plugin that creates PagerDuty incidents.

    Registers two actions with the ReactionEngine:
        - pagerduty-trigger: Create a new incident
        - pagerduty-resolve: Resolve an existing incident

    In production, this would POST to PagerDuty Events API v2.
    Currently logs the action (ready for real integration).
    """

    meta = PluginMeta(
        name="example-pagerduty-reactor",
        version="1.0.0",
        plugin_type=PluginType.REACTOR,
        description="PagerDuty incident reactor (example)",
        author="AgentCost",
    )

    def __init__(self):
        self.routing_key: str = ""
        self._incidents: dict[str, dict] = {}

    def configure(self, config: dict) -> None:
        self.routing_key = config.get("routing_key", "")

    def get_actions(self) -> dict:
        return {
            "pagerduty-trigger": self._trigger_incident,
            "pagerduty-resolve": self._resolve_incident,
        }

    def _trigger_incident(self, event_type: str, event_data: dict) -> bool:
        """Create a PagerDuty incident."""
        severity = event_data.get("severity", "warning")
        summary = f"AgentCost: {event_type} — {event_data.get('message', 'Alert')}"
        dedup_key = event_data.get("dedup_key", event_type)

        incident = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "dedup_key": dedup_key,
            "payload": {
                "summary": summary[:1024],
                "severity": severity,
                "source": "agentcost",
                "component": event_data.get("project", "unknown"),
                "custom_details": {
                    k: v
                    for k, v in event_data.items()
                    if k not in ("_reaction", "_webhook_url")
                },
            },
        }
        self._incidents[dedup_key] = incident

        if self.routing_key:
            # In production: POST to https://events.pagerduty.com/v2/enqueue
            logger.info(
                "PAGERDUTY TRIGGER: dedup=%s severity=%s summary='%s'",
                dedup_key,
                severity,
                summary[:100],
            )
        else:
            logger.info(
                "PAGERDUTY TRIGGER [dry-run]: dedup=%s severity=%s",
                dedup_key,
                severity,
            )
        return True

    def _resolve_incident(self, event_type: str, event_data: dict) -> bool:
        """Resolve a PagerDuty incident."""
        dedup_key = event_data.get("dedup_key", event_type)
        self._incidents.pop(dedup_key, None)

        logger.info("PAGERDUTY RESOLVE: dedup=%s", dedup_key)
        return True

    def health_check(self) -> HealthStatus:
        return HealthStatus(
            healthy=True,
            details={
                "routing_key_set": bool(self.routing_key),
                "active_incidents": len(self._incidents),
            },
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _event_emoji(event_type: str) -> str:
    emojis = {
        "budget.exceeded": "\U0001f6a8",
        "budget.warning": "\u26a0\ufe0f",
        "policy.violation": "\U0001f6d1",
        "approval.pending": "\U0001f4cb",
        "approval.decide": "\u2705",
        "agent.suspended": "\u23f8\ufe0f",
        "agent.resumed": "\u25b6\ufe0f",
        "test": "\U0001f9ea",
    }
    return emojis.get(event_type, "\U0001f4e2")


def _http_post(url: str, payload: dict, headers: dict | None = None) -> SendResult:
    """HTTP POST helper — gracefully degrades to logging on failure."""
    hdrs = headers or {"Content-Type": "application/json"}
    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=hdrs,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return SendResult(
                success=200 <= resp.status < 300,
                message=f"HTTP {resp.status}",
            )
    except Exception as e:
        logger.debug("HTTP POST to %s failed (logged): %s", url, e)
        return SendResult(success=True, message=f"logged: {str(e)[:100]}")


def _emit_lifecycle_event(
    agent_id: str, old_state: str, new_state: str, reason: str
) -> None:
    """Emit an agent lifecycle event to the EventBus (best-effort)."""
    try:
        from ..events import get_event_bus

        bus = get_event_bus()
        event_type = f"agent.{new_state}"
        bus.emit(
            event_type,
            {
                "agent_id": agent_id,
                "from_state": old_state,
                "to_state": new_state,
                "reason": reason,
            },
        )
    except Exception:
        pass  # EventBus may not be initialized yet
