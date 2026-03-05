"""
Model Registry API — serves vendored pricing data to the dashboard.

Endpoints:
    GET  /api/models              — full registry (filterable)
    GET  /api/models/tiers        — tier summary + grouped models
    GET  /api/models/search       — search/filter by name, provider, tier, cost range
    GET  /api/models/providers    — list of all providers
    GET  /api/models/{model_id}   — single model details

Replaces the hardcoded dashboard/js/models.js 42-model array with
a dynamic API backed by 2,610+ vendored model prices.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query

logger = logging.getLogger("agentcost.api.models")
router = APIRouter(prefix="/api/models", tags=["models"])


def _get_registry():
    """Lazy import to avoid circular deps."""
    from .calculator import get_model_registry_for_dashboard
    return get_model_registry_for_dashboard


def _get_tier_registry():
    from ..intelligence.tier_registry import get_tier_registry
    return get_tier_registry()


# ── Full Registry ─────────────────────────────────────────────────────────────


@router.get("")
async def list_models(
    provider: Optional[str] = Query(None, description="Filter by provider (e.g., openai, anthropic)"),
    tier: Optional[str] = Query(None, description="Filter by tier (economy, standard, premium, free)"),
    mode: Optional[str] = Query(None, description="Filter by mode (chat, completion, embedding)"),
    limit: int = Query(100, ge=1, le=5000, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    sort: str = Query("input_asc", description="Sort: input_asc, input_desc, name, provider"),
):
    """List all models from the vendored pricing data.

    Returns the same format as the old dashboard/js/models.js MODEL_REGISTRY
    but powered by the full 2,610+ model dataset.
    """
    get_fn = _get_registry()
    providers = [provider] if provider else None
    tiers = [tier] if tier else None
    models = get_fn(providers=providers, tiers=tiers)

    # Mode filter
    if mode:
        models = [m for m in models if m.get("mode", "chat") == mode]

    # Sort
    if sort == "input_asc":
        models.sort(key=lambda m: m.get("input", 0))
    elif sort == "input_desc":
        models.sort(key=lambda m: m.get("input", 0), reverse=True)
    elif sort == "name":
        models.sort(key=lambda m: m.get("id", ""))
    elif sort == "provider":
        models.sort(key=lambda m: (m.get("provider", ""), m.get("input", 0)))

    total = len(models)
    models = models[offset:offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "models": models,
    }


# ── Tier Summary ──────────────────────────────────────────────────────────────


@router.get("/tiers")
async def get_tiers(
    limit_per_tier: int = Query(50, ge=1, le=500, description="Max models per tier"),
):
    """Tier summary with grouped models — for dashboard tier visualization."""
    reg = _get_tier_registry()
    return reg.to_dashboard_data(limit_per_tier=limit_per_tier)


# ── Search / Filter ───────────────────────────────────────────────────────────


@router.get("/search")
async def search_models(
    q: str = Query("", description="Search by model name (substring match)"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    tier: Optional[str] = Query(None, description="Filter by tier"),
    min_input: Optional[float] = Query(None, description="Min input cost per 1M tokens"),
    max_input: Optional[float] = Query(None, description="Max input cost per 1M tokens"),
    min_context: Optional[int] = Query(None, description="Min context window (K tokens)"),
    limit: int = Query(50, ge=1, le=500),
):
    """Search and filter models by name, provider, tier, cost range, context size.

    Designed for the dashboard model explorer with real-time search.
    """
    get_fn = _get_registry()
    models = get_fn()

    # Text search
    if q:
        q_lower = q.lower()
        models = [m for m in models if q_lower in m["id"].lower() or q_lower in m.get("provider", "").lower()]

    # Provider filter
    if provider:
        models = [m for m in models if m.get("provider", "").lower() == provider.lower()]

    # Tier filter
    if tier:
        models = [m for m in models if m.get("tier", "") == tier]

    # Cost range filter
    if min_input is not None:
        models = [m for m in models if m.get("input", 0) >= min_input]
    if max_input is not None:
        models = [m for m in models if m.get("input", 0) <= max_input]

    # Context window filter
    if min_context is not None:
        models = [m for m in models if m.get("context", 0) >= min_context]

    # Sort by input cost ascending
    models.sort(key=lambda m: m.get("input", 0))

    total = len(models)
    models = models[:limit]

    return {
        "total": total,
        "query": q,
        "filters": {
            "provider": provider,
            "tier": tier,
            "min_input": min_input,
            "max_input": max_input,
            "min_context": min_context,
        },
        "models": models,
    }


# ── Providers List ────────────────────────────────────────────────────────────


@router.get("/providers")
async def list_providers():
    """List all unique providers and model counts."""
    get_fn = _get_registry()
    models = get_fn()
    providers: dict[str, int] = {}
    for m in models:
        p = m.get("provider", "unknown")
        providers[p] = providers.get(p, 0) + 1
    return {
        "providers": [
            {"name": p, "model_count": c}
            for p, c in sorted(providers.items(), key=lambda x: -x[1])
        ]
    }


# ── Single Model ──────────────────────────────────────────────────────────────


@router.get("/{model_id:path}")
async def get_model(model_id: str):
    """Get detailed info for a single model including tier classification."""
    from .calculator import get_model_info, get_pricing_per_1m

    info = get_model_info(model_id)
    if not info:
        return {"error": f"Model not found: {model_id}"}

    pricing = get_pricing_per_1m(model_id)
    reg = _get_tier_registry()
    tier_info = reg.get_tier_info(model_id)

    return {
        "id": model_id,
        "provider": info.get("litellm_provider", "unknown"),
        "pricing_per_1m": pricing,
        "tier": tier_info.tier.value if tier_info else "unknown",
        "max_input_tokens": info.get("max_input_tokens", 0),
        "max_output_tokens": info.get("max_output_tokens", 0),
        "mode": info.get("mode", "chat"),
        "supports_vision": info.get("supports_vision", False),
        "supports_function_calling": info.get("supports_function_calling", False),
    }
