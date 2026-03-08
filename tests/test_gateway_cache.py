"""Tests for enhanced gateway caching with stats tracking."""

import time
import pytest
from agentcost.gateway import ResponseCache, CacheStats, GatewayConfig


# ── CacheStats Tests ────────────────────────────────────────────────────────


class TestCacheStats:
    def test_initial_state(self):
        stats = CacheStats()
        assert stats.total_hits == 0
        assert stats.total_misses == 0
        assert stats.total_cost_saved == 0.0
        assert stats.hit_rate == 0.0

    def test_record_hit(self):
        stats = CacheStats()
        stats.record_hit("proj1", "gpt-4o", 0.05, latency_saved_ms=200)
        assert stats.total_hits == 1
        assert stats.total_cost_saved == 0.05
        assert stats.total_latency_saved_ms == 200

    def test_record_miss(self):
        stats = CacheStats()
        stats.record_miss("proj1", "gpt-4o")
        assert stats.total_misses == 1

    def test_hit_rate_calculation(self):
        stats = CacheStats()
        stats.record_hit("p", "m", 0.01)
        stats.record_hit("p", "m", 0.01)
        stats.record_hit("p", "m", 0.01)
        stats.record_miss("p", "m")
        assert stats.hit_rate == 75.0

    def test_per_project_tracking(self):
        stats = CacheStats()
        stats.record_hit("proj1", "gpt-4o", 0.05)
        stats.record_hit("proj1", "gpt-4o", 0.03)
        stats.record_hit("proj2", "gpt-4o-mini", 0.001)
        stats.record_miss("proj2", "gpt-4o-mini")

        d = stats.to_dict()
        assert d["by_project"]["proj1"]["hits"] == 2
        assert d["by_project"]["proj1"]["cost_saved"] == 0.08
        assert d["by_project"]["proj2"]["hits"] == 1
        assert d["by_project"]["proj2"]["misses"] == 1

    def test_per_model_tracking(self):
        stats = CacheStats()
        stats.record_hit("p", "gpt-4o", 0.05)
        stats.record_hit("p", "gpt-4o-mini", 0.001)
        stats.record_hit("p", "gpt-4o", 0.03)

        d = stats.to_dict()
        assert d["by_model"]["gpt-4o"]["hits"] == 2
        assert d["by_model"]["gpt-4o"]["cost_saved"] == 0.08
        assert d["by_model"]["gpt-4o-mini"]["hits"] == 1

    def test_to_dict_structure(self):
        stats = CacheStats()
        stats.record_hit("p", "m", 0.01, 100)
        d = stats.to_dict()
        assert "total_hits" in d
        assert "total_misses" in d
        assert "hit_rate_pct" in d
        assert "total_cost_saved" in d
        assert "total_latency_saved_ms" in d
        assert "uptime_seconds" in d
        assert "by_project" in d
        assert "by_model" in d

    def test_reset(self):
        stats = CacheStats()
        stats.record_hit("p", "m", 0.05, 100)
        stats.record_miss("p", "m")
        stats.reset()
        assert stats.total_hits == 0
        assert stats.total_misses == 0
        assert stats.total_cost_saved == 0.0
        assert stats.hit_rate == 0.0


# ── ResponseCache Tests ──────────────────────────────────────────────────────


class TestResponseCache:
    def test_basic_put_get(self):
        cache = ResponseCache(max_entries=100, ttl=3600)
        msgs = [{"role": "user", "content": "Hello"}]
        resp = {
            "choices": [{"message": {"content": "Hi"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }
        cache.put("gpt-4o", msgs, 0.0, resp)
        result = cache.get("gpt-4o", msgs, 0.0)
        assert result == resp

    def test_miss_returns_none(self):
        cache = ResponseCache(max_entries=100, ttl=3600)
        result = cache.get("gpt-4o", [{"role": "user", "content": "Hello"}], 0.0)
        assert result is None

    def test_different_messages_different_keys(self):
        cache = ResponseCache(max_entries=100, ttl=3600)
        msgs1 = [{"role": "user", "content": "Hello"}]
        msgs2 = [{"role": "user", "content": "Goodbye"}]
        resp1 = {"id": "1"}
        resp2 = {"id": "2"}
        cache.put("gpt-4o", msgs1, 0.0, resp1)
        cache.put("gpt-4o", msgs2, 0.0, resp2)
        assert cache.get("gpt-4o", msgs1, 0.0) == resp1
        assert cache.get("gpt-4o", msgs2, 0.0) == resp2

    def test_different_models_different_keys(self):
        cache = ResponseCache(max_entries=100, ttl=3600)
        msgs = [{"role": "user", "content": "Hello"}]
        cache.put("gpt-4o", msgs, 0.0, {"id": "1"})
        cache.put("gpt-4o-mini", msgs, 0.0, {"id": "2"})
        assert cache.get("gpt-4o", msgs, 0.0)["id"] == "1"
        assert cache.get("gpt-4o-mini", msgs, 0.0)["id"] == "2"

    def test_tools_in_cache_key(self):
        cache = ResponseCache(max_entries=100, ttl=3600)
        msgs = [{"role": "user", "content": "Hello"}]
        tools1 = [{"type": "function", "function": {"name": "get_weather"}}]
        cache.put("gpt-4o", msgs, 0.0, {"id": "with-tools"}, tools=tools1)
        cache.put("gpt-4o", msgs, 0.0, {"id": "no-tools"}, tools=None)
        assert cache.get("gpt-4o", msgs, 0.0, tools=tools1)["id"] == "with-tools"
        assert cache.get("gpt-4o", msgs, 0.0, tools=None)["id"] == "no-tools"

    def test_ttl_expiry(self):
        cache = ResponseCache(max_entries=100, ttl=1)  # 1 second TTL
        msgs = [{"role": "user", "content": "Hello"}]
        cache.put("gpt-4o", msgs, 0.0, {"id": "1"})
        assert cache.get("gpt-4o", msgs, 0.0) is not None
        time.sleep(1.1)
        assert cache.get("gpt-4o", msgs, 0.0) is None

    def test_lru_eviction(self):
        cache = ResponseCache(max_entries=2, ttl=3600)
        msgs = lambda i: [{"role": "user", "content": f"msg{i}"}]
        cache.put("m", msgs(1), 0.0, {"id": "1"})
        cache.put("m", msgs(2), 0.0, {"id": "2"})
        assert cache.size == 2
        # Adding a third should evict the oldest
        cache.put("m", msgs(3), 0.0, {"id": "3"})
        assert cache.size == 2
        # First entry should be evicted
        assert cache.get("m", msgs(1), 0.0) is None
        assert cache.get("m", msgs(3), 0.0) is not None

    def test_is_cacheable(self):
        cache = ResponseCache(temp_threshold=0.2)
        assert cache.is_cacheable(0.0, stream=False) is True
        assert cache.is_cacheable(0.1, stream=False) is True
        assert cache.is_cacheable(0.2, stream=False) is True
        assert cache.is_cacheable(0.3, stream=False) is False
        assert cache.is_cacheable(1.0, stream=False) is False
        # Streaming is never cacheable
        assert cache.is_cacheable(0.0, stream=True) is False

    def test_custom_temp_threshold(self):
        cache = ResponseCache(temp_threshold=0.5)
        assert cache.is_cacheable(0.5, False) is True
        assert cache.is_cacheable(0.6, False) is False

    def test_clear(self):
        cache = ResponseCache(max_entries=100, ttl=3600)
        msgs = [{"role": "user", "content": "Hello"}]
        cache.put("gpt-4o", msgs, 0.0, {"id": "1"})
        cache.put("gpt-4o-mini", msgs, 0.0, {"id": "2"})
        assert cache.size == 2
        cleared = cache.clear()
        assert cleared == 2
        assert cache.size == 0

    def test_stats_integration(self):
        cache = ResponseCache(max_entries=100, ttl=3600)
        assert cache.stats.total_hits == 0
        # Stats are tracked externally by the gateway handler,
        # but the stats object is accessible via cache.stats
        cache.stats.record_hit("proj", "gpt-4o", 0.05, 200)
        assert cache.stats.total_hits == 1
        assert cache.stats.total_cost_saved == 0.05


# ── GatewayConfig Tests ─────────────────────────────────────────────────────


class TestGatewayConfig:
    def test_default_config(self):
        cfg = GatewayConfig()
        assert cfg.cache_enabled is True
        assert cfg.cache_ttl == 3600
        assert cfg.max_cache_entries == 10000
        assert cfg.rate_limit_rpm == 600
        assert cfg.port == 8200

    def test_from_env_defaults(self):
        import os

        # Clear any existing env vars
        for k in [
            "GATEWAY_HOST",
            "GATEWAY_PORT",
            "AGENTCOST_API",
            "GATEWAY_CACHE",
            "GATEWAY_RATE_LIMIT",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "OLLAMA_BASE_URL",
        ]:
            os.environ.pop(k, None)
        cfg = GatewayConfig.from_env()
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8200
        assert cfg.cache_enabled is True


# ── Integration-like Tests ───────────────────────────────────────────────────


class TestCacheCostSavings:
    """Test that cache correctly tracks cost savings."""

    def test_cost_savings_accumulate(self):
        stats = CacheStats()
        # Simulate 10 cache hits saving $0.05 each
        for _ in range(10):
            stats.record_hit("proj1", "gpt-4o", 0.05, 200)
        assert stats.total_cost_saved == pytest.approx(0.50, abs=0.001)
        assert stats.total_hits == 10
        assert stats.total_latency_saved_ms == 2000

    def test_mixed_projects_cost_attribution(self):
        stats = CacheStats()
        stats.record_hit("frontend", "gpt-4o", 0.10)
        stats.record_hit("frontend", "gpt-4o", 0.10)
        stats.record_hit("backend", "gpt-4o-mini", 0.001)
        stats.record_miss("backend", "gpt-4o-mini")

        d = stats.to_dict()
        assert d["by_project"]["frontend"]["cost_saved"] == pytest.approx(
            0.20, abs=0.001
        )
        assert d["by_project"]["backend"]["cost_saved"] == pytest.approx(
            0.001, abs=0.0001
        )
        assert d["hit_rate_pct"] == 75.0

    def test_model_ranking_in_stats(self):
        """by_model should be sorted by cost_saved descending."""
        stats = CacheStats()
        stats.record_hit("p", "gpt-4o", 0.50)
        stats.record_hit("p", "gpt-4o-mini", 0.001)
        stats.record_hit("p", "claude-3-opus", 1.00)

        d = stats.to_dict()
        models = list(d["by_model"].keys())
        # claude-3-opus ($1.00) should come first
        assert models[0] == "claude-3-opus"
        assert models[1] == "gpt-4o"
