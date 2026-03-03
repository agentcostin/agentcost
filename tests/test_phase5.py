"""
Phase 5 Test Suite — Ecosystem
Tests: Gateway, Anomaly Detection, CrewAI/AutoGen, Event Bus, Grafana, VS Code
"""

import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ═══════════════════════════════════════════════════════════════════════════════
# 5.1 — AI Gateway Proxy
# ═══════════════════════════════════════════════════════════════════════════════


class TestGateway:
    def test_config_defaults(self):
        from agentcost.gateway import GatewayConfig

        cfg = GatewayConfig()
        assert cfg.port == 8200
        assert cfg.cache_enabled is True
        assert cfg.rate_limit_rpm == 600

    def test_config_from_env(self, monkeypatch):
        monkeypatch.setenv("GATEWAY_PORT", "9000")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        from agentcost.gateway import GatewayConfig

        cfg = GatewayConfig.from_env()
        assert cfg.port == 9000
        assert "openai" in cfg.providers

    def test_cache_put_get(self):
        from agentcost.gateway import ResponseCache

        cache = ResponseCache(max_entries=10, ttl=60)
        msgs = [{"role": "user", "content": "Hello"}]
        cache.put("gpt-4o", msgs, 0, {"result": "Hi"})
        assert cache.size == 1
        assert cache.get("gpt-4o", msgs, 0) == {"result": "Hi"}

    def test_cache_miss(self):
        from agentcost.gateway import ResponseCache

        assert ResponseCache().get("gpt-4o", [{"content": "X"}], 0) is None

    def test_cache_eviction(self):
        from agentcost.gateway import ResponseCache

        cache = ResponseCache(max_entries=3, ttl=60)
        for i in range(5):
            cache.put("m", [{"content": str(i)}], 0, {"r": i})
        assert cache.size == 3

    def test_rate_limiter_allows(self):
        from agentcost.gateway import RateLimiter

        limiter = RateLimiter(rpm=100)
        assert limiter.check("proj") is True
        assert limiter.remaining("proj") == 99

    def test_rate_limiter_blocks(self):
        from agentcost.gateway import RateLimiter

        limiter = RateLimiter(rpm=5)
        for _ in range(5):
            limiter.check("proj")
        assert limiter.check("proj") is False

    def test_resolve_provider_openai(self):
        from agentcost.gateway import resolve_provider, GatewayConfig, ProviderRoute

        cfg = GatewayConfig()
        cfg.providers["openai"] = ProviderRoute(
            "openai", "https://api.openai.com/v1", "sk-x"
        )
        assert resolve_provider("gpt-4o", cfg).name == "openai"

    def test_resolve_provider_ollama(self):
        from agentcost.gateway import resolve_provider, GatewayConfig, ProviderRoute

        cfg = GatewayConfig()
        cfg.providers["ollama"] = ProviderRoute(
            "ollama", "http://localhost:11434/v1", "x"
        )
        assert resolve_provider("llama3:8b", cfg).name == "ollama"

    def test_resolve_provider_none(self):
        from agentcost.gateway import resolve_provider, GatewayConfig

        assert resolve_provider("unknown", GatewayConfig()) is None

    def test_extract_project(self):
        from agentcost.gateway import _extract_project

        assert _extract_project("ac_myproj_secret") == "myproj"
        assert _extract_project("sk-key") == "gateway-default"

    def test_create_app(self):
        from agentcost.gateway import create_gateway_app, GatewayConfig

        app = create_gateway_app(GatewayConfig())
        assert app.title == "AgentCost AI Gateway"


# ═══════════════════════════════════════════════════════════════════════════════
# 5.2 — Anomaly Detection
# ═══════════════════════════════════════════════════════════════════════════════


def _make_event(cost=0.01, latency=100, tokens=50, status="success"):
    return {
        "project": "p",
        "model": "m",
        "cost": cost,
        "latency_ms": latency,
        "output_tokens": tokens,
        "status": status,
    }


class TestAnomalyDetection:
    def test_rolling_stats(self):
        from agentcost.anomaly import RollingStats

        rs = RollingStats(10)
        for v in [10, 12, 11, 10, 13, 11, 12, 10, 11, 12]:
            rs.add(v)
        assert rs.count == 10
        assert abs(rs.mean - 11.2) < 0.1
        assert rs.std > 0

    def test_z_score(self):
        from agentcost.anomaly import RollingStats

        rs = RollingStats(10)
        for _ in range(10):
            rs.add(10)
        assert rs.z_score(10) == 0
        assert rs.z_score(100) == float("inf")

    def test_init(self):
        from agentcost.anomaly import AnomalyDetector

        d = AnomalyDetector(sensitivity=3.0, min_samples=5)
        assert d.sensitivity == 3.0
        assert d.total_alerts == 0

    def test_no_alert_below_min_samples(self):
        from agentcost.anomaly import AnomalyDetector

        d = AnomalyDetector(min_samples=10)
        for _ in range(5):
            d.ingest(_make_event())
        assert d.total_alerts == 0

    def test_cost_spike(self):
        from agentcost.anomaly import AnomalyDetector, AnomalyType

        d = AnomalyDetector(sensitivity=2.0, min_samples=10)
        for _ in range(20):
            d.ingest(_make_event(cost=0.01))
        alerts = d.ingest(_make_event(cost=1.0))
        assert any(a.type == AnomalyType.COST_SPIKE for a in alerts)

    def test_latency_anomaly(self):
        from agentcost.anomaly import AnomalyDetector, AnomalyType

        d = AnomalyDetector(sensitivity=2.0, min_samples=10)
        for _ in range(20):
            d.ingest(_make_event(latency=100))
        alerts = d.ingest(_make_event(latency=10000))
        assert any(a.type == AnomalyType.LATENCY_ANOMALY for a in alerts)

    def test_token_explosion(self):
        from agentcost.anomaly import AnomalyDetector, AnomalyType

        d = AnomalyDetector(sensitivity=2.0, min_samples=10)
        for _ in range(20):
            d.ingest(_make_event(tokens=50))
        alerts = d.ingest(_make_event(tokens=5000))
        assert any(a.type == AnomalyType.TOKEN_EXPLOSION for a in alerts)

    def test_error_burst(self):
        from agentcost.anomaly import AnomalyDetector, AnomalyType

        d = AnomalyDetector(
            min_samples=10, error_rate_threshold=0.3, error_rate_window=20
        )
        for _ in range(10):
            d.ingest(_make_event(status="success"))
        all_alerts = []
        for _ in range(10):
            all_alerts.extend(d.ingest(_make_event(status="error")))
        assert any(a.type == AnomalyType.ERROR_BURST for a in all_alerts)

    def test_baselines(self):
        from agentcost.anomaly import AnomalyDetector

        d = AnomalyDetector()
        for _ in range(15):
            d.ingest(_make_event())
        bl = d.get_baselines("p", "m")
        assert bl["cost"]["samples"] == 15
        assert bl["cost"]["mean"] > 0

    def test_reset(self):
        from agentcost.anomaly import AnomalyDetector

        d = AnomalyDetector()
        for _ in range(15):
            d.ingest(_make_event())
        d.reset()
        assert d.get_baselines("p", "m")["cost"]["samples"] == 0

    def test_alert_to_dict(self):
        from agentcost.anomaly import AnomalyAlert, AnomalyType, Severity

        a = AnomalyAlert(
            AnomalyType.COST_SPIKE, Severity.WARNING, "p", "m", "test", 1.0, 0.01, 5.0
        )
        d = a.to_dict()
        assert d["type"] == "cost_spike"
        assert d["z_score"] == 5.0

    def test_callback(self):
        from agentcost.anomaly import AnomalyDetector

        received = []
        d = AnomalyDetector(
            sensitivity=2.0, min_samples=10, on_anomaly=lambda a: received.append(a)
        )
        for _ in range(20):
            d.ingest(_make_event())
        d.ingest(_make_event(cost=1.0))
        assert len(received) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5.3 — CrewAI, AutoGen, LangChain & LlamaIndex Integrations
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrewAIAutoGen:
    def test_crewai_init(self):
        from agentcost.sdk.integrations.crewai import AgentCostCrewCallbacks

        cb = AgentCostCrewCallbacks(project="test-crew")
        assert cb.project == "test-crew"

    def test_crewai_summary(self):
        from agentcost.sdk.integrations.crewai import AgentCostCrewCallbacks

        cb = AgentCostCrewCallbacks(project="crew")
        cb.on_agent_start("researcher")
        cb.on_llm_end("gpt-4o", input_tokens=100, output_tokens=200, cost=0.005)
        cb.on_agent_start("writer")
        cb.on_llm_end("gpt-4o", input_tokens=200, output_tokens=400, cost=0.01)
        s = cb.summary()
        assert s["total_cost"] == 0.015
        assert s["total_calls"] == 2
        assert "researcher" in s["by_agent"]

    def test_autogen_init(self):
        from agentcost.sdk.integrations.crewai import AgentCostAutoGenHandler

        h = AgentCostAutoGenHandler(project="ag")
        assert h.project == "ag"

    def test_autogen_passthrough(self):
        from agentcost.sdk.integrations.crewai import AgentCostAutoGenHandler

        h = AgentCostAutoGenHandler()
        assert h.on_message("a", "Hello") == "Hello"

    def test_autogen_summary(self):
        from agentcost.sdk.integrations.crewai import AgentCostAutoGenHandler

        h = AgentCostAutoGenHandler()
        h.on_message("a1", "Hi")
        h.on_llm_call("a1", "gpt-4o", 100, 200, 0.005)
        s = h.summary()
        assert s["total_messages"] == 2
        assert s["total_cost"] == 0.005


class TestLangChainIntegration:
    def test_import(self):
        from agentcost.sdk.integrations.langchain import AgentCostCallback

        assert callable(AgentCostCallback)

    def test_init(self):
        from agentcost.sdk.integrations.langchain import AgentCostCallback

        cb = AgentCostCallback(project="lc-test", agent_id="agent-1")
        assert cb.project == "lc-test"
        assert cb.agent_id == "agent-1"
        assert cb.persist is True

    def test_on_llm_start_tracks_pending(self):
        from agentcost.sdk.integrations.langchain import AgentCostCallback

        cb = AgentCostCallback(project="lc-test", persist=False)
        cb.on_llm_start(
            {"kwargs": {"model_name": "gpt-4o"}}, ["Hello"], run_id="run-123"
        )
        assert "run-123" in cb._pending
        assert cb._pending["run-123"]["model"] == "gpt-4o"

    def test_on_chat_model_start(self):
        from agentcost.sdk.integrations.langchain import AgentCostCallback

        cb = AgentCostCallback(project="lc-test", persist=False)
        cb.on_chat_model_start(
            {"kwargs": {"model": "claude-3-5-sonnet"}},
            [[{"role": "user", "content": "Hi"}]],
            run_id="run-456",
        )
        assert "run-456" in cb._pending
        assert cb._pending["run-456"]["model"] == "claude-3-5-sonnet"

    def test_on_llm_end_records_trace(self):
        from agentcost.sdk.integrations.langchain import AgentCostCallback

        cb = AgentCostCallback(project="lc-end-test", persist=False)
        cb.on_llm_start(
            {"kwargs": {"model_name": "gpt-4o"}}, ["test"], run_id="run-789"
        )

        # Simulate LLMResult-like response
        class FakeResponse:
            llm_output = {
                "token_usage": {"prompt_tokens": 50, "completion_tokens": 100}
            }
            generations = []

        cb.on_llm_end(FakeResponse(), run_id="run-789")
        summary = cb.summary()
        assert summary["total_calls"] >= 1

    def test_on_llm_error_records_trace(self):
        from agentcost.sdk.integrations.langchain import AgentCostCallback

        cb = AgentCostCallback(project="lc-err-test", persist=False)
        cb.on_llm_start(
            {"kwargs": {"model_name": "gpt-4o"}}, ["test"], run_id="run-err"
        )
        cb.on_llm_error(Exception("Rate limit"), run_id="run-err")
        assert "run-err" not in cb._pending  # cleaned up

    def test_extract_model_from_invocation_params(self):
        from agentcost.sdk.integrations.langchain import _extract_model

        assert (
            _extract_model({}, {"invocation_params": {"model_name": "gpt-4o-mini"}})
            == "gpt-4o-mini"
        )

    def test_extract_model_fallback(self):
        from agentcost.sdk.integrations.langchain import _extract_model

        assert (
            _extract_model({"kwargs": {"model": "claude-3-haiku"}}, {})
            == "claude-3-haiku"
        )

    def test_extract_tokens_from_llm_output(self):
        from agentcost.sdk.integrations.langchain import _extract_tokens

        class FakeResp:
            llm_output = {
                "token_usage": {"prompt_tokens": 100, "completion_tokens": 200}
            }
            generations = []

        assert _extract_tokens(FakeResp()) == (100, 200)

    def test_extract_tokens_from_generation_info(self):
        from agentcost.sdk.integrations.langchain import _extract_tokens

        class FakeGen:
            generation_info = {"usage": {"prompt_tokens": 30, "completion_tokens": 60}}

        class FakeResp:
            llm_output = {}
            generations = [[FakeGen()]]

        assert _extract_tokens(FakeResp()) == (30, 60)


class TestLlamaIndexIntegration:
    def test_import(self):
        from agentcost.sdk.integrations.llamaindex import AgentCostLlamaIndex

        assert callable(AgentCostLlamaIndex)

    def test_init(self):
        from agentcost.sdk.integrations.llamaindex import AgentCostLlamaIndex

        h = AgentCostLlamaIndex(project="li-test", agent_id="idx-1")
        assert h.project == "li-test"
        assert h.agent_id == "idx-1"

    def test_event_start_tracks_pending(self):
        from agentcost.sdk.integrations.llamaindex import AgentCostLlamaIndex, LLM_EVENT

        h = AgentCostLlamaIndex(project="li-test", persist=False)
        h.on_event_start(LLM_EVENT, {"model_name": "gpt-4o"}, event_id="ev-1")
        assert "ev-1" in h._pending
        assert h._pending["ev-1"]["model"] == "gpt-4o"

    def test_event_end_records_trace(self):
        from agentcost.sdk.integrations.llamaindex import AgentCostLlamaIndex, LLM_EVENT

        h = AgentCostLlamaIndex(project="li-end-test", persist=False)
        h.on_event_start(LLM_EVENT, {"model_name": "gpt-4o"}, event_id="ev-2")
        h.on_event_end(
            LLM_EVENT, {"prompt_tokens": 50, "completion_tokens": 100}, event_id="ev-2"
        )
        summary = h.summary()
        assert summary["total_calls"] >= 1

    def test_start_end_trace_noop(self):
        from agentcost.sdk.integrations.llamaindex import AgentCostLlamaIndex

        h = AgentCostLlamaIndex()
        h.start_trace("t1")  # should not error
        h.end_trace("t1")  # should not error

    def test_extract_tokens_from_payload(self):
        from agentcost.sdk.integrations.llamaindex import _extract_tokens_llamaindex

        it, ot = _extract_tokens_llamaindex(
            {"prompt_tokens": 100, "completion_tokens": 200}
        )
        assert it == 100
        assert ot == 200

    def test_extract_tokens_empty(self):
        from agentcost.sdk.integrations.llamaindex import _extract_tokens_llamaindex

        assert _extract_tokens_llamaindex(None) == (0, 0)
        assert _extract_tokens_llamaindex({}) == (0, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# 5.4 — Event Bus & Webhooks
# ═══════════════════════════════════════════════════════════════════════════════


class TestEventBus:
    def test_event_creation(self):
        from agentcost.events import Event

        ev = Event(type="test", data={"k": "v"})
        assert len(ev.event_id) == 12

    def test_event_to_sse(self):
        from agentcost.events import Event

        ev = Event(type="budget.warning", data={"pct": 85})
        assert "event: budget.warning" in ev.to_sse()

    def test_emit_callback(self):
        from agentcost.events import EventBus

        bus = EventBus()
        received = []
        bus.subscribe_callback(lambda e: received.append(e), ["test.*"])
        bus.emit("test.hello", {"msg": "hi"})
        assert len(received) == 1

    def test_wildcard(self):
        from agentcost.events import EventBus

        bus = EventBus()
        received = []
        bus.subscribe_callback(lambda e: received.append(e), ["*"])
        bus.emit("a", {})
        bus.emit("b", {})
        assert len(received) == 2

    def test_prefix_match(self):
        from agentcost.events import EventBus

        bus = EventBus()
        received = []
        bus.subscribe_callback(lambda e: received.append(e), ["budget.*"])
        bus.emit("budget.warning", {})
        bus.emit("budget.exceeded", {})
        bus.emit("policy.violation", {})
        assert len(received) == 2

    def test_unsubscribe(self):
        from agentcost.events import EventBus

        bus = EventBus()
        received = []
        sid = bus.subscribe_callback(lambda e: received.append(e), ["*"])
        bus.emit("t1", {})
        bus.unsubscribe(sid)
        bus.emit("t2", {})
        assert len(received) == 1

    def test_history(self):
        from agentcost.events import EventBus

        bus = EventBus(max_history=5)
        for i in range(10):
            bus.emit("ev", {"i": i})
        assert len(bus.get_history()) == 5

    def test_history_filter(self):
        from agentcost.events import EventBus

        bus = EventBus()
        bus.emit("a", {})
        bus.emit("b", {})
        bus.emit("a", {})
        assert len(bus.get_history("a")) == 2

    def test_stats(self):
        from agentcost.events import EventBus

        bus = EventBus()
        bus.subscribe_callback(lambda e: None, ["*"])
        bus.emit("x", {})
        assert bus.stats["total_emitted"] == 1

    def test_sse_queue(self):
        from agentcost.events import EventBus

        bus = EventBus()
        q = bus.subscribe_sse()
        bus.emit("sse.test", {})
        assert q.get(timeout=1).type == "sse.test"

    def test_singleton(self):
        from agentcost.events import get_event_bus

        assert get_event_bus() is get_event_bus()

    def test_event_types(self):
        from agentcost.events import EventType

        assert EventType.BUDGET_WARNING == "budget.warning"
        assert EventType.ANOMALY_DETECTED == "anomaly.detected"


# ═══════════════════════════════════════════════════════════════════════════════
# 5.5 — Grafana Dashboard
# ═══════════════════════════════════════════════════════════════════════════════


class TestGrafana:
    def test_json_valid(self):
        with open(os.path.join(ROOT, "agentcost/otel/grafana-dashboard.json")) as f:
            d = json.load(f)
        assert d["title"] == "AgentCost - AI Cost Monitoring"

    def test_has_panels(self):
        with open(os.path.join(ROOT, "agentcost/otel/grafana-dashboard.json")) as f:
            d = json.load(f)
        assert len(d["panels"]) >= 10

    def test_panel_types(self):
        with open(os.path.join(ROOT, "agentcost/otel/grafana-dashboard.json")) as f:
            d = json.load(f)
        types = {p["type"] for p in d["panels"]}
        assert {"stat", "timeseries", "gauge"}.issubset(types)

    def test_references_metrics(self):
        with open(os.path.join(ROOT, "agentcost/otel/grafana-dashboard.json")) as f:
            raw = f.read()
        for metric in [
            "agentcost_llm_cost_total",
            "agentcost_llm_calls_total",
            "agentcost_llm_latency_seconds",
            "agentcost_budget_utilization",
        ]:
            assert metric in raw


# ═══════════════════════════════════════════════════════════════════════════════
# 5.6 — VS Code Extension
# ═══════════════════════════════════════════════════════════════════════════════


class TestVSCode:
    def test_package_json(self):
        with open(os.path.join(ROOT, "vscode-extension/package.json")) as f:
            pkg = json.load(f)
        assert pkg["name"] == "agentcost-vscode"

    def test_views(self):
        with open(os.path.join(ROOT, "vscode-extension/package.json")) as f:
            pkg = json.load(f)
        views = {v["id"] for v in pkg["contributes"]["views"]["agentcost"]}
        assert {"agentcost.summary", "agentcost.traces", "agentcost.budgets"} == views

    def test_commands(self):
        with open(os.path.join(ROOT, "vscode-extension/package.json")) as f:
            pkg = json.load(f)
        cmds = {c["command"] for c in pkg["contributes"]["commands"]}
        assert "agentcost.refreshSummary" in cmds

    def test_extension_source(self):
        path = os.path.join(ROOT, "vscode-extension/src/extension.ts")
        with open(path) as f:
            src = f.read()
        assert "export function activate" in src
        assert "CostSummaryProvider" in src


# ═══════════════════════════════════════════════════════════════════════════════
# Module Imports
# ═══════════════════════════════════════════════════════════════════════════════


class TestImports:
    def test_gateway(self):
        pass

    def test_anomaly(self):
        pass

    def test_events(self):
        pass

    def test_crewai(self):
        pass

    def test_langchain(self):
        pass

    def test_llamaindex(self):
        pass

    def test_version(self):
        from agentcost import __version__

        assert __version__ >= "0.5.0"
