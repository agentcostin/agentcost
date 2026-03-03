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


# Pricing per 1M tokens (input, output) — Feb 2026 approximate
MODEL_PRICING = {
    # ── OpenAI ─── (per 1M tokens: input, output) ─────────────────────────
    # GPT-5.x (latest)
    "gpt-5.2": (1.75, 14.00),
    "gpt-5.2-pro": (21.00, 168.00),
    "gpt-5.2-codex": (1.75, 14.00),
    "gpt-5.1": (1.25, 10.00),
    "gpt-5.1-codex": (1.25, 10.00),
    "gpt-5.1-codex-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    # GPT-4.x (current)
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    # OpenAI reasoning
    "o4-mini": (1.10, 4.40),
    "o3": (2.00, 8.00),
    "o3-mini": (1.10, 4.40),
    # OpenAI open-source
    "gpt-oss-20b": (0.03, 0.14),
    "gpt-oss-120b": (0.039, 0.19),
    # ── Anthropic ─── (per 1M tokens: input, output) ──────────────────────
    # Claude 4.6 (Feb 2026 — latest)
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    # Claude 4.5 (Nov 2025)
    "claude-opus-4-5": (5.00, 25.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # Claude 4.x (legacy, still active)
    "claude-sonnet-4": (3.00, 15.00),
    # ── Google Gemini ─── (per 1M tokens: input, output) ──────────────────
    "gemini-3-pro": (2.00, 12.00),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.0-flash": (0.10, 0.40),
    # ── xAI Grok ─── (per 1M tokens: input, output) ──────────────────────
    "grok-4": (3.00, 15.00),
    "grok-4-fast": (0.20, 0.50),
    "grok-4.1-fast": (0.20, 0.50),
    # ── DeepSeek ─── (per 1M tokens: input, output) ──────────────────────
    "deepseek-chat": (0.28, 0.42),
    "deepseek-reasoner": (0.28, 0.42),
    "deepseek-r1": (0.55, 2.19),
    # ── Local / Self-hosted (free) ────────────────────────────────────────
    "llama3:8b": (0.0, 0.0),
    "llama3:70b": (0.0, 0.0),
    "mistral": (0.0, 0.0),
    "mixtral": (0.0, 0.0),
    "gemma2": (0.0, 0.0),
    "qwen2": (0.0, 0.0),
}

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
        self._pricing = dict(MODEL_PRICING)
        if custom_pricing:
            self._pricing.update(custom_pricing)

    def add_pricing(self, model: str, input_per_1m: float, output_per_1m: float):
        """Add or update model pricing."""
        self._pricing[model] = (input_per_1m, output_per_1m)

    @property
    def supported_models(self) -> List[str]:
        return sorted(self._pricing.keys())

    def count_tokens(self, text: str) -> int:
        """
        Approximate token count using the ~4 chars per token heuristic.
        For production, use tiktoken — this is a fast approximation.
        """
        if not text:
            return 0
        # Rough approximation: ~4 chars per token for English
        # This works well for GPT-style tokenizers
        return max(1, len(text) // 4)

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

    def compare_models(
        self, prompt: str, models: List[str] = None, task_type: str = "default"
    ) -> List[dict]:
        """
        Compare estimated costs across models for the same prompt.
        Returns sorted by cost (cheapest first).
        """
        if models is None:
            models = list(self._pricing.keys())

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

        # Look up pricing
        pricing = self._get_pricing(model)
        input_price, output_price = pricing

        cost_in = input_tokens * input_price / 1_000_000
        cost_out = estimated_output * output_price / 1_000_000
        total_cost = cost_in + cost_out

        # Determine confidence
        if model in self._pricing:
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

    def _get_pricing(self, model: str) -> tuple:
        """Get pricing for a model with fuzzy matching."""
        if model in self._pricing:
            return self._pricing[model]

        # Fuzzy match: try prefix matching
        for known_model, pricing in self._pricing.items():
            if model.startswith(known_model) or known_model.startswith(model):
                return pricing

        # Default fallback: assume mid-range pricing
        return (1.0, 3.0)
