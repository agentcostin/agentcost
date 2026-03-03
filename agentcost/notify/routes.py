"""
Notify Routes — FastAPI router for notifications & scorecards (Block 5).

Endpoints:
  Channels:
    POST   /notify/channels              → Create notification channel
    GET    /notify/channels              → List channels
    GET    /notify/channels/{id}         → Get channel
    PUT    /notify/channels/{id}         → Update channel
    PUT    /notify/channels/{id}/toggle  → Enable/disable channel
    DELETE /notify/channels/{id}         → Delete channel
    POST   /notify/channels/{id}/test    → Send test notification

  Dispatch:
    POST   /notify/send                  → Dispatch event to matching channels

  Scorecards:
    POST   /notify/scorecards/generate       → Generate scorecard for an agent
    POST   /notify/scorecards/generate-all   → Generate scorecards for all agents
    GET    /notify/scorecards/agents         → List agents with trace data
    GET    /notify/scorecards/period         → Leaderboard for a period
    GET    /notify/scorecards/{agent_id}     → Scorecard history for an agent
    POST   /notify/scorecards/compare        → Compare agents side-by-side
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth.dependencies import get_current_user, require_role
from ..auth.models import AuthContext, Role

logger = logging.getLogger("agentcost.notify.routes")

notify_router = APIRouter(prefix="/notify", tags=["notify"])


# ── Request Models ───────────────────────────────────────────────────────────

class ChannelCreate(BaseModel):
    channel_type: str
    name: str
    config: dict
    events: str = "*"
    enabled: bool = True

class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    events: Optional[str] = None
    enabled: Optional[bool] = None

class ChannelToggle(BaseModel):
    enabled: bool

class DispatchEvent(BaseModel):
    event_type: str
    message: str = ""
    details: Optional[dict] = None

class ScorecardGenerate(BaseModel):
    agent_id: str
    period: Optional[str] = None

class ScorecardCompare(BaseModel):
    agent_ids: list[str]
    period: Optional[str] = None


# ── Service factories ────────────────────────────────────────────────────────

def _channel_svc():
    from .channel_service import ChannelService
    return ChannelService()

def _dispatcher():
    from .dispatcher import Dispatcher
    return Dispatcher()

def _scorecard_svc():
    from .scorecard_service import ScorecardService
    return ScorecardService()

def _audit_svc():
    from ..org.audit_service import AuditService
    return AuditService()


# ─────────────────────────────────────────────────────────────────────────────
# CHANNEL ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@notify_router.post("/channels")
async def create_channel(
    body: ChannelCreate,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Create a notification channel. Requires org_admin."""
    svc = _channel_svc()
    audit = _audit_svc()
    result = svc.create(
        org_id=user.org_id, channel_type=body.channel_type,
        name=body.name, config=body.config,
        events=body.events, enabled=body.enabled,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])

    audit.log(
        event_type="notification.channel.create", org_id=user.org_id,
        actor_id=user.user_id, resource_type="notification_channel",
        resource_id=result.get("id", ""), action="create",
        details={"name": body.name, "type": body.channel_type},
    )
    return result


@notify_router.get("/channels")
async def list_channels(
    enabled_only: bool = False,
    user: AuthContext = Depends(get_current_user),
):
    """List notification channels."""
    svc = _channel_svc()
    return svc.list(user.org_id, enabled_only=enabled_only)


@notify_router.get("/channels/{ch_id}")
async def get_channel(
    ch_id: str,
    user: AuthContext = Depends(get_current_user),
):
    """Get a specific channel."""
    svc = _channel_svc()
    ch = svc.get(ch_id, user.org_id)
    if not ch:
        raise HTTPException(404, "Channel not found")
    return ch


@notify_router.put("/channels/{ch_id}")
async def update_channel(
    ch_id: str,
    body: ChannelUpdate,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Update a channel. Requires org_admin."""
    svc = _channel_svc()
    result = svc.update(ch_id, user.org_id, **body.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(404, "Channel not found")
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@notify_router.put("/channels/{ch_id}/toggle")
async def toggle_channel(
    ch_id: str,
    body: ChannelToggle,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Enable or disable a channel."""
    svc = _channel_svc()
    result = svc.toggle(ch_id, user.org_id, body.enabled)
    if not result:
        raise HTTPException(404, "Channel not found")
    return result


@notify_router.delete("/channels/{ch_id}")
async def delete_channel(
    ch_id: str,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Delete a channel. Requires org_admin."""
    svc = _channel_svc()
    audit = _audit_svc()
    result = svc.delete(ch_id, user.org_id)
    audit.log(
        event_type="notification.channel.delete", org_id=user.org_id,
        actor_id=user.user_id, resource_type="notification_channel",
        resource_id=ch_id, action="delete",
    )
    return result


@notify_router.post("/channels/{ch_id}/test")
async def test_channel(
    ch_id: str,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Send a test notification to verify channel configuration."""
    svc = _channel_svc()
    return svc.test_channel(ch_id, user.org_id)


# ─────────────────────────────────────────────────────────────────────────────
# DISPATCH ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

@notify_router.post("/send")
async def dispatch_event(
    body: DispatchEvent,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Dispatch a notification event to all matching channels."""
    d = _dispatcher()
    event_data = {"message": body.message}
    if body.details:
        event_data["details"] = body.details
    return d.dispatch(user.org_id, body.event_type, event_data)


# ─────────────────────────────────────────────────────────────────────────────
# SCORECARD ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@notify_router.post("/scorecards/generate")
async def generate_scorecard(
    body: ScorecardGenerate,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Generate a scorecard for a specific agent."""
    svc = _scorecard_svc()
    return svc.generate(user.org_id, body.agent_id, body.period)


@notify_router.post("/scorecards/generate-all")
async def generate_all_scorecards(
    period: Optional[str] = None,
    user: AuthContext = Depends(require_role(Role.ORG_ADMIN)),
):
    """Generate scorecards for ALL agents in the org."""
    svc = _scorecard_svc()
    return svc.generate_all(user.org_id, period)


@notify_router.get("/scorecards/agents")
async def list_agents(
    user: AuthContext = Depends(get_current_user),
):
    """List all agents with trace data in this org."""
    svc = _scorecard_svc()
    agents = svc.get_agents(user.org_id)
    return {"agents": agents, "total": len(agents)}


@notify_router.get("/scorecards/period")
async def scorecards_for_period(
    period: Optional[str] = None,
    user: AuthContext = Depends(get_current_user),
):
    """Get all agent scorecards for a period (leaderboard)."""
    svc = _scorecard_svc()
    return svc.list_for_period(user.org_id, period)


@notify_router.get("/scorecards/{agent_id}")
async def scorecard_history(
    agent_id: str,
    limit: int = 12,
    user: AuthContext = Depends(get_current_user),
):
    """Get scorecard history for an agent (most recent first)."""
    svc = _scorecard_svc()
    return svc.list_for_agent(user.org_id, agent_id, limit)


@notify_router.post("/scorecards/compare")
async def compare_agents(
    body: ScorecardCompare,
    user: AuthContext = Depends(get_current_user),
):
    """Compare multiple agents side-by-side."""
    svc = _scorecard_svc()
    if len(body.agent_ids) < 2:
        raise HTTPException(400, "Provide at least 2 agent IDs to compare")
    return svc.compare(user.org_id, body.agent_ids, body.period)
