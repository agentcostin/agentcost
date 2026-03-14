"""Tests for AgentCost OTel Collector — incoming span ingestion."""

import pytest

from agentcost.otel.collector import (
    span_to_trace_event,
    parse_otlp_json,
    _get_attr,
    _first_match,
)


# ── Attribute Extraction ─────────────────────────────────────────────────────


class TestGetAttr:
    def test_dict_format(self):
        attrs = {"model": "gpt-4o", "cost": 0.003}
        assert _get_attr(attrs, "model") == "gpt-4o"
        assert _get_attr(attrs, "cost") == 0.003
        assert _get_attr(attrs, "missing") is None
        assert _get_attr(attrs, "missing", "default") == "default"

    def test_otlp_list_format_string(self):
        attrs = [{"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}}]
        assert _get_attr(attrs, "gen_ai.request.model") == "gpt-4o"

    def test_otlp_list_format_int(self):
        attrs = [{"key": "gen_ai.usage.prompt_tokens", "value": {"intValue": 150}}]
        assert _get_attr(attrs, "gen_ai.usage.prompt_tokens") == 150

    def test_otlp_list_format_double(self):
        attrs = [{"key": "llm.cost", "value": {"doubleValue": 0.0035}}]
        assert _get_attr(attrs, "llm.cost") == 0.0035

    def test_otlp_list_missing(self):
        attrs = [{"key": "other", "value": {"stringValue": "x"}}]
        assert _get_attr(attrs, "gen_ai.request.model") is None


# ── Span Conversion: OpenLLMetry Format ──────────────────────────────────────


class TestSpanToTraceEventOpenLLMetry:
    def test_basic_openllmetry_span(self):
        span = {
            "traceId": "abc123",
            "spanId": "def456",
            "name": "openai.chat",
            "startTimeUnixNano": 1710000000000000000,
            "endTimeUnixNano": 1710000001500000000,
            "attributes": [
                {"key": "gen_ai.system", "value": {"stringValue": "openai"}},
                {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}},
                {"key": "gen_ai.usage.prompt_tokens", "value": {"intValue": 150}},
                {"key": "gen_ai.usage.completion_tokens", "value": {"intValue": 80}},
            ],
            "status": {"code": 1},
        }
        event = span_to_trace_event(span)
        assert event is not None
        assert event["model"] == "gpt-4o"
        assert event["provider"] == "openai"
        assert event["input_tokens"] == 150
        assert event["output_tokens"] == 80
        assert event["latency_ms"] == 1500.0
        assert event["status"] == "success"
        assert event["trace_id"] == "abc123"

    def test_openllmetry_with_response_model(self):
        """gen_ai.response.model overrides request model if request is missing."""
        span = {
            "attributes": [
                {"key": "gen_ai.system", "value": {"stringValue": "anthropic"}},
                {
                    "key": "gen_ai.response.model",
                    "value": {"stringValue": "claude-sonnet-4-6"},
                },
                {"key": "gen_ai.usage.prompt_tokens", "value": {"intValue": 200}},
                {"key": "gen_ai.usage.completion_tokens", "value": {"intValue": 100}},
            ],
        }
        event = span_to_trace_event(span)
        assert event["model"] == "claude-sonnet-4-6"
        assert event["provider"] == "anthropic"


# ── Span Conversion: OpenInference Format ────────────────────────────────────


class TestSpanToTraceEventOpenInference:
    def test_openinference_span(self):
        span = {
            "traceId": "oi-trace-1",
            "attributes": [
                {"key": "llm.model_name", "value": {"stringValue": "gpt-4.1"}},
                {"key": "llm.provider", "value": {"stringValue": "openai"}},
                {"key": "llm.token_count.prompt", "value": {"intValue": 120}},
                {"key": "llm.token_count.completion", "value": {"intValue": 60}},
            ],
        }
        event = span_to_trace_event(span)
        assert event is not None
        assert event["model"] == "gpt-4.1"
        assert event["provider"] == "openai"
        assert event["input_tokens"] == 120
        assert event["output_tokens"] == 60


# ── Span Conversion: AgentCost Native ────────────────────────────────────────


class TestSpanToTraceEventNative:
    def test_native_attributes(self):
        span = {
            "attributes": {
                "llm.model": "gpt-4o-mini",
                "llm.provider": "openai",
                "llm.tokens.input": 50,
                "llm.tokens.output": 30,
                "llm.cost": 0.0001,
                "llm.project": "my-app",
            },
        }
        event = span_to_trace_event(span)
        assert event is not None
        assert event["model"] == "gpt-4o-mini"
        assert event["cost"] == 0.0001
        assert event["project"] == "my-app"


# ── Span Conversion: Flat Custom Attributes ──────────────────────────────────


class TestSpanToTraceEventFlat:
    def test_flat_attributes(self):
        span = {
            "attributes": {
                "model": "claude-haiku-4-5",
                "provider": "anthropic",
                "input_tokens": 80,
                "output_tokens": 40,
            },
        }
        event = span_to_trace_event(span)
        assert event is not None
        assert event["model"] == "claude-haiku-4-5"
        assert event["input_tokens"] == 80
        assert event["output_tokens"] == 40


# ── Edge Cases ───────────────────────────────────────────────────────────────


class TestSpanEdgeCases:
    def test_no_model_returns_none(self):
        """Non-LLM spans (HTTP, DB, etc.) should be skipped."""
        span = {
            "name": "HTTP GET /api/users",
            "attributes": [
                {"key": "http.method", "value": {"stringValue": "GET"}},
                {"key": "http.url", "value": {"stringValue": "/api/users"}},
            ],
        }
        assert span_to_trace_event(span) is None

    def test_error_status(self):
        span = {
            "attributes": {"model": "gpt-4o", "input_tokens": 100},
            "status": {"code": 2, "message": "Rate limit exceeded"},
        }
        event = span_to_trace_event(span)
        assert event["status"] == "error"
        assert event["error"] == "Rate limit exceeded"

    def test_missing_tokens_defaults_to_zero(self):
        span = {"attributes": {"model": "gpt-4o"}}
        event = span_to_trace_event(span)
        assert event["input_tokens"] == 0
        assert event["output_tokens"] == 0

    def test_resource_attrs_for_project(self):
        span = {"attributes": {"model": "gpt-4o"}}
        resource_attrs = [
            {"key": "service.name", "value": {"stringValue": "my-service"}}
        ]
        event = span_to_trace_event(span, resource_attrs)
        assert event["project"] == "my-service"

    def test_auto_cost_calculation(self):
        """Cost should be auto-calculated from vendored pricing when not provided."""
        span = {
            "attributes": {
                "model": "gpt-4o",
                "input_tokens": 1000,
                "output_tokens": 500,
            },
        }
        event = span_to_trace_event(span)
        assert event["cost"] > 0  # should be calculated from vendored pricing

    def test_pre_calculated_cost_preserved(self):
        span = {
            "attributes": {
                "model": "gpt-4o",
                "llm.cost": 0.042,
                "input_tokens": 1000,
                "output_tokens": 500,
            },
        }
        event = span_to_trace_event(span)
        assert event["cost"] == 0.042  # pre-calculated cost preserved

    def test_metadata_includes_otel_source(self):
        span = {
            "name": "openai.chat",
            "parentSpanId": "parent-123",
            "attributes": {"model": "gpt-4o"},
        }
        event = span_to_trace_event(span)
        assert event["metadata"]["otel_source"] is True
        assert event["metadata"]["span_name"] == "openai.chat"
        assert event["metadata"]["parent_span_id"] == "parent-123"


# ── Full OTLP JSON Parsing ───────────────────────────────────────────────────


class TestParseOtlpJson:
    def test_full_otlp_format(self):
        payload = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": "chat-app"},
                            }
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "openai"},
                            "spans": [
                                {
                                    "traceId": "t1",
                                    "attributes": [
                                        {
                                            "key": "gen_ai.request.model",
                                            "value": {"stringValue": "gpt-4o"},
                                        },
                                        {
                                            "key": "gen_ai.usage.prompt_tokens",
                                            "value": {"intValue": 100},
                                        },
                                        {
                                            "key": "gen_ai.usage.completion_tokens",
                                            "value": {"intValue": 50},
                                        },
                                    ],
                                },
                                {
                                    "traceId": "t2",
                                    "name": "HTTP GET",
                                    "attributes": [
                                        {
                                            "key": "http.method",
                                            "value": {"stringValue": "GET"},
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ]
        }
        events = parse_otlp_json(payload)
        assert len(events) == 1  # only LLM span, HTTP skipped
        assert events[0]["model"] == "gpt-4o"
        assert events[0]["project"] == "chat-app"  # from resource

    def test_simplified_spans_format(self):
        payload = {
            "spans": [
                {"attributes": {"model": "gpt-4o", "input_tokens": 50}},
                {"attributes": {"model": "claude-sonnet-4-6", "input_tokens": 80}},
            ]
        }
        events = parse_otlp_json(payload)
        assert len(events) == 2

    def test_list_format(self):
        payload = [
            {"attributes": {"model": "gpt-4o"}},
            {"attributes": {"model": "gpt-4.1-mini"}},
        ]
        events = parse_otlp_json(payload)
        assert len(events) == 2

    def test_empty_payload(self):
        assert parse_otlp_json({}) == []
        assert parse_otlp_json({"resourceSpans": []}) == []

    def test_mixed_llm_and_non_llm_spans(self):
        payload = {
            "spans": [
                {"attributes": {"model": "gpt-4o", "input_tokens": 100}},
                {"attributes": {"http.method": "POST"}},
                {"attributes": {"model": "claude-haiku-4-5", "input_tokens": 50}},
                {"attributes": {"db.system": "postgresql"}},
            ]
        }
        events = parse_otlp_json(payload)
        assert len(events) == 2
        models = {e["model"] for e in events}
        assert models == {"gpt-4o", "claude-haiku-4-5"}

    def test_multiple_resource_spans(self):
        payload = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "svc-a"}}
                        ]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "attributes": [
                                        {
                                            "key": "gen_ai.request.model",
                                            "value": {"stringValue": "gpt-4o"},
                                        },
                                        {
                                            "key": "gen_ai.usage.prompt_tokens",
                                            "value": {"intValue": 100},
                                        },
                                    ]
                                },
                            ]
                        }
                    ],
                },
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "svc-b"}}
                        ]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "attributes": [
                                        {
                                            "key": "gen_ai.request.model",
                                            "value": {
                                                "stringValue": "claude-sonnet-4-6"
                                            },
                                        },
                                        {
                                            "key": "gen_ai.usage.prompt_tokens",
                                            "value": {"intValue": 200},
                                        },
                                    ]
                                },
                            ]
                        }
                    ],
                },
            ]
        }
        events = parse_otlp_json(payload)
        assert len(events) == 2
        assert events[0]["project"] == "svc-a"
        assert events[1]["project"] == "svc-b"
