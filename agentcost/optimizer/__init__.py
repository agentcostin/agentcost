"""
AgentCost Cost Optimizer — Phase 6 Block 3

Analyzes traces and generates actionable cost optimization recommendations.

Usage:
    from agentcost.optimizer import CostOptimizer

    optimizer = CostOptimizer()
    optimizer.add_traces(traces)
    report = optimizer.analyze()
    for rec in report.recommendations:
        print(f"[{rec['priority']}] {rec['message']} — Save ~${rec['estimated_savings']:.2f}/mo")
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import defaultdict
import math


@dataclass
class OptimizationReport:
    """Complete optimization analysis."""
    total_cost: float
    total_calls: int
    total_tokens: int
    recommendations: List[dict]
    model_breakdown: Dict[str, dict]
    efficiency_score: float  # 0-100, overall cost efficiency
    potential_savings_pct: float
    potential_savings_usd: float

    def to_dict(self) -> dict:
        return {
            "total_cost": round(self.total_cost, 4),
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "recommendations": self.recommendations,
            "model_breakdown": self.model_breakdown,
            "efficiency_score": round(self.efficiency_score, 1),
            "potential_savings_pct": round(self.potential_savings_pct, 1),
            "potential_savings_usd": round(self.potential_savings_usd, 4),
        }


# Model cost tiers for comparison
MODEL_TIERS = {
    "premium": {"models": ["gpt-4o", "claude-3-5-sonnet", "claude-3-opus"], "cost_range": "$$$$"},
    "standard": {"models": ["gpt-4o-mini", "claude-3-5-haiku", "claude-3-haiku"], "cost_range": "$$"},
    "economy": {"models": ["llama3:8b", "llama3:70b", "mistral", "gemma2"], "cost_range": "$"},
    "free": {"models": ["llama3:8b", "mistral", "gemma2", "phi3"], "cost_range": "free"},
}

# Cheaper alternatives mapping
CHEAPER_ALTERNATIVES = {
    # OpenAI
    "gpt-5.2-pro": ["gpt-5.2", "gpt-5.1"],
    "gpt-5.2": ["gpt-5.1", "gpt-5-mini"],
    "gpt-5.1": ["gpt-5", "gpt-5-mini"],
    "gpt-5": ["gpt-5-mini", "gpt-5-nano"],
    "gpt-5-mini": ["gpt-5-nano", "gpt-4o-mini"],
    "gpt-4.1": ["gpt-4.1-mini", "gpt-4.1-nano"],
    "gpt-4o": ["gpt-4o-mini", "gpt-4.1-mini"],
    "o3": ["o3-mini", "o4-mini"],
    # Anthropic
    "claude-opus-4-6": ["claude-sonnet-4-6", "claude-haiku-4-5"],
    "claude-opus-4-5": ["claude-sonnet-4-5", "claude-haiku-4-5"],
    "claude-sonnet-4-6": ["claude-haiku-4-5", "gpt-4o-mini"],
    "claude-sonnet-4-5": ["claude-haiku-4-5", "gpt-4o-mini"],
    "claude-sonnet-4": ["claude-haiku-4-5", "gpt-4o-mini"],
    # Google
    "gemini-3-pro": ["gemini-2.5-pro", "gemini-2.5-flash"],
    "gemini-2.5-pro": ["gemini-2.5-flash", "gemini-2.5-flash-lite"],
    "gemini-2.5-flash": ["gemini-2.5-flash-lite", "gemini-2.0-flash"],
    # xAI
    "grok-4": ["grok-4-fast", "grok-4.1-fast"],
}


class CostOptimizer:
    """Analyzes trace data and generates cost optimization recommendations."""

    def __init__(self):
        self._traces: List[dict] = []

    def add_traces(self, traces: List[dict]):
        """Add trace data for analysis."""
        self._traces.extend(traces)

    def add_trace(self, trace: dict):
        """Add a single trace."""
        self._traces.append(trace)

    def clear(self):
        """Clear all traces."""
        self._traces.clear()

    @property
    def trace_count(self) -> int:
        return len(self._traces)

    def analyze(self) -> OptimizationReport:
        """Run full optimization analysis and return report."""
        if not self._traces:
            return OptimizationReport(
                total_cost=0, total_calls=0, total_tokens=0,
                recommendations=[{"priority": "info", "message": "No traces to analyze"}],
                model_breakdown={}, efficiency_score=0,
                potential_savings_pct=0, potential_savings_usd=0,
            )

        # Aggregate stats
        stats = self._aggregate_stats()
        recommendations = []
        potential_savings = 0.0

        # Run analyzers
        savings, recs = self._check_model_downgrade(stats)
        potential_savings += savings
        recommendations.extend(recs)

        savings, recs = self._check_caching_opportunity(stats)
        potential_savings += savings
        recommendations.extend(recs)

        savings, recs = self._check_token_waste(stats)
        potential_savings += savings
        recommendations.extend(recs)

        savings, recs = self._check_error_waste(stats)
        potential_savings += savings
        recommendations.extend(recs)

        savings, recs = self._check_batching_opportunity(stats)
        potential_savings += savings
        recommendations.extend(recs)

        savings, recs = self._check_off_peak(stats)
        potential_savings += savings
        recommendations.extend(recs)

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        recommendations.sort(key=lambda r: priority_order.get(r.get("priority", "info"), 3))

        # Efficiency score (0-100)
        total_cost = stats["total_cost"]
        savings_pct = (potential_savings / total_cost * 100) if total_cost > 0 else 0
        efficiency = max(0, 100 - savings_pct)

        return OptimizationReport(
            total_cost=total_cost,
            total_calls=stats["total_calls"],
            total_tokens=stats["total_tokens"],
            recommendations=recommendations,
            model_breakdown=stats["by_model"],
            efficiency_score=efficiency,
            potential_savings_pct=savings_pct,
            potential_savings_usd=potential_savings,
        )

    # ── Aggregation ──────────────────────────────────────────────────────

    def _aggregate_stats(self) -> dict:
        total_cost = 0
        total_calls = 0
        total_tokens = 0
        total_errors = 0
        by_model: Dict[str, dict] = defaultdict(lambda: {
            "cost": 0, "calls": 0, "input_tokens": 0, "output_tokens": 0,
            "errors": 0, "avg_latency": 0, "latencies": [],
            "prompts_seen": set(),
        })

        for t in self._traces:
            cost = float(t.get("cost", 0))
            it = int(t.get("input_tokens", 0))
            ot = int(t.get("output_tokens", 0))
            model = t.get("model", "unknown")
            latency = float(t.get("latency_ms", 0))
            status = t.get("status", "success")

            total_cost += cost
            total_calls += 1
            total_tokens += it + ot
            if status == "error":
                total_errors += 1

            m = by_model[model]
            m["cost"] += cost
            m["calls"] += 1
            m["input_tokens"] += it
            m["output_tokens"] += ot
            m["latencies"].append(latency)
            if status == "error":
                m["errors"] += 1

            # Track unique prompts for cache analysis (simplified)
            prompt_key = str((t.get("metadata") or {}).get("prompt_hash", ""))[:8]
            if prompt_key:
                m["prompts_seen"].add(prompt_key)

        # Finalize by_model
        for model, m in by_model.items():
            lats = m.pop("latencies")
            m["avg_latency"] = sum(lats) / len(lats) if lats else 0
            m["unique_prompts"] = len(m.pop("prompts_seen"))
            m["error_rate"] = m["errors"] / m["calls"] if m["calls"] > 0 else 0
            m["cost_per_call"] = m["cost"] / m["calls"] if m["calls"] > 0 else 0
            m["tokens_per_call"] = (m["input_tokens"] + m["output_tokens"]) / m["calls"] if m["calls"] > 0 else 0

        return {
            "total_cost": total_cost,
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "total_errors": total_errors,
            "error_rate": total_errors / total_calls if total_calls > 0 else 0,
            "by_model": dict(by_model),
        }

    # ── Analyzers ────────────────────────────────────────────────────────

    def _check_model_downgrade(self, stats: dict) -> tuple:
        """Check if cheaper model alternatives exist."""
        savings = 0
        recs = []
        for model, m in stats["by_model"].items():
            alternatives = CHEAPER_ALTERNATIVES.get(model, [])
            if alternatives and m["cost"] > 0:
                est_savings = m["cost"] * 0.6  # Typical 60% savings on downgrade
                savings += est_savings
                recs.append({
                    "type": "model_downgrade",
                    "priority": "high" if m["cost"] > 1.0 else "medium",
                    "message": f"Consider switching from {model} to {alternatives[0]} "
                               f"for non-critical tasks ({m['calls']} calls, ${m['cost']:.4f} spent)",
                    "model": model,
                    "alternatives": alternatives,
                    "estimated_savings": round(est_savings, 4),
                    "current_cost": round(m["cost"], 4),
                })
        return savings, recs

    def _check_caching_opportunity(self, stats: dict) -> tuple:
        """Check for repeated/similar calls that could be cached."""
        savings = 0
        recs = []
        for model, m in stats["by_model"].items():
            if m["calls"] > 10:
                # If fewer unique prompts than calls, caching could help
                1 - (m["unique_prompts"] / m["calls"]) if m["unique_prompts"] > 0 else 0
                if m["calls"] > 20 and m["cost"] > 0:
                    # Estimate: temperature=0 calls are cache candidates
                    est_cache_hit = 0.3  # Conservative 30% cache hit rate estimate
                    est_savings = m["cost"] * est_cache_hit
                    savings += est_savings
                    recs.append({
                        "type": "enable_caching",
                        "priority": "medium",
                        "message": f"Enable response caching for {model} — "
                                   f"{m['calls']} calls could benefit from gateway cache",
                        "model": model,
                        "estimated_savings": round(est_savings, 4),
                        "calls": m["calls"],
                    })
        return savings, recs

    def _check_token_waste(self, stats: dict) -> tuple:
        """Check for high output-to-input token ratios (verbose responses)."""
        savings = 0
        recs = []
        for model, m in stats["by_model"].items():
            if m["input_tokens"] > 0 and m["output_tokens"] > 0:
                ratio = m["output_tokens"] / m["input_tokens"]
                if ratio > 3.0 and m["calls"] > 5:
                    # Output is 3x+ input — likely verbose responses
                    m["output_tokens"] - m["input_tokens"] * 2
                    est_savings = m["cost"] * 0.2  # ~20% savings by constraining output
                    savings += est_savings
                    recs.append({
                        "type": "reduce_output",
                        "priority": "medium",
                        "message": f"{model}: output tokens are {ratio:.1f}x input tokens — "
                                   f"consider adding max_tokens or more specific prompts",
                        "model": model,
                        "output_ratio": round(ratio, 1),
                        "estimated_savings": round(est_savings, 4),
                    })

                # Check for very large prompts
                avg_input = m["input_tokens"] / m["calls"]
                if avg_input > 4000:
                    est_savings_prompt = m["cost"] * 0.15
                    savings += est_savings_prompt
                    recs.append({
                        "type": "reduce_prompt",
                        "priority": "low",
                        "message": f"{model}: average input is {avg_input:.0f} tokens/call — "
                                   f"consider prompt compression or summarization",
                        "model": model,
                        "avg_input_tokens": round(avg_input),
                        "estimated_savings": round(est_savings_prompt, 4),
                    })
        return savings, recs

    def _check_error_waste(self, stats: dict) -> tuple:
        """Check for wasted spend on errors."""
        savings = 0
        recs = []
        if stats["error_rate"] > 0.05:
            error_cost = stats["total_cost"] * stats["error_rate"]
            savings += error_cost
            recs.append({
                "type": "reduce_errors",
                "priority": "high",
                "message": f"Error rate is {stats['error_rate']*100:.1f}% — "
                           f"~${error_cost:.4f} wasted on failed calls. "
                           f"Check provider status and implement retries",
                "error_rate": round(stats["error_rate"], 3),
                "estimated_savings": round(error_cost, 4),
            })
        return savings, recs

    def _check_batching_opportunity(self, stats: dict) -> tuple:
        """Check if calls could be batched for discounts."""
        savings = 0
        recs = []
        for model, m in stats["by_model"].items():
            if m["calls"] > 50 and "gpt" in model.lower():
                est_savings = m["cost"] * 0.5  # Batch API is 50% off
                savings += est_savings
                recs.append({
                    "type": "use_batch_api",
                    "priority": "medium",
                    "message": f"{model} has {m['calls']} calls — consider OpenAI Batch API "
                               f"for non-realtime tasks (50% cost reduction)",
                    "model": model,
                    "estimated_savings": round(est_savings, 4),
                    "calls": m["calls"],
                })
        return savings, recs

    def _check_off_peak(self, stats: dict) -> tuple:
        """Check for off-peak usage opportunities (informational)."""
        recs = []
        if stats["total_calls"] > 100:
            recs.append({
                "type": "scheduling",
                "priority": "low",
                "message": "With 100+ calls, consider scheduling non-urgent tasks "
                           "during off-peak hours for better latency",
                "calls": stats["total_calls"],
                "estimated_savings": 0,
            })
        return 0, recs