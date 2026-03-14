"""
AgentCost OTel Collector — Accept incoming OpenTelemetry spans.

Teams with existing OTel instrumentation (Traceloop/OpenLLMetry,
OpenInference, LangSmith, custom) can send spans to AgentCost without
re-instrumenting. AgentCost extracts LLM-specific attributes and
converts them to trace events with cost calculation.

Accepts OTLP/HTTP JSON format on:
    POST /v1/otel/traces    (OTLP JSON)
    POST /v1/traces         (OTLP JSON — standard endpoint)

Supported span attribute conventions:
    - OpenLLMetry/Traceloop: gen_ai.system, gen_ai.request.model, gen_ai.usage.*
    - OpenInference: llm.model_name, llm.token_count.*, llm.provider
    - AgentCost native: llm.model, llm.cost, llm.tokens.*
    - Custom: model, provider, input_tokens, output_tokens (flat attributes)

Usage:
    # In existing OTel-instrumented app, just add AgentCost as an exporter:
    export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8100

    # Or configure programmatically:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    exporter = OTLPSpanExporter(endpoint="http://localhost:8100/v1/traces")
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

logger = logging.getLogger("agentcost.otel.collector")


# ── Attribute Extraction ─────────────────────────────────────────────────────
# Maps various OTel semantic conventions to AgentCost's internal format.


def _get_attr(attributes: list[dict] | dict, key: str, default: Any = None) -> Any:
    """Extract an attribute value from OTel attribute list or dict.

    OTel JSON format uses: [{"key": "k", "value": {"stringValue": "v"}}]
    Simplified format uses: {"k": "v"}
    """
    if isinstance(attributes, dict):
        return attributes.get(key, default)

    if isinstance(attributes, list):
        for attr in attributes:
            if attr.get("key") == key:
                val = attr.get("value", {})
                # OTLP JSON uses typed value wrappers
                if isinstance(val, dict):
                    return (
                        val.get("stringValue")
                        or val.get("intValue")
                        or val.get("doubleValue")
                        or val.get("boolValue")
                        or default
                    )
                return val
    return default


def _to_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _to_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


# ── Span Attribute Convention Mappings ────────────────────────────────────────

# Model name: try these attribute keys in order
_MODEL_KEYS = [
    "gen_ai.request.model",  # OpenLLMetry / Traceloop
    "gen_ai.response.model",  # OpenLLMetry response
    "llm.model_name",  # OpenInference
    "llm.request.model",  # OpenInference alt
    "llm.model",  # AgentCost native
    "model",  # flat custom
]

# Provider / system
_PROVIDER_KEYS = [
    "gen_ai.system",  # OpenLLMetry (openai, anthropic, etc.)
    "llm.provider",  # OpenInference / AgentCost
    "provider",  # flat custom
]

# Input tokens
_INPUT_TOKEN_KEYS = [
    "gen_ai.usage.prompt_tokens",  # OpenLLMetry
    "gen_ai.usage.input_tokens",  # OpenLLMetry alt
    "llm.token_count.prompt",  # OpenInference
    "llm.token_count.input",  # OpenInference alt
    "llm.tokens.input",  # AgentCost native
    "input_tokens",  # flat custom
    "prompt_tokens",  # flat custom alt
]

# Output tokens
_OUTPUT_TOKEN_KEYS = [
    "gen_ai.usage.completion_tokens",  # OpenLLMetry
    "gen_ai.usage.output_tokens",  # OpenLLMetry alt
    "llm.token_count.completion",  # OpenInference
    "llm.token_count.output",  # OpenInference alt
    "llm.tokens.output",  # AgentCost native
    "output_tokens",  # flat custom
    "completion_tokens",  # flat custom alt
]

# Cost (if pre-calculated)
_COST_KEYS = [
    "llm.cost",  # AgentCost native
    "gen_ai.cost",  # Custom
    "cost",  # flat custom
]

# Project / service
_PROJECT_KEYS = [
    "llm.project",  # AgentCost native
    "project",  # flat custom
    "service.name",  # OTel resource attribute
]

# Agent
_AGENT_KEYS = [
    "llm.agent_id",
    "agent_id",
    "agent.id",
]

# Session
_SESSION_KEYS = [
    "session.id",
    "llm.session_id",
    "session_id",
]


def _first_match(attributes, keys, default=None):
    """Return the first matching attribute value from a list of keys."""
    for key in keys:
        val = _get_attr(attributes, key)
        if val is not None:
            return val
    return default


# ── Span → TraceEvent Conversion ─────────────────────────────────────────────


def span_to_trace_event(
    span: dict, resource_attrs: dict | list | None = None
) -> dict | None:
    """Convert an OTLP span to an AgentCost trace event dict.

    Returns None if the span doesn't look like an LLM call (no model attribute).
    """
    attributes = span.get("attributes", [])

    # Extract model — this is the key signal that it's an LLM span
    model = _first_match(attributes, _MODEL_KEYS)
    if not model:
        # Not an LLM span — skip silently
        return None

    provider = _first_match(attributes, _PROVIDER_KEYS, "unknown")
    input_tokens = _to_int(_first_match(attributes, _INPUT_TOKEN_KEYS, 0))
    output_tokens = _to_int(_first_match(attributes, _OUTPUT_TOKEN_KEYS, 0))
    cost = _to_float(_first_match(attributes, _COST_KEYS))
    project = _first_match(attributes, _PROJECT_KEYS, "default")
    agent_id = _first_match(attributes, _AGENT_KEYS, "")
    session_id = _first_match(attributes, _SESSION_KEYS, "")

    # Also check resource attributes for service.name → project
    if resource_attrs and project == "default":
        res_project = _first_match(resource_attrs, ["service.name"])
        if res_project:
            project = res_project

    # Calculate cost if not pre-calculated
    if cost == 0 and input_tokens + output_tokens > 0:
        try:
            from ..providers.tracked import calculate_cost

            cost = calculate_cost(str(model), input_tokens, output_tokens)
        except Exception:
            pass

    # Extract timing
    start_ns = _to_int(span.get("startTimeUnixNano", 0))
    end_ns = _to_int(span.get("endTimeUnixNano", 0))
    latency_ms = (end_ns - start_ns) / 1_000_000 if end_ns > start_ns else 0

    # Trace ID: use OTel traceId or span spanId
    trace_id = (
        span.get("traceId", "") or span.get("spanId", "") or uuid.uuid4().hex[:16]
    )

    # Status
    status_obj = span.get("status", {})
    status_code = status_obj.get("code", 0) if isinstance(status_obj, dict) else 0
    status = "error" if status_code == 2 else "success"
    error_msg = status_obj.get("message", "") if isinstance(status_obj, dict) else ""

    # Timestamp
    if start_ns > 0:
        from datetime import datetime, timezone

        timestamp = datetime.fromtimestamp(
            start_ns / 1_000_000_000, tz=timezone.utc
        ).isoformat()
    else:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

    # Collect remaining attributes as metadata
    metadata = {"otel_source": True}
    span_name = span.get("name", "")
    if span_name:
        metadata["span_name"] = span_name
    parent_span_id = span.get("parentSpanId", "")
    if parent_span_id:
        metadata["parent_span_id"] = parent_span_id

    return {
        "trace_id": str(trace_id),
        "project": str(project),
        "model": str(model),
        "provider": str(provider),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": round(cost, 8),
        "latency_ms": round(latency_ms, 1),
        "status": status,
        "error": error_msg or None,
        "agent_id": str(agent_id) if agent_id else None,
        "session_id": str(session_id) if session_id else None,
        "timestamp": timestamp,
        "metadata": metadata,
    }


def parse_otlp_json(body: dict | list) -> list[dict]:
    """Parse OTLP/HTTP JSON payload and extract LLM trace events.

    Handles both:
      - Full OTLP format: {"resourceSpans": [...]}
      - Simplified format: {"spans": [...]} or [span, span, ...]
    """
    events = []

    # Simplified: body is a list of spans
    if isinstance(body, list):
        for span in body:
            event = span_to_trace_event(span)
            if event:
                events.append(event)
        return events

    # Full OTLP format
    resource_spans = body.get("resourceSpans", [])
    if resource_spans:
        for rs in resource_spans:
            resource = rs.get("resource", {})
            resource_attrs = resource.get("attributes", [])

            for scope_spans in rs.get("scopeSpans", []):
                for span in scope_spans.get("spans", []):
                    event = span_to_trace_event(span, resource_attrs)
                    if event:
                        events.append(event)
        return events

    # Simplified: {"spans": [...]}
    spans = body.get("spans", [])
    if spans:
        for span in spans:
            event = span_to_trace_event(span)
            if event:
                events.append(event)
        return events

    # Simplified: body is a list of spans
    if isinstance(body, list):
        for span in body:
            event = span_to_trace_event(span)
            if event:
                events.append(event)

    return events


def ingest_spans(body: dict) -> dict:
    """Parse OTLP payload, convert to trace events, and store.

    Returns summary of what was ingested.
    """
    events = parse_otlp_json(body)
    if not events:
        return {"accepted": 0, "skipped": "no LLM spans found"}

    from ..data.events import EventStore
    from ..sdk.trace import TraceEvent

    store = EventStore()
    count = 0
    for ev in events:
        trace_event = TraceEvent(
            trace_id=ev["trace_id"],
            project=ev["project"],
            model=ev["model"],
            provider=ev["provider"],
            input_tokens=ev["input_tokens"],
            output_tokens=ev["output_tokens"],
            cost=ev["cost"],
            latency_ms=ev["latency_ms"],
            status=ev["status"],
            error=ev.get("error"),
            agent_id=ev.get("agent_id"),
            session_id=ev.get("session_id"),
            timestamp=ev["timestamp"],
            metadata=ev.get("metadata", {}),
        )
        store.log_trace(trace_event)
        count += 1

    logger.info("Ingested %d LLM spans from OTel payload", count)
    return {"accepted": count}
