"""
ChannelService — Notification channel lifecycle management.

Channels define WHERE notifications go (Slack, email, webhook, PagerDuty)
and WHICH events they subscribe to (budget alerts, policy violations, etc.).

Config format varies by channel_type:
  - slack:     {"webhook_url": "https://hooks.slack.com/...", "channel": "#alerts"}
  - email:     {"recipients": ["admin@co.com"], "from": "care@agentcost.in"}
  - webhook:   {"url": "https://...", "headers": {"Authorization": "..."}, "method": "POST"}
  - pagerduty: {"routing_key": "...", "severity": "warning"}

Events field: comma-separated event types or "*" for all.
  Examples: "budget.exceeded,policy.violation" or "*"
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional

from ..data.connection import get_db


VALID_CHANNEL_TYPES = {"slack", "email", "webhook", "pagerduty"}


class ChannelService:
    def __init__(self, db=None):
        self._db = db or get_db()

    # ── Create ───────────────────────────────────────────────────

    def create(
        self,
        org_id: str,
        channel_type: str,
        name: str,
        config: dict,
        events: str = "*",
        enabled: bool = True,
    ) -> dict:
        if channel_type not in VALID_CHANNEL_TYPES:
            return {
                "error": f"Invalid channel_type: {channel_type}. Must be one of {VALID_CHANNEL_TYPES}"
            }

        ch_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        config_json = json.dumps(config)

        self._db.execute(
            "INSERT INTO notification_channels (id, org_id, channel_type, name, config, events, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ch_id, org_id, channel_type, name, config_json, events, enabled, now),
        )
        return {
            "id": ch_id,
            "org_id": org_id,
            "channel_type": channel_type,
            "name": name,
            "config": config,
            "events": events,
            "enabled": enabled,
        }

    # ── Read ─────────────────────────────────────────────────────

    def get(self, ch_id: str, org_id: str) -> Optional[dict]:
        row = self._db.fetch_one(
            "SELECT * FROM notification_channels WHERE id = ? AND org_id = ?",
            (ch_id, org_id),
        )
        return self._parse_row(row) if row else None

    def list(self, org_id: str, enabled_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM notification_channels WHERE org_id = ?"
        params: list = [org_id]
        if enabled_only:
            sql += " AND enabled = ?"
            params.append(True)
        sql += " ORDER BY name ASC"
        rows = self._db.fetch_all(sql, params)
        return [self._parse_row(r) for r in rows]

    def get_channels_for_event(self, org_id: str, event_type: str) -> list[dict]:
        """Get all enabled channels subscribed to a specific event type."""
        channels = self.list(org_id, enabled_only=True)
        result = []
        for ch in channels:
            events = ch.get("events", "*")
            if events == "*" or event_type in [e.strip() for e in events.split(",")]:
                result.append(ch)
        return result

    # ── Update ───────────────────────────────────────────────────

    def update(self, ch_id: str, org_id: str, **kwargs) -> Optional[dict]:
        allowed = {"name", "config", "events", "enabled", "channel_type"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return self.get(ch_id, org_id)

        if "config" in updates and isinstance(updates["config"], dict):
            updates["config"] = json.dumps(updates["config"])
        if (
            "channel_type" in updates
            and updates["channel_type"] not in VALID_CHANNEL_TYPES
        ):
            return {"error": f"Invalid channel_type: {updates['channel_type']}"}

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [ch_id, org_id]
        self._db.execute(
            f"UPDATE notification_channels SET {set_clause} WHERE id = ? AND org_id = ?",
            params,
        )
        return self.get(ch_id, org_id)

    def toggle(self, ch_id: str, org_id: str, enabled: bool) -> Optional[dict]:
        return self.update(ch_id, org_id, enabled=enabled)

    # ── Delete ───────────────────────────────────────────────────

    def delete(self, ch_id: str, org_id: str) -> dict:
        self._db.execute(
            "DELETE FROM notification_channels WHERE id = ? AND org_id = ?",
            (ch_id, org_id),
        )
        return {"status": "deleted", "id": ch_id}

    # ── Test ─────────────────────────────────────────────────────

    def test_channel(self, ch_id: str, org_id: str) -> dict:
        """Send a test notification to verify channel config."""
        ch = self.get(ch_id, org_id)
        if not ch:
            return {"error": "Channel not found"}

        from .dispatcher import Dispatcher

        dispatcher = Dispatcher(self._db)
        test_event = {
            "event_type": "test",
            "message": "This is a test notification from AgentCost.",
            "org_id": org_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        result = dispatcher.send_to_channel(ch, test_event)
        return {
            "channel_id": ch_id,
            "channel_type": ch["channel_type"],
            "result": result,
        }

    # ── Helpers ──────────────────────────────────────────────────

    def _parse_row(self, row) -> dict:
        d = dict(row)
        if d.get("config") and isinstance(d["config"], str):
            try:
                d["config"] = json.loads(d["config"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d
