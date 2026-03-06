# Changelog

See the full [CHANGELOG.md](https://github.com/agentcostin/agentcost/blob/main/CHANGELOG.md) for detailed release notes.

## Current Release

### v1.2.0 (March 2026)

Paperclip-inspired features for agent orchestration:

- **Goal Attribution** — Track costs per business objective with hierarchical rollup
- **Governance Templates** — 5 built-in profiles (startup, enterprise, SOC2, agency, research-lab)
- **Heartbeat Monitoring** — Per-cycle cost tracking with anomaly detection and auto-pause
- **59 new tests**, 588 total passing

### v1.1.0 (March 2026)

Integration release — six phases of hardening and intelligence:

- **Vendored Pricing** — 2,610+ models from 40+ providers, zero external dependencies
- **8-Slot Plugin Architecture** — Notifier, Policy, Exporter, Provider, Tracker, Reactor, Runtime, Agent
- **Cost Intelligence** — Tier registry, complexity router, budget gates, token analyzer
- **Dashboard Models Explorer** — Search/filter 2,610+ models by provider, tier, cost, context
- **Generic SSO** — Any OIDC/SAML provider (replaced Keycloak dependency)
- **Weekly Sync** — Automated upstream pricing sync via GitHub Actions
- **550+ tests** passing across all components

### v1.0.0 (March 2026)

First stable release with:

- **Core SDK** — Python + TypeScript tracing for OpenAI, Anthropic, LiteLLM
- **Dashboard** — 7-tab web UI with model explorer (2,610+ models)
- **CLI** — Benchmark, compare, trace, budget, plugin management
- **Cost Intelligence** — Forecasting, optimization, analytics, estimation
- **Plugin System** — Hot-reload runtime with scaffold and test commands
- **Integrations** — LangChain, CrewAI, AutoGen, LlamaIndex
- **Exporters** — OpenTelemetry, Prometheus
- **Enterprise** — SSO/SAML, orgs, budgets, policies, approvals, notifications, scorecards, audit, anomaly detection, AI gateway

### Previous Releases

- v0.5.0 — Cost intelligence (Phase 6)
- v0.4.0 — AI Gateway, anomaly detection (Phase 5)
- v0.3.0 — PyPI packaging, TypeScript SDK, plugins (Phase 4)
- v0.2.0 — Enterprise features (Phase 3)
- v0.1.0 — Core benchmarking and tracing (Phase 1–2)
