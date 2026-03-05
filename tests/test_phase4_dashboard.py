"""
AgentCost Phase 4 — Dashboard Integration Test Suite

Tests for:
  - Model Registry API routes (model_routes.py)
  - Dynamic models.js structure
  - Tier/provider/search functionality
  - Server route wiring
"""

import json
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Model Registry API Logic (unit tests, no HTTP needed)
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelRegistryAPI:
    def test_get_model_registry_returns_list(self):
        from agentcost.cost.calculator import get_model_registry_for_dashboard

        models = get_model_registry_for_dashboard()
        assert isinstance(models, list)
        assert len(models) > 100  # should have many models

    def test_registry_entry_format(self):
        from agentcost.cost.calculator import get_model_registry_for_dashboard

        models = get_model_registry_for_dashboard()
        m = models[0]
        assert "id" in m
        assert "provider" in m
        assert "label" in m
        assert "input" in m
        assert "output" in m
        assert "tier" in m
        assert "context" in m

    def test_filter_by_provider(self):
        from agentcost.cost.calculator import get_model_registry_for_dashboard

        openai_models = get_model_registry_for_dashboard(providers=["openai"])
        assert len(openai_models) > 5
        for m in openai_models:
            assert m["provider"] == "openai"

    def test_filter_by_tier(self):
        from agentcost.cost.calculator import get_model_registry_for_dashboard

        flagships = get_model_registry_for_dashboard(tiers=["flagship"])
        assert len(flagships) > 0
        for m in flagships:
            assert m["tier"] == "flagship"

    def test_pricing_is_per_1m(self):
        from agentcost.cost.calculator import get_model_registry_for_dashboard

        models = get_model_registry_for_dashboard(providers=["openai"])
        gpt4o = next((m for m in models if m["id"] == "gpt-4o"), None)
        if gpt4o:
            assert gpt4o["input"] > 0.1  # per 1M, should be dollars
            assert gpt4o["input"] < 100   # not per token
            assert gpt4o["output"] > gpt4o["input"]  # output usually costs more

    def test_context_in_k(self):
        from agentcost.cost.calculator import get_model_registry_for_dashboard

        models = get_model_registry_for_dashboard(providers=["openai"])
        gpt4o = next((m for m in models if m["id"] == "gpt-4o"), None)
        if gpt4o:
            assert gpt4o["context"] >= 64  # at least 64K

    def test_mode_field(self):
        from agentcost.cost.calculator import get_model_registry_for_dashboard

        models = get_model_registry_for_dashboard()
        modes = {m.get("mode", "") for m in models}
        assert "chat" in modes  # most models are chat


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Tier Integration with Dashboard Data
# ═══════════════════════════════════════════════════════════════════════════════


class TestTierDashboardData:
    def test_to_dashboard_data_structure(self):
        from agentcost.intelligence.tier_registry import TierRegistry

        reg = TierRegistry()
        data = reg.to_dashboard_data(limit_per_tier=10)
        assert "thresholds" in data
        assert "summary" in data
        assert "tiers" in data
        assert "economy" in data["tiers"]
        assert "standard" in data["tiers"]
        assert "premium" in data["tiers"]
        assert "free" in data["tiers"]

    def test_dashboard_tier_entries_have_required_fields(self):
        from agentcost.intelligence.tier_registry import TierRegistry

        reg = TierRegistry()
        data = reg.to_dashboard_data(limit_per_tier=5)
        for tier_name, models in data["tiers"].items():
            for m in models:
                assert "model" in m
                assert "provider" in m
                assert "input_cost_per_1m" in m
                assert "output_cost_per_1m" in m

    def test_limit_per_tier(self):
        from agentcost.intelligence.tier_registry import TierRegistry

        reg = TierRegistry()
        data = reg.to_dashboard_data(limit_per_tier=3)
        for tier_name, models in data["tiers"].items():
            assert len(models) <= 3


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Provider List
# ═══════════════════════════════════════════════════════════════════════════════


class TestProviderList:
    def test_list_providers(self):
        from agentcost.cost.calculator import list_providers

        providers = list_providers()
        assert len(providers) > 5
        assert "openai" in providers
        assert "anthropic" in providers

    def test_providers_from_registry(self):
        from agentcost.cost.calculator import get_model_registry_for_dashboard

        models = get_model_registry_for_dashboard()
        providers = {}
        for m in models:
            p = m.get("provider", "unknown")
            providers[p] = providers.get(p, 0) + 1
        assert len(providers) > 5
        # Verify counts are reasonable
        assert providers.get("openai", 0) > 10
        assert providers.get("anthropic", 0) > 3


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Search / Filter Logic
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelSearch:
    def _get_models(self):
        from agentcost.cost.calculator import get_model_registry_for_dashboard
        return get_model_registry_for_dashboard()

    def test_text_search(self):
        models = self._get_models()
        query = "gpt-4"
        results = [m for m in models if query.lower() in m["id"].lower()]
        assert len(results) > 0
        for m in results:
            assert "gpt-4" in m["id"].lower()

    def test_cost_range_filter(self):
        models = self._get_models()
        cheap = [m for m in models if 0 < m.get("input", 0) < 1.0]
        assert len(cheap) > 0
        for m in cheap:
            assert m["input"] < 1.0

    def test_context_filter(self):
        models = self._get_models()
        large_ctx = [m for m in models if m.get("context", 0) >= 100]
        assert len(large_ctx) > 0

    def test_combined_filters(self):
        """Provider + tier + cost range."""
        models = self._get_models()
        filtered = [
            m for m in models
            if m.get("provider") == "openai"
            and m.get("tier") in ("fast", "budget", "economy")
            and 0 < m.get("input", 0) < 1.0
        ]
        for m in filtered:
            assert m["provider"] == "openai"
            assert m["input"] < 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Single Model Detail
# ═══════════════════════════════════════════════════════════════════════════════


class TestSingleModelDetail:
    def test_get_model_info(self):
        from agentcost.cost.calculator import get_model_info

        info = get_model_info("gpt-4o")
        assert info is not None
        assert info.get("input_cost_per_token", 0) > 0

    def test_get_pricing_per_1m(self):
        from agentcost.cost.calculator import get_pricing_per_1m

        pricing = get_pricing_per_1m("gpt-4o")
        assert pricing.get("input", 0) > 0
        assert pricing.get("output", 0) > 0

    def test_tier_for_single_model(self):
        from agentcost.intelligence.tier_registry import get_tier_registry

        reg = get_tier_registry()
        info = reg.get_tier_info("gpt-4o")
        assert info is not None
        assert info.tier.value == "standard"
        assert info.provider == "openai"

    def test_unknown_model(self):
        from agentcost.cost.calculator import get_model_info

        info = get_model_info("nonexistent-model-xyz-123")
        assert info is None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Route Module Structure
# ═══════════════════════════════════════════════════════════════════════════════


class TestRouteModule:
    def test_model_routes_importable(self):
        pytest.importorskip("fastapi")
        from agentcost.cost.model_routes import router
        assert router is not None
        assert router.prefix == "/api/models"

    def test_route_count(self):
        pytest.importorskip("fastapi")
        from agentcost.cost.model_routes import router
        routes = [r for r in router.routes]
        assert len(routes) >= 5

    def test_server_includes_model_routes(self):
        """Verify model routes are wired into server.py."""
        import os
        server_path = os.path.join(
            os.path.dirname(__file__), "..", "agentcost", "api", "server.py"
        )
        source = open(server_path).read()
        assert "model_routes" in source
        assert "model_router" in source


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Dashboard Files
# ═══════════════════════════════════════════════════════════════════════════════


class TestDashboardFiles:
    def test_models_js_is_dynamic(self):
        """models.js should fetch from /api/models, not hardcode models."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "dashboard", "js", "models.js"
        )
        content = open(path).read()
        # Should reference the API
        assert "/api/models" in content
        assert "loadModels" in content
        assert "searchModels" in content
        # Should have fallback
        assert "FALLBACK_REGISTRY" in content
        # Should NOT have 42 hardcoded models
        assert "gpt-5.2" not in content  # old hardcoded model
        assert "gemini-3-pro" not in content  # old hardcoded model

    def test_models_js_backward_compat(self):
        """models.js should still expose getModel, getProviders, etc."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "dashboard", "js", "models.js"
        )
        content = open(path).read()
        assert "ns.getModel" in content
        assert "ns.getProviders" in content
        assert "ns.getEstimatorModels" in content
        assert "TIER_COLORS" in content
        assert "PROVIDER_COLORS" in content

    def test_index_html_has_models_tab(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "dashboard", "index.html"
        )
        content = open(path).read()
        assert "models" in content.lower()
        assert "ModelsExplorer" in content
        assert "Model Explorer" in content

    def test_index_html_has_models_nav(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "dashboard", "index.html"
        )
        content = open(path).read()
        assert "id:'models'" in content

    def test_intelligence_js_has_models_explorer(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "dashboard", "js", "intelligence.js"
        )
        content = open(path).read()
        assert "ModelsExplorer" in content
        assert "/api/models/tiers" in content
        assert "/api/models/providers" in content
        assert "searchModels" in content
