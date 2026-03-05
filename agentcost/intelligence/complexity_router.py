"""
Complexity Router — auto-classify prompts and route to cost tiers.

Classifies each request into a complexity level:
    SIMPLE    — short, factual, extractive (FAQ, lookup, classification)
    MEDIUM    — moderate generation, summarization, standard tasks
    COMPLEX   — multi-step reasoning, analysis, long-form generation
    REASONING — math, logic, proofs, chain-of-thought required

Each level maps to a default cost tier:
    SIMPLE    → economy   (gpt-4o-mini, haiku)
    MEDIUM    → standard  (gpt-4o, sonnet)
    COMPLEX   → standard  (gpt-4o, sonnet)
    REASONING → premium   (o1, opus)

Usage:
    from agentcost.intelligence import ComplexityRouter, ComplexityLevel

    router = ComplexityRouter()
    result = router.classify("What is the capital of France?")
    # result.level == ComplexityLevel.SIMPLE
    # result.suggested_tier == "economy"
    # result.suggested_model == "gpt-4o-mini"  (from tier registry)

    # Or one-shot classify + route:
    model = router.route("Prove that sqrt(2) is irrational", provider="openai")
    # model == "o1" or similar premium model
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("agentcost.intelligence.complexity")


class ComplexityLevel(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    REASONING = "reasoning"


# Map complexity levels to default cost tiers
LEVEL_TO_TIER: dict[str, str] = {
    "simple": "economy",
    "medium": "standard",
    "complex": "standard",
    "reasoning": "premium",
}

# Preferred models per level per provider (fallback defaults)
LEVEL_MODELS: dict[str, dict[str, str]] = {
    "simple": {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-haiku-20240307",
        "groq": "llama-3.1-8b-instant",
        "default": "gpt-4o-mini",
    },
    "medium": {
        "openai": "gpt-4o",
        "anthropic": "claude-3-5-sonnet-20241022",
        "groq": "llama-3.1-70b-versatile",
        "default": "gpt-4o",
    },
    "complex": {
        "openai": "gpt-4o",
        "anthropic": "claude-3-5-sonnet-20241022",
        "groq": "llama-3.1-70b-versatile",
        "default": "gpt-4o",
    },
    "reasoning": {
        "openai": "o1",
        "anthropic": "claude-3-5-sonnet-20241022",
        "default": "o1",
    },
}


@dataclass
class ClassificationResult:
    """Result of complexity classification."""

    level: ComplexityLevel
    suggested_tier: str
    suggested_model: str
    confidence: float  # 0-1
    signals: list[str] = field(default_factory=list)  # what triggered the classification

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "tier": self.suggested_tier,
            "model": self.suggested_model,
            "confidence": round(self.confidence, 2),
            "signals": self.signals,
        }


# ── Signal Patterns ───────────────────────────────────────────────────────────

# Reasoning indicators — patterns that suggest chain-of-thought is needed
REASONING_PATTERNS = [
    r"\bprove\b",
    r"\bproof\b",
    r"\bderive\b",
    r"\bderivation\b",
    r"\btheorem\b",
    r"\blemma\b",
    r"\binduction\b",
    r"\bcontradiction\b",
    r"\bif and only if\b",
    r"\blogic(?:al)?\s+(?:puzzle|problem)\b",
    r"\bstep[\s-]by[\s-]step\b",
    r"\bchain[\s-]of[\s-]thought\b",
    r"\bthink\s+(?:carefully|through|deeply)\b",
    r"\bsolve\b.*\bequation",
    r"\bcalculate\b.*\bintegral",
    r"\boptimize\b.*\bfunction",
    r"\balgorithm\b.*\bcomplexity\b",
    r"\brecursive\b.*\brelation\b",
]

# Complex indicators — multi-step tasks, analysis, code
COMPLEX_PATTERNS = [
    r"\banalyze\b",
    r"\bcompare\s+and\s+contrast\b",
    r"\bevaluate\b.*\bpros\s+and\s+cons\b",
    r"\bwrite\s+(?:a|an)\s+(?:essay|article|report|paper)\b",
    r"\brefactor\b",
    r"\bdebug\b",
    r"\barchitect(?:ure)?\b",
    r"\bdesign\s+(?:a|an)\s+(?:system|api|database|schema)\b",
    r"\bimplement\b.*\b(?:class|function|module|service)\b",
    r"\bmulti[\s-]step\b",
    r"\bcomprehensive\b",
    r"\bin[\s-]depth\b",
    r"\bdetailed\s+(?:analysis|review|breakdown)\b",
    r"\bcode\s+review\b",
]

# Simple indicators — short, factual, lookup
SIMPLE_PATTERNS = [
    r"^(?:what|who|when|where|how\s+(?:many|much|old|long|far))\b.{0,60}\?$",
    r"^(?:is|are|was|were|do|does|did|can|could|will|would)\b.{0,60}\?$",
    r"\btranslate\b.{0,30}\bto\b",
    r"\bdefine\b",
    r"\bwhat\s+(?:is|are|was)\s+(?:the|a|an)\b",
    r"\blist\b.{0,20}(?:top|best|main|key)\b",
    r"\bconvert\b",
    r"\bformat\b",
    r"\byes\s+or\s+no\b",
    r"\btrue\s+or\s+false\b",
]

# Length thresholds (character count)
SHORT_PROMPT = 200    # likely simple
MEDIUM_PROMPT = 1000  # moderate
LONG_PROMPT = 3000    # complex or reasoning


class ComplexityRouter:
    """Auto-classifies prompt complexity and routes to appropriate model/tier.

    Uses heuristic analysis of the prompt text:
        1. Pattern matching for reasoning/complex/simple indicators
        2. Prompt length as a signal
        3. Message count (multi-turn conversations are more complex)
        4. Presence of code blocks or structured data
    """

    def __init__(
        self,
        level_to_tier: dict[str, str] | None = None,
        level_models: dict[str, dict[str, str]] | None = None,
    ):
        self._level_to_tier = level_to_tier or LEVEL_TO_TIER
        self._level_models = level_models or LEVEL_MODELS
        self._classification_log: list[dict] = []

    def classify(self, prompt: str, message_count: int = 1) -> ClassificationResult:
        """Classify the complexity of a prompt.

        Args:
            prompt: The user's prompt text (or last message)
            message_count: Number of messages in the conversation

        Returns:
            ClassificationResult with level, tier, model suggestion, confidence
        """
        signals: list[str] = []
        scores = {
            "simple": 0.0,
            "medium": 0.0,
            "complex": 0.0,
            "reasoning": 0.0,
        }

        prompt_lower = prompt.lower().strip()
        prompt_len = len(prompt)

        # 1. Pattern matching
        for pattern in REASONING_PATTERNS:
            if re.search(pattern, prompt_lower):
                scores["reasoning"] += 2.0
                signals.append(f"reasoning_pattern:{pattern[:30]}")

        for pattern in COMPLEX_PATTERNS:
            if re.search(pattern, prompt_lower):
                scores["complex"] += 1.5
                signals.append(f"complex_pattern:{pattern[:30]}")

        for pattern in SIMPLE_PATTERNS:
            if re.search(pattern, prompt_lower):
                scores["simple"] += 1.5
                signals.append(f"simple_pattern:{pattern[:30]}")

        # 2. Length signal
        if prompt_len < SHORT_PROMPT:
            scores["simple"] += 1.0
            signals.append("short_prompt")
        elif prompt_len < MEDIUM_PROMPT:
            scores["medium"] += 1.0
            signals.append("medium_prompt")
        elif prompt_len < LONG_PROMPT:
            scores["complex"] += 0.5
            signals.append("long_prompt")
        else:
            scores["complex"] += 1.0
            scores["reasoning"] += 0.5
            signals.append("very_long_prompt")

        # 3. Code blocks
        code_blocks = prompt.count("```")
        if code_blocks >= 2:
            scores["complex"] += 1.0
            signals.append(f"code_blocks:{code_blocks // 2}")

        # 4. Multi-turn conversation
        if message_count > 5:
            scores["complex"] += 0.5
            signals.append(f"multi_turn:{message_count}")
        elif message_count > 10:
            scores["complex"] += 1.0

        # 5. Structured data (JSON, XML, tables)
        if re.search(r'\{["\']?\w+["\']?\s*:', prompt) or "<" in prompt:
            scores["medium"] += 0.5
            signals.append("structured_data")

        # 6. Default: if no strong signals, lean medium
        total_score = sum(scores.values())
        if total_score < 1.0:
            scores["medium"] += 1.0
            signals.append("default_medium")

        # Determine winner
        level_name = max(scores, key=scores.get)
        level = ComplexityLevel(level_name)
        max_score = scores[level_name]
        total = sum(scores.values())
        confidence = min(1.0, max_score / total if total > 0 else 0.5)

        tier = self._level_to_tier.get(level_name, "standard")
        model = self._level_models.get(level_name, {}).get("default", "gpt-4o")

        result = ClassificationResult(
            level=level,
            suggested_tier=tier,
            suggested_model=model,
            confidence=confidence,
            signals=signals,
        )

        self._classification_log.append(result.to_dict())
        if len(self._classification_log) > 500:
            self._classification_log = self._classification_log[-500:]

        return result

    def route(
        self,
        prompt: str,
        provider: str = "default",
        message_count: int = 1,
    ) -> str:
        """Classify and return the recommended model for a provider.

        One-shot convenience: classify complexity → pick model from provider.
        """
        result = self.classify(prompt, message_count)
        level_name = result.level.value
        models = self._level_models.get(level_name, {})
        return models.get(provider, models.get("default", "gpt-4o"))

    def get_log(self, limit: int = 50) -> list[dict]:
        """Return recent classification decisions."""
        return self._classification_log[-limit:]

    def reset(self):
        """Clear classification log."""
        self._classification_log.clear()
