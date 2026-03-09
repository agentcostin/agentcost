# AgentCost vs Portkey

**Last updated:** March 2026

Portkey is the closest competitor to AgentCost in the AI infrastructure space. Both offer AI gateways, cost tracking, and some level of governance. But they differ fundamentally in scope: Portkey is a gateway-first platform that added governance features. AgentCost is a governance-first platform with a gateway. This distinction shapes what each tool does best.

!!! info "TL;DR"
    **Portkey** = production AI gateway with routing, guardrails, and virtual key budgeting.
    **AgentCost** = cost governance platform with forecasting, policy engine, approval workflows, and smart routing.
    Portkey governs at the *gateway level* (routing, rate limits, key budgets). AgentCost governs at the *organizational level* (policies, approvals, forecasting, scorecards).

## How They Compare

| Capability | Portkey | AgentCost |
|-----------|---------|-----------|
| **AI Gateway / Proxy** | ✅ Rust-based, <1ms overhead, 200+ LLMs | ✅ Python/FastAPI, OpenAI-compatible |
| **Model Routing** | ✅ Conditional, load-balanced, fallback chains | ✅ Complexity-based (SIMPLE/MEDIUM/COMPLEX/REASONING) |
| **Response Caching** | ✅ Exact + semantic caching | ✅ Exact-match with cost savings tracking |
| **Guardrails** | ✅ 50+ guardrails (incl. Prisma AIRS) | ✅ Policy engine with JSON rules |
| **Model Pricing DB** | ✅ 2,300+ models | ✅ 2,610+ models from 83+ providers |
| **Cost Tracking** | ✅ Per-request, per-key | ✅ Per-request, per-project, per-model |
| **Virtual Key Budgets** | ✅ Per-key spending limits | ✅ Per-project, per-team, per-goal budgets |
| **Cost Forecasting** | ❌ | ✅ Linear, EMA, ensemble — predicts budget exhaustion |
| **Budget Enforcement with Auto-Downgrade** | ❌ | ✅ ALLOW → WARN → DOWNGRADE → BLOCK pipeline |
| **Complexity-Based Prompt Classification** | ❌ | ✅ Auto-classify and route by prompt complexity |
| **Policy Engine** | ❌ | ✅ JSON rules with priority evaluation and dry-run |
| **Approval Workflows** | ❌ | ✅ Human-in-the-loop for policy exceptions |
| **Event-Driven Reactions** | ❌ | ✅ 11 action types, YAML-configurable, cooldowns |
| **Agent Scorecards** | ❌ | ✅ Monthly A–F grading with optimization recommendations |
| **Goal-Aware Cost Attribution** | ❌ | ✅ Map spend to business objectives with hierarchical rollup |
| **Governance Templates** | ❌ | ✅ Pre-built profiles (startup, enterprise, soc2, agency) |
| **Heartbeat Agent Monitoring** | ❌ | ✅ Per-cycle cost tracking with anomaly detection |
| **Cost Optimizer** | ❌ | ✅ Model downgrade recommendations with savings estimates |
| **Chargeback Reports** | ❌ | ✅ Cost center allocations, per-team spend |
| **CI/CD Cost Checks** | ❌ | ✅ GitHub Actions to fail builds on cost regression |
| **Anomaly Detection** | Basic alerting | ✅ ML-based cost/latency/error spike detection |
| **Audit Logs** | ✅ | ✅ Hash-chained compliance trail |
| **SSO/RBAC** | ✅ | ✅ Any OIDC/SAML provider |
| **MCP Gateway** | ✅ Tool access control | ❌ (planned) |
| **Prompt Management** | ✅ Versioning, templates | ❌ |
| **OTel Support** | ✅ | ✅ Export to OTel/Prometheus |
| **Self-Hosting** | ✅ Open-source gateway (MIT) | ✅ Docker Compose, single command |
| **Pricing** | Free (10K logs) → $49/mo → Enterprise | Free (MIT core), Enterprise BSL 1.1 |
| **Funding** | $15M Series A (Feb 2026) | Bootstrapped |
| **GitHub Stars** | ~10,600 (gateway) | Growing |

## Where Portkey Wins

**Gateway performance and scale.** Portkey processes 500B+ tokens and 125M requests/day across 24,000+ organizations. Its Rust-based gateway adds less than 1ms latency. For teams that need a high-performance, battle-tested proxy handling millions of requests daily, Portkey's infrastructure is proven at a scale AgentCost has not yet reached.

**Guardrails breadth.** Portkey offers 50+ built-in guardrails including integration with Palo Alto Networks' Prisma AIRS for enterprise security. AgentCost's policy engine is flexible (JSON rules can express any condition) but requires manual rule creation rather than offering a library of pre-built guardrails.

**Provider coverage for routing.** Portkey's gateway supports 200+ LLMs and 45+ providers with advanced routing: conditional logic, weighted load balancing, and fallback chains. AgentCost's gateway supports OpenAI, Anthropic, and Ollama with automatic model-prefix routing — functional but less comprehensive.

**MCP Gateway.** Portkey recently launched an MCP Gateway for controlling tool access in agentic workflows. AgentCost has MCP support planned but not yet implemented.

**Prompt management.** Portkey includes prompt versioning and templates. AgentCost does not have prompt management.

**Enterprise backing.** Portkey's $15M Series A (February 2026), Gartner Cool Vendor recognition, and 24,000+ organizations provide enterprise credibility that early-stage tools cannot match.

## Where AgentCost Wins

**Cost forecasting.** This is a capability no competitor offers — not Portkey, not Langfuse, not Helicone, not Braintrust. AgentCost predicts future spending using three methods (linear regression, exponential moving average, and ensemble averaging) and tells you the exact date your budget will be exhausted. According to the Mavvrik AI Cost Governance Report, only 15% of companies can forecast AI costs within 10% accuracy. AgentCost solves this directly.

**Organizational-level budget enforcement.** Portkey offers virtual key budgets — spending limits per API key. AgentCost operates at a higher level: budgets per project, per team, per cost center, and per business goal, with a four-stage enforcement pipeline (ALLOW → WARN → auto-DOWNGRADE → BLOCK). The auto-downgrade capability is unique: when a project hits 90% of its budget, AgentCost automatically routes requests to cheaper models rather than simply blocking them.

**Complexity-based routing.** Portkey routes based on conditions you define (model, headers, metadata). AgentCost's complexity router analyzes each prompt and classifies it automatically as SIMPLE, MEDIUM, COMPLEX, or REASONING — then routes to the cheapest model that can handle that complexity level. The user does not need to define routing rules; the system makes intelligent decisions based on prompt analysis. This typically saves 40-60% by ensuring simple queries never touch premium models.

**Policy engine with approval workflows.** AgentCost's policy engine evaluates JSON rules in priority order with conditions on model, cost, project, and provider. When a request violates a policy, it can block the request, log it, or route it to an approval queue where a human must approve or deny the exception. Portkey's guardrails block or allow — there is no approval workflow.

**Event-driven reactions.** The reactions engine is a complete event-driven automation system: when budget-exceeded fires, execute notify → log → block-calls → suspend-agent, with a 30-minute cooldown and escalation after 2 hours if unresolved. Fifteen default reaction rules ship out of the box, configurable via YAML. Portkey has alerting but not programmable event-driven automation.

**Agent scorecards.** Monthly agent grading (A through F) with specific optimization recommendations. For organizations managing 10-50+ AI agents, this is how you identify which agents are cost-effective and which should be decommissioned — the "HR for AI agents" use case.

**Goal-aware cost attribution.** Tag any LLM call to a business goal. Goals form a hierarchy (goal → parent → grandparent) with cost rollup, enabling "how much did achieving Goal X cost?" reporting. No competitor offers this.

**Governance templates.** Pre-built governance profiles for common organizational patterns: startup (economy-focused, $500/month budget), enterprise (5 cost centers, approval workflows), SOC 2 compliance (full audit trail, no free-tier models), agency (per-client budgets, chargeback), and research lab (unrestricted, analytics focus). Apply a template and your entire governance posture is configured in one step.

**CI/CD cost checks.** GitHub Actions that benchmark model costs per PR and fail the build if costs regress beyond a configurable threshold. This embeds cost awareness into the development workflow — before code is merged, not after costs appear on an invoice.

**No per-seat pricing.** AgentCost's community edition is MIT-licensed with no per-seat charges. The entire team uses it for free. Portkey's Production tier at $49/month plus enterprise pricing can add up quickly for larger organizations.

## The Governance Gap

The fundamental difference is scope of governance:

| Governance Level | Portkey | AgentCost |
|-----------------|---------|-----------|
| **Per-request** | ✅ Guardrails, routing | ✅ Policy checks, cache |
| **Per-key** | ✅ Virtual key budgets | — |
| **Per-project** | — | ✅ Budgets, forecasts, analytics |
| **Per-team** | — | ✅ Cost centers, chargeback |
| **Per-goal** | — | ✅ Goal-aware attribution |
| **Per-agent** | — | ✅ Scorecards, heartbeat monitoring |
| **Per-organization** | Basic RBAC | ✅ Policy engine, approval workflows, templates |
| **Predictive** | — | ✅ Forecasting, budget exhaustion |
| **Automated response** | Alerting | ✅ Reactions engine (11 actions) |

Portkey governs individual requests and API keys. AgentCost governs the entire organizational cost structure — from individual calls up to business objectives.

## Can You Use Both?

Yes. Portkey's high-performance gateway for routing and guardrails, AgentCost for forecasting, budget enforcement, policy controls, and organizational governance. Requests flowing through Portkey can be logged to AgentCost via its SDK or trace API for cost analysis and governance enforcement.

## Quick Start

=== "AgentCost"
    ```bash
    docker run -d -p 8100:8100 agentcost/agentcost:latest
    ```

=== "Portkey (Gateway)"
    ```bash
    npx @portkey-ai/gateway
    ```

---

**Try it yourself:** [Live Demo](https://demo.agentcost.in) · [GitHub](https://github.com/agentcostin/agentcost) · [Docs](https://docs.agentcost.in)
