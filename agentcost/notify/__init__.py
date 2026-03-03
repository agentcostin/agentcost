"""
AgentCost Notify — Notification Channels & Agent Scorecards (Block 5, Phase 3)

Provides:
  - Notification channel CRUD (Slack, email, webhook, PagerDuty)
  - Event routing — subscribe channels to specific event types
  - Notification dispatch (fire events to matching channels)
  - Agent scorecard generation from trace data
  - Scorecard comparison and recommendation engine

Usage:
    from agentcost.notify import ChannelService, Dispatcher, ScorecardService
"""

from .channel_service import ChannelService
from .dispatcher import Dispatcher
from .scorecard_service import ScorecardService

__all__ = [
    "ChannelService",
    "Dispatcher",
    "ScorecardService",
]
