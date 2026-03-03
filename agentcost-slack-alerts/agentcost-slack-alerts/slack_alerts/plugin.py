"""
slack-alerts — AgentCost Notifier Plugin

Sends notifications to slack-alerts.
"""
from agentcost.plugins import (
    NotifierPlugin, NotifyEvent, SendResult, PluginMeta, PluginType, HealthStatus,
)


class SlackAlertsPlugin(NotifierPlugin):
    meta = PluginMeta(
        name="slack-alerts",
        version="0.1.0",
        plugin_type=PluginType.NOTIFIER,
        description="Send AgentCost alerts to slack-alerts",
        config_schema={
            "webhook_url": {"type": "string", "required": True},
        },
    )

    def __init__(self):
        self.webhook_url: str = ""

    def configure(self, config: dict) -> None:
        self.webhook_url = config.get("webhook_url", "")

    def send(self, event: NotifyEvent) -> SendResult:
        # TODO: Implement your notification logic here
        import urllib.request
        import json
        data = json.dumps({
            "text": f"[{event.severity.upper()}] {event.title}\n{event.message}"
        }).encode()
        try:
            req = urllib.request.Request(self.webhook_url, data=data,
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=5)
            return SendResult(success=True)
        except Exception as e:
            return SendResult(success=False, message=str(e))

    def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=bool(self.webhook_url),
            message="ok" if self.webhook_url else "webhook_url not configured")
