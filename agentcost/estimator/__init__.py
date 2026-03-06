"""
AgentCost Prompt Cost Estimator — Phase 6 Block 5

Estimates token count and cost BEFORE sending a request to an LLM.
Supports multiple tokenizer approximations.

Usage:
    from agentcost.estimator import CostEstimator

    estimator = CostEstimator()

    # Quick estimate
    est = estimator.estimate("gpt-4o", "Explain quantum computing in 3 paragraphs")
    print(est)
    # {'model': 'gpt-4o', 'estimated_input_tokens': 8,
    #  'estimated_output_tokens': 300, 'estimated_cost': 0.0047,
    #  'confidence': 'medium'}

    # With messages
    est = estimator.estimate_messages("gpt-4o", [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"},
    ])

    # Batch estimate
    estimates = estimator.estimate_batch([
        {"model": "gpt-4o", "prompt": "Hello"},
        {"model": "gpt-4o-mini", "prompt": "Hello"},
    ])
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..cost.calculator import (
    get_pricing_per_1m,
    list_models,
    register_model_per_1m,
    estimate_tokens,
)

# Average output-to-input ratios by task type
OUTPUT_RATIOS = {
    "chat": 2.0,  # Conversational responses
    "code": 3.0,  # Code generation
    "summary": 0.3,  # Summarization (output < input)
    "analysis": 2.5,  # Analytical tasks
    "creative": 4.0,  # Creative writing
    "translation": 1.1,  # Translation (roughly same length)
    "extraction": 0.5,  # Data extraction
    "classification": 0.1,  # Classification (very short output)
    "default": 2.0,
}


@dataclass
class CostEstimate:
    """Pre-call cost estimate."""

    model: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_total_tokens: int
    estimated_cost: float
    cost_input: float
    cost_output: float
    confidence: str  # 'high', 'medium', 'low'
    pricing_source: str  # 'known', 'estimated', 'free'
    task_type: str

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "estimated_input_tokens": self.estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "estimated_total_tokens": self.estimated_total_tokens,
            "estimated_cost": round(self.estimated_cost, 6),
            "cost_breakdown": {
                "input": round(self.cost_input, 6),
                "output": round(self.cost_output, 6),
            },
            "confidence": self.confidence,
            "pricing_source": self.pricing_source,
            "task_type": self.task_type,
        }


class CostEstimator:
    """Pre-call cost estimator for LLM requests."""

    def __init__(self, custom_pricing: Dict[str, tuple] = None):
        if custom_pricing:
            for model, (inp, out) in custom_pricing.items():
                register_model_per_1m(model, inp, out)

    def add_pricing(self, model: str, input_per_1m: float, output_per_1m: float):
        """Add or update model pricing."""
        register_model_per_1m(model, input_per_1m, output_per_1m)

    @property
    def supported_models(self) -> List[str]:
        return list_models()

    def count_tokens(self, text: str) -> int:
        """
        Approximate token count using tiktoken (if available) or ~4 chars/token.
        """
        return estimate_tokens(text)

    def count_message_tokens(self, messages: List[dict]) -> int:
        """Estimate token count for a list of chat messages."""
        total = 0
        for msg in messages:
            # ~4 tokens overhead per message (role, delimiters)
            total += 4
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count_tokens(content)
            elif isinstance(content, list):
                # Multimodal content
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += self.count_tokens(part.get("text", ""))
                    elif isinstance(part, dict) and part.get("type") == "image_url":
                        total += 765  # ~765 tokens for a standard image
        # System overhead
        total += 3  # reply priming
        return total

    def estimate(
        self,
        model: str,
        prompt: str,
        task_type: str = "default",
        max_output_tokens: int = None,
    ) -> CostEstimate:
        """
        Estimate cost for a prompt string.

        Args:
            model: Model name
            prompt: The prompt text
            task_type: Type of task (affects output estimate)
            max_output_tokens: If set, caps estimated output
        """
        input_tokens = self.count_tokens(prompt)
        return self._build_estimate(model, input_tokens, task_type, max_output_tokens)

    def estimate_messages(
        self,
        model: str,
        messages: List[dict],
        task_type: str = "default",
        max_output_tokens: int = None,
    ) -> CostEstimate:
        """Estimate cost for chat messages."""
        input_tokens = self.count_message_tokens(messages)
        return self._build_estimate(model, input_tokens, task_type, max_output_tokens)

    def estimate_batch(self, requests: List[dict]) -> List[CostEstimate]:
        """
        Estimate costs for multiple requests.
        Each request: {"model": ..., "prompt": ..., "task_type": ...}
        """
        results = []
        for req in requests:
            model = req.get("model", "unknown")
            if "messages" in req:
                est = self.estimate_messages(
                    model,
                    req["messages"],
                    task_type=req.get("task_type", "default"),
                    max_output_tokens=req.get("max_output_tokens"),
                )
            else:
                est = self.estimate(
                    model,
                    req.get("prompt", ""),
                    task_type=req.get("task_type", "default"),
                    max_output_tokens=req.get("max_output_tokens"),
                )
            results.append(est)
        return results

    # Popular models for quick comparison (used when no models specified)
    _DEFAULT_COMPARE_MODELS = [
        "gpt-4o",
        "gpt-4o-mini",
        "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
        "gemini-2.0-flash",
        "deepseek-chat",
    ]

    def compare_models(
        self, prompt: str, models: List[str] = None, task_type: str = "default"
    ) -> List[dict]:
        """
        Compare estimated costs across models for the same prompt.
        Returns sorted by cost (cheapest first).
        """
        if models is None:
            models = self._DEFAULT_COMPARE_MODELS

        estimates = []
        for model in models:
            est = self.estimate(model, prompt, task_type)
            estimates.append(est.to_dict())

        return sorted(estimates, key=lambda e: e["estimated_cost"])

    # ── Internal ─────────────────────────────────────────────────────────

    def _build_estimate(
        self,
        model: str,
        input_tokens: int,
        task_type: str,
        max_output_tokens: int = None,
    ) -> CostEstimate:
        # Estimate output tokens
        ratio = OUTPUT_RATIOS.get(task_type, OUTPUT_RATIOS["default"])
        estimated_output = int(input_tokens * ratio)
        if max_output_tokens:
            estimated_output = min(estimated_output, max_output_tokens)

        # Look up pricing via vendored cost map (2,600+ models)
        pricing = get_pricing_per_1m(model)
        input_price = pricing["input"]
        output_price = pricing["output"]

        cost_in = input_tokens * input_price / 1_000_000
        cost_out = estimated_output * output_price / 1_000_000
        total_cost = cost_in + cost_out

        # Determine confidence
        from ..cost.calculator import get_model_info as _get_info

        info = _get_info(model)
        if info is not None:
            pricing_source = (
                "free" if input_price == 0 and output_price == 0 else "known"
            )
            confidence = "high" if task_type != "default" else "medium"
        else:
            pricing_source = "estimated"
            confidence = "low"

        return CostEstimate(
            model=model,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=estimated_output,
            estimated_total_tokens=input_tokens + estimated_output,
            estimated_cost=total_cost,
            cost_input=cost_in,
            cost_output=cost_out,
            confidence=confidence,
            pricing_source=pricing_source,
            task_type=task_type,
        )
