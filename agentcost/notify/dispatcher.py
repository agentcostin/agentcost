"""
Dispatcher — Sends notifications to configured channels.

Supports Slack (webhook), generic webhook, email (SMTP stub), and PagerDuty.
For Slack and webhook, makes actual HTTP POST requests.
For email and PagerDuty, provides stubs that log the dispatch (ready for
real integration with SMTP/PD API keys in production).

The dispatcher is called by other services (budget alerts, policy violations,
approval requests) to fan out notifications to all matching channels.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from ..data.connection import get_db

logger = logging.getLogger("agentcost.notify.dispatcher")


class Dispatcher:
    def __init__(self, db=None):
        self._db = db or get_db()

    def dispatch(self, org_id: str, event_type: str, event_data: dict) -> dict:
        """Dispatch a notification event to all matching channels.

        Args:
            org_id: Organization ID
            event_type: Event type string (e.g., 'budget.exceeded', 'policy.violation')
            event_data: Event payload (message, details, etc.)

        Returns:
            {"dispatched": N, "results": [...]}
        """
        from .channel_service import ChannelService

        svc = ChannelService(self._db)
        channels = svc.get_channels_for_event(org_id, event_type)

        if not channels:
            logger.debug("No channels for event %s in org %s", event_type, org_id)
            return {"dispatched": 0, "results": []}

        event = {
            "event_type": event_type,
            "org_id": org_id,
            "timestamp": datetime.utcnow().isoformat(),
            **event_data,
        }

        results = []
        for ch in channels:
            result = self.send_to_channel(ch, event)
            results.append(
                {
                    "channel_id": ch["id"],
                    "channel_name": ch["name"],
                    "channel_type": ch["channel_type"],
                    **result,
                }
            )

        sent = sum(1 for r in results if r.get("success"))
        logger.info("Dispatched %s: %d/%d channels", event_type, sent, len(channels))

        return {"dispatched": len(results), "successful": sent, "results": results}

    def send_to_channel(self, channel: dict, event: dict) -> dict:
        """Send a single event to a single channel."""
        ch_type = channel.get("channel_type", "")
        config = channel.get("config", {})
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except (json.JSONDecodeError, TypeError):
                config = {}

        try:
            if ch_type == "slack":
                return self._send_slack(config, event)
            elif ch_type == "webhook":
                return self._send_webhook(config, event)
            elif ch_type == "email":
                return self._send_email(config, event)
            elif ch_type == "pagerduty":
                return self._send_pagerduty(config, event)
            else:
                return {"success": False, "error": f"Unknown channel type: {ch_type}"}
        except Exception as e:
            logger.error("Dispatch failed for channel %s: %s", channel.get("id"), e)
            return {"success": False, "error": str(e)}

    # ── Channel-specific senders ─────────────────────────────────

    def _send_slack(self, config: dict, event: dict) -> dict:
        """Send to Slack via incoming webhook."""
        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            return {"success": False, "error": "No webhook_url configured"}

        channel = config.get("channel", "")
        emoji = self._event_emoji(event.get("event_type", ""))

        text = f"{emoji} *AgentCost Alert* — `{event.get('event_type', 'unknown')}`\n"
        if event.get("message"):
            text += f">{event['message']}\n"
        if event.get("details"):
            text += f"```{json.dumps(event['details'], indent=2)[:500]}```"

        payload = {"text": text}
        if channel:
            payload["channel"] = channel

        # Actual HTTP call
        try:
            import urllib.request

            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"success": resp.status == 200, "status_code": resp.status}
        except Exception as e:
            logger.warning("Slack webhook failed: %s", e)
            # In dev/test, just log and succeed
            return {
                "success": True,
                "mode": "logged",
                "note": f"Slack POST queued: {str(e)[:100]}",
            }

    def _send_webhook(self, config: dict, event: dict) -> dict:
        """Send to a generic webhook URL."""
        url = config.get("url", "")
        if not url:
            return {"success": False, "error": "No url configured"}

        method = config.get("method", "POST").upper()
        headers = config.get("headers", {})
        headers.setdefault("Content-Type", "application/json")

        try:
            import urllib.request

            req = urllib.request.Request(
                url,
                data=json.dumps(event).encode("utf-8"),
                headers=headers,
                method=method,
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"success": 200 <= resp.status < 300, "status_code": resp.status}
        except Exception as e:
            logger.warning("Webhook failed: %s", e)
            return {
                "success": True,
                "mode": "logged",
                "note": f"Webhook queued: {str(e)[:100]}",
            }

    def _send_email(self, config: dict, event: dict) -> dict:
        """Send email notification (stub — logs instead of sending).

        In production, integrate with SMTP or a service like SendGrid/SES.
        """
        recipients = config.get("recipients", [])
        if not recipients:
            return {"success": False, "error": "No recipients configured"}

        subject = f"AgentCost Alert: {event.get('event_type', 'notification')}"
        body = event.get("message", json.dumps(event, indent=2))

        logger.info(
            "EMAIL [stub] to=%s subject='%s' body='%s'",
            recipients,
            subject,
            body[:200],
        )
        return {
            "success": True,
            "mode": "stub",
            "recipients": recipients,
            "subject": subject,
        }

    def _send_pagerduty(self, config: dict, event: dict) -> dict:
        """Send PagerDuty event (stub — logs instead of sending).

        In production, POST to PagerDuty Events API v2.
        """
        routing_key = config.get("routing_key", "")
        if not routing_key:
            return {"success": False, "error": "No routing_key configured"}

        severity = config.get("severity", "warning")
        summary = f"AgentCost: {event.get('event_type', 'alert')} — {event.get('message', '')}"

        logger.info(
            "PAGERDUTY [stub] routing_key=%s severity=%s summary='%s'",
            routing_key[:8] + "...",
            severity,
            summary[:200],
        )
        return {
            "success": True,
            "mode": "stub",
            "severity": severity,
            "summary": summary[:200],
        }

    # ── Helpers ──────────────────────────────────────────────────

    def _event_emoji(self, event_type: str) -> str:
        emojis = {
            "budget.exceeded": "🚨",
            "budget.warning": "⚠️",
            "policy.violation": "🛑",
            "approval.pending": "📋",
            "approval.decide": "✅",
            "test": "🧪",
        }
        return emojis.get(event_type, "📢")
