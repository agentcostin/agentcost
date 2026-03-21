"""
Simulator API Routes — Backend endpoints for the Live Cost Simulator.

Endpoints:
    GET  /api/simulator/baseline        — Real metrics from trace data
    GET  /api/simulator/config          — Architecture auto-detection
    GET  /api/simulator/scenarios        — List saved scenarios
    POST /api/simulator/scenarios        — Save a scenario
    GET  /api/simulator/scenarios/{id}   — Get a specific scenario
    PUT  /api/simulator/scenarios/{id}   — Update a scenario
    DELETE /api/simulator/scenarios/{id} — Delete a scenario
    POST /api/simulator/whatif           — Run a what-if projection
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Request

from ..edition import ENTERPRISE

# Conditional auth import (same pattern as other routes)
try:
    if ENTERPRISE:
        from ..auth.dependencies import get_optional_user
        from ..auth.models import AuthContext
    else:
        raise ImportError
except ImportError:
    from ..community_auth import get_optional_user, AuthContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/simulator", tags=["simulator"])


# ── Baseline Metrics ─────────────────────────────────────────────────────────


@router.get("/baseline")
async def get_baseline(
    project: str | None = None,
    hours: int = 24,
    user: AuthContext = Depends(get_optional_user),
):
    """Get real baseline metrics from trace data for simulator seeding.

    Returns avg RPS, cost/hour, token counts, model distribution,
    cache stats, and simulator-ready default values.
    """
    from .baseline import get_baseline_metrics

    return get_baseline_metrics(project=project, hours=hours)


@router.get("/config")
async def get_config(user: AuthContext = Depends(get_optional_user)):
    """Auto-detect architecture configuration from real data.

    Scans trace data, gateway, cache, and budgets to build
    a realistic architecture diagram for the simulator.
    """
    from .baseline import get_architecture_config

    return get_architecture_config()


# ── What-If Projection ──────────────────────────────────────────────────────


@router.post("/whatif")
async def run_whatif(
    request: Request,
    user: AuthContext = Depends(get_optional_user),
):
    """Run a what-if cost projection.

    Accepts a JSON body with:
    - project: str (optional, defaults to all)
    - hours: int (baseline window, default 24)
    - days: int (projection days, default 30)
    - changes: dict with:
        - price_multiplier: float (e.g., 2.0 for 2× price increase)
        - cache_hit_rate: float (e.g., 0.85)
        - traffic_multiplier: float (e.g., 1.5)
        - tokens_per_request: int
    """
    from .baseline import get_baseline_metrics, compute_whatif_projection

    body = await request.json()
    project = body.get("project")
    hours = body.get("hours", 24)
    days = body.get("days", 30)
    changes = body.get("changes", {})

    baseline = get_baseline_metrics(project=project, hours=hours)
    projection = compute_whatif_projection(baseline, changes, days=days)

    return projection


# ── Scenario CRUD ────────────────────────────────────────────────────────────


@router.get("/scenarios")
async def list_scenarios(user: AuthContext = Depends(get_optional_user)):
    """List all saved simulation scenarios (user's + templates)."""
    from .store import SimulatorStore

    store = SimulatorStore()
    org_id = getattr(user, "org_id", "default") if user else "default"
    return store.list_scenarios(org_id=org_id)


@router.post("/scenarios")
async def save_scenario(
    request: Request,
    user: AuthContext = Depends(get_optional_user),
):
    """Save a simulation scenario.

    Accepts JSON body with:
    - name: str (required)
    - description: str (optional)
    - chaos_events: list[str] — event IDs
    - traffic: int (0-100)
    - budget: float
    - architecture: dict (optional, node overrides)
    - results: dict (optional, simulation results to save)
    - tags: list[str] (optional)
    """
    from .store import SimulatorStore

    body = await request.json()
    store = SimulatorStore()
    org_id = getattr(user, "org_id", "default") if user else "default"
    user_name = getattr(user, "name", None) or getattr(user, "email", None) if user else None

    result = store.save_scenario(
        name=body["name"],
        chaos_events=body.get("chaos_events", []),
        traffic=body.get("traffic", 50),
        budget=body.get("budget", 5000),
        description=body.get("description"),
        architecture=body.get("architecture"),
        results=body.get("results"),
        tags=body.get("tags"),
        org_id=org_id,
        created_by=user_name,
    )
    return result


@router.get("/scenarios/{scenario_id}")
async def get_scenario(
    scenario_id: int,
    user: AuthContext = Depends(get_optional_user),
):
    """Get a specific saved scenario."""
    from .store import SimulatorStore

    store = SimulatorStore()
    org_id = getattr(user, "org_id", "default") if user else "default"
    scenario = store.get_scenario(scenario_id, org_id=org_id)
    if not scenario:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"error": "Scenario not found"})
    return scenario


@router.put("/scenarios/{scenario_id}")
async def update_scenario(
    scenario_id: int,
    request: Request,
    user: AuthContext = Depends(get_optional_user),
):
    """Update an existing scenario."""
    from .store import SimulatorStore

    body = await request.json()
    store = SimulatorStore()
    org_id = getattr(user, "org_id", "default") if user else "default"

    result = store.update_scenario(scenario_id, org_id=org_id, **body)
    if not result:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"error": "Scenario not found"})
    return result


@router.delete("/scenarios/{scenario_id}")
async def delete_scenario(
    scenario_id: int,
    user: AuthContext = Depends(get_optional_user),
):
    """Delete a saved scenario (templates cannot be deleted)."""
    from .store import SimulatorStore

    store = SimulatorStore()
    org_id = getattr(user, "org_id", "default") if user else "default"
    store.delete_scenario(scenario_id, org_id=org_id)
    return {"status": "ok", "deleted": scenario_id}
