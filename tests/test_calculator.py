"""
Tests for agentcost.cost.calculator — vendored model pricing.

Phase 1 validation:
    - Vendored cost map loads correctly (2,600+ models)
    - Cost calculation matches expected values
    - Provider prefix stripping works
    - Ollama tag stripping works
    - Cache-aware pricing works (Anthropic prompt caching)
    - Unknown models return zero cost (never block LLM calls)
    - Runtime model registration works
    - completion_cost works with dict and object responses
    - Backward compatibility with providers/tracked.py
    - Backward compatibility with estimator
    - Token estimation works (heuristic fallback)
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
    estimate_tokens,
    reload,
)


# ── Cost Map Loading ─────────────────────────────────────────────────────────


class TestCostMapLoading:
    def test_model_count_above_2000(self):
        """Vendored cost map should have 2000+ models."""
        assert model_count() > 2000

    def test_providers_include_major_clouds(self):
        providers = list_providers()
        for expected in ["openai", "anthropic", "gemini", "deepseek", "mistral"]:
            assert expected in providers, f"Missing provider: {expected}"

    def test_list_models_returns_sorted(self):
        models = list_models()
        assert len(models) > 100
        assert models == sorted(models)

    def test_list_models_by_provider(self):
        openai_models = list_models(provider="openai")
        assert len(openai_models) > 10
        assert all("gpt" in m or "o1" in m or "o3" in m or "o4" in m or "dall-e" in m or "tts" in m or "whisper" in m or "text-embedding" in m or "chatgpt" in m or "ft:" in m for m in openai_models[:5])

    def test_reload_works(self):
        """reload() should re-read from disk without error."""
        reload()
        assert model_count() > 2000


# ── Known Model Pricing ──────────────────────────────────────────────────────


class TestKnownModels:
    def test_gpt4o_pricing(self):
        pricing = get_pricing_per_1m("gpt-4o")
        assert pricing["input"] == pytest.approx(2.50, abs=0.01)
        assert pricing["output"] == pytest.approx(10.00, abs=0.01)

    def test_claude_sonnet_pricing(self):
        pricing = get_pricing_per_1m("claude-sonnet-4-5-20250929")
        assert pricing["input"] == pytest.approx(3.00, abs=0.01)
        assert pricing["output"] == pytest.approx(15.00, abs=0.01)

    def test_deepseek_pricing(self):
        pricing = get_pricing_per_1m("deepseek-chat")
        assert pricing["input"] == pytest.approx(0.28, abs=0.05)
        assert pricing["output"] == pytest.approx(0.42, abs=0.05)

    def test_gemini_flash_pricing(self):
        pricing = get_pricing_per_1m("gemini-2.0-flash")
        assert pricing["input"] == pytest.approx(0.10, abs=0.05)
        assert pricing["output"] == pytest.approx(0.40, abs=0.05)

    def test_model_info_has_required_fields(self):
        info = get_model_info("gpt-4o")
        assert info is not None
        assert "input_cost_per_token" in info
        assert "output_cost_per_token" in info
        assert "max_tokens" in info or "max_output_tokens" in info
        assert "litellm_provider" in info


# ── Cost Calculation ─────────────────────────────────────────────────────────


class TestCostCalculation:
    def test_cost_per_token_basic(self):
        inp, out, savings = cost_per_token("gpt-4o", 1000, 500)
        # 1000 * $2.50/1M + 500 * $10.00/1M = $0.0025 + $0.005 = $0.0075
        assert inp + out == pytest.approx(0.0075, abs=0.0001)

    def test_calculate_cost_backward_compat(self):
        cost = calculate_cost("gpt-4o", 1000, 500)
        assert cost == pytest.approx(0.0075, abs=0.0001)

    def test_zero_tokens_zero_cost(self):
        inp, out, sav = cost_per_token("gpt-4o", 0, 0)
        assert inp == 0.0
        assert out == 0.0

    def test_large_token_count(self):
        inp, out, sav = cost_per_token("gpt-4o", 1_000_000, 500_000)
        # 1M * $2.50/1M + 500K * $10.00/1M = $2.50 + $5.00 = $7.50
        assert inp + out == pytest.approx(7.50, abs=0.01)


# ── Unknown Models ───────────────────────────────────────────────────────────


class TestUnknownModels:
    def test_unknown_model_returns_zero(self):
        """Unknown models must return zero cost — NEVER block LLM calls."""
        inp, out, sav = cost_per_token("totally-unknown-model-xyz", 1000, 500)
        assert inp == 0.0
        assert out == 0.0
        assert sav == 0.0

    def test_unknown_model_info_is_none(self):
        info = get_model_info("totally-unknown-model-xyz")
        assert info is None

    def test_unknown_model_pricing_per_1m_is_zero(self):
        pricing = get_pricing_per_1m("totally-unknown-model-xyz")
        assert pricing["input"] == 0.0
        assert pricing["output"] == 0.0


# ── Provider Prefix Stripping ────────────────────────────────────────────────


class TestPrefixStripping:
    def test_openai_prefix(self):
        info = get_model_info("openai/gpt-4o")
        assert info is not None
        assert info.get("input_cost_per_token", 0) > 0

    def test_anthropic_prefix(self):
        info = get_model_info("anthropic/claude-sonnet-4-5-20250929")
        assert info is not None

    def test_groq_prefix(self):
        """groq/model should resolve if groq models exist in cost map."""
        # This tests the prefix stripping mechanism
        models = list_models(provider="groq")
        if models:
            info = get_model_info(f"groq/{models[0].replace('groq/', '')}")
            # Should at least not error


# ── Cache-Aware Pricing ──────────────────────────────────────────────────────


class TestCacheAwarePricing:
    def test_anthropic_cache_discount(self):
        """Cached tokens should cost less than non-cached."""
        info = get_model_info("claude-sonnet-4-5-20250929")
        assert info is not None

        full_cost, _, _ = cost_per_token("claude-sonnet-4-5-20250929", 1000, 0)
        cached_cost, _, savings = cost_per_token(
            "claude-sonnet-4-5-20250929", 1000, 0, cached_tokens=800
        )
        assert cached_cost < full_cost
        assert savings > 0

    def test_zero_cached_tokens_no_savings(self):
        _, _, savings = cost_per_token("gpt-4o", 1000, 500, cached_tokens=0)
        assert savings == 0.0

    def test_all_cached_maximum_savings(self):
        """When all tokens are cached, savings should be maximal."""
        full_inp, _, _ = cost_per_token("claude-sonnet-4-5-20250929", 1000, 0)
        cached_inp, _, savings = cost_per_token(
            "claude-sonnet-4-5-20250929", 1000, 0, cached_tokens=1000
        )
        assert cached_inp < full_inp
        assert savings == pytest.approx(full_inp - cached_inp, abs=0.000001)


# ── completion_cost ──────────────────────────────────────────────────────────


class TestCompletionCost:
    def test_dict_response(self):
        resp = {
            "model": "gpt-4o",
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }
        cost = completion_cost(resp)
        assert cost == pytest.approx(0.0075, abs=0.0001)

    def test_dict_response_with_model_override(self):
        resp = {
            "model": "unknown",
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }
        cost = completion_cost(resp, model="gpt-4o")
        assert cost == pytest.approx(0.0075, abs=0.0001)

    def test_empty_response_returns_zero(self):
        assert completion_cost({}) == 0.0
        assert completion_cost({"usage": {}}) == 0.0

    def test_anthropic_cache_in_response(self):
        resp = {
            "model": "claude-sonnet-4-5-20250929",
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "cache_read_input_tokens": 800,
            },
        }
        cost_with_cache = completion_cost(resp)
        resp_no_cache = {
            "model": "claude-sonnet-4-5-20250929",
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }
        cost_no_cache = completion_cost(resp_no_cache)
        assert cost_with_cache < cost_no_cache

    def test_object_response(self):
        """Test with an object that has attributes (like OpenAI SDK response)."""

        class MockUsage:
            prompt_tokens = 1000
            completion_tokens = 500
            cache_read_input_tokens = 0
            prompt_tokens_details = None

        class MockResponse:
            model = "gpt-4o"
            usage = MockUsage()

        cost = completion_cost(MockResponse())
        assert cost == pytest.approx(0.0075, abs=0.0001)


# ── Model Registration ───────────────────────────────────────────────────────


class TestModelRegistration:
    def test_register_model_per_1m(self):
        register_model_per_1m("test-corp/custom-v1", 2.00, 8.00)
        pricing = get_pricing_per_1m("test-corp/custom-v1")
        assert pricing["input"] == pytest.approx(2.00, abs=0.01)
        assert pricing["output"] == pytest.approx(8.00, abs=0.01)

    def test_register_model_raw(self):
        register_model("test-corp/custom-v2", {
            "input_cost_per_token": 0.000003,
            "output_cost_per_token": 0.000015,
        })
        cost = calculate_cost("test-corp/custom-v2", 1000, 500)
        assert cost > 0

    def test_runtime_override_takes_priority(self):
        """Runtime registration should override vendored data."""
        original = calculate_cost("gpt-4o", 1000, 500)
        register_model_per_1m("gpt-4o", 100.0, 200.0)  # Absurdly expensive
        overridden = calculate_cost("gpt-4o", 1000, 500)
        assert overridden > original
        # Clean up: reload to restore original pricing
        reload()


# ── Token Estimation ─────────────────────────────────────────────────────────


class TestTokenEstimation:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_short_text(self):
        tokens = estimate_tokens("Hello world")
        assert 1 <= tokens <= 5

    def test_longer_text(self):
        text = "The quick brown fox jumps over the lazy dog. " * 10
        tokens = estimate_tokens(text)
        assert tokens > 50


# ── Backward Compatibility ───────────────────────────────────────────────────


class TestBackwardCompatibility:
    def test_providers_tracked_calculate_cost(self):
        from agentcost.providers.tracked import calculate_cost as tracked_calc

        cost = tracked_calc("gpt-4o", 1000, 500)
        assert cost == pytest.approx(0.0075, abs=0.0001)

    def test_providers_tracked_get_pricing(self):
        from agentcost.providers.tracked import get_pricing

        pricing = get_pricing("gpt-4o")
        assert "input" in pricing
        assert "output" in pricing
        assert pricing["input"] > 0

    def test_estimator_works(self):
        from agentcost.estimator import CostEstimator

        estimator = CostEstimator()
        est = estimator.estimate("gpt-4o", "Hello world")
        assert est.estimated_cost > 0
        assert est.pricing_source == "known"

    def test_estimator_supported_models_expanded(self):
        from agentcost.estimator import CostEstimator

        estimator = CostEstimator()
        models = estimator.supported_models
        assert len(models) > 2000  # Was 42, now 2,600+

    def test_sdk_trace_calc(self):
        from agentcost.sdk.trace import _calc

        cost = _calc("gpt-4o", 1000, 500)
        assert cost == pytest.approx(0.0075, abs=0.0001)

    def test_cost_module_top_level_exports(self):
        from agentcost.cost import (
            cost_per_token,
            completion_cost,
            calculate_cost,
            model_count,
        )

        assert model_count() > 2000
        assert calculate_cost("gpt-4o", 1000, 500) > 0
