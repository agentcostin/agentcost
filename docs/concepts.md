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

AgentCost calculates costs using a vendored pricing database of 2,610+ models from 40+ providers (sourced from LiteLLM's community-maintained dataset, synced weekly):

```
cost = (input_tokens × input_price + output_tokens × output_price) / 1,000,000
```

The vendored data lives in `agentcost/cost/model_prices.json` and is the single source of truth. Custom pricing overrides can be added via `overrides.json` or at runtime with `register_model()`. Cache-aware pricing is supported for Anthropic prompt caching and OpenAI cached tokens.

## Cost Tiers

Every model is automatically classified into a cost tier based on input pricing:

| Tier | Price Range (per 1M input tokens) | Examples |
|------|----------------------------------|----------|
| **Economy** | < $0.50 | gpt-4o-mini, Claude 3 Haiku |
| **Standard** | $0.50 – $5.00 | gpt-4o, Claude Sonnet |
| **Premium** | > $5.00 | o1, Claude Opus |
| **Free** | $0.00 | Ollama/local models |

Tiers integrate with the policy engine (restrict agents to specific tiers), budget gates (block premium when budget is low), and the complexity router.

## Complexity Router

The complexity router auto-classifies each prompt and routes to the appropriate cost tier:

| Level | Routes To | Triggers |
|-------|-----------|----------|
| **SIMPLE** | Economy | Short factual questions, yes/no, lookups |
| **MEDIUM** | Standard | Summarization, moderate generation |
| **COMPLEX** | Standard | Code review, architecture design, analysis |
| **REASONING** | Premium | Mathematical proofs, chain-of-thought, logic |

## Budget Gates

Pre-execution budget checks at each workflow step:

- **ALLOW** — Budget is healthy, proceed
- **WARN** (80%) — Budget warning, proceed but emit alert
- **DOWNGRADE** (90%) — Auto-switch to cheaper model (e.g., gpt-4o → gpt-4o-mini)
- **BLOCK** (100%) — Budget exhausted, deny the call

## Cost Intelligence

AgentCost provides five intelligence modules on top of raw trace data:

**Forecasting** — Predicts future costs using linear regression, exponential moving average (EMA), and ensemble methods. Includes budget exhaustion prediction.

**Optimizer** — Analyzes your usage patterns and recommends cheaper models that could handle the same workloads. Shows estimated savings.

**Analytics** — Breakdowns by model, project, agent, and time. Token efficiency metrics and chargeback reports.

**Estimator** — Pre-call cost estimation. Before making an expensive LLM call, estimate what it will cost across 2,610+ models.

**Token Analyzer** — Context efficiency scoring (0–100). Detects wasteful patterns: excessive system prompts, under-utilized context windows, and low output ratios.

## Plugin Architecture

AgentCost uses an 8-slot plugin system. Every integration point is swappable:

| Slot | Plugin Class | Purpose |
|------|-------------|---------|
| 1. Notifier | `NotifierPlugin` | Alerts (Slack, email, webhook, PagerDuty) |
| 2. Policy | `PolicyPlugin` | Custom policy evaluation rules |
| 3. Exporter | `ExporterPlugin` | Export traces (S3, Snowflake, Datadog) |
| 4. Provider | `ProviderPlugin` | Cost calculation for custom LLM providers |
| 5. Tracker | `TrackerPlugin` | Cost tracking backends (in-memory, DB, Langfuse) |
| 6. Reactor | `ReactorPlugin` | Custom reaction action handlers |
| 7. Runtime | `RuntimePlugin` | Model routing, rate limiting, feature flags |
| 8. Agent | `AgentPlugin` | Agent lifecycle management, workspace config |

Built-in plugins ship out of the box: 4 notifiers, InMemoryTracker, AgentLifecycle, PagerDutyReactor.

## Data Storage

**Community edition**: SQLite database (zero configuration, file-based).

**Enterprise edition**: PostgreSQL with connection pooling for production workloads.

The database stores `trace_events` and `benchmark_runs` tables. Enterprise adds `orgs`, `users`, `cost_centers`, `policies`, `approval_requests`, and more.

## Editions

| Feature | Community (MIT) | Enterprise (BSL 1.1) |
|---------|:-:|:-:|
| Tracing SDK | ✅ | ✅ |
| Dashboard + Models Explorer | ✅ | ✅ |
| 2,610+ Model Pricing | ✅ | ✅ |
| Cost Tiers & Complexity Router | ✅ | ✅ |
| Budget Gates | ✅ | ✅ |
| Token Analyzer | ✅ | ✅ |
| Forecasting | ✅ | ✅ |
| Optimizer | ✅ | ✅ |
| Analytics | ✅ | ✅ |
| Estimator | ✅ | ✅ |
| 8-Slot Plugin System | ✅ | ✅ |
| Reactions Engine (YAML) | ✅ | ✅ |
| CLI | ✅ | ✅ |
| OTel/Prometheus | ✅ | ✅ |
| SSO (any OIDC/SAML provider) | — | ✅ |
| Organizations | — | ✅ |
| Budget Enforcement | — | ✅ |
| Policy Engine | — | ✅ |
| Approval Workflows | — | ✅ |
| Notifications | — | ✅ |
| Anomaly Detection | — | ✅ |
| AI Gateway | — | ✅ |
