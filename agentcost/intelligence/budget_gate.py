"""
Budget Gate — pre-execution budget checks for workflow nodes.

Provides cost-aware workflow gates that check available budget
before each LLM call, automatically downgrading or pausing
when thresholds are approached.

Actions:
    ALLOW     — proceed with the requested model
    DOWNGRADE — switch to a cheaper model (automatic)
    WARN      — proceed but emit a budget.warning event
    BLOCK     — deny the call, budget exhausted

Usage:
    from agentcost.intelligence import BudgetGate, GateDecision

    gate = BudgetGate(budget=10.00)
    decision = gate.check("gpt-4o", estimated_tokens=5000)
    if decision.action == "allow":
        # proceed with decision.model
        ...
    elif decision.action == "downgrade":
        # use decision.model (cheaper alternative)
        ...
    elif decision.action == "block":
        # budget exhausted
        ...
    gate.record_spend(0.05)  # track actual cost after call
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("agentcost.intelligence.gate")


class GateAction(str, Enum):
    ALLOW = "allow"
    DOWNGRADE = "downgrade"
    WARN = "warn"
    BLOCK = "block"


@dataclass
class GateDecision:
    """Result of a budget gate check."""

    action: str  # allow, downgrade, warn, block
    model: str  # model to use (may differ from requested if downgraded)
    reason: str
    budget_remaining: float
    budget_used_pct: float
    estimated_cost: float = 0.0

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "model": self.model,
            "reason": self.reason,
            "budget_remaining": round(self.budget_remaining, 4),
            "budget_used_pct": round(self.budget_used_pct, 1),
            "estimated_cost": round(self.estimated_cost, 6),
        }


# Default downgrade chains per provider
DEFAULT_DOWNGRADE_CHAINS: dict[str, list[str]] = {
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
    "anthropic": [
        "claude-3-5-sonnet-20241022",
        "claude-3-haiku-20240307",
    ],
    "groq": ["llama-3.1-70b-versatile", "llama-3.1-8b-instant"],
    "default": [],  # no default chain
}


class BudgetGate:
    """Pre-execution budget gate for workflow nodes.

    Tracks spend against a budget and makes allow/downgrade/block
    decisions before each LLM call.

    Thresholds:
        - warn_pct (default 80%): Emit warning but allow
        - downgrade_pct (default 90%): Auto-downgrade to cheaper model
        - block_pct (default 100%): Block the call entirely
    """

    def __init__(
        self,
        budget: float,
        warn_pct: float = 0.80,
        downgrade_pct: float = 0.90,
        block_pct: float = 1.00,
        downgrade_chains: dict[str, list[str]] | None = None,
    ):
        self.budget = budget
        self.warn_pct = warn_pct
        self.downgrade_pct = downgrade_pct
        self.block_pct = block_pct
        self.spent = 0.0
        self._downgrade_chains = downgrade_chains or DEFAULT_DOWNGRADE_CHAINS
        self._history: list[dict] = []

    @property
    def remaining(self) -> float:
        return max(0.0, self.budget - self.spent)

    @property
    def used_pct(self) -> float:
        if self.budget <= 0:
            return 100.0
        return (self.spent / self.budget) * 100

    def check(
        self,
        model: str,
        estimated_tokens: int = 0,
        provider: str = "",
    ) -> GateDecision:
        """Check if a model call should proceed given the current budget.

        Args:
            model: Requested model name
            estimated_tokens: Estimated total tokens for the call
            provider: Provider name (for downgrade chain lookup)
        """
        est_cost = self._estimate_cost(model, estimated_tokens)
        remaining = self.remaining
        used_pct = self.used_pct

        base = dict(
            budget_remaining=remaining,
            budget_used_pct=used_pct,
            estimated_cost=est_cost,
        )

        # Block threshold
        if used_pct >= self.block_pct * 100:
            decision = GateDecision(
                action=GateAction.BLOCK.value,
                model=model,
                reason=f"Budget exhausted ({used_pct:.1f}% used)",
                **base,
            )
            self._log(decision)
            return decision

        # Would this call exceed the budget?
        if est_cost > 0 and est_cost > remaining:
            # Try downgrade
            alt = self._find_downgrade(model, provider, remaining)
            if alt and alt != model:
                decision = GateDecision(
                    action=GateAction.DOWNGRADE.value,
                    model=alt,
                    reason=f"Estimated cost ${est_cost:.4f} exceeds remaining "
                           f"${remaining:.4f} — downgraded to {alt}",
                    **base,
                )
            else:
                decision = GateDecision(
                    action=GateAction.BLOCK.value,
                    model=model,
                    reason=f"Estimated cost ${est_cost:.4f} exceeds remaining "
                           f"${remaining:.4f}, no downgrade available",
                    **base,
                )
            self._log(decision)
            return decision

        # Downgrade threshold
        if used_pct >= self.downgrade_pct * 100:
            alt = self._find_downgrade(model, provider, remaining)
            if alt and alt != model:
                decision = GateDecision(
                    action=GateAction.DOWNGRADE.value,
                    model=alt,
                    reason=f"Budget at {used_pct:.1f}% — auto-downgrade to {alt}",
                    **base,
                )
                self._log(decision)
                return decision

        # Warn threshold
        if used_pct >= self.warn_pct * 100:
            decision = GateDecision(
                action=GateAction.WARN.value,
                model=model,
                reason=f"Budget warning: {used_pct:.1f}% used",
                **base,
            )
            self._log(decision)
            return decision

        # All clear
        decision = GateDecision(
            action=GateAction.ALLOW.value,
            model=model,
            reason="ok",
            **base,
        )
        self._log(decision)
        return decision

    def record_spend(self, cost: float) -> float:
        """Record actual spend after a call. Returns new remaining budget."""
        self.spent += cost
        return self.remaining

    def reset(self, new_budget: float | None = None):
        """Reset spend counter, optionally with new budget."""
        self.spent = 0.0
        if new_budget is not None:
            self.budget = new_budget

    def get_history(self, limit: int = 50) -> list[dict]:
        """Return recent gate decisions."""
        return self._history[-limit:]

    def _estimate_cost(self, model: str, tokens: int) -> float:
        """Estimate cost for a call using the cost calculator."""
        if tokens <= 0:
            return 0.0
        try:
            from ..cost.calculator import get_pricing_per_1m

            pricing = get_pricing_per_1m(model)
            input_per_tok = pricing.get("input_per_1m", 0) / 1_000_000
            return input_per_tok * tokens
        except Exception:
            return 0.0

    def _find_downgrade(
        self, model: str, provider: str, remaining: float
    ) -> str | None:
        """Find a cheaper model in the downgrade chain."""
        # Determine chain
        chain = self._downgrade_chains.get(provider, [])
        if not chain:
            # Try to infer provider from model name
            for prov, ch in self._downgrade_chains.items():
                if model in ch:
                    chain = ch
                    break

        if not chain or model not in chain:
            return None

        idx = chain.index(model)
        # Return the next cheaper model in the chain
        for alt in chain[idx + 1:]:
            return alt
        return None

    def _log(self, decision: GateDecision):
        self._history.append({
            **decision.to_dict(),
            "timestamp": time.time(),
        })
        if len(self._history) > 500:
            self._history = self._history[-500:]
