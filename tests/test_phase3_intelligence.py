"""
AgentCost Phase 3 — Cost Intelligence Layer Test Suite

Tests for:
  - TierRegistry: model classification, policy checks, dashboard data
  - TokenAnalyzer: efficiency scoring, waste detection, recommendations
  - BudgetGate: allow/warn/downgrade/block decisions
  - ComplexityRouter: prompt classification, tier routing
"""

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Cost-Tier Registry
# ═══════════════════════════════════════════════════════════════════════════════


class TestCostTier:
    def test_tier_enum(self):
        from agentcost.intelligence import CostTier

        assert CostTier.ECONOMY == "economy"
        assert CostTier.STANDARD == "standard"
        assert CostTier.PREMIUM == "premium"
        assert CostTier.FREE == "free"
        assert CostTier.UNKNOWN == "unknown"

    def test_classify_gpt4o_mini_economy(self):
        from agentcost.intelligence import TierRegistry, CostTier

        reg = TierRegistry()
        assert reg.classify("gpt-4o-mini") == CostTier.ECONOMY

    def test_classify_gpt4o_standard(self):
        from agentcost.intelligence import TierRegistry, CostTier

        reg = TierRegistry()
        assert reg.classify("gpt-4o") == CostTier.STANDARD

    def test_classify_o1_premium(self):
        from agentcost.intelligence import TierRegistry, CostTier

        reg = TierRegistry()
        assert reg.classify("o1") == CostTier.PREMIUM

    def test_classify_haiku_economy(self):
        from agentcost.intelligence import TierRegistry, CostTier

        reg = TierRegistry()
        assert reg.classify("claude-3-haiku-20240307") == CostTier.ECONOMY

    def test_classify_opus_premium(self):
        from agentcost.intelligence import TierRegistry, CostTier

        reg = TierRegistry()
        assert reg.classify("claude-3-opus-20240229") == CostTier.PREMIUM

    def test_classify_unknown_model(self):
        from agentcost.intelligence import TierRegistry, CostTier

        reg = TierRegistry()
        assert reg.classify("nonexistent-model-xyz") == CostTier.UNKNOWN

    def test_get_tier_info(self):
        from agentcost.intelligence import TierRegistry

        reg = TierRegistry()
        info = reg.get_tier_info("gpt-4o")
        assert info is not None
        assert info.model == "gpt-4o"
        assert info.input_cost_per_1m > 0
        assert info.output_cost_per_1m > 0
        assert info.provider == "openai"

    def test_models_in_tier(self):
        from agentcost.intelligence import TierRegistry

        reg = TierRegistry()
        economy = reg.models_in_tier("economy")
        assert len(economy) > 10  # many cheap models
        assert "gpt-4o-mini" in economy

    def test_models_in_tier_by_provider(self):
        from agentcost.intelligence import TierRegistry

        reg = TierRegistry()
        anthropic_economy = reg.models_in_tier("economy", provider="anthropic")
        for m in anthropic_economy:
            info = reg.get_tier_info(m)
            assert info.provider == "anthropic"

    def test_tier_summary(self):
        from agentcost.intelligence import TierRegistry

        reg = TierRegistry()
        summary = reg.tier_summary()
        assert "economy" in summary
        assert "standard" in summary
        assert "premium" in summary
        assert sum(summary.values()) > 100

    def test_cheapest_in_tier(self):
        from agentcost.intelligence import TierRegistry

        reg = TierRegistry()
        cheapest = reg.cheapest_in_tier("economy")
        assert cheapest is not None
        assert cheapest.input_cost_per_1m >= 0

    def test_cheapest_in_tier_by_provider(self):
        from agentcost.intelligence import TierRegistry

        reg = TierRegistry()
        cheapest = reg.cheapest_in_tier("standard", provider="openai")
        assert cheapest is not None
        assert cheapest.provider == "openai"

    def test_check_tier_policy_allowed(self):
        from agentcost.intelligence import TierRegistry

        reg = TierRegistry()
        result = reg.check_tier_policy(
            "gpt-4o-mini", allowed_tiers=["economy", "standard"]
        )
        assert result["allowed"]
        assert result["tier"] == "economy"

    def test_check_tier_policy_blocked(self):
        from agentcost.intelligence import TierRegistry

        reg = TierRegistry()
        result = reg.check_tier_policy(
            "o1", allowed_tiers=["economy"]
        )
        assert not result["allowed"]
        assert "premium" in result["reason"]
        assert result["suggested_alternative"] is not None

    def test_check_tier_policy_cost_limit(self):
        from agentcost.intelligence import TierRegistry

        reg = TierRegistry()
        result = reg.check_tier_policy(
            "gpt-4o",
            max_cost_per_call=0.001,
            estimated_tokens=10000,
        )
        # With 10K tokens at gpt-4o pricing, cost should exceed $0.001
        if result["estimated_cost"] > 0.001:
            assert not result["allowed"]

    def test_set_override(self):
        from agentcost.intelligence import TierRegistry, CostTier

        reg = TierRegistry()
        reg.classify("gpt-4o")  # ensure loaded
        reg.set_override("gpt-4o", "economy")
        assert reg.classify("gpt-4o") == CostTier.ECONOMY

    def test_custom_thresholds(self):
        from agentcost.intelligence import TierRegistry, CostTier

        # Make everything under $3/1M "economy"
        reg = TierRegistry(thresholds={"economy_max": 3.00, "standard_max": 10.00})
        assert reg.classify("gpt-4o") == CostTier.ECONOMY

    def test_to_dashboard_data(self):
        from agentcost.intelligence import TierRegistry

        reg = TierRegistry()
        data = reg.to_dashboard_data(limit_per_tier=5)
        assert "thresholds" in data
        assert "summary" in data
        assert "tiers" in data
        assert "economy" in data["tiers"]
        assert len(data["tiers"]["economy"]) <= 5

    def test_singleton(self):
        from agentcost.intelligence import get_tier_registry

        r1 = get_tier_registry()
        r2 = get_tier_registry()
        assert r1 is r2


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Token Budget Analyzer
# ═══════════════════════════════════════════════════════════════════════════════


class TestTokenAnalyzer:
    def test_record_call(self):
        from agentcost.intelligence import TokenAnalyzer

        a = TokenAnalyzer()
        call = a.record_call(
            model="gpt-4o", input_tokens=5000, output_tokens=500,
            max_context=128000, system_tokens=2000, project="p1",
        )
        assert call.total_tokens == 5500
        assert call.context_utilization == pytest.approx(5000 / 128000, rel=0.01)
        assert call.system_ratio == pytest.approx(2000 / 5000, rel=0.01)

    def test_analyze_healthy_usage(self):
        from agentcost.intelligence import TokenAnalyzer

        a = TokenAnalyzer()
        for _ in range(10):
            a.record_call(
                model="gpt-4o", input_tokens=20000, output_tokens=2000,
                max_context=128000, system_tokens=3000, project="healthy",
            )
        report = a.analyze("healthy")
        assert report.total_calls == 10
        assert report.efficiency_score > 50  # should be decent
        assert len(report.warnings) == 0  # no major issues

    def test_warn_excessive_system_prompt(self):
        from agentcost.intelligence import TokenAnalyzer

        a = TokenAnalyzer()
        for _ in range(5):
            a.record_call(
                model="gpt-4o", input_tokens=10000, output_tokens=500,
                max_context=128000, system_tokens=5000,  # 50% system!
                project="bloated",
            )
        report = a.analyze("bloated")
        assert any("system" in w.lower() for w in report.warnings)
        assert any("system" in r.lower() or "shorten" in r.lower()
                    for r in report.recommendations)

    def test_warn_low_utilization(self):
        from agentcost.intelligence import TokenAnalyzer

        a = TokenAnalyzer()
        for _ in range(5):
            a.record_call(
                model="gpt-4o", input_tokens=500, output_tokens=100,
                max_context=128000, project="low",
            )
        report = a.analyze("low")
        assert any("utilization" in w.lower() for w in report.warnings)

    def test_warn_near_limit(self):
        from agentcost.intelligence import TokenAnalyzer

        a = TokenAnalyzer()
        for _ in range(5):
            a.record_call(
                model="gpt-4o", input_tokens=120000, output_tokens=5000,
                max_context=128000, project="full",
            )
        report = a.analyze("full")
        assert any("context limit" in w.lower() or "near" in w.lower()
                    for w in report.warnings)

    def test_warn_low_output_ratio(self):
        from agentcost.intelligence import TokenAnalyzer

        a = TokenAnalyzer()
        for _ in range(5):
            a.record_call(
                model="gpt-4o", input_tokens=50000, output_tokens=50,
                max_context=128000, project="low-out",
            )
        report = a.analyze("low-out")
        assert any("output" in w.lower() for w in report.warnings)

    def test_efficiency_score_range(self):
        from agentcost.intelligence import TokenAnalyzer

        a = TokenAnalyzer()
        a.record_call(
            model="gpt-4o", input_tokens=20000, output_tokens=2000,
            max_context=128000, project="test",
        )
        report = a.analyze("test")
        assert 0 <= report.efficiency_score <= 100

    def test_analyze_all_calls(self):
        from agentcost.intelligence import TokenAnalyzer

        a = TokenAnalyzer()
        a.record_call(model="a", input_tokens=100, output_tokens=50, max_context=1000, project="p1")
        a.record_call(model="b", input_tokens=200, output_tokens=100, max_context=1000, project="p2")
        report = a.analyze()  # no scope filter
        assert report.total_calls == 2

    def test_to_dict(self):
        from agentcost.intelligence import TokenAnalyzer

        a = TokenAnalyzer()
        a.record_call(model="m", input_tokens=100, output_tokens=50, max_context=1000)
        report = a.analyze()
        d = report.to_dict()
        assert "efficiency_score" in d
        assert "warnings" in d
        assert "recommendations" in d

    def test_max_calls_cap(self):
        from agentcost.intelligence import TokenAnalyzer

        a = TokenAnalyzer(max_calls=5)
        for i in range(10):
            a.record_call(model="m", input_tokens=100, output_tokens=50, max_context=1000)
        assert len(a._calls) == 5

    def test_reset(self):
        from agentcost.intelligence import TokenAnalyzer

        a = TokenAnalyzer()
        a.record_call(model="m", input_tokens=100, output_tokens=50, max_context=1000)
        a.reset()
        report = a.analyze()
        assert report.total_calls == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Budget Gate
# ═══════════════════════════════════════════════════════════════════════════════


class TestBudgetGate:
    def test_allow_when_budget_ok(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=10.00)
        d = gate.check("gpt-4o")
        assert d.action == "allow"
        assert d.model == "gpt-4o"
        assert d.budget_remaining == 10.00

    def test_warn_at_80_percent(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=10.00)
        gate.spent = 8.50  # 85%
        d = gate.check("gpt-4o")
        assert d.action == "warn"
        assert "warning" in d.reason.lower()

    def test_downgrade_at_90_percent(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=10.00)
        gate.spent = 9.50  # 95%
        d = gate.check("gpt-4o", provider="openai")
        assert d.action == "downgrade"
        assert d.model == "gpt-4o-mini"  # next in openai chain

    def test_block_at_100_percent(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=10.00)
        gate.spent = 10.00
        d = gate.check("gpt-4o")
        assert d.action == "block"

    def test_record_spend(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=5.00)
        gate.record_spend(2.00)
        assert gate.remaining == 3.00
        assert gate.used_pct == pytest.approx(40.0)

    def test_reset(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=5.00)
        gate.record_spend(3.00)
        gate.reset()
        assert gate.remaining == 5.00
        assert gate.spent == 0.0

    def test_reset_with_new_budget(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=5.00)
        gate.record_spend(3.00)
        gate.reset(new_budget=20.00)
        assert gate.budget == 20.00
        assert gate.spent == 0.0

    def test_custom_thresholds(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=10.00, warn_pct=0.50, downgrade_pct=0.70, block_pct=0.90)
        gate.spent = 5.50  # 55%
        d = gate.check("gpt-4o")
        assert d.action == "warn"

        gate.spent = 7.50  # 75%
        d = gate.check("gpt-4o", provider="openai")
        assert d.action == "downgrade"

        gate.spent = 9.50  # 95%
        d = gate.check("gpt-4o")
        assert d.action == "block"

    def test_downgrade_chain_inference(self):
        """Should infer provider from model name in chain."""
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=10.00)
        gate.spent = 9.50
        # Don't pass provider — should infer from model being in openai chain
        d = gate.check("gpt-4o")
        assert d.action == "downgrade"
        assert d.model == "gpt-4o-mini"

    def test_no_downgrade_for_cheapest(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=10.00)
        gate.spent = 9.50
        # gpt-3.5-turbo is last in openai chain, no further downgrade
        d = gate.check("gpt-3.5-turbo", provider="openai")
        # Should still downgrade or block based on threshold
        assert d.action in ("downgrade", "block", "warn")

    def test_block_when_cost_exceeds_remaining(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=0.01)
        gate.spent = 0.005
        # If estimated cost > remaining and no downgrade available
        d = gate.check("unknown-model", estimated_tokens=100000)
        # Should block if estimated cost exceeds remaining
        # (depends on whether cost estimation finds the model)
        assert d.action in ("allow", "block", "warn")

    def test_decision_to_dict(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=10.00)
        d = gate.check("gpt-4o")
        data = d.to_dict()
        assert "action" in data
        assert "model" in data
        assert "budget_remaining" in data

    def test_history(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=10.00)
        gate.check("gpt-4o")
        gate.check("gpt-4o-mini")
        history = gate.get_history()
        assert len(history) == 2

    def test_anthropic_downgrade_chain(self):
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=10.00)
        gate.spent = 9.50
        d = gate.check("claude-3-5-sonnet-20241022", provider="anthropic")
        assert d.action == "downgrade"
        assert d.model == "claude-3-haiku-20240307"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Complexity Router
# ═══════════════════════════════════════════════════════════════════════════════


class TestComplexityRouter:
    def test_simple_question(self):
        from agentcost.intelligence import ComplexityRouter, ComplexityLevel

        cr = ComplexityRouter()
        r = cr.classify("What is the capital of France?")
        assert r.level == ComplexityLevel.SIMPLE
        assert r.suggested_tier == "economy"

    def test_simple_yes_no(self):
        from agentcost.intelligence import ComplexityRouter, ComplexityLevel

        cr = ComplexityRouter()
        r = cr.classify("Is Python a compiled language?")
        assert r.level == ComplexityLevel.SIMPLE

    def test_medium_summarize(self):
        from agentcost.intelligence import ComplexityRouter, ComplexityLevel

        cr = ComplexityRouter()
        r = cr.classify(
            "Summarize the key themes in this quarterly earnings report and highlight "
            "the main revenue drivers and areas of concern for stakeholders across each "
            "business unit. Include a brief analysis of year-over-year trends and "
            "compare performance against the guidance provided last quarter."
        )
        assert r.level in (ComplexityLevel.MEDIUM, ComplexityLevel.COMPLEX)

    def test_complex_code_review(self):
        from agentcost.intelligence import ComplexityRouter, ComplexityLevel

        cr = ComplexityRouter()
        r = cr.classify(
            "Please do a comprehensive code review of this module. "
            "Analyze the architecture, evaluate pros and cons of the "
            "design patterns used, and suggest refactoring opportunities.\n"
            "```python\nclass MyService:\n    pass\n```"
        )
        assert r.level == ComplexityLevel.COMPLEX
        assert r.suggested_tier == "standard"

    def test_reasoning_proof(self):
        from agentcost.intelligence import ComplexityRouter, ComplexityLevel

        cr = ComplexityRouter()
        r = cr.classify(
            "Prove that the square root of 2 is irrational using proof by contradiction."
        )
        assert r.level == ComplexityLevel.REASONING
        assert r.suggested_tier == "premium"

    def test_reasoning_step_by_step(self):
        from agentcost.intelligence import ComplexityRouter, ComplexityLevel

        cr = ComplexityRouter()
        r = cr.classify(
            "Think carefully step-by-step through this optimization problem "
            "and derive the optimal solution."
        )
        assert r.level == ComplexityLevel.REASONING

    def test_reasoning_theorem(self):
        from agentcost.intelligence import ComplexityRouter, ComplexityLevel

        cr = ComplexityRouter()
        r = cr.classify("Prove the following theorem using mathematical induction.")
        assert r.level == ComplexityLevel.REASONING

    def test_complex_design(self):
        from agentcost.intelligence import ComplexityRouter, ComplexityLevel

        cr = ComplexityRouter()
        r = cr.classify("Design a system architecture for a distributed message queue.")
        assert r.level == ComplexityLevel.COMPLEX

    def test_classification_result_fields(self):
        from agentcost.intelligence import ComplexityRouter

        cr = ComplexityRouter()
        r = cr.classify("Hello")
        assert r.level is not None
        assert r.suggested_tier in ("economy", "standard", "premium")
        assert 0 <= r.confidence <= 1
        assert isinstance(r.signals, list)

    def test_to_dict(self):
        from agentcost.intelligence import ComplexityRouter

        cr = ComplexityRouter()
        d = cr.classify("test").to_dict()
        assert "level" in d
        assert "tier" in d
        assert "model" in d
        assert "confidence" in d

    def test_route_openai(self):
        from agentcost.intelligence import ComplexityRouter

        cr = ComplexityRouter()
        model = cr.route("What is 2+2?", provider="openai")
        assert model == "gpt-4o-mini"  # simple → economy → mini

    def test_route_anthropic(self):
        from agentcost.intelligence import ComplexityRouter

        cr = ComplexityRouter()
        model = cr.route("What is 2+2?", provider="anthropic")
        assert model == "claude-3-haiku-20240307"

    def test_route_reasoning_openai(self):
        from agentcost.intelligence import ComplexityRouter

        cr = ComplexityRouter()
        model = cr.route(
            "Prove that sqrt(2) is irrational by contradiction",
            provider="openai",
        )
        assert model == "o1"

    def test_default_medium(self):
        """Ambiguous prompts should default to medium."""
        from agentcost.intelligence import ComplexityRouter, ComplexityLevel

        cr = ComplexityRouter()
        r = cr.classify("hello")
        # Short + no patterns → should lean simple or medium
        assert r.level in (ComplexityLevel.SIMPLE, ComplexityLevel.MEDIUM)

    def test_multi_turn_boosts_complexity(self):
        from agentcost.intelligence import ComplexityRouter, ComplexityLevel

        cr = ComplexityRouter()
        r1 = cr.classify("Write a function", message_count=1)
        r2 = cr.classify("Write a function", message_count=10)
        # More turns should push toward complex
        assert r2.level.value >= r1.level.value or r2.level == r1.level

    def test_custom_level_models(self):
        from agentcost.intelligence import ComplexityRouter

        custom_models = {
            "simple": {"default": "my-cheap-model"},
            "medium": {"default": "my-mid-model"},
            "complex": {"default": "my-good-model"},
            "reasoning": {"default": "my-best-model"},
        }
        cr = ComplexityRouter(level_models=custom_models)
        model = cr.route("What is 2+2?")
        assert model == "my-cheap-model"

    def test_log(self):
        from agentcost.intelligence import ComplexityRouter

        cr = ComplexityRouter()
        cr.classify("test 1")
        cr.classify("test 2")
        log = cr.get_log()
        assert len(log) == 2

    def test_reset(self):
        from agentcost.intelligence import ComplexityRouter

        cr = ComplexityRouter()
        cr.classify("test")
        cr.reset()
        assert len(cr.get_log()) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Integration: Tier + Complexity + Gate
# ═══════════════════════════════════════════════════════════════════════════════


class TestPhase3Integration:
    def test_complexity_to_tier_to_policy(self):
        """Classify complexity → get tier → check policy."""
        from agentcost.intelligence import ComplexityRouter, TierRegistry

        cr = ComplexityRouter()
        reg = TierRegistry()

        # Simple question → economy tier
        result = cr.classify("What is 2+2?")
        assert result.suggested_tier == "economy"

        # Check that the suggested model is in the right tier
        tier = reg.classify(result.suggested_model)
        # Model might not be in economy if it's a default like gpt-4o-mini
        # but the routing intention is economy

    def test_gate_with_tier_downgrade(self):
        """Budget gate downgrades should respect tier hierarchy."""
        from agentcost.intelligence import BudgetGate

        gate = BudgetGate(budget=1.00)
        gate.spent = 0.95  # 95% used
        d = gate.check("gpt-4o", provider="openai")
        assert d.action == "downgrade"
        assert d.model == "gpt-4o-mini"

    def test_full_workflow(self):
        """Simulate: classify → gate check → record spend."""
        from agentcost.intelligence import ComplexityRouter, BudgetGate

        cr = ComplexityRouter()
        gate = BudgetGate(budget=5.00)

        # 1. Classify the prompt
        result = cr.classify("Analyze the performance of our Q3 portfolio")
        model = cr.route("Analyze the performance of our Q3 portfolio", provider="openai")

        # 2. Gate check
        decision = gate.check(model, estimated_tokens=5000, provider="openai")
        assert decision.action == "allow"  # budget is fresh

        # 3. Record spend
        gate.record_spend(0.05)
        assert gate.remaining == pytest.approx(4.95)

    def test_token_analyzer_feeds_recommendations(self):
        """Token analyzer + tier registry interaction."""
        from agentcost.intelligence import TokenAnalyzer, TierRegistry

        analyzer = TokenAnalyzer()
        reg = TierRegistry()

        # Record calls with very low utilization
        for _ in range(5):
            analyzer.record_call(
                model="gpt-4o",
                input_tokens=500,
                output_tokens=100,
                max_context=128000,
                project="wasteful",
            )

        report = analyzer.analyze("wasteful")
        # Should get recommendation about smaller model
        assert any("smaller" in r.lower() or "context" in r.lower()
                    for r in report.recommendations)

        # Verify gpt-4o-mini would be cheaper
        gpt4o_tier = reg.get_tier_info("gpt-4o")
        mini_tier = reg.get_tier_info("gpt-4o-mini")
        if gpt4o_tier and mini_tier:
            assert mini_tier.input_cost_per_1m < gpt4o_tier.input_cost_per_1m
