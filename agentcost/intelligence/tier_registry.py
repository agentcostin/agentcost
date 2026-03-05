"""
Cost-Tier Registry — classify every model into economy/standard/premium.

Tiers are assigned automatically from vendored pricing data:
    economy   — input cost < $0.50 per 1M tokens
    standard  — input cost $0.50 – $5.00 per 1M tokens
    premium   — input cost > $5.00 per 1M tokens

Tiers integrate with:
    - Policy engine (restrict agents to specific tiers)
    - Smart router (route by tier instead of model name)
    - Budget gates (block premium tier when budget is low)
    - Dashboard (group models by tier)

Usage:
    from agentcost.intelligence import TierRegistry, CostTier, get_tier_registry

    reg = get_tier_registry()
    tier = reg.classify("gpt-4o")          # CostTier.STANDARD
    models = reg.models_in_tier("economy") # ["gpt-4o-mini", "gpt-3.5-turbo", ...]
    allowed = reg.check_tier_policy("gpt-4o", allowed_tiers=["economy", "standard"])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("agentcost.intelligence.tiers")


class CostTier(str, Enum):
    """Model cost tiers based on input token pricing."""

    ECONOMY = "economy"
    STANDARD = "standard"
    PREMIUM = "premium"
    FREE = "free"
    UNKNOWN = "unknown"


# Thresholds in cost per 1M input tokens (USD)
DEFAULT_THRESHOLDS = {
    "economy_max": 0.50,    # < $0.50/1M → economy
    "standard_max": 5.00,   # $0.50 – $5.00/1M → standard
    # > $5.00/1M → premium
}


@dataclass
class TierInfo:
    """Tier classification result for a single model."""

    model: str
    tier: CostTier
    input_cost_per_1m: float
    output_cost_per_1m: float
    provider: str = ""
    max_context: int = 0


@dataclass
class TierPolicy:
    """Policy rules for tier-based access control."""

    allowed_tiers: list[str] = field(default_factory=lambda: ["economy", "standard", "premium"])
    max_cost_per_call: float = 0.0  # 0 = no limit
    require_approval_for: list[str] = field(default_factory=list)  # tiers requiring approval


class TierRegistry:
    """Classifies models into cost tiers from vendored pricing data.

    Automatically loads and classifies all 2,600+ models on first use.
    Supports custom thresholds and tier overrides.
    """

    def __init__(
        self,
        thresholds: dict | None = None,
        overrides: dict[str, str] | None = None,
    ):
        self._thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._overrides: dict[str, str] = overrides or {}  # model → tier name
        self._cache: dict[str, TierInfo] = {}
        self._loaded = False

    def _ensure_loaded(self):
        """Lazy-load tier classifications from cost calculator."""
        if self._loaded:
            return
        try:
            from ..cost import calculator as calc_mod

            calc_mod._ensure_loaded()

            # Merge all pricing sources (access through module to get updated refs)
            all_models = {}
            all_models.update(calc_mod._COST_MAP)
            all_models.update(calc_mod._OVERRIDES)
            all_models.update(calc_mod._RUNTIME_OVERRIDES)

            for name, info in all_models.items():
                if not isinstance(info, dict):
                    continue
                input_cost = info.get("input_cost_per_token", 0)
                output_cost = info.get("output_cost_per_token", 0)
                if input_cost == 0 and output_cost == 0:
                    # Skip non-chat models (embeddings, images, audio, etc.)
                    mode = info.get("mode", "")
                    if mode and mode not in ("chat", "completion"):
                        continue

                self._cache[name] = TierInfo(
                    model=name,
                    tier=self._classify_by_price(name, input_cost * 1_000_000),
                    input_cost_per_1m=round(input_cost * 1_000_000, 4),
                    output_cost_per_1m=round(output_cost * 1_000_000, 4),
                    provider=info.get("litellm_provider", ""),
                    max_context=info.get("max_input_tokens", 0) or info.get("max_tokens", 0),
                )
        except Exception as e:
            logger.warning("Failed to load tier data: %s", e)

        self._loaded = True

    def _classify_by_price(self, model: str, input_cost_per_1m: float) -> CostTier:
        """Classify a model by its input cost per 1M tokens."""
        # Check manual overrides first
        if model in self._overrides:
            try:
                return CostTier(self._overrides[model])
            except ValueError:
                pass

        if input_cost_per_1m == 0:
            return CostTier.FREE

        economy_max = self._thresholds["economy_max"]
        standard_max = self._thresholds["standard_max"]

        if input_cost_per_1m < economy_max:
            return CostTier.ECONOMY
        elif input_cost_per_1m <= standard_max:
            return CostTier.STANDARD
        else:
            return CostTier.PREMIUM

    # ── Public API ────────────────────────────────────────────────

    def classify(self, model: str) -> CostTier:
        """Get the cost tier for a model."""
        self._ensure_loaded()
        info = self._cache.get(model)
        if info:
            return info.tier

        # Try resolving through the cost calculator
        try:
            from ..cost.calculator import get_pricing_per_1m

            pricing = get_pricing_per_1m(model)
            if pricing.get("input_per_1m", 0) > 0:
                tier = self._classify_by_price(model, pricing["input_per_1m"])
                self._cache[model] = TierInfo(
                    model=model,
                    tier=tier,
                    input_cost_per_1m=pricing.get("input_per_1m", 0),
                    output_cost_per_1m=pricing.get("output_per_1m", 0),
                )
                return tier
        except Exception:
            pass

        return CostTier.UNKNOWN

    def get_tier_info(self, model: str) -> TierInfo | None:
        """Get full tier info including pricing for a model."""
        self._ensure_loaded()
        info = self._cache.get(model)
        if info:
            return info
        # Trigger classify to populate cache
        tier = self.classify(model)
        return self._cache.get(model)

    def models_in_tier(self, tier: str, provider: str | None = None) -> list[str]:
        """List all models in a specific tier, optionally filtered by provider."""
        self._ensure_loaded()
        results = []
        for name, info in self._cache.items():
            if info.tier.value == tier:
                if provider and info.provider != provider:
                    continue
                results.append(name)
        return sorted(results)

    def tier_summary(self) -> dict[str, int]:
        """Count of models per tier."""
        self._ensure_loaded()
        counts: dict[str, int] = {}
        for info in self._cache.values():
            counts[info.tier.value] = counts.get(info.tier.value, 0) + 1
        return counts

    def cheapest_in_tier(
        self, tier: str, provider: str | None = None, min_context: int = 0
    ) -> TierInfo | None:
        """Find the cheapest model in a tier meeting constraints."""
        self._ensure_loaded()
        candidates = []
        for info in self._cache.values():
            if info.tier.value != tier:
                continue
            if provider and info.provider != provider:
                continue
            if min_context and info.max_context < min_context:
                continue
            candidates.append(info)

        if not candidates:
            return None
        return min(candidates, key=lambda x: x.input_cost_per_1m)

    def check_tier_policy(
        self, model: str, allowed_tiers: list[str] | None = None,
        max_cost_per_call: float = 0, estimated_tokens: int = 0,
    ) -> dict:
        """Check if a model is allowed under tier policy rules.

        Returns:
            {
                "allowed": bool,
                "tier": str,
                "reason": str,
                "estimated_cost": float (if tokens provided),
                "suggested_alternative": str | None,
            }
        """
        tier = self.classify(model)
        info = self._cache.get(model)

        result: dict = {
            "allowed": True,
            "tier": tier.value,
            "reason": "ok",
            "estimated_cost": 0.0,
            "suggested_alternative": None,
        }

        # Tier restriction check
        if allowed_tiers and tier.value not in allowed_tiers:
            result["allowed"] = False
            result["reason"] = (
                f"Model '{model}' is in '{tier.value}' tier, "
                f"but only {allowed_tiers} are allowed"
            )
            # Suggest a cheaper alternative
            for fallback_tier in ["economy", "standard", "premium"]:
                if fallback_tier in allowed_tiers:
                    alt = self.cheapest_in_tier(
                        fallback_tier,
                        provider=info.provider if info else None,
                    )
                    if alt:
                        result["suggested_alternative"] = alt.model
                    break
            return result

        # Cost-per-call check
        if max_cost_per_call > 0 and estimated_tokens > 0 and info:
            est_cost = (info.input_cost_per_1m / 1_000_000) * estimated_tokens
            result["estimated_cost"] = round(est_cost, 6)
            if est_cost > max_cost_per_call:
                result["allowed"] = False
                result["reason"] = (
                    f"Estimated cost ${est_cost:.4f} exceeds "
                    f"max ${max_cost_per_call:.4f} per call"
                )

        return result

    def set_override(self, model: str, tier: str) -> None:
        """Manually override the tier for a specific model."""
        self._overrides[model] = tier
        if model in self._cache:
            self._cache[model].tier = CostTier(tier)

    def get_thresholds(self) -> dict:
        """Return current tier thresholds."""
        return dict(self._thresholds)

    def set_thresholds(self, thresholds: dict) -> None:
        """Update tier thresholds and reclassify all models."""
        self._thresholds.update(thresholds)
        self._loaded = False
        self._cache.clear()

    def to_dashboard_data(self, limit_per_tier: int = 50) -> dict:
        """Export tier data for the dashboard API.

        Returns a dict suitable for the /api/models/tiers endpoint.
        """
        self._ensure_loaded()
        data: dict = {
            "thresholds": self._thresholds,
            "summary": self.tier_summary(),
            "tiers": {},
        }
        for tier_name in ["economy", "standard", "premium", "free"]:
            models = []
            for info in sorted(
                (i for i in self._cache.values() if i.tier.value == tier_name),
                key=lambda x: x.input_cost_per_1m,
            ):
                models.append({
                    "model": info.model,
                    "provider": info.provider,
                    "input_cost_per_1m": info.input_cost_per_1m,
                    "output_cost_per_1m": info.output_cost_per_1m,
                    "max_context": info.max_context,
                })
                if len(models) >= limit_per_tier:
                    break
            data["tiers"][tier_name] = models
        return data


# ── Singleton ─────────────────────────────────────────────────────────────────

_global_registry: Optional[TierRegistry] = None


def get_tier_registry() -> TierRegistry:
    """Get or create the global tier registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = TierRegistry()
    return _global_registry
