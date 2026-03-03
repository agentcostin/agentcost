"""
AgentCost Event Bus & Webhook System — Phase 5 Block 4

A comprehensive event bus that plugins and external systems can subscribe to.

Events:
    trace.created       — fires on every LLM call (batched)
    budget.warning      — budget threshold reached
    budget.exceeded     — budget limit hit
    policy.violation    — policy check failed
    anomaly.detected    — anomaly detection triggered
    approval.pending    — new approval request
    scorecard.generated — monthly scorecard created

Delivery:
    - Webhook URLs (HTTP POST with retry)
    - Server-Sent Events (SSE) for real-time streaming
    - In-process callbacks

Usage:
    from agentcost.events import EventBus, EventType

    bus = EventBus()
    bus.subscribe("budget.warning", webhook_url="https://hooks.slack.com/...")
    bus.subscribe("anomaly.detected", callback=my_handler)
    bus.emit("budget.warning", {"project": "prod", "usage_pct": 85})
"""

from __future__ import annotations
import json
import time
import logging
import threading
import hashlib
from dataclasses import dataclass, field
from typing import Callable, Optional, Any
from collections import defaultdict
from queue import Queue, Empty

logger = logging.getLogger("agentcost.events")


class EventType:
    """Known event types."""

    TRACE_CREATED = "trace.created"
    BUDGET_WARNING = "budget.warning"
    BUDGET_EXCEEDED = "budget.exceeded"
    POLICY_VIOLATION = "policy.violation"
    ANOMALY_DETECTED = "anomaly.detected"
    APPROVAL_PENDING = "approval.pending"
    APPROVAL_DECIDED = "approval.decided"
    SCORECARD_GENERATED = "scorecard.generated"
    USER_LOGIN = "user.login"
    ORG_UPDATED = "org.updated"


@dataclass
class Event:
    """An event on the bus."""

    type: str
    data: dict
    timestamp: float = field(default_factory=time.time)
    event_id: str = ""

    def __post_init__(self):
        if not self.event_id:
            raw = (
                f"{self.type}:{self.timestamp}:{json.dumps(self.data, sort_keys=True)}"
            )
            self.event_id = hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "type": self.type,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        return f"id: {self.event_id}\nevent: {self.type}\ndata: {json.dumps(self.data)}\n\n"


@dataclass
class WebhookSubscription:
    """A webhook subscriber."""

    url: str
    event_types: list[str]  # which events to deliver
    secret: str = ""  # HMAC secret for signature verification
    max_retries: int = 3
    retry_delay: float = 5.0  # seconds between retries
    active: bool = True
    _failures: int = 0

    @property
    def id(self) -> str:
        return hashlib.md5(self.url.encode()).hexdigest()[:8]


@dataclass
class CallbackSubscription:
    """An in-process callback subscriber."""

    callback: Callable[[Event], None]
    event_types: list[str]
    name: str = ""

    @property
    def id(self) -> str:
        return self.name or f"cb-{id(self.callback)}"


# ── Event Bus ─────────────────────────────────────────────────────────────────


class EventBus:
    """
    Central event bus for AgentCost.
    Supports webhook delivery, SSE streaming, and in-process callbacks.
    """

    def __init__(self, max_history: int = 1000):
        self._webhooks: dict[str, WebhookSubscription] = {}
        self._callbacks: dict[str, CallbackSubscription] = {}
        self._sse_queues: list[Queue] = []
        self._history: list[Event] = []
        self._max_history = max_history
        self._total_emitted = 0
        self._total_delivered = 0
        self._total_failures = 0
        self._lock = threading.Lock()

    # ── Subscribe ─────────────────────────────────────────────────────────

    def subscribe_webhook(
        self,
        url: str,
        event_types: list[str] = None,
        secret: str = "",
        max_retries: int = 3,
    ) -> str:
        """Add a webhook subscriber. Returns subscription ID."""
        sub = WebhookSubscription(
            url=url,
            event_types=event_types or ["*"],
            secret=secret,
            max_retries=max_retries,
        )
        self._webhooks[sub.id] = sub
        logger.info(f"Webhook subscribed: {sub.id} → {url} for {sub.event_types}")
        return sub.id

    def subscribe_callback(
        self,
        callback: Callable[[Event], None],
        event_types: list[str] = None,
        name: str = "",
    ) -> str:
        """Add an in-process callback subscriber."""
        sub = CallbackSubscription(
            callback=callback,
            event_types=event_types or ["*"],
            name=name,
        )
        self._callbacks[sub.id] = sub
        logger.info(f"Callback subscribed: {sub.id} for {sub.event_types}")
        return sub.id

    def subscribe_sse(self) -> Queue:
        """Create an SSE stream queue. Returns a Queue that receives Event objects."""
        q: Queue = Queue(maxsize=100)
        with self._lock:
            self._sse_queues.append(q)
        return q

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscription by ID."""
        if subscription_id in self._webhooks:
            del self._webhooks[subscription_id]
            return True
        if subscription_id in self._callbacks:
            del self._callbacks[subscription_id]
            return True
        return False

    # ── Emit ──────────────────────────────────────────────────────────────

    def emit(self, event_type: str, data: dict) -> Event:
        """Emit an event to all matching subscribers."""
        event = Event(type=event_type, data=data)

        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history.pop(0)
            self._total_emitted += 1

        # Deliver to callbacks (synchronous)
        for sub in list(self._callbacks.values()):
            if self._matches(event_type, sub.event_types):
                try:
                    sub.callback(event)
                    self._total_delivered += 1
                except Exception as e:
                    logger.error(f"Callback {sub.id} error: {e}")
                    self._total_failures += 1

        # Deliver to SSE queues
        with self._lock:
            dead_queues = []
            for q in self._sse_queues:
                try:
                    q.put_nowait(event)
                except Exception:
                    dead_queues.append(q)
            for q in dead_queues:
                self._sse_queues.remove(q)

        # Deliver to webhooks (async, fire-and-forget)
        for sub in list(self._webhooks.values()):
            if sub.active and self._matches(event_type, sub.event_types):
                threading.Thread(
                    target=self._deliver_webhook, args=(sub, event), daemon=True
                ).start()

        return event

    def _matches(self, event_type: str, patterns: list[str]) -> bool:
        """Check if event type matches subscription patterns."""
        for p in patterns:
            if p == "*":
                return True
            if p == event_type:
                return True
            # Prefix match: "budget.*" matches "budget.warning"
            if p.endswith(".*"):
                prefix = p[:-2]
                if event_type.startswith(prefix + "."):
                    return True
        return False

    def _deliver_webhook(self, sub: WebhookSubscription, event: Event) -> None:
        """Deliver event to a webhook with retry."""
        import urllib.request
        import urllib.error

        payload = json.dumps(event.to_dict()).encode()
        headers = {"Content-Type": "application/json", "X-AgentCost-Event": event.type}

        # Add HMAC signature if secret configured
        if sub.secret:
            import hmac as hmac_mod

            sig = hmac_mod.new(sub.secret.encode(), payload, "sha256").hexdigest()
            headers["X-AgentCost-Signature"] = f"sha256={sig}"

        for attempt in range(sub.max_retries):
            try:
                req = urllib.request.Request(
                    sub.url, data=payload, headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status < 300:
                        self._total_delivered += 1
                        sub._failures = 0
                        return
            except Exception as e:
                logger.warning(f"Webhook {sub.id} attempt {attempt + 1} failed: {e}")
                if attempt < sub.max_retries - 1:
                    time.sleep(sub.retry_delay)

        # All retries failed
        sub._failures += 1
        self._total_failures += 1
        if sub._failures >= 10:
            sub.active = False
            logger.error(f"Webhook {sub.id} disabled after {sub._failures} failures")

    # ── Query ─────────────────────────────────────────────────────────────

    def get_history(self, event_type: str = None, limit: int = 50) -> list[dict]:
        """Get recent events from history."""
        events = self._history
        if event_type:
            events = [e for e in events if e.type == event_type]
        return [e.to_dict() for e in events[-limit:]]

    @property
    def subscriptions(self) -> dict:
        return {
            "webhooks": [
                {
                    "id": s.id,
                    "url": s.url,
                    "events": s.event_types,
                    "active": s.active,
                    "failures": s._failures,
                }
                for s in self._webhooks.values()
            ],
            "callbacks": [
                {"id": s.id, "name": s.name, "events": s.event_types}
                for s in self._callbacks.values()
            ],
            "sse_streams": len(self._sse_queues),
        }

    @property
    def stats(self) -> dict:
        return {
            "total_emitted": self._total_emitted,
            "total_delivered": self._total_delivered,
            "total_failures": self._total_failures,
            "webhook_count": len(self._webhooks),
            "callback_count": len(self._callbacks),
            "sse_streams": len(self._sse_queues),
            "history_size": len(self._history),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_global_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus singleton."""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus
