# Exporters

Send AgentCost data to your existing observability stack.

## OpenTelemetry

Export trace data as OpenTelemetry spans to Datadog, Jaeger, Grafana Tempo, or any OTel-compatible backend.

### Installation

```bash
pip install agentcostin[otel]
```

### Setup

```python
from agentcost.otel import install_otel_exporter

# OTLP gRPC (Jaeger, Grafana Tempo)
install_otel_exporter(endpoint="http://localhost:4317")

# OTLP HTTP (Datadog)
install_otel_exporter(
    endpoint="https://trace.agent.datadoghq.com",
    headers={"DD-API-KEY": "your-key"},
    protocol="http",
)
```

### What Gets Exported

Each trace becomes an OTel span with attributes:

- `agentcost.model` — Model name
- `agentcost.provider` — Provider name
- `agentcost.project` — Project name
- `agentcost.cost` — Cost in USD
- `agentcost.input_tokens` — Input token count
- `agentcost.output_tokens` — Output token count
- `agentcost.latency_ms` — Latency in milliseconds
- `agentcost.status` — success/error

## Prometheus

Expose metrics for Prometheus scraping and Grafana dashboards.

### Setup

The `/metrics` endpoint is available automatically when the server is running:

```bash
agentcost dashboard
# Metrics at http://localhost:8500/metrics
```

### Available Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `agentcost_trace_total` | Counter | Total trace events |
| `agentcost_cost_total` | Counter | Total cost in USD |
| `agentcost_tokens_total` | Counter | Total tokens (input + output) |
| `agentcost_latency_ms` | Histogram | Request latency distribution |
| `agentcost_errors_total` | Counter | Total error events |

Labels: `model`, `provider`, `project`, `status`

### Grafana Dashboard

Import the included Grafana dashboard:

1. Open Grafana → Dashboards → Import
2. Upload `examples/grafana-dashboard.json`
3. Select your Prometheus data source

### Prometheus Config

```yaml
# prometheus.yml
scrape_configs:
  - job_name: "agentcost"
    scrape_interval: 15s
    static_configs:
      - targets: ["localhost:8500"]
    metrics_path: /metrics
```
