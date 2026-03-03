"""
AgentCost OpenTelemetry & Prometheus Integration

OTel Span Exporter:
    Converts AgentCost TraceEvents into OpenTelemetry spans with LLM-specific
    attributes (llm.model, llm.cost, llm.tokens.*).

Prometheus /metrics:
    Exposes agentcost_* counters and histograms for Grafana/Prometheus.

Usage:
    # OTel
    from agentcost.otel import AgentCostSpanExporter, setup_otel
    setup_otel(service_name="my-agent", endpoint="http://jaeger:4317")

    # Prometheus
    from agentcost.otel import start_metrics_server
    start_metrics_server(port=9090)
"""

from __future__ import annotations

import logging
import time
from typing import Sequence

logger = logging.getLogger("agentcost.otel")


# ── OpenTelemetry Span Exporter ───────────────────────────────────────────────


class AgentCostSpanExporter:
    """
    Exports AgentCost TraceEvents as OpenTelemetry spans.

    Attach to CostTracker.on_trace() to auto-export every LLM call.
    """

    def __init__(self, tracer_name: str = "agentcost"):
        try:
            from opentelemetry import trace as otel_trace
            from opentelemetry.trace import StatusCode

            self._tracer = otel_trace.get_tracer(tracer_name)
            self._StatusCode = StatusCode
            self._available = True
        except ImportError:
            self._available = False
            logger.warning("opentelemetry-api not installed — OTel export disabled")

    @property
    def available(self) -> bool:
        return self._available

    def export_event(self, event) -> None:
        """Convert a TraceEvent into an OTel span."""
        if not self._available:
            return

        from opentelemetry.trace import StatusCode

        with self._tracer.start_as_current_span(
            name=f"llm.{event.provider}.{event.model}",
            attributes={
                "llm.model": event.model,
                "llm.provider": event.provider,
                "llm.project": event.project,
                "llm.tokens.input": event.input_tokens,
                "llm.tokens.output": event.output_tokens,
                "llm.tokens.total": event.input_tokens + event.output_tokens,
                "llm.cost": event.cost,
                "llm.latency_ms": event.latency_ms,
                "llm.status": event.status,
                "llm.agent_id": event.agent_id or "",
                "llm.trace_id": event.trace_id,
            },
        ) as span:
            if event.status == "error":
                span.set_status(StatusCode.ERROR, event.error or "unknown error")
            else:
                span.set_status(StatusCode.OK)


def setup_otel(
    service_name: str = "agentcost",
    endpoint: str | None = None,
    project: str = "default",
) -> AgentCostSpanExporter | None:
    """
    Set up OpenTelemetry tracing with OTLP export and hook into CostTracker.

    Args:
        service_name: OTel service name
        endpoint: OTLP collector endpoint (e.g., "http://jaeger:4317")
        project: AgentCost project to attach the exporter to
    """
    try:
        from opentelemetry import trace as otel_trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                otlp_exporter = OTLPSpanExporter(endpoint=endpoint)
                provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            except ImportError:
                logger.warning(
                    "OTLP exporter not available — install opentelemetry-exporter-otlp"
                )

        otel_trace.set_tracer_provider(provider)

        exporter = AgentCostSpanExporter(service_name)

        # Hook into CostTracker
        from ..sdk.trace import get_tracker

        get_tracker(project).on_trace(exporter.export_event)

        logger.info(
            f"OTel tracing configured: service={service_name}, endpoint={endpoint}"
        )
        return exporter

    except ImportError:
        logger.warning(
            "opentelemetry-sdk not installed — run: pip install agentcostin[otel]"
        )
        return None


# ── Prometheus Metrics ────────────────────────────────────────────────────────


class PrometheusMetrics:
    """
    Prometheus metrics collector for AgentCost.

    Exposes:
        agentcost_llm_calls_total        (counter, labels: model, provider, project, status)
        agentcost_llm_cost_total         (counter, labels: model, provider, project)
        agentcost_llm_tokens_total       (counter, labels: model, provider, project, direction)
        agentcost_llm_latency_seconds    (histogram, labels: model, provider, project)
        agentcost_budget_utilization     (gauge, labels: project)
    """

    def __init__(self):
        try:
            from prometheus_client import Counter, Histogram, Gauge

            self._available = True

            self.calls_total = Counter(
                "agentcost_llm_calls_total",
                "Total LLM API calls",
                ["model", "provider", "project", "status"],
            )
            self.cost_total = Counter(
                "agentcost_llm_cost_total",
                "Total LLM cost in USD",
                ["model", "provider", "project"],
            )
            self.tokens_total = Counter(
                "agentcost_llm_tokens_total",
                "Total tokens processed",
                ["model", "provider", "project", "direction"],
            )
            self.latency = Histogram(
                "agentcost_llm_latency_seconds",
                "LLM call latency in seconds",
                ["model", "provider", "project"],
                buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
            )
            self.budget_utilization = Gauge(
                "agentcost_budget_utilization",
                "Budget utilization percentage",
                ["project"],
            )

        except ImportError:
            self._available = False
            logger.warning("prometheus-client not installed — metrics disabled")

    @property
    def available(self) -> bool:
        return self._available

    def record_event(self, event) -> None:
        """Record a TraceEvent as Prometheus metrics."""
        if not self._available:
            return

        labels = {
            "model": event.model,
            "provider": event.provider,
            "project": event.project,
        }

        self.calls_total.labels(**labels, status=event.status).inc()
        self.cost_total.labels(**labels).inc(event.cost)
        self.tokens_total.labels(**labels, direction="input").inc(event.input_tokens)
        self.tokens_total.labels(**labels, direction="output").inc(event.output_tokens)
        self.latency.labels(**labels).observe(event.latency_ms / 1000.0)


# Singleton
_metrics: PrometheusMetrics | None = None


def get_metrics() -> PrometheusMetrics:
    global _metrics
    if _metrics is None:
        _metrics = PrometheusMetrics()
    return _metrics


def setup_prometheus(project: str = "default") -> PrometheusMetrics:
    """Hook Prometheus metrics into CostTracker."""
    metrics = get_metrics()
    if metrics.available:
        from ..sdk.trace import get_tracker

        get_tracker(project).on_trace(metrics.record_event)
        logger.info(f"Prometheus metrics attached to project={project}")
    return metrics


def start_metrics_server(port: int = 9090) -> None:
    """Start a standalone Prometheus HTTP metrics server."""
    try:
        from prometheus_client import start_http_server

        start_http_server(port)
        logger.info(f"Prometheus metrics server started on :{port}")
    except ImportError:
        logger.error(
            "prometheus-client not installed — run: pip install agentcostin[otel]"
        )
