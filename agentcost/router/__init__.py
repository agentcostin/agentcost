"""
AgentCost Smart Model Router — Phase 6 Block 2

Automatically routes LLM requests to the cheapest model that meets a quality
threshold based on historical benchmark data.

Usage:
    from agentcost.router import ModelRouter

    router = ModelRouter()
    router.add_model("gpt-4o", cost_per_1k=0.0025, quality=0.85, latency_p50=800)
    router.add_model("gpt-4o-mini", cost_per_1k=0.000075, quality=0.78, latency_p50=400)
    router.add_model("llama3:8b", cost_per_1k=0.0, quality=0.72, latency_p50=600)

    # Get cheapest model with quality >= 0.75
    model = router.route(min_quality=0.75)
    # Returns: "gpt-4o-mini" (cheapest that meets threshold)

    # With latency constraint
    model = router.route(min_quality=0.80, max_latency_ms=1000)
    # Returns: "gpt-4o"

    # Fallback chain
    model = router.route(min_quality=0.75, fallback="gpt-4o")
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import time
import random


@dataclass
class ModelProfile:
    """Performance profile for a model."""
    name: str
    cost_per_1k_tokens: float  # cost per 1K total tokens
    quality_score: float  # 0-1 quality from benchmarks
    latency_p50_ms: float  # median latency in ms
    latency_p99_ms: float = 0  # p99 latency
    max_context: int = 128000  # max context window
    supports_json: bool = True
    supports_vision: bool = False
    supports_tools: bool = True
    available: bool = True
    error_rate: float = 0.0  # recent error rate 0-1
    tags: List[str] = field(default_factory=list)  # e.g. ["fast", "code", "creative"]

    @property
    def cost_efficiency(self) -> float:
        """Quality per dollar (higher is better)."""
        if self.cost_per_1k_tokens == 0:
            return float('inf') if self.quality_score > 0 else 0
        return self.quality_score / self.cost_per_1k_tokens

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "cost_per_1k_tokens": self.cost_per_1k_tokens,
            "quality_score": round(self.quality_score, 3),
            "latency_p50_ms": self.latency_p50_ms,
            "cost_efficiency": round(self.cost_efficiency, 2) if self.cost_efficiency != float('inf') else "∞",
            "available": self.available,
            "error_rate": round(self.error_rate, 3),
            "tags": self.tags,
        }


@dataclass
class RoutingDecision:
    """Result of a routing decision."""
    model: str
    reason: str
    alternatives: List[str]
    constraints_applied: Dict[str, any]
    cost_savings_vs_best: float  # % saved vs highest-quality model

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "reason": self.reason,
            "alternatives": self.alternatives,
            "constraints": self.constraints_applied,
            "cost_savings_pct": round(self.cost_savings_vs_best, 1),
        }


class ModelRouter:
    """
    Smart model router that selects the optimal model based on constraints.

    Routing strategies:
        - cheapest: Cheapest model meeting quality threshold (default)
        - quality: Highest quality within budget
        - balanced: Best quality/cost ratio
        - latency: Fastest model meeting quality threshold
    """

    def __init__(self):
        self._models: Dict[str, ModelProfile] = {}
        self._routing_log: List[dict] = []

    def add_model(self, name: str, cost_per_1k: float = 0.0,
                  quality: float = 0.5, latency_p50: float = 500,
                  **kwargs) -> ModelProfile:
        """Register a model with its performance profile."""
        profile = ModelProfile(
            name=name,
            cost_per_1k_tokens=cost_per_1k,
            quality_score=quality,
            latency_p50_ms=latency_p50,
            **kwargs,
        )
        self._models[name] = profile
        return profile

    def update_model(self, name: str, **kwargs):
        """Update model profile fields."""
        if name not in self._models:
            raise KeyError(f"Model not found: {name}")
        profile = self._models[name]
        for k, v in kwargs.items():
            if hasattr(profile, k):
                setattr(profile, k, v)

    def remove_model(self, name: str):
        """Remove a model from the router."""
        self._models.pop(name, None)

    def set_available(self, name: str, available: bool):
        """Mark a model as available/unavailable (e.g., after errors)."""
        if name in self._models:
            self._models[name].available = available

    @property
    def models(self) -> Dict[str, ModelProfile]:
        return dict(self._models)

    @property
    def routing_log(self) -> List[dict]:
        return list(self._routing_log[-100:])

    def route(self, min_quality: float = 0.0, max_latency_ms: float = None,
              max_cost_per_1k: float = None, strategy: str = "cheapest",
              require_tags: List[str] = None, require_json: bool = False,
              require_vision: bool = False, require_tools: bool = False,
              fallback: str = None) -> RoutingDecision:
        """
        Route to optimal model based on constraints.

        Args:
            min_quality: Minimum quality score (0-1)
            max_latency_ms: Maximum acceptable p50 latency
            max_cost_per_1k: Maximum cost per 1K tokens
            strategy: 'cheapest', 'quality', 'balanced', 'latency'
            require_tags: Required model tags
            require_json: Must support JSON mode
            require_vision: Must support vision
            require_tools: Must support tool calling
            fallback: Fallback model if no match found

        Returns:
            RoutingDecision with selected model and reasoning
        """
        candidates = self._filter_candidates(
            min_quality=min_quality,
            max_latency_ms=max_latency_ms,
            max_cost_per_1k=max_cost_per_1k,
            require_tags=require_tags,
            require_json=require_json,
            require_vision=require_vision,
            require_tools=require_tools,
        )

        constraints = {
            "min_quality": min_quality,
            "max_latency_ms": max_latency_ms,
            "max_cost_per_1k": max_cost_per_1k,
            "strategy": strategy,
        }

        if not candidates:
            if fallback and fallback in self._models:
                decision = RoutingDecision(
                    model=fallback,
                    reason=f"No model meets constraints; using fallback '{fallback}'",
                    alternatives=[],
                    constraints_applied=constraints,
                    cost_savings_vs_best=0,
                )
            else:
                decision = RoutingDecision(
                    model="",
                    reason="No model meets constraints and no fallback specified",
                    alternatives=[],
                    constraints_applied=constraints,
                    cost_savings_vs_best=0,
                )
            self._log_routing(decision)
            return decision

        # Sort by strategy
        if strategy == "cheapest":
            candidates.sort(key=lambda m: m.cost_per_1k_tokens)
        elif strategy == "quality":
            candidates.sort(key=lambda m: -m.quality_score)
        elif strategy == "balanced":
            candidates.sort(key=lambda m: -m.cost_efficiency)
        elif strategy == "latency":
            candidates.sort(key=lambda m: m.latency_p50_ms)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        selected = candidates[0]
        alternatives = [m.name for m in candidates[1:3]]

        # Calculate savings vs best quality model
        best_quality = max(self._models.values(), key=lambda m: m.quality_score)
        if best_quality.cost_per_1k_tokens > 0:
            savings = (1 - selected.cost_per_1k_tokens / best_quality.cost_per_1k_tokens) * 100
        else:
            savings = 0

        decision = RoutingDecision(
            model=selected.name,
            reason=f"Selected by '{strategy}' strategy (quality={selected.quality_score:.2f}, "
                   f"cost=${selected.cost_per_1k_tokens:.4f}/1K)",
            alternatives=alternatives,
            constraints_applied=constraints,
            cost_savings_vs_best=max(0, savings),
        )
        self._log_routing(decision)
        return decision

    def recommend(self) -> List[dict]:
        """
        Get optimization recommendations based on registered models.

        Returns list of actionable suggestions.
        """
        recs = []
        models = list(self._models.values())

        if len(models) < 2:
            return [{"type": "info", "message": "Add more models to get routing recommendations"}]

        # Find models with similar quality but different costs
        sorted_by_quality = sorted(models, key=lambda m: -m.quality_score)
        for i in range(len(sorted_by_quality) - 1):
            expensive = sorted_by_quality[i]
            for cheaper in sorted_by_quality[i + 1:]:
                quality_diff = expensive.quality_score - cheaper.quality_score
                if quality_diff < 0.05 and expensive.cost_per_1k_tokens > 0:
                    cost_ratio = cheaper.cost_per_1k_tokens / expensive.cost_per_1k_tokens
                    if cost_ratio < 0.5:
                        savings_pct = (1 - cost_ratio) * 100
                        recs.append({
                            "type": "switch_model",
                            "message": f"Switch from {expensive.name} to {cheaper.name}: "
                                       f"similar quality ({cheaper.quality_score:.2f} vs "
                                       f"{expensive.quality_score:.2f}) but {savings_pct:.0f}% cheaper",
                            "from_model": expensive.name,
                            "to_model": cheaper.name,
                            "savings_pct": round(savings_pct, 1),
                            "quality_impact": round(-quality_diff, 3),
                        })

        # High error rate warnings
        for m in models:
            if m.error_rate > 0.1:
                recs.append({
                    "type": "high_error_rate",
                    "message": f"{m.name} has {m.error_rate*100:.0f}% error rate — "
                               f"consider disabling or investigating",
                    "model": m.name,
                    "error_rate": m.error_rate,
                })

        # Free model suggestions
        free_models = [m for m in models if m.cost_per_1k_tokens == 0 and m.quality_score > 0.6]
        paid_models = [m for m in models if m.cost_per_1k_tokens > 0]
        for free in free_models:
            for paid in paid_models:
                if free.quality_score >= paid.quality_score * 0.9:
                    recs.append({
                        "type": "use_free",
                        "message": f"Use free model {free.name} instead of {paid.name}: "
                                   f"{free.quality_score:.2f} vs {paid.quality_score:.2f} quality "
                                   f"at $0 cost",
                        "free_model": free.name,
                        "paid_model": paid.name,
                    })

        return recs if recs else [{"type": "info", "message": "Current model selection looks optimized"}]

    def comparison_table(self) -> List[dict]:
        """Get all models as a sorted comparison table."""
        return sorted(
            [m.to_dict() for m in self._models.values()],
            key=lambda m: -(m["cost_efficiency"] if isinstance(m["cost_efficiency"], (int, float)) else float('inf')),
        )

    # ── Internal ─────────────────────────────────────────────────────────

    def _filter_candidates(self, min_quality, max_latency_ms, max_cost_per_1k,
                           require_tags, require_json, require_vision,
                           require_tools) -> List[ModelProfile]:
        candidates = []
        for m in self._models.values():
            if not m.available:
                continue
            if m.quality_score < min_quality:
                continue
            if max_latency_ms and m.latency_p50_ms > max_latency_ms:
                continue
            if max_cost_per_1k is not None and m.cost_per_1k_tokens > max_cost_per_1k:
                continue
            if require_json and not m.supports_json:
                continue
            if require_vision and not m.supports_vision:
                continue
            if require_tools and not m.supports_tools:
                continue
            if require_tags:
                if not all(tag in m.tags for tag in require_tags):
                    continue
            candidates.append(m)
        return candidates

    def _log_routing(self, decision: RoutingDecision):
        self._routing_log.append({
            "timestamp": time.time(),
            "model": decision.model,
            "reason": decision.reason,
            "strategy": decision.constraints_applied.get("strategy"),
        })
        # Keep last 100 entries
        if len(self._routing_log) > 100:
            self._routing_log = self._routing_log[-100:]