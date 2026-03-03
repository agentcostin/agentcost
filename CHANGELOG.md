# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-03-01

### Added
- **Core SDK**: Python tracing SDK with `trace()` wrapper for OpenAI, Anthropic, and LiteLLM clients
- **TypeScript SDK**: `@agentcost/sdk` npm package for Node.js, Deno, and Bun
- **Dashboard**: Web-based cost dashboard with 6 intelligence tabs (Overview, Costs, Forecasts, Optimizer, Analytics, Estimator)
- **CLI**: `agentcost benchmark`, `compare`, `leaderboard`, `dashboard`, `traces`, `budget`, `plugin`, `gateway`, `info`
- **Cost Forecasting**: Linear, EMA, and ensemble forecasting with budget exhaustion prediction
- **Cost Optimizer**: Model downgrade recommendations and efficiency scoring
- **Usage Analytics**: Cost breakdowns by model, project, time, agent, and error rates
- **Prompt Estimator**: Pre-call cost estimation for 42 models with model comparison
- **Plugin System**: Hot-reload plugin runtime with scaffold, install, and test commands
- **Framework Integrations**: LangChain, LlamaIndex, CrewAI, AutoGen callbacks
- **OTel Exporter**: OpenTelemetry span export for Datadog, Jaeger, Grafana
- **Prometheus Metrics**: `/metrics` endpoint for Grafana dashboards
- **GitHub Action**: CI/CD cost checking with `agentcost/benchmark-action`
- **Docker Compose**: `docker-compose.dev.yml` (community) and `docker-compose.yml` (enterprise)
- **Seed Data**: `POST /api/seed` endpoint and `scripts/seed_sample_data.py` for demo data
- **Edition System**: `AGENTCOST_EDITION=community|enterprise|auto` for feature gating

### Enterprise Features (BSL 1.1)
- **SSO/SAML Authentication**: Keycloak integration with OIDC and SAML 2.0
- **Multi-Tenant Organizations**: Team management, invites, roles, org isolation
- **Budget Enforcement**: Cost centers, allocation rules, pre-call budget validation
- **Policy Engine**: JSON rule engine with priority evaluation, model blocking, cost caps
- **Approval Workflows**: Human-in-the-loop approval for policy exceptions
- **Notifications**: Slack, email, webhook, PagerDuty dispatch with channel management
- **Agent Scorecards**: Monthly agent grading (A–F) with recommendations
- **Audit Log**: Hash-chained audit trail for compliance
- **Anomaly Detection**: ML-based cost/latency/error spike detection
- **AI Gateway Proxy**: Transparent LLM proxy with policy enforcement
- **Event Bus**: Webhook subscriptions and SSE streaming

## [0.5.0] - 2026-02-15

### Added
- Phase 6: Cost forecasting, smart model router, cost optimizer, usage analytics, prompt estimator

## [0.4.0] - 2026-02-01

### Added
- Phase 5: AI Gateway proxy, anomaly detection, CrewAI/AutoGen integrations, event bus, Grafana, VS Code extension

## [0.3.0] - 2026-01-15

### Added
- Phase 4: PyPI packaging, TypeScript SDK, plugin system, framework integrations, OTel, GitHub Actions

## [0.2.0] - 2026-01-01

### Added
- Phase 3: Enterprise SSO/SAML, org management, budgets, policies, approvals, notifications, scorecards

## [0.1.0] - 2025-12-15

### Added
- Phase 1–2: Core benchmarking, SDK tracing, event store, dashboard, CLI
