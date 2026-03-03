# Core Concepts

Understanding AgentCost's data model and how cost tracking works.

## Traces

A **trace** is a single LLM API call. Every time your application calls OpenAI, Anthropic, or any other provider through an AgentCost-wrapped client, a trace is recorded with:

| Field | Description |
|-------|-------------|
| `trace_id` | Unique identifier |
| `project` | Logical grouping (e.g., "customer-support") |
| `model` | Model name (e.g., "gpt-4o") |
| `provider` | Provider name (e.g., "openai") |
| `input_tokens` | Tokens sent to the model |
| `output_tokens` | Tokens received from the model |
| `cost` | Computed cost in USD |
| `latency_ms` | Round-trip time in milliseconds |
| `status` | `success` or `error` |
| `agent_id` | Optional: which agent made the call |
| `session_id` | Optional: session grouping |
| `timestamp` | When the call was made |

## Projects

A **project** is a logical namespace for traces. Use projects to separate different applications, environments, or teams:

```python
# Different projects for different use cases
support_client = trace(OpenAI(), project="customer-support")
pipeline_client = trace(OpenAI(), project="data-pipeline")
research_client = trace(OpenAI(), project="research")
```

## Agents & Sessions

**Agents** are identifiers for specific AI components within a project:

```python
client = trace(OpenAI(), project="support", agent_id="ticket-classifier")
```

**Sessions** group multiple calls into a conversation or workflow:

```python
client = trace(OpenAI(), project="support", session_id="conv-12345")
```

## Cost Calculation

AgentCost calculates costs using a built-in model registry covering 42 models:

```
cost = (input_tokens × input_price + output_tokens × output_price) / 1,000,000
```

The model registry (`dashboard/js/models.js`) is the single source of truth for pricing and is updated with each release.

## Cost Intelligence

AgentCost provides four intelligence modules on top of raw trace data:

**Forecasting** — Predicts future costs using linear regression, exponential moving average (EMA), and ensemble methods. Includes budget exhaustion prediction.

**Optimizer** — Analyzes your usage patterns and recommends cheaper models that could handle the same workloads. Shows estimated savings.

**Analytics** — Breakdowns by model, project, agent, and time. Token efficiency metrics and chargeback reports.

**Estimator** — Pre-call cost estimation. Before making an expensive LLM call, estimate what it will cost across 42 models.

## Data Storage

**Community edition**: SQLite database (zero configuration, file-based).

**Enterprise edition**: PostgreSQL with connection pooling for production workloads.

The database stores `trace_events` and `benchmark_runs` tables. Enterprise adds `orgs`, `users`, `cost_centers`, `policies`, `approval_requests`, and more.

## Editions

| Feature | Community (MIT) | Enterprise (BSL 1.1) |
|---------|:-:|:-:|
| Tracing SDK | ✅ | ✅ |
| Dashboard | ✅ | ✅ |
| Forecasting | ✅ | ✅ |
| Optimizer | ✅ | ✅ |
| Analytics | ✅ | ✅ |
| Estimator | ✅ | ✅ |
| Plugins | ✅ | ✅ |
| CLI | ✅ | ✅ |
| OTel/Prometheus | ✅ | ✅ |
| SSO/SAML | — | ✅ |
| Organizations | — | ✅ |
| Budget Enforcement | — | ✅ |
| Policy Engine | — | ✅ |
| Approval Workflows | — | ✅ |
| Notifications | — | ✅ |
| Anomaly Detection | — | ✅ |
| AI Gateway | — | ✅ |
