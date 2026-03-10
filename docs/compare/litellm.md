# AgentCost vs LiteLLM

**Last updated:** March 2026

LiteLLM is the most popular open-source LLM proxy — a unified API that routes calls to 100+ providers through an OpenAI-compatible interface. AgentCost actually uses LiteLLM's pricing database under the hood (2,610+ models). But they solve fundamentally different problems: LiteLLM routes your calls, AgentCost governs whether you should be making those calls in the first place.

!!! info "TL;DR"
    **LiteLLM** = unified LLM proxy (route calls to any provider through one API, with cost tracking).
    **AgentCost** = cost governance platform (forecasting, budget enforcement, smart routing, policy engine).
    LiteLLM is the plumbing. AgentCost is the control room.

## How They Compare

| Capability | LiteLLM | AgentCost |
|-----------|---------|-----------|
| **Unified LLM Proxy** | ✅ Core feature — 100+ providers via one API | ✅ AI gateway (OpenAI, Anthropic, Ollama) |
| **Provider Coverage** | ✅ 100+ providers | Gateway: 3 providers; Pricing DB: 83+ providers |
| **Cost Tracking** | ✅ Per-request, per-key, per-team | ✅ Per-request, per-project, per-model, per-goal |
| **Model Pricing Database** | ✅ 2,600+ models (AgentCost vendors this) | ✅ 2,610+ models (vendored from LiteLLM + overrides) |
| **Virtual Keys / Budgets** | ✅ Per-key spending limits | ✅ Per-project, per-team, per-cost-center budgets |
| **Cost Forecasting** | ❌ | ✅ Linear, EMA, ensemble — predicts budget exhaustion |
| **Budget Enforcement with Auto-Downgrade** | ❌ (blocks at limit) | ✅ ALLOW → WARN → auto-DOWNGRADE → BLOCK pipeline |
| **Complexity-Based Routing** | ❌ | ✅ Auto-classify prompts as SIMPLE/MEDIUM/COMPLEX/REASONING |
| **Smart Model Routing** | ✅ Fallbacks, load balancing, lowest-latency | ✅ Cost-optimized routing based on quality threshold |
| **Policy Engine** | ❌ | ✅ JSON rules with priority evaluation and dry-run |
| **Approval Workflows** | ❌ | ✅ Human-in-the-loop for policy exceptions |
| **Event-Driven Reactions** | ❌ | ✅ 11 action types, YAML-configurable, cooldowns |
| **Cost Optimizer** | ❌ | ✅ Model downgrade recommendations with savings estimates |
| **Agent Scorecards** | ❌ | ✅ Monthly A–F grading with recommendations |
| **Goal-Aware Attribution** | ❌ | ✅ Map spend to business objectives with rollup |
| **Governance Templates** | ❌ | ✅ Pre-built profiles (startup, enterprise, soc2, agency) |
| **Heartbeat Agent Monitoring** | ❌ | ✅ Per-cycle cost tracking with auto-pause |
| **Anomaly Detection** | ❌ | ✅ ML-based cost/latency spike detection |
| **Chargeback Reports** | ❌ | ✅ Cost center allocations, per-team spend |
| **CI/CD Cost Checks** | ❌ | ✅ GitHub Actions to fail builds on cost regression |
| **Response Caching** | ✅ Redis-based | ✅ In-memory exact-match with cost savings tracking |
| **Guardrails** | ✅ Via integrations (Lakera, Presidio) | ✅ Policy engine with JSON rules |
| **Dashboard** | ✅ Admin UI | ✅ 7-tab React dashboard |
| **SSO/RBAC** | ✅ Enterprise | ✅ Enterprise (any OIDC/SAML provider) |
| **Audit Logs** | ✅ | ✅ Hash-chained compliance trail |
| **OTel Support** | ✅ | ✅ Export to OTel/Prometheus |
| **Self-Hosting** | ✅ Docker | ✅ Docker, one-command install |
| **License** | Apache 2.0 | MIT (core), BSL 1.1 (enterprise) |

## Where LiteLLM Wins

**Provider coverage.** LiteLLM supports 100+ LLM providers through a single API. If you need to call Bedrock, Azure OpenAI, Vertex AI, Together, Fireworks, Groq, and a dozen others through one interface, LiteLLM is the established standard. AgentCost's gateway currently supports OpenAI, Anthropic, and Ollama directly.

**Proxy maturity.** LiteLLM has been in production at thousands of companies as a proxy layer. Its fallback chains, load balancing, cooldown logic, and retry mechanisms are battle-tested. AgentCost's gateway is functional but younger.

**Key management at scale.** LiteLLM's virtual key system with per-key budgets, team assignments, and admin UI is mature. It handles the operational complexity of managing API keys across large organizations.

**Caching.** LiteLLM supports Redis-based caching with semantic similarity matching. AgentCost currently offers in-memory exact-match caching.

**Community size.** LiteLLM has widespread adoption, a large community, more integrations, and more battle-tested edge cases handled.

## Where AgentCost Wins

**Cost forecasting.** This is the capability that separates governance from tracking. LiteLLM tells you what each key spent today. AgentCost predicts what each project will spend over the next 7, 14, and 30 days using three forecasting methods, and tells you the exact date your budget will be exhausted. Only 15% of companies can forecast AI costs within 10% accuracy — AgentCost addresses this directly.

**Budget enforcement with auto-downgrade.** LiteLLM blocks requests when a key's budget is exceeded. AgentCost's four-stage gate (ALLOW → WARN at 80% → auto-DOWNGRADE at 90% → BLOCK at 100%) is fundamentally different: instead of cutting off a production feature when the budget hits, it automatically routes to a cheaper model. Your users keep getting responses while costs drop. The downgrade chains are per-provider: Claude Opus 4.6 → Sonnet 4.6 → Haiku 4.5, or GPT-4.1 → GPT-4.1-mini → GPT-4.1-nano.

**Complexity-based routing.** LiteLLM routes based on model availability, latency, and load balancing rules you define. AgentCost analyzes each prompt and classifies it as SIMPLE, MEDIUM, COMPLEX, or REASONING — then routes to the cheapest model that can handle that complexity. Simple factual queries never touch premium models. This typically saves 40-60% with no quality loss on the downgraded calls.

**Policy engine and approval workflows.** JSON-based rules that evaluate on every request: block specific models, cap per-call costs, require human approval above thresholds. LiteLLM has no equivalent policy system.

**Event-driven automation.** When budget-exceeded fires, execute notify → log → block-calls → suspend-agent, with cooldowns and escalation. Fifteen default reaction rules ship out of the box, configurable via YAML.

**Organizational governance.** Agent scorecards, goal-aware cost attribution, governance templates, chargeback reports, CI/CD cost checks — these target the CFO, CIO, and compliance team. LiteLLM is a developer tool. AgentCost bridges developers and organizational cost management.

## They Work Best Together

LiteLLM and AgentCost are complementary, not competitive:

- **LiteLLM** as the proxy layer: unified API, provider routing, fallbacks, key management
- **AgentCost** as the governance layer: forecasting, budget enforcement, policy controls, organizational reporting

If you're already running LiteLLM, adding AgentCost takes one line:

```python
from agentcost.sdk import trace
from openai import OpenAI

# Point at your LiteLLM proxy, wrap with AgentCost
client = trace(
    OpenAI(base_url="http://litellm-proxy:4000"),
    project="my-app"
)
# LiteLLM routes the call. AgentCost tracks, forecasts, and enforces.
```

Or use AgentCost's gateway alongside LiteLLM — the gateway logs traces to the AgentCost dashboard while LiteLLM handles provider routing.

## Quick Start

=== "AgentCost"
    ```bash
    docker run -d -p 8100:8100 agentcost/agentcost:latest
    ```

=== "LiteLLM"
    ```bash
    docker run -d -p 4000:4000 ghcr.io/berriai/litellm:latest
    ```

---

**Try it yourself:** [Live Demo](https://demo.agentcost.in) · [GitHub](https://github.com/agentcostin/agentcost) · [Docs](https://docs.agentcost.in)
