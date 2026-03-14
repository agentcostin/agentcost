"""
AgentCost OTel Collector Routes — Accept incoming OTLP/HTTP spans.

Mounts standard OTLP endpoints:
    POST /v1/traces          (OTLP/HTTP standard)
    POST /v1/otel/traces     (AgentCost-specific alias)

Teams point their OTel SDK at AgentCost instead of (or in addition to)
Jaeger/Datadog/etc. LLM spans are auto-detected and converted to trace
events with cost calculation.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .collector import parse_otlp_json, ingest_spans

router = APIRouter(tags=["otel-collector"])


@router.post("/v1/traces")
async def otlp_ingest(request: Request):
    """Standard OTLP/HTTP trace ingest endpoint.

    Accepts OTLP JSON format. Non-LLM spans are silently skipped.
    LLM spans are converted to AgentCost trace events with auto cost calculation.
    """
    body = await request.json()
    result = ingest_spans(body)
    return JSONResponse(result, status_code=200)


@router.post("/v1/otel/traces")
async def otel_ingest_alias(request: Request):
    """AgentCost OTel ingest endpoint (alias for /v1/traces)."""
    body = await request.json()
    result = ingest_spans(body)
    return JSONResponse(result, status_code=200)


@router.get("/v1/otel/status")
async def otel_collector_status():
    """Check if the OTel collector is active and what conventions it supports."""
    return {
        "status": "active",
        "endpoints": ["/v1/traces", "/v1/otel/traces"],
        "format": "OTLP/HTTP JSON",
        "supported_conventions": [
            "OpenLLMetry/Traceloop (gen_ai.*)",
            "OpenInference (llm.*)",
            "AgentCost native (llm.model, llm.cost)",
            "Flat attributes (model, input_tokens, output_tokens)",
        ],
        "auto_cost_calculation": True,
        "models_supported": "2,610+ (vendored pricing database)",
    }
