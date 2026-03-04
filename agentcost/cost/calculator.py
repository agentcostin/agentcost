"""
AgentCost Cost Calculator — native cost tracking with vendored model pricing.

Replaces the previous approach of three duplicate MODEL_PRICING dicts
(providers/tracked.py, estimator/__init__.py, dashboard/js/models.js)
with a single source of truth: the vendored LiteLLM model_prices.json
(2,600+ models from 40+ providers, community-maintained).

Design principles:
    - Zero external dependencies (no `pip install litellm` required)
    - Cost tracking failures NEVER block LLM calls
    - Overrides take priority (custom/private models in overrides.json)
    - Provider-prefix stripping for flexible model name matching
    - Cache-aware pricing (Anthropic prompt caching, etc.)

Usage:
    from agentcost.cost.calculator import (
        cost_per_token,
        completion_cost,
        get_model_info,
        register_model,
        list_providers,
        list_models,
    )

    # Calculate cost from known token counts
    input_cost, output_cost, cache_savings = cost_per_token(
        "gpt-4o", prompt_tokens=1000, completion_tokens=500
    )

    # Calculate cost from an OpenAI-compatible response dict
    total = completion_cost(response_dict)

    # Register a custom model at runtime
    register_model("my-corp/fine-tuned-llama", {
        "input_cost_per_token": 0.0000005,
        "output_cost_per_token": 0.0000015,
        "litellm_provider": "custom",
    })
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("agentcost.cost.calculator")

# ── Module-level state ───────────────────────────────────────────────────────

_COST_MAP: dict[str, dict] = {}
_OVERRIDES: dict[str, dict] = {}
_RUNTIME_OVERRIDES: dict[str, dict] = {}
_LOADED: bool = False

# Where the vendored data lives (relative to this file)
_DATA_DIR = Path(__file__).parent
_COST_MAP_PATH = _DATA_DIR / "model_prices.json"
_OVERRIDES_PATH = _DATA_DIR / "overrides.json"

# Common provider prefixes that LiteLLM uses in model names
_PROVIDER_PREFIXES = (
    "openai/",
    "anthropic/",
    "groq/",
    "together_ai/",
    "mistral/",
    "bedrock/",
    "bedrock_converse/",
    "vertex_ai/",
    "vertex_ai-language-models/",
    "azure/",
    "azure_ai/",
    "ollama/",
    "ollama_chat/",
    "huggingface/",
    "replicate/",
    "cohere/",
    "deepseek/",
    "fireworks_ai/",
    "anyscale/",
    "perplexity/",
    "deepinfra/",
    "openrouter/",
    "novita/",
    "vercel_ai_gateway/",
)


# ── Loading ──────────────────────────────────────────────────────────────────


def _ensure_loaded():
    """Lazy-load the cost map on first access."""
    global _COST_MAP, _OVERRIDES, _LOADED
    if _LOADED:
        return

    # Load vendored cost map
    if _COST_MAP_PATH.exists():
        try:
            with open(_COST_MAP_PATH) as f:
                _COST_MAP = json.load(f)
            logger.debug(f"Loaded {len(_COST_MAP)} models from {_COST_MAP_PATH.name}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load model_prices.json: {e}")
            _COST_MAP = {}
    else:
        logger.warning(f"Vendored cost map not found at {_COST_MAP_PATH}")
        _COST_MAP = {}

    # Load overrides
    if _OVERRIDES_PATH.exists():
        try:
            with open(_OVERRIDES_PATH) as f:
                raw = json.load(f)
            # Filter out comment keys
            _OVERRIDES = {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict)}
            if _OVERRIDES:
                logger.debug(f"Loaded {len(_OVERRIDES)} pricing overrides")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load overrides.json: {e}")
            _OVERRIDES = {}

    # Also check env-var for Ollama custom pricing
    _env_ollama = os.environ.get("AGENTCOST_OLLAMA_PRICING")
    if _env_ollama:
        try:
            parts = _env_ollama.split(",")
            inp = float(parts[0]) / 1_000_000  # Convert from per-1M to per-token
            out = float(parts[1]) / 1_000_000 if len(parts) > 1 else inp
            _OVERRIDES["_ollama_env"] = {"input_cost_per_token": inp, "output_cost_per_token": out}
        except (ValueError, IndexError):
            pass

    _LOADED = True


def reload():
    """Force reload of cost map and overrides (e.g. after sync_upstream)."""
    global _LOADED, _RUNTIME_OVERRIDES
    _LOADED = False
    _RUNTIME_OVERRIDES = {}
    _ensure_loaded()


# ── Model Lookup ─────────────────────────────────────────────────────────────


def _resolve_model(model: str) -> Optional[dict]:
    """
    Look up model pricing info with multi-strategy matching.

    Priority:
        1. Runtime overrides (register_model)
        2. File overrides (overrides.json)
        3. Exact match in vendored cost map
        4. Strip provider prefix and retry
        5. Strip Ollama tags (:7b, :latest) and retry
        6. Substring match as last resort
    """
    _ensure_loaded()

    # 1. Runtime overrides
    if model in _RUNTIME_OVERRIDES:
        return _RUNTIME_OVERRIDES[model]

    # 2. File overrides
    if model in _OVERRIDES:
        return _OVERRIDES[model]

    # 3. Exact match in vendored map
    if model in _COST_MAP:
        return _COST_MAP[model]

    # 4. Strip provider prefix
    stripped = model
    for prefix in _PROVIDER_PREFIXES:
        if model.startswith(prefix):
            stripped = model[len(prefix):]
            break

    if stripped != model:
        if stripped in _RUNTIME_OVERRIDES:
            return _RUNTIME_OVERRIDES[stripped]
        if stripped in _OVERRIDES:
            return _OVERRIDES[stripped]
        if stripped in _COST_MAP:
            return _COST_MAP[stripped]

    # 5. Strip Ollama tags (e.g. "llama3:8b" → "llama3")
    if ":" in stripped:
        base = stripped.split(":")[0]
        if base in _COST_MAP:
            return _COST_MAP[base]

    # 6. Substring fallback (e.g. "gpt-4o-2024-08-06" matches "gpt-4o")
    # Only check shorter known keys that are prefixes of the query
    for key, val in _COST_MAP.items():
        if isinstance(val, dict) and (model.startswith(key) or stripped.startswith(key)):
            return val

    return None


# ── Core API ─────────────────────────────────────────────────────────────────


def cost_per_token(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
) -> tuple[float, float, float]:
    """
    Calculate cost from token counts.

    Args:
        model: Model name (e.g. "gpt-4o", "claude-sonnet-4-5-20250929")
        prompt_tokens: Number of input/prompt tokens
        completion_tokens: Number of output/completion tokens
        cached_tokens: Number of cached input tokens (subset of prompt_tokens)

    Returns:
        Tuple of (input_cost_usd, output_cost_usd, cache_savings_usd).
        Returns (0.0, 0.0, 0.0) for unknown models — cost tracking
        failures must NEVER block LLM calls.
    """
    info = _resolve_model(model)

    if info is None:
        logger.debug(f"Unknown model '{model}' — returning zero cost")
        return 0.0, 0.0, 0.0

    input_cpt = info.get("input_cost_per_token", 0.0) or 0.0
    output_cpt = info.get("output_cost_per_token", 0.0) or 0.0
    cache_read_cpt = info.get("cache_read_input_token_cost", input_cpt) or input_cpt

    # Calculate costs
    regular_input_tokens = max(0, prompt_tokens - cached_tokens)
    input_cost = (regular_input_tokens * input_cpt) + (cached_tokens * cache_read_cpt)
    output_cost = completion_tokens * output_cpt
    cache_savings = cached_tokens * (input_cpt - cache_read_cpt)

    return input_cost, output_cost, max(0.0, cache_savings)


def completion_cost(
    response: dict | Any,
    model: str | None = None,
) -> float:
    """
    Calculate cost from an OpenAI-compatible response dict.

    Works with responses from OpenAI, Anthropic, LiteLLM, and any provider
    that returns usage.prompt_tokens / usage.completion_tokens.

    Args:
        response: The LLM API response (dict or object with .usage)
        model: Override model name (uses response.model if not provided)

    Returns:
        Total cost in USD. Returns 0.0 if calculation fails.
    """
    try:
        # Handle both dict and object responses
        if hasattr(response, "model"):
            _model = model or getattr(response, "model", "") or ""
            usage = getattr(response, "usage", None)
            if usage:
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                # Anthropic-style cache info
                cache_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0
                # OpenAI-style cache info
                if not cache_tokens:
                    details = getattr(usage, "prompt_tokens_details", None)
                    if details:
                        cache_tokens = getattr(details, "cached_tokens", 0) or 0
            else:
                prompt_tokens = completion_tokens = cache_tokens = 0
        elif isinstance(response, dict):
            _model = model or response.get("model", "") or ""
            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0) or 0
            completion_tokens = usage.get("completion_tokens", 0) or 0
            # Anthropic-style
            cache_tokens = usage.get("cache_read_input_tokens", 0) or 0
            # OpenAI-style
            if not cache_tokens:
                details = usage.get("prompt_tokens_details", {})
                if isinstance(details, dict):
                    cache_tokens = details.get("cached_tokens", 0) or 0
        else:
            return 0.0

        input_cost, output_cost, _ = cost_per_token(
            _model, prompt_tokens, completion_tokens, cache_tokens
        )
        return input_cost + output_cost

    except Exception as e:
        logger.debug(f"completion_cost failed: {e}")
        return 0.0


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Simple cost calculation (backward-compatible with providers/tracked.py).

    Returns total cost in USD.
    """
    input_cost, output_cost, _ = cost_per_token(model, input_tokens, output_tokens)
    return input_cost + output_cost


# ── Model Registration ───────────────────────────────────────────────────────


def register_model(model: str, pricing: dict):
    """
    Register or override pricing for a model at runtime.

    Args:
        model: Model name
        pricing: Dict with at minimum 'input_cost_per_token' and 'output_cost_per_token'.
                 Can also include 'cache_read_input_token_cost', 'max_tokens', etc.
    """
    _ensure_loaded()
    _RUNTIME_OVERRIDES[model] = pricing
    logger.info(f"Registered runtime pricing for '{model}'")


def register_model_per_1m(
    model: str,
    input_per_1m: float,
    output_per_1m: float,
    cache_read_per_1m: float | None = None,
    **extra,
):
    """
    Register model pricing using per-1M-token format (more human-readable).

    Args:
        model: Model name
        input_per_1m: USD per 1 million input tokens
        output_per_1m: USD per 1 million output tokens
        cache_read_per_1m: USD per 1M cached input tokens (optional)
        **extra: Additional fields (max_tokens, litellm_provider, mode, etc.)
    """
    pricing = {
        "input_cost_per_token": input_per_1m / 1_000_000,
        "output_cost_per_token": output_per_1m / 1_000_000,
        **extra,
    }
    if cache_read_per_1m is not None:
        pricing["cache_read_input_token_cost"] = cache_read_per_1m / 1_000_000
    register_model(model, pricing)


# ── Query API ────────────────────────────────────────────────────────────────


def get_model_info(model: str) -> Optional[dict]:
    """Get full pricing and metadata for a model. Returns None if unknown."""
    return _resolve_model(model)


def get_pricing_per_1m(model: str) -> dict[str, float]:
    """
    Get pricing in per-1M-token format (human-readable).

    Returns:
        {"input": X, "output": Y, "cache_read": Z} in USD per 1M tokens.
        Falls back to {"input": 0.0, "output": 0.0} for unknown models.
    """
    info = _resolve_model(model)
    if info is None:
        return {"input": 0.0, "output": 0.0, "cache_read": 0.0}
    return {
        "input": (info.get("input_cost_per_token", 0.0) or 0.0) * 1_000_000,
        "output": (info.get("output_cost_per_token", 0.0) or 0.0) * 1_000_000,
        "cache_read": (info.get("cache_read_input_token_cost", 0.0) or 0.0) * 1_000_000,
    }


def list_models(provider: str | None = None) -> list[str]:
    """List all known model names, optionally filtered by provider."""
    _ensure_loaded()

    all_maps = [_COST_MAP, _OVERRIDES, _RUNTIME_OVERRIDES]
    models = set()
    for m in all_maps:
        for k, v in m.items():
            if k.startswith("_"):
                continue
            if not isinstance(v, dict):
                continue
            if provider and v.get("litellm_provider", "") != provider:
                continue
            models.add(k)
    return sorted(models)


def list_providers() -> list[str]:
    """List all known provider names."""
    _ensure_loaded()

    providers = set()
    for v in _COST_MAP.values():
        if isinstance(v, dict) and "litellm_provider" in v:
            providers.add(v["litellm_provider"])
    return sorted(providers)


def model_count() -> int:
    """Total number of models with pricing data."""
    _ensure_loaded()
    return len(_COST_MAP) + len(_OVERRIDES) + len(_RUNTIME_OVERRIDES)


def get_model_registry_for_dashboard(
    providers: list[str] | None = None,
    tiers: list[str] | None = None,
) -> list[dict]:
    """
    Generate model registry entries for the dashboard UI.

    Returns a list of dicts matching the dashboard/js/models.js format:
        {id, provider, label, input, output, tier, context, cache_read}

    Pricing is returned in per-1M-token format.
    """
    _ensure_loaded()

    # Tier classification based on input cost per 1M tokens
    def _classify_tier(info: dict) -> str:
        input_per_1m = (info.get("input_cost_per_token", 0.0) or 0.0) * 1_000_000
        mode = info.get("mode", "chat")
        if input_per_1m == 0.0:
            return "free"
        if input_per_1m >= 5.0:
            return "flagship"
        if input_per_1m >= 1.0:
            return "balanced"
        if input_per_1m >= 0.1:
            return "fast"
        return "budget"

    results = []
    seen = set()

    for model_name, info in _COST_MAP.items():
        if not isinstance(info, dict):
            continue
        if model_name.startswith("_"):
            continue

        provider = info.get("litellm_provider", "unknown")
        if providers and provider not in providers:
            continue

        tier = _classify_tier(info)
        if tiers and tier not in tiers:
            continue

        # Deduplicate — prefer shorter model names
        if model_name in seen:
            continue
        seen.add(model_name)

        input_per_1m = (info.get("input_cost_per_token", 0.0) or 0.0) * 1_000_000
        output_per_1m = (info.get("output_cost_per_token", 0.0) or 0.0) * 1_000_000
        cache_per_1m = (info.get("cache_read_input_token_cost", 0.0) or 0.0) * 1_000_000
        try:
            context_k = int(info.get("max_input_tokens", 0) or 0) / 1000
        except (ValueError, TypeError):
            context_k = 0

        results.append({
            "id": model_name,
            "provider": provider,
            "label": model_name,
            "input": round(input_per_1m, 4),
            "output": round(output_per_1m, 4),
            "cache_read": round(cache_per_1m, 4),
            "tier": tier,
            "context": int(context_k),
            "mode": info.get("mode", "chat"),
        })

    return results


# ── Token Estimation ─────────────────────────────────────────────────────────


def estimate_tokens(text: str, model: str | None = None) -> int:
    """
    Estimate token count for a text string.

    Uses tiktoken if available (accurate for OpenAI models),
    falls back to ~4-chars-per-token heuristic.
    """
    if not text:
        return 0

    try:
        import tiktoken

        # Try model-specific encoding first
        if model:
            try:
                enc = tiktoken.encoding_for_model(model)
                return len(enc.encode(text))
            except (KeyError, Exception):
                pass
        # Fall back to cl100k_base (GPT-4/Claude-approximate)
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        # tiktoken not installed, encoding download failed, or any other error
        pass

    # Heuristic fallback: ~4 chars per token for English
    return max(1, len(text) // 4)
