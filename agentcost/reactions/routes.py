"""
Reaction Engine API Routes — manage and query event-driven automations.

Endpoints:
    GET  /reactions/               — list all configured reactions
    GET  /reactions/{name}         — get a specific reaction
    POST /reactions/               — add/update a reaction
    DELETE /reactions/{name}       — remove a reaction
    POST /reactions/{name}/enable  — enable a reaction
    POST /reactions/{name}/disable — disable a reaction
    POST /reactions/{name}/reset-cooldown — clear cooldown timer
    POST /reactions/{name}/trigger — manually trigger a reaction
    GET  /reactions/history        — reaction execution history
    GET  /reactions/stats          — engine statistics
    POST /reactions/reload         — reload from YAML config
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("agentcost.reactions.routes")


def create_reaction_routes():
    """Create FastAPI router for reaction endpoints."""
    try:
        from fastapi import APIRouter, HTTPException, Body
    except ImportError:
        return None

    router = APIRouter(prefix="/reactions", tags=["reactions"])

    def _get_engine():
        from ..reactions import get_reaction_engine

        return get_reaction_engine()

    # ── List / Get ──────────────────────────────────────────────

    @router.get("/")
    def list_reactions():
        """List all configured reactions."""
        engine = _get_engine()
        return {
            "reactions": [
                {
                    "name": r.name,
                    "auto": r.auto,
                    "enabled": r.enabled,
                    "actions": r.actions,
                    "condition": r.condition,
                    "cooldown_seconds": r.cooldown_seconds,
                    "escalate_after_seconds": r.escalate_after_seconds,
                }
                for r in engine.reactions.values()
            ],
            "count": len(engine.reactions),
        }

    @router.get("/stats")
    def reaction_stats():
        """Get reaction engine statistics."""
        return _get_engine().stats

    @router.get("/history")
    def reaction_history(limit: int = 50):
        """Get recent reaction execution history."""
        return {"history": _get_engine().get_history(limit=limit)}

    @router.get("/{name}")
    def get_reaction(name: str):
        """Get a specific reaction by name."""
        engine = _get_engine()
        r = engine.reactions.get(name)
        if not r:
            raise HTTPException(status_code=404, detail=f"Reaction '{name}' not found")
        return {
            "name": r.name,
            "auto": r.auto,
            "enabled": r.enabled,
            "actions": r.actions,
            "condition": r.condition,
            "cooldown_seconds": r.cooldown_seconds,
            "escalate_after_seconds": r.escalate_after_seconds,
            "retries": r.retries,
        }

    # ── Create / Update ─────────────────────────────────────────

    @router.post("/")
    def add_reaction(body: dict = Body(...)):
        """Add or update a reaction."""
        name = body.get("name")
        if not name:
            raise HTTPException(status_code=400, detail="'name' is required")
        engine = _get_engine()
        reaction = engine.add_reaction(name, body)
        return {
            "status": "created",
            "reaction": {
                "name": reaction.name,
                "auto": reaction.auto,
                "actions": reaction.actions,
                "enabled": reaction.enabled,
            },
        }

    # ── Delete ──────────────────────────────────────────────────

    @router.delete("/{name}")
    def delete_reaction(name: str):
        """Remove a reaction."""
        engine = _get_engine()
        if engine.remove_reaction(name):
            return {"status": "deleted", "name": name}
        raise HTTPException(status_code=404, detail=f"Reaction '{name}' not found")

    # ── Enable / Disable ────────────────────────────────────────

    @router.post("/{name}/enable")
    def enable_reaction(name: str):
        engine = _get_engine()
        if engine.enable_reaction(name):
            return {"status": "enabled", "name": name}
        raise HTTPException(status_code=404, detail=f"Reaction '{name}' not found")

    @router.post("/{name}/disable")
    def disable_reaction(name: str):
        engine = _get_engine()
        if engine.disable_reaction(name):
            return {"status": "disabled", "name": name}
        raise HTTPException(status_code=404, detail=f"Reaction '{name}' not found")

    # ── Cooldown Reset ──────────────────────────────────────────

    @router.post("/{name}/reset-cooldown")
    def reset_cooldown(name: str):
        engine = _get_engine()
        if engine.reset_cooldown(name):
            return {"status": "cooldown_reset", "name": name}
        return {"status": "no_cooldown", "name": name}

    # ── Manual Trigger ──────────────────────────────────────────

    @router.post("/{name}/trigger")
    def trigger_reaction(name: str, body: dict = Body(default={})):
        """Manually trigger a reaction with custom event data."""
        engine = _get_engine()
        reaction = engine.reactions.get(name)
        if not reaction:
            raise HTTPException(status_code=404, detail=f"Reaction '{name}' not found")

        event_type = body.get("event_type", name.replace("-", "."))
        event_data = body.get("data", body)

        result = engine.execute(reaction, event_type, event_data)
        return {
            "status": "triggered",
            "result": result.to_dict(),
        }

    # ── Reload ──────────────────────────────────────────────────

    @router.post("/reload")
    def reload_reactions(body: dict = Body(default={})):
        """Reload reactions from YAML config."""
        config_path = body.get("config_path")
        engine = _get_engine()
        count = engine.reload(config_path)
        return {"status": "reloaded", "reaction_count": count}

    return router
