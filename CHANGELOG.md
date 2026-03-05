# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-03-05

### Integration Phases (vendor-cost-map branch)

#### Phase 1 — Vendored Cost Calculator
- Vendored LiteLLM `model_prices_and_context_window.json` — 2,610 models from 40+ providers
- Native cost calculator in `agentcost/cost/calculator.py` — zero external dependencies
- Multi-strategy model name resolution (exact → strip prefix → strip tags → substring)
- Cache-aware pricing (Anthropic prompt caching, OpenAI cached tokens)
- `overrides.json` for custom/private model pricing, `sync_upstream.py` for updates
- `litellm` moved from core to optional dependency
- 80 new tests

#### Phase 2 — Plugin Architecture Rewrite
- Expanded plugin system from 6 to 8 slots: added `RuntimePlugin` (model routing, rate limiting) and `AgentPlugin` (lifecycle, workspace config)
- 7 built-in plugins: Slack/Webhook/Email/PagerDuty notifiers, InMemoryTracker, AgentLifecycle, PagerDutyReactor
- Agent lifecycle state machine: Registered → Active → BudgetWarning → Suspended → Resumed → Terminated
- SDK `CostTracker` emits `budget.warning` (80%) and `budget.exceeded` (100%) via EventBus
- Traces auto-recorded to TrackerPlugin when loaded
- Scaffold templates for all 8 plugin types
- 77 new tests

#### Phase 3 — Cost Intelligence Layer
- **Tier Registry**: Classifies 2,610 models into economy/standard/premium tiers from pricing data, with policy integration
- **Token Analyzer**: Context efficiency scoring (0–100), detects excessive system prompts, under-utilization, near-limit usage
- **Budget Gate**: Pre-execution checks with ALLOW → WARN (80%) → DOWNGRADE (90%) → BLOCK (100%), auto-downgrade chains per provider
- **Complexity Router**: Auto-classify prompts as SIMPLE/MEDIUM/COMPLEX/REASONING, route to appropriate tier/model
- 67 new tests

#### Phase 4 — Dashboard Integration
- 5 new API endpoints: `/api/models`, `/api/models/tiers`, `/api/models/search`, `/api/models/providers`, `/api/models/{id}`
- Replaced hardcoded 42-model `dashboard/js/models.js` with dynamic API fetch (2,610+ models)
- New **Models Explorer** dashboard tab with real-time search, provider/tier/cost/context filters
- Backward-compatible: `getModel()`, `getProviders()`, `TIER_COLORS`, `PROVIDER_COLORS` preserved
- 26 new tests

#### Phase 5 — Auth Simplification
- Replaced Keycloak-specific config with generic OIDC/SAML: works with Okta, Auth0, Azure AD, Google, any compliant IdP
- Single `OIDC_ISSUER_URL` replaces `KEYCLOAK_URL` + `KEYCLOAK_REALM` (legacy env vars still supported)
- Explicit endpoint overrides: `OIDC_JWKS_URL`, `OIDC_TOKEN_URL`, etc. for non-standard providers
- OIDC auto-discovery from `{issuer}/.well-known/openid-configuration`
- Generic SAML IdP config: `SAML_IDP_ENTITY_ID`, `SAML_IDP_SSO_URL`, `SAML_IDP_CERT`
- Removed `docker/keycloak/` and `scripts/start-sso.sh`
- 3 new auth config tests

#### Phase 6 — Hardening
- GitHub Action for automated weekly upstream cost map sync (`sync-pricing.yml`) with auto-PR
- 42 end-to-end integration tests: multi-provider cost paths, reaction→notifier dispatch, SDK→tracker→budget chain, intelligence pipeline, plugin lifecycle, agent events, dashboard consistency
- Fixed `test_heuristic_fallback` assertion range for tiktoken/heuristic compatibility
- Verified `pyproject.toml` includes `reactions/*.yaml` and `cost/*.json` in wheel artifacts

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
