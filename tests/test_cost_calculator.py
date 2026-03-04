"""
Tests for agentcost.cost.calculator — the vendored cost calculation engine.

Covers:
  - Loading and model count validation
  - Cost calculation accuracy (known models)
  - Cache-aware pricing (Anthropic prompt caching)
  - Provider prefix stripping
  - Unknown model graceful degradation
  - Runtime model registration
  - Backward compatibility with providers/tracked.py and estimator
  - Dashboard registry generation
  - completion_cost from response dicts and objects
"""

import pytest
from agentcost.cost.calculator import (
    cost_per_token,
    completion_cost,
    calculate_cost,
    get_model_info,
    get_pricing_per_1m,
    register_model,
    register_model_per_1m,
    list_providers,
    list_models,
    model_count,
    get_model_registry_for_dashboard,
    estimate_tokens,
    reload,
)


# ── Loading & Model Count ────────────────────────────────────────────────────


class TestLoading:
    def test_model_count_minimum(self):
        """Vendored cost map should have 2000+ models."""
        assert model_count() > 2000

    def test_providers_exist(self):
        """Should have major providers."""
        providers = list_providers()
        assert "openai" in providers
        assert "anthropic" in providers
        assert "gemini" in providers or any("vertex" in p for p in providers)

    def test_list_models_returns_sorted(self):
        models = list_models()
        assert models == sorted(models)
        assert len(models) > 100

    def test_list_models_filter_by_provider(self):
        openai_models = list_models(provider="openai")
        assert len(openai_models) > 10
        for m in openai_models:
            info = get_model_info(m)
            assert info["litellm_provider"] == "openai"

    def test_reload(self):
        """reload() should re-read from disk without error."""
        reload()
        assert model_count() > 2000


# ── Cost Calculation ─────────────────────────────────────────────────────────


class TestCostPerToken:
    def test_gpt4o_basic(self):
        """GPT-4o: $2.50/MTok input, $10.00/MTok output."""
        inp, out, sav = cost_per_token("gpt-4o", 1000, 500)
        assert inp == pytest.approx(0.0025, rel=0.01)
        assert out == pytest.approx(0.005, rel=0.01)
        assert sav == 0.0

    def test_claude_sonnet(self):
        """Claude Sonnet 4.5: $3.00/MTok input, $15.00/MTok output."""
        inp, out, sav = cost_per_token("claude-sonnet-4-5-20250929", 1000, 500)
        assert inp == pytest.approx(0.003, rel=0.01)
        assert out == pytest.approx(0.0075, rel=0.01)

    def test_cache_aware_anthropic(self):
        """Cached tokens should cost 90% less for Anthropic."""
        # Without cache
        inp_full, out_full, _ = cost_per_token("claude-sonnet-4-5-20250929", 1000, 500, cached_tokens=0)
        # With 800 cached tokens
        inp_cached, out_cached, savings = cost_per_token("claude-sonnet-4-5-20250929", 1000, 500, cached_tokens=800)

        # Cached input should be cheaper
        assert inp_cached < inp_full
        assert savings > 0
        # Output cost unchanged
        assert out_cached == out_full

    def test_zero_tokens(self):
        inp, out, sav = cost_per_token("gpt-4o", 0, 0)
        assert inp == 0.0
        assert out == 0.0
        assert sav == 0.0

    def test_unknown_model_returns_zero(self):
        """Unknown models must return 0 — never block LLM calls."""
        inp, out, sav = cost_per_token("nonexistent-model-xyz-999", 1000, 500)
        assert inp == 0.0
        assert out == 0.0
        assert sav == 0.0

    def test_free_model(self):
        """Local/free models should have zero cost."""
        # Check if any ollama model is in the map
        info = get_model_info("ollama/llama3")
        if info:
            inp, out, _ = cost_per_token("ollama/llama3", 10000, 5000)
            assert inp == 0.0
            assert out == 0.0


class TestCalculateCost:
    def test_backward_compat(self):
        """calculate_cost should return total USD."""
        cost = calculate_cost("gpt-4o", 1000, 500)
        assert cost > 0
        assert cost == pytest.approx(0.0075, rel=0.01)

    def test_deepseek(self):
        cost = calculate_cost("deepseek-chat", 10000, 5000)
        assert cost > 0
        assert cost < 0.01  # DeepSeek is cheap


# ── Provider Prefix Stripping ────────────────────────────────────────────────


class TestPrefixStripping:
    def test_openai_prefix(self):
        info = get_model_info("openai/gpt-4o")
        assert info is not None

    def test_anthropic_prefix(self):
        info = get_model_info("anthropic/claude-sonnet-4-5-20250929")
        assert info is not None

    def test_groq_prefix(self):
        info = get_model_info("groq/llama-3.1-70b-versatile")
        # May or may not be in the map, but shouldn't error
        assert info is None or isinstance(info, dict)

    def test_cost_same_with_and_without_prefix(self):
        """Cost should be identical whether prefix is used or not."""
        cost1 = calculate_cost("gpt-4o", 1000, 500)
        cost2 = calculate_cost("openai/gpt-4o", 1000, 500)
        assert cost1 == cost2


# ── Model Registration ───────────────────────────────────────────────────────


class TestRegistration:
    def test_register_model(self):
        register_model("test-custom-model-abc", {
            "input_cost_per_token": 0.000001,
            "output_cost_per_token": 0.000005,
        })
        info = get_model_info("test-custom-model-abc")
        assert info is not None
        assert info["input_cost_per_token"] == 0.000001

    def test_register_model_per_1m(self):
        register_model_per_1m("test-human-readable-model", 2.50, 10.00)
        p = get_pricing_per_1m("test-human-readable-model")
        assert p["input"] == pytest.approx(2.50, rel=0.01)
        assert p["output"] == pytest.approx(10.00, rel=0.01)

    def test_override_takes_priority(self):
        """Runtime overrides should take priority over vendored data."""
        original = calculate_cost("gpt-4o", 1000, 500)
        register_model_per_1m("gpt-4o", 100.0, 200.0)  # Ridiculously expensive
        overridden = calculate_cost("gpt-4o", 1000, 500)
        assert overridden > original
        # Clean up by reloading
        reload()


# ── completion_cost ──────────────────────────────────────────────────────────


class TestCompletionCost:
    def test_from_dict(self):
        resp = {
            "model": "gpt-4o",
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }
        cost = completion_cost(resp)
        assert cost == pytest.approx(0.0075, rel=0.01)

    def test_from_dict_with_cache(self):
        resp = {
            "model": "claude-sonnet-4-5-20250929",
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "cache_read_input_tokens": 800,
            },
        }
        cost = completion_cost(resp)
        assert cost > 0

    def test_from_dict_openai_cache(self):
        resp = {
            "model": "gpt-4o",
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "prompt_tokens_details": {"cached_tokens": 800},
            },
        }
        cost = completion_cost(resp)
        assert cost > 0

    def test_model_override(self):
        """Model parameter should override response.model."""
        resp = {
            "model": "gpt-4o",
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }
        cost_gpt = completion_cost(resp)
        cost_override = completion_cost(resp, model="gpt-4o-mini")
        assert cost_override < cost_gpt  # mini is cheaper

    def test_empty_response(self):
        assert completion_cost({}) == 0.0
        assert completion_cost({"model": "gpt-4o"}) == 0.0

    def test_invalid_input(self):
        assert completion_cost("not a dict") == 0.0
        assert completion_cost(None) == 0.0
        assert completion_cost(42) == 0.0


# ── Pricing Queries ──────────────────────────────────────────────────────────


class TestPricingQueries:
    def test_get_pricing_per_1m(self):
        p = get_pricing_per_1m("gpt-4o")
        assert p["input"] == pytest.approx(2.50, rel=0.01)
        assert p["output"] == pytest.approx(10.00, rel=0.01)
        assert "cache_read" in p

    def test_unknown_model_pricing(self):
        p = get_pricing_per_1m("nonexistent-model")
        assert p["input"] == 0.0
        assert p["output"] == 0.0

    def test_get_model_info(self):
        info = get_model_info("gpt-4o")
        assert info is not None
        assert "input_cost_per_token" in info
        assert "max_input_tokens" in info
        assert "litellm_provider" in info
        assert info["litellm_provider"] == "openai"


# ── Token Estimation ─────────────────────────────────────────────────────────


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_heuristic_fallback(self):
        # ~4 chars per token, so 100 chars ≈ 25 tokens
        tokens = estimate_tokens("a" * 100)
        assert 20 <= tokens <= 30

    def test_returns_at_least_one(self):
        assert estimate_tokens("Hi") >= 1


# ── Dashboard Registry ───────────────────────────────────────────────────────


class TestDashboardRegistry:
    def test_returns_list(self):
        registry = get_model_registry_for_dashboard()
        assert isinstance(registry, list)
        assert len(registry) > 100

    def test_entry_format(self):
        registry = get_model_registry_for_dashboard()
        entry = registry[0]
        assert "id" in entry
        assert "provider" in entry
        assert "input" in entry
        assert "output" in entry
        assert "tier" in entry
        assert "context" in entry

    def test_filter_by_provider(self):
        openai_only = get_model_registry_for_dashboard(providers=["openai"])
        assert len(openai_only) > 0
        for entry in openai_only:
            assert entry["provider"] == "openai"


# ── Backward Compatibility ───────────────────────────────────────────────────


class TestBackwardCompat:
    def test_providers_tracked_get_pricing(self):
        """providers.tracked.get_pricing should still return per-1M-token dict."""
        from agentcost.providers.tracked import get_pricing
        p = get_pricing("gpt-4o")
        assert "input" in p
        assert "output" in p
        assert p["input"] == pytest.approx(2.50, rel=0.01)

    def test_providers_tracked_calculate_cost(self):
        from agentcost.providers.tracked import calculate_cost
        cost = calculate_cost("gpt-4o", 1000, 500)
        assert cost == pytest.approx(0.0075, rel=0.01)

    def test_estimator_still_works(self):
        from agentcost.estimator import CostEstimator
        est = CostEstimator()
        result = est.estimate("gpt-4o", "Hello world", task_type="chat")
        assert result.estimated_cost > 0
        assert result.pricing_source == "known"

    def test_estimator_custom_pricing(self):
        from agentcost.estimator import CostEstimator
        est = CostEstimator(custom_pricing={"my-test-model": (5.0, 20.0)})
        result = est.estimate("my-test-model", "Hello world")
        assert result.estimated_cost > 0

    def test_sdk_trace_imports(self):
        from agentcost.sdk.trace import CostTracker, _calc
        cost = _calc("gpt-4o", 1000, 500)
        assert cost == pytest.approx(0.0075, rel=0.01)
