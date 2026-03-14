# OTel Collector — Accept Incoming Spans

AgentCost can accept incoming OpenTelemetry spans, not just export them. Teams with existing OTel instrumentation — Traceloop, OpenLLMetry, OpenInference, or custom — can send spans to AgentCost without re-instrumenting their applications.

LLM spans are auto-detected. Cost is auto-calculated from 2,610+ model pricing. Non-LLM spans are silently skipped.

## Why This Matters

Most teams already have OTel instrumentation. Adding AgentCost shouldn't mean ripping that out or adding a second SDK. With the OTel collector, you change one environment variable and AgentCost starts tracking your LLM costs:

```bash
# Before: spans go to Jaeger
export OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318

# After: spans go to AgentCost (which can also forward to Jaeger)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://agentcost:8100
```

Zero code changes. Zero re-instrumentation.

## Quick Start

### If you use Traceloop / OpenLLMetry

```python
from traceloop.sdk import Traceloop

# Just point at AgentCost
Traceloop.init(exporter_endpoint="http://localhost:8100")

# Your existing LLM calls are now cost-tracked automatically
```

### If you use OpenInference (Arize / Phoenix)

```python
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

exporter = OTLPSpanExporter(endpoint="http://localhost:8100/v1/traces")
# Add to your existing tracer provider
provider.add_span_processor(BatchSpanProcessor(exporter))
```

### If you use any OTel SDK

```bash
# Environment variable — works with any OTel-instrumented app
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8100
export OTEL_EXPORTER_OTLP_PROTOCOL=http/json

python my_app.py
```

### Direct API call

```bash
curl -X POST http://localhost:8100/v1/traces \
  -H "Content-Type: application/json" \
  -d '{
    "resourceSpans": [{
      "resource": {
        "attributes": [{"key": "service.name", "value": {"stringValue": "my-app"}}]
      },
      "scopeSpans": [{
        "spans": [{
          "traceId": "abc123",
          "name": "openai.chat",
          "startTimeUnixNano": 1710000000000000000,
          "endTimeUnixNano": 1710000001500000000,
          "attributes": [
            {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}},
            {"key": "gen_ai.system", "value": {"stringValue": "openai"}},
            {"key": "gen_ai.usage.prompt_tokens", "value": {"intValue": 150}},
            {"key": "gen_ai.usage.completion_tokens", "value": {"intValue": 80}}
          ]
        }]
      }]
    }]
  }'
```

Response:
```json
{"accepted": 1}
```

## Supported Attribute Conventions

AgentCost understands four attribute naming conventions. You don't need to change yours — it auto-detects the format.

### OpenLLMetry / Traceloop

The most popular OTel LLM instrumentation library.

| Attribute | Maps to |
|-----------|---------|
| `gen_ai.system` | provider |
| `gen_ai.request.model` | model |
| `gen_ai.response.model` | model (fallback) |
| `gen_ai.usage.prompt_tokens` | input_tokens |
| `gen_ai.usage.completion_tokens` | output_tokens |

### OpenInference (Arize / Phoenix)

| Attribute | Maps to |
|-----------|---------|
| `llm.model_name` | model |
| `llm.provider` | provider |
| `llm.token_count.prompt` | input_tokens |
| `llm.token_count.completion` | output_tokens |

### AgentCost Native

| Attribute | Maps to |
|-----------|---------|
| `llm.model` | model |
| `llm.provider` | provider |
| `llm.tokens.input` | input_tokens |
| `llm.tokens.output` | output_tokens |
| `llm.cost` | cost (pre-calculated) |
| `llm.project` | project |

### Flat Custom

| Attribute | Maps to |
|-----------|---------|
| `model` | model |
| `provider` | provider |
| `input_tokens` | input_tokens |
| `output_tokens` | output_tokens |
| `cost` | cost |

## Auto Cost Calculation

When a span includes token counts but no cost, AgentCost automatically calculates cost using its vendored pricing database of 2,610+ models from 40+ providers. No external API calls needed.

If the span already includes a cost attribute (`llm.cost`, `gen_ai.cost`, or `cost`), the pre-calculated value is preserved.

## Project Mapping

AgentCost maps incoming spans to projects using this priority:

1. `llm.project` attribute (AgentCost native)
2. `project` attribute (flat custom)
3. `service.name` resource attribute (OTel standard)
4. `"default"` (fallback)

This means your OTel `service.name` automatically becomes the AgentCost project — no extra configuration.

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/traces` | Standard OTLP/HTTP ingest |
| `POST` | `/v1/otel/traces` | AgentCost alias |
| `GET` | `/v1/otel/status` | Collector status and supported conventions |

## Monitoring

Check the collector status:

```bash
curl http://localhost:8100/v1/otel/status
```

```json
{
  "status": "active",
  "endpoints": ["/v1/traces", "/v1/otel/traces"],
  "format": "OTLP/HTTP JSON",
  "supported_conventions": [
    "OpenLLMetry/Traceloop (gen_ai.*)",
    "OpenInference (llm.*)",
    "AgentCost native (llm.model, llm.cost)",
    "Flat attributes (model, input_tokens, output_tokens)"
  ],
  "auto_cost_calculation": true,
  "models_supported": "2,610+"
}
```

## Non-LLM Spans

The collector silently skips spans that don't have a model attribute. HTTP spans, database spans, queue spans — they're all ignored. Only LLM-related spans are ingested as trace events. This means you can point your full OTel pipeline at AgentCost without worrying about noise.
