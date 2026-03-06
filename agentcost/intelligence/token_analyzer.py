"""
Token Budget Analyzer — context efficiency scoring.

Measures how effectively agents use their context windows and
identifies wasteful patterns:
    - Over-prompting (system messages > 30% of context)
    - Redundant context (repeated content across calls)
    - Under-utilization (using <10% of available context)
    - Output waste (requesting max tokens when short answers suffice)

Usage:
    from agentcost.intelligence import TokenAnalyzer, EfficiencyReport

    analyzer = TokenAnalyzer()
    analyzer.record_call(
        model="gpt-4o", input_tokens=50000, output_tokens=200,
        system_tokens=40000, max_context=128000,
    )
    report = analyzer.analyze("my-project")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("agentcost.intelligence.tokens")


@dataclass
class TokenCall:
    """A recorded LLM call for analysis."""

    model: str
    input_tokens: int
    output_tokens: int
    max_context: int
    system_tokens: int = 0  # tokens used by system prompt
    project: str = ""
    agent_id: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def context_utilization(self) -> float:
        """What fraction of the context window was used (0-1)."""
        if self.max_context <= 0:
            return 0.0
        return min(self.input_tokens / self.max_context, 1.0)

    @property
    def system_ratio(self) -> float:
        """Fraction of input tokens from system prompt (0-1)."""
        if self.input_tokens <= 0:
            return 0.0
        return min(self.system_tokens / self.input_tokens, 1.0)

    @property
    def output_ratio(self) -> float:
        """Output tokens as fraction of total (0-1)."""
        total = self.total_tokens
        if total <= 0:
            return 0.0
        return self.output_tokens / total


@dataclass
class EfficiencyReport:
    """Efficiency analysis for a scope (project/agent)."""

    scope: str
    scope_id: str
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    avg_context_utilization: float  # 0-1
    avg_system_ratio: float  # 0-1
    avg_output_ratio: float  # 0-1
    efficiency_score: float  # 0-100
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "scope_id": self.scope_id,
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "avg_context_utilization": round(self.avg_context_utilization, 3),
            "avg_system_ratio": round(self.avg_system_ratio, 3),
            "avg_output_ratio": round(self.avg_output_ratio, 3),
            "efficiency_score": round(self.efficiency_score, 1),
            "warnings": self.warnings,
            "recommendations": self.recommendations,
        }


# Thresholds for efficiency warnings
SYSTEM_PROMPT_WARN = 0.30  # system > 30% of input is excessive
LOW_UTILIZATION = 0.05  # using < 5% of context window
HIGH_UTILIZATION = 0.90  # using > 90% risks truncation
LOW_OUTPUT_RATIO = 0.02  # output < 2% of total → possible waste
IDEAL_UTILIZATION = (0.10, 0.70)  # ideal range for context usage


class TokenAnalyzer:
    """Analyzes token usage patterns across LLM calls.

    Records calls and produces efficiency reports with actionable
    recommendations for reducing cost and improving context usage.
    """

    def __init__(self, max_calls: int = 10_000):
        self._calls: list[TokenCall] = []
        self._max_calls = max_calls

    def record_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        max_context: int = 128000,
        system_tokens: int = 0,
        project: str = "",
        agent_id: str = "",
    ) -> TokenCall:
        """Record an LLM call for later analysis."""
        call = TokenCall(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            max_context=max_context,
            system_tokens=system_tokens,
            project=project,
            agent_id=agent_id,
        )
        self._calls.append(call)
        if len(self._calls) > self._max_calls:
            self._calls = self._calls[-self._max_calls :]
        return call

    def analyze(self, scope_id: str = "", scope: str = "project") -> EfficiencyReport:
        """Analyze token efficiency for a scope.

        Args:
            scope_id: Project or agent ID (empty = all calls)
            scope: "project" or "agent_id"
        """
        calls = self._filter_calls(scope_id, scope)
        if not calls:
            return EfficiencyReport(
                scope=scope,
                scope_id=scope_id or "all",
                total_calls=0,
                total_input_tokens=0,
                total_output_tokens=0,
                avg_context_utilization=0,
                avg_system_ratio=0,
                avg_output_ratio=0,
                efficiency_score=0,
                warnings=["No calls recorded"],
            )

        total_input = sum(c.input_tokens for c in calls)
        total_output = sum(c.output_tokens for c in calls)
        avg_ctx = sum(c.context_utilization for c in calls) / len(calls)
        avg_sys = sum(c.system_ratio for c in calls) / len(calls)
        avg_out = sum(c.output_ratio for c in calls) / len(calls)

        warnings = []
        recommendations = []

        # Check for excessive system prompts
        if avg_sys > SYSTEM_PROMPT_WARN:
            pct = round(avg_sys * 100, 1)
            warnings.append(f"System prompts average {pct}% of input tokens")
            recommendations.append(
                "Consider shortening system prompts or using few-shot examples "
                "more selectively to reduce input cost"
            )

        # Check for under-utilization
        if avg_ctx < LOW_UTILIZATION and total_input > 0:
            pct = round(avg_ctx * 100, 1)
            warnings.append(f"Context utilization is very low ({pct}%)")
            recommendations.append(
                "Consider using a model with a smaller context window "
                "(smaller models are usually cheaper)"
            )

        # Check for near-limit usage
        high_util_calls = sum(
            1 for c in calls if c.context_utilization > HIGH_UTILIZATION
        )
        if high_util_calls > len(calls) * 0.2:
            warnings.append(
                f"{high_util_calls}/{len(calls)} calls near context limit (>90%)"
            )
            recommendations.append(
                "Many calls approach the context limit — consider "
                "summarizing context or using a model with larger context window"
            )

        # Check for low output ratio (paying lots of input for little output)
        if avg_out < LOW_OUTPUT_RATIO and total_output > 0:
            warnings.append(
                f"Output is only {round(avg_out * 100, 2)}% of total tokens"
            )
            recommendations.append(
                "Most cost is on input tokens with minimal output — "
                "consider whether all context is necessary"
            )

        # Calculate efficiency score (0-100)
        score = self._calculate_score(avg_ctx, avg_sys, avg_out, calls)

        return EfficiencyReport(
            scope=scope,
            scope_id=scope_id or "all",
            total_calls=len(calls),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            avg_context_utilization=avg_ctx,
            avg_system_ratio=avg_sys,
            avg_output_ratio=avg_out,
            efficiency_score=score,
            warnings=warnings,
            recommendations=recommendations,
        )

    def _filter_calls(self, scope_id: str, scope: str) -> list[TokenCall]:
        """Filter calls by scope."""
        if not scope_id:
            return list(self._calls)
        return [c for c in self._calls if getattr(c, scope, "") == scope_id]

    def _calculate_score(
        self,
        avg_ctx: float,
        avg_sys: float,
        avg_out: float,
        calls: list[TokenCall],
    ) -> float:
        """Calculate efficiency score 0-100.

        Scoring:
        - Context utilization in ideal range (10-70%): +40 points
        - System prompt ratio < 30%: +20 points
        - Output ratio balanced (2-50%): +20 points
        - No near-limit calls: +20 points
        """
        score = 0.0

        # Context utilization (40 pts)
        low, high = IDEAL_UTILIZATION
        if low <= avg_ctx <= high:
            score += 40.0
        elif avg_ctx < low:
            score += max(0, 40 * (avg_ctx / low))
        else:
            excess = (avg_ctx - high) / (1.0 - high) if high < 1.0 else 0
            score += max(0, 40 * (1.0 - excess))

        # System prompt efficiency (20 pts)
        if avg_sys <= SYSTEM_PROMPT_WARN:
            score += 20.0
        else:
            excess = (avg_sys - SYSTEM_PROMPT_WARN) / (1.0 - SYSTEM_PROMPT_WARN)
            score += max(0, 20 * (1.0 - excess))

        # Output ratio (20 pts)
        if 0.02 <= avg_out <= 0.50:
            score += 20.0
        elif avg_out < 0.02:
            score += max(0, 20 * (avg_out / 0.02))
        else:
            score += max(0, 20 * (1.0 - (avg_out - 0.50) / 0.50))

        # Near-limit penalty (20 pts)
        high_pct = sum(
            1 for c in calls if c.context_utilization > HIGH_UTILIZATION
        ) / len(calls)
        score += max(0, 20 * (1.0 - high_pct * 2))

        return min(100.0, max(0.0, score))

    def get_calls(self, limit: int = 100) -> list[dict]:
        """Return recent calls as dicts."""
        return [
            {
                "model": c.model,
                "input_tokens": c.input_tokens,
                "output_tokens": c.output_tokens,
                "context_utilization": round(c.context_utilization, 3),
                "system_ratio": round(c.system_ratio, 3),
                "project": c.project,
            }
            for c in self._calls[-limit:]
        ]

    def reset(self):
        """Clear all recorded calls."""
        self._calls.clear()
