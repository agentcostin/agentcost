"""
AgentCost Phase 6 — Test Suite
Cost Intelligence & Optimization

Tests for: Forecasting, Smart Router, Optimizer, Analytics, Estimator
"""
import json


# ═══════════════════════════════════════════════════════════════════════════════
# 6.1 — Cost Forecasting Engine
# ═══════════════════════════════════════════════════════════════════════════════

class TestCostForecaster:
    def test_init(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        assert f.data_points == 0

    def test_add_daily_cost(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        f.add_daily_cost("2026-02-01", 10.0)
        f.add_daily_cost("2026-02-02", 12.0)
        assert f.data_points == 2

    def test_add_from_traces(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        traces = [
            {"timestamp": "2026-02-01T10:00:00", "cost": 5.0, "input_tokens": 100, "output_tokens": 200},
            {"timestamp": "2026-02-01T14:00:00", "cost": 3.0, "input_tokens": 80, "output_tokens": 100},
            {"timestamp": "2026-02-02T10:00:00", "cost": 7.0, "input_tokens": 150, "output_tokens": 250},
        ]
        f.add_from_traces(traces)
        assert f.data_points == 2  # 2 unique days

    def test_linear_forecast(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        # Increasing trend: 10, 12, 14, 16, 18
        for i in range(5):
            f.add_daily_cost(f"2026-02-0{i+1}", 10 + i * 2)
        result = f.predict(days_ahead=7, method="linear")
        assert result.method == "linear"
        assert result.data_points == 5
        assert len(result.forecasts) == 7
        assert result.trend == "increasing"
        assert result.total_predicted > 0
        assert result.confidence >= 0

    def test_ema_forecast(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        for i in range(10):
            f.add_daily_cost(f"2026-02-{i+1:02d}", 10 + i)
        result = f.predict(days_ahead=5, method="ema")
        assert result.method == "ema"
        assert len(result.forecasts) == 5
        assert result.daily_average > 0

    def test_ensemble_forecast(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        for i in range(10):
            f.add_daily_cost(f"2026-02-{i+1:02d}", 10 + i * 0.5)
        result = f.predict(days_ahead=7, method="ensemble")
        assert result.method == "ensemble"
        assert len(result.forecasts) == 7

    def test_empty_forecast(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        result = f.predict(days_ahead=7)
        assert result.data_points == 0
        assert result.total_predicted == 0

    def test_single_point_forecast(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        f.add_daily_cost("2026-02-01", 10.0)
        result = f.predict(days_ahead=3)
        assert result.data_points == 1

    def test_stable_trend(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        for i in range(10):
            f.add_daily_cost(f"2026-02-{i+1:02d}", 10.0)
        result = f.predict(days_ahead=5, method="linear")
        assert result.trend == "stable"

    def test_decreasing_trend(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        for i in range(10):
            f.add_daily_cost(f"2026-02-{i+1:02d}", 20 - i * 2)
        result = f.predict(days_ahead=5, method="linear")
        assert result.trend == "decreasing"

    def test_forecast_to_dict(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        for i in range(5):
            f.add_daily_cost(f"2026-02-0{i+1}", 10 + i)
        result = f.predict(days_ahead=3)
        d = result.to_dict()
        assert "method" in d
        assert "forecasts" in d
        assert "total_predicted" in d
        assert "trend" in d

    def test_budget_exhaustion(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        for i in range(10):
            f.add_daily_cost(f"2026-02-{i+1:02d}", 10.0)
        result = f.predict_budget_exhaustion(200.0)
        assert result is not None
        assert "exhaustion_date" in result
        assert result["days_remaining"] > 0
        assert result["daily_burn_rate"] > 0

    def test_budget_already_exhausted(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        for i in range(10):
            f.add_daily_cost(f"2026-02-{i+1:02d}", 100.0)
        result = f.predict_budget_exhaustion(50.0)
        assert result is not None
        assert result["days_remaining"] == 0

    def test_reset(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        f.add_daily_cost("2026-02-01", 10.0)
        f.reset()
        assert f.data_points == 0

    def test_non_negative_predictions(self):
        from agentcost.forecast import CostForecaster
        f = CostForecaster()
        # Rapidly decreasing
        for i in range(10):
            f.add_daily_cost(f"2026-02-{i+1:02d}", max(0, 50 - i * 10))
        result = f.predict(days_ahead=30, method="linear")
        for fc in result.forecasts:
            assert fc["predicted_cost"] >= 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6.2 — Smart Model Router
# ═══════════════════════════════════════════════════════════════════════════════

class TestModelRouter:
    def _setup_router(self):
        from agentcost.router import ModelRouter
        r = ModelRouter()
        r.add_model("gpt-4o", cost_per_1k=0.0025, quality=0.85, latency_p50=800)
        r.add_model("gpt-4o-mini", cost_per_1k=0.000075, quality=0.78, latency_p50=400)
        r.add_model("llama3:8b", cost_per_1k=0.0, quality=0.72, latency_p50=600)
        r.add_model("claude-3-5-sonnet", cost_per_1k=0.003, quality=0.87, latency_p50=900)
        return r

    def test_init(self):
        from agentcost.router import ModelRouter
        r = ModelRouter()
        assert len(r.models) == 0

    def test_add_model(self):
        r = self._setup_router()
        assert len(r.models) == 4
        assert "gpt-4o" in r.models

    def test_route_cheapest(self):
        r = self._setup_router()
        decision = r.route(min_quality=0.70, strategy="cheapest")
        assert decision.model == "llama3:8b"  # Free, meets threshold

    def test_route_cheapest_with_quality(self):
        r = self._setup_router()
        decision = r.route(min_quality=0.80, strategy="cheapest")
        assert decision.model == "gpt-4o"  # Cheapest with quality >= 0.80

    def test_route_quality(self):
        r = self._setup_router()
        decision = r.route(strategy="quality")
        assert decision.model == "claude-3-5-sonnet"  # Highest quality

    def test_route_balanced(self):
        r = self._setup_router()
        decision = r.route(min_quality=0.70, strategy="balanced")
        assert decision.model in r.models  # Should select best efficiency

    def test_route_latency(self):
        r = self._setup_router()
        decision = r.route(strategy="latency")
        assert decision.model == "gpt-4o-mini"  # Fastest (400ms)

    def test_route_with_max_latency(self):
        r = self._setup_router()
        decision = r.route(max_latency_ms=500, strategy="cheapest")
        # Only gpt-4o-mini (400ms) qualifies
        assert decision.model == "gpt-4o-mini"

    def test_route_no_match_with_fallback(self):
        r = self._setup_router()
        decision = r.route(min_quality=0.99, fallback="gpt-4o")
        assert decision.model == "gpt-4o"
        assert "fallback" in decision.reason

    def test_route_no_match_no_fallback(self):
        r = self._setup_router()
        decision = r.route(min_quality=0.99)
        assert decision.model == ""

    def test_route_unavailable_model(self):
        r = self._setup_router()
        r.set_available("llama3:8b", False)
        decision = r.route(min_quality=0.0, strategy="cheapest")
        assert decision.model != "llama3:8b"

    def test_routing_decision_to_dict(self):
        r = self._setup_router()
        decision = r.route()
        d = decision.to_dict()
        assert "model" in d
        assert "reason" in d
        assert "alternatives" in d

    def test_model_profile_cost_efficiency(self):
        from agentcost.router import ModelProfile
        p = ModelProfile(name="test", cost_per_1k_tokens=0.001, quality_score=0.8, latency_p50_ms=500)
        assert p.cost_efficiency == 800.0  # 0.8 / 0.001

    def test_model_profile_free_efficiency(self):
        from agentcost.router import ModelProfile
        p = ModelProfile(name="test", cost_per_1k_tokens=0.0, quality_score=0.7, latency_p50_ms=500)
        assert p.cost_efficiency == float('inf')

    def test_recommend(self):
        r = self._setup_router()
        recs = r.recommend()
        assert len(recs) > 0
        assert all("message" in rec for rec in recs)

    def test_comparison_table(self):
        r = self._setup_router()
        table = r.comparison_table()
        assert len(table) == 4
        assert all("name" in row for row in table)

    def test_update_model(self):
        r = self._setup_router()
        r.update_model("gpt-4o", quality_score=0.90)
        assert r.models["gpt-4o"].quality_score == 0.90

    def test_remove_model(self):
        r = self._setup_router()
        r.remove_model("llama3:8b")
        assert "llama3:8b" not in r.models

    def test_routing_log(self):
        r = self._setup_router()
        r.route()
        r.route(min_quality=0.80)
        assert len(r.routing_log) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 6.3 — Cost Optimizer
# ═══════════════════════════════════════════════════════════════════════════════

class TestCostOptimizer:
    def _make_traces(self, n=20, model="gpt-4o", cost=0.01):
        return [
            {
                "model": model, "cost": cost, "input_tokens": 100,
                "output_tokens": 200, "latency_ms": 500,
                "status": "success", "project": "test",
                "timestamp": f"2026-02-{(i%28)+1:02d}T10:00:00",
            }
            for i in range(n)
        ]

    def test_init(self):
        from agentcost.optimizer import CostOptimizer
        opt = CostOptimizer()
        assert opt.trace_count == 0

    def test_add_traces(self):
        from agentcost.optimizer import CostOptimizer
        opt = CostOptimizer()
        opt.add_traces(self._make_traces(10))
        assert opt.trace_count == 10

    def test_analyze_empty(self):
        from agentcost.optimizer import CostOptimizer
        opt = CostOptimizer()
        report = opt.analyze()
        assert report.total_calls == 0
        assert len(report.recommendations) == 1

    def test_analyze_model_downgrade(self):
        from agentcost.optimizer import CostOptimizer
        opt = CostOptimizer()
        opt.add_traces(self._make_traces(20, model="gpt-4o", cost=0.05))
        report = opt.analyze()
        downgrade_recs = [r for r in report.recommendations if r["type"] == "model_downgrade"]
        assert len(downgrade_recs) > 0

    def test_analyze_error_waste(self):
        from agentcost.optimizer import CostOptimizer
        opt = CostOptimizer()
        traces = self._make_traces(20)
        # Make 30% errors
        for t in traces[:6]:
            t["status"] = "error"
        opt.add_traces(traces)
        report = opt.analyze()
        error_recs = [r for r in report.recommendations if r["type"] == "reduce_errors"]
        assert len(error_recs) > 0

    def test_analyze_token_waste(self):
        from agentcost.optimizer import CostOptimizer
        opt = CostOptimizer()
        # High output-to-input ratio
        traces = [
            {"model": "gpt-4o", "cost": 0.05, "input_tokens": 50,
             "output_tokens": 500, "latency_ms": 500, "status": "success",
             "project": "test", "timestamp": f"2026-02-{i+1:02d}T10:00:00"}
            for i in range(10)
        ]
        opt.add_traces(traces)
        report = opt.analyze()
        token_recs = [r for r in report.recommendations if r["type"] == "reduce_output"]
        assert len(token_recs) > 0

    def test_analyze_caching(self):
        from agentcost.optimizer import CostOptimizer
        opt = CostOptimizer()
        opt.add_traces(self._make_traces(30, cost=0.05))
        report = opt.analyze()
        cache_recs = [r for r in report.recommendations if r["type"] == "enable_caching"]
        assert len(cache_recs) > 0

    def test_analyze_batching(self):
        from agentcost.optimizer import CostOptimizer
        opt = CostOptimizer()
        opt.add_traces(self._make_traces(60, model="gpt-4o", cost=0.05))
        report = opt.analyze()
        batch_recs = [r for r in report.recommendations if r["type"] == "use_batch_api"]
        assert len(batch_recs) > 0

    def test_efficiency_score(self):
        from agentcost.optimizer import CostOptimizer
        opt = CostOptimizer()
        opt.add_traces(self._make_traces(10, model="llama3:8b", cost=0.0))
        report = opt.analyze()
        assert 0 <= report.efficiency_score <= 100

    def test_report_to_dict(self):
        from agentcost.optimizer import CostOptimizer
        opt = CostOptimizer()
        opt.add_traces(self._make_traces(10))
        d = opt.analyze().to_dict()
        assert "recommendations" in d
        assert "efficiency_score" in d

    def test_clear(self):
        from agentcost.optimizer import CostOptimizer
        opt = CostOptimizer()
        opt.add_traces(self._make_traces(5))
        opt.clear()
        assert opt.trace_count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6.4 — Usage Analytics
# ═══════════════════════════════════════════════════════════════════════════════

class TestUsageAnalytics:
    def _traces(self):
        return [
            {"model": "gpt-4o", "project": "alpha", "provider": "openai",
             "cost": 0.05, "input_tokens": 200, "output_tokens": 400,
             "latency_ms": 800, "status": "success", "timestamp": "2026-02-01T10:00:00"},
            {"model": "gpt-4o", "project": "alpha", "provider": "openai",
             "cost": 0.03, "input_tokens": 150, "output_tokens": 300,
             "latency_ms": 600, "status": "success", "timestamp": "2026-02-01T14:00:00"},
            {"model": "gpt-4o-mini", "project": "beta", "provider": "openai",
             "cost": 0.001, "input_tokens": 100, "output_tokens": 200,
             "latency_ms": 300, "status": "success", "timestamp": "2026-02-02T10:00:00"},
            {"model": "llama3:8b", "project": "alpha", "provider": "ollama",
             "cost": 0.0, "input_tokens": 300, "output_tokens": 500,
             "latency_ms": 500, "status": "error", "timestamp": "2026-02-02T12:00:00"},
        ]

    def test_init(self):
        from agentcost.analytics import UsageAnalytics
        a = UsageAnalytics()
        assert a.trace_count == 0

    def test_summary(self):
        from agentcost.analytics import UsageAnalytics
        a = UsageAnalytics()
        a.add_traces(self._traces())
        s = a.summary()
        assert s["total_calls"] == 4
        assert s["total_cost"] > 0
        assert s["unique_models"] == 3
        assert s["error_count"] == 1

    def test_top_spenders_by_model(self):
        from agentcost.analytics import UsageAnalytics
        a = UsageAnalytics()
        a.add_traces(self._traces())
        top = a.top_spenders(by="model")
        assert top[0]["model"] == "gpt-4o"  # Highest cost

    def test_top_spenders_by_project(self):
        from agentcost.analytics import UsageAnalytics
        a = UsageAnalytics()
        a.add_traces(self._traces())
        top = a.top_spenders(by="project")
        assert top[0]["project"] == "alpha"

    def test_token_efficiency(self):
        from agentcost.analytics import UsageAnalytics
        a = UsageAnalytics()
        a.add_traces(self._traces())
        eff = a.token_efficiency()
        assert len(eff) == 3  # 3 models
        assert all("output_input_ratio" in e for e in eff)

    def test_cost_trends_daily(self):
        from agentcost.analytics import UsageAnalytics
        a = UsageAnalytics()
        a.add_traces(self._traces())
        trends = a.cost_trends(period="daily")
        assert len(trends) == 2  # 2 days

    def test_cost_trends_hourly(self):
        from agentcost.analytics import UsageAnalytics
        a = UsageAnalytics()
        a.add_traces(self._traces())
        trends = a.cost_trends(period="hourly")
        assert len(trends) >= 2

    def test_latency_analysis(self):
        from agentcost.analytics import UsageAnalytics
        a = UsageAnalytics()
        a.add_traces(self._traces())
        lat = a.latency_analysis()
        assert len(lat) > 0
        assert all("p50_ms" in item for item in lat)

    def test_chargeback_report(self):
        from agentcost.analytics import UsageAnalytics
        a = UsageAnalytics()
        a.add_traces(self._traces())
        report = a.chargeback_report(group_by="project")
        assert report["report_type"] == "chargeback"
        assert len(report["line_items"]) == 2  # alpha, beta
        assert report["total_cost"] > 0
        # Percentages should sum to ~100
        total_pct = sum(li["pct_of_total"] for li in report["line_items"])
        assert abs(total_pct - 100.0) < 1

    def test_export_csv(self):
        from agentcost.analytics import UsageAnalytics
        a = UsageAnalytics()
        a.add_traces(self._traces())
        csv_str = a.export_csv()
        assert "model" in csv_str
        assert "gpt-4o" in csv_str
        lines = csv_str.strip().split("\n")
        assert len(lines) == 5  # header + 4 traces

    def test_export_json(self):
        from agentcost.analytics import UsageAnalytics
        a = UsageAnalytics()
        a.add_traces(self._traces())
        json_str = a.export_json()
        data = json.loads(json_str)
        assert "summary" in data
        assert "top_models" in data

    def test_clear(self):
        from agentcost.analytics import UsageAnalytics
        a = UsageAnalytics()
        a.add_traces(self._traces())
        a.clear()
        assert a.trace_count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6.5 — Prompt Cost Estimator
# ═══════════════════════════════════════════════════════════════════════════════

class TestCostEstimator:
    def test_init(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        assert len(e.supported_models) > 10

    def test_count_tokens(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        tokens = e.count_tokens("Hello, how are you today?")
        assert tokens > 0
        assert tokens < 20  # Should be ~6-7 tokens

    def test_count_tokens_empty(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        assert e.count_tokens("") == 0

    def test_count_message_tokens(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2?"},
        ]
        tokens = e.count_message_tokens(messages)
        assert tokens > 10

    def test_estimate_known_model(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        est = e.estimate("gpt-4o", "Explain quantum computing")
        assert est.model == "gpt-4o"
        assert est.estimated_input_tokens > 0
        assert est.estimated_output_tokens > 0
        assert est.estimated_cost > 0
        assert est.pricing_source == "known"

    def test_estimate_free_model(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        est = e.estimate("llama3:8b", "Hello world")
        assert est.estimated_cost == 0
        assert est.pricing_source == "free"

    def test_estimate_unknown_model(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        est = e.estimate("totally-unknown-model", "Hello")
        assert est.pricing_source == "estimated"
        assert est.confidence == "low"

    def test_estimate_with_task_type(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        code_est = e.estimate("gpt-4o", "Write a function", task_type="code")
        summary_est = e.estimate("gpt-4o", "Write a function", task_type="summary")
        # Code should predict more output than summary
        assert code_est.estimated_output_tokens > summary_est.estimated_output_tokens

    def test_estimate_with_max_output(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        est = e.estimate("gpt-4o", "Write a long essay about everything", max_output_tokens=50)
        assert est.estimated_output_tokens <= 50

    def test_estimate_messages(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        est = e.estimate_messages("gpt-4o", [
            {"role": "user", "content": "What is the capital of France?"}
        ])
        assert est.estimated_input_tokens > 0
        assert est.estimated_cost > 0

    def test_estimate_batch(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        estimates = e.estimate_batch([
            {"model": "gpt-4o", "prompt": "Hello"},
            {"model": "gpt-4o-mini", "prompt": "Hello"},
            {"model": "llama3:8b", "prompt": "Hello"},
        ])
        assert len(estimates) == 3
        assert estimates[2].estimated_cost == 0  # llama3 is free

    def test_compare_models(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        comparison = e.compare_models("Explain AI", models=["gpt-4o", "gpt-4o-mini", "llama3:8b"])
        assert len(comparison) == 3
        # Should be sorted by cost (cheapest first)
        assert comparison[0]["estimated_cost"] <= comparison[1]["estimated_cost"]

    def test_custom_pricing(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator(custom_pricing={"my-model": (5.0, 15.0)})
        est = e.estimate("my-model", "Hello")
        assert est.pricing_source == "known"
        assert est.estimated_cost > 0

    def test_add_pricing(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        e.add_pricing("new-model", 2.0, 8.0)
        est = e.estimate("new-model", "Hello")
        assert est.pricing_source == "known"

    def test_to_dict(self):
        from agentcost.estimator import CostEstimator
        e = CostEstimator()
        est = e.estimate("gpt-4o", "Hello")
        d = est.to_dict()
        assert "model" in d
        assert "estimated_cost" in d
        assert "cost_breakdown" in d


# ═══════════════════════════════════════════════════════════════════════════════
# Imports
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhase6Imports:
    def test_forecast(self):
        pass

    def test_router(self):
        pass

    def test_optimizer(self):
        pass

    def test_analytics(self):
        pass

    def test_estimator(self):
        pass