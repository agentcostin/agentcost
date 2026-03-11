# How AgentCost Slots Into Your Existing AI Project

_A practical integration guide for engineering teams already running LLM workloads_

---

You have an AI project running. Prompts are going out, tokens are being consumed, and somewhere in your cloud bill a number is quietly climbing. But you don't know which agent is spending the most, which model choice is wasteful, or whether that caching layer you added last month is actually saving anything.

That's exactly the gap AgentCost was built to fill — and it's designed to slot into what you already have, not replace it.

This guide walks through every integration layer, from zero-code observability to deep policy enforcement, so you can pick the right entry point for your stack.

---

## The Integration Philosophy

AgentCost is not a framework. It doesn't ask you to rewrite your agents, migrate your prompts, or adopt a new orchestration system. It attaches to your existing AI project at whichever layer makes sense — and you can start shallow and go deeper over time.

Think of it in three rings:

- **Observe** — See where money is going
- **Control** — Set rules around how it's spent
- **Optimize** — Make systematic improvements over time

You can stop at ring one. Most teams find that visibility alone changes behaviour.

---

## Layer 1: The Gateway — Drop-In Proxy

**Best for:** Teams making direct calls to OpenAI, Anthropic, or other providers. Zero-framework setups. The fastest path to cost visibility.

The AI gateway is an OpenAI-compatible proxy. You change one line — the `base_url` — and all LLM traffic flows through AgentCost before hitting the provider.

```python
# Before
client = OpenAI(api_key="sk-...")

# After — nothing else changes
client = OpenAI(
    api_key="sk-...",
    base_url="http://localhost:8001/v1"
)
```

What you get immediately:

- **Real-time cost tracking** for every call, logged against project, model, and user
- **Intelligent caching** — semantically similar prompts served from cache, with configurable temperature thresholds so deterministic calls cache aggressively and creative calls don't
- **Pre-call cost estimation** — know what a call will cost before it's made
- **Budget enforcement** — hard stops or approval workflows when thresholds are crossed

The gateway also surfaces cache analytics: hits, misses, cost saved, latency saved — broken down per project and per model. This alone often reveals that 20–40% of calls are near-identical and eliminable.

---

## Layer 2: SDK Instrumentation — Wrap, Don't Rewrite

**Best for:** Teams that can't proxy traffic (compliance, latency requirements, on-prem providers) or want per-call attribution within existing code.

The AgentCost Python and JavaScript SDKs provide decorator-style instrumentation. Add a single line to existing call sites and get full cost attribution without rerouting traffic.

```python
from agentcost import track

@track(project="customer-support", agent="triage-bot")
def classify_ticket(ticket_text: str):
    return openai.chat.completions.create(...)
```

Every decorated call is logged with token counts, model costs, and the metadata tags you provide. Teams typically instrument critical paths first — classification, summarisation, generation — then expand coverage gradually.

The SDKs are available on PyPI (`pip install agentcostin`) and npm, and work in any environment where you can install packages.

---

## Layer 3: Agent Framework Hooks — Native Callback Integration

**Best for:** Projects using LangChain, CrewAI, AutoGen, or LlamaIndex. Attaches at the framework level, capturing cost for every step automatically.

### LangChain

LangChain's callback system lets you attach handlers to any chain or agent. AgentCost provides a `CostCallbackHandler` that captures token usage, model, and latency at every step — including intermediate reasoning steps that often account for significant spend.

```python
from agentcost.integrations.langchain import CostCallbackHandler

chain = LLMChain(
    llm=ChatOpenAI(model="gpt-4"),
    callbacks=[CostCallbackHandler(project="legal-review")]
)
```

### CrewAI & AutoGen

Both frameworks expose step-level hooks. AgentCost attaches at task boundaries, giving you cost-per-agent and cost-per-task visibility across multi-agent runs. This feeds into **agent scorecards** — a per-agent cost efficiency rating that helps you identify which agents in a crew are expensive relative to the value they add.

### LlamaIndex

For RAG pipelines, instrumentation at the query engine level captures retrieval costs separately from synthesis costs — useful when optimising the balance between retrieval depth and generation length.

---

## Layer 4: Observability Stack — Push Into Existing Dashboards

**Best for:** Teams with Prometheus/Grafana or OpenTelemetry already in place. No new tooling required.

AgentCost exports metrics in both OpenTelemetry and Prometheus formats. If your infrastructure team already has dashboards, cost data flows straight in alongside latency, error rates, and throughput.

**Prometheus** — scrape the `/metrics` endpoint and query `agentcost_tokens_total`, `agentcost_cost_usd`, and `agentcost_cache_hit_ratio` from your existing Grafana setup.

**OpenTelemetry** — configure the OTLP exporter to point at your collector. Cost spans appear as traces alongside your existing application telemetry.

This means AI costs get treated like any other infrastructure metric — alertable, dashboardable, part of your standard incident runbooks.

---

## Layer 5: Multi-Team Attribution — Cost Centers

**Best for:** Organisations where multiple teams share API keys or infrastructure. Platforms teams, internal AI tooling, any setup where "who spent what" matters.

Cost centers let you partition LLM spend by team, product, feature, or business unit — without requiring separate API keys or infrastructure per team.

```python
client = AgentCostClient(
    cost_center="platform-team",
    project="search-reranking"
)
```

At the end of the month, finance gets a breakdown. Teams get accountability. Nobody is surprised by the bill.

---

## Layer 6: Policy Engine — Governance at Scale

**Best for:** Regulated industries, enterprise deployments, or any team that needs controls beyond "don't spend too much."

The policy engine lets you define rules that govern how LLM calls are made:

- **Budget gates** — block or queue calls that would exceed a daily/monthly budget
- **Model policies** — enforce that certain teams use only approved models
- **Approval workflows** — route high-cost calls through a human approval step before execution
- **Governance templates** — five built-in profiles (conservative, balanced, aggressive, experimental, audit-only) that apply sensible defaults for different risk tolerances

Policies are defined in YAML and hot-reloaded, so you don't need a deployment to update rules.

---

## Layer 7: Anomaly Detection — Catch Runaway Agents

**Best for:** Autonomous agents, background jobs, or any AI workload that runs without human supervision.

Agentic loops are uniquely dangerous from a cost perspective. A misconfigured retry, an infinite tool-call loop, or an unexpectedly verbose model response can burn through budget in minutes.

AgentCost's heartbeat-based anomaly detection monitors spend velocity in real time. When a job's cost-per-minute spikes beyond the expected envelope — based on its own historical pattern — it triggers an alert or an automatic pause.

This is the feature most teams didn't know they needed until they got their first unexpected $800 bill.

---

## Layer 8: CI/CD Integration — Shift Cost Left

**Best for:** Teams that want to catch expensive prompts before they reach production.

Pre-call cost estimation can run in test environments. You can add assertions to your test suite:

```python
estimate = agentcost.estimate(prompt=my_prompt, model="claude-opus-4-6")
assert estimate.cost_usd < 0.05, f"Prompt too expensive: ${estimate.cost_usd:.4f}"
```

This treats prompt cost as a first-class quality signal — the same way you'd assert on response latency or token count. Budget regression tests prevent expensive prompt refactors from sneaking into production unnoticed.

---

## Choosing Your Entry Point

| What you have today                | Start here                      |
| ---------------------------------- | ------------------------------- |
| Direct OpenAI/Anthropic calls      | Gateway proxy — one line change |
| LangChain, CrewAI, AutoGen         | Framework callbacks             |
| Prometheus/Grafana already running | OTel/Prometheus exporters       |
| Multiple teams sharing one API key | Cost centers + policy engine    |
| Long-running autonomous agents     | Heartbeat anomaly detection     |
| Active CI/CD pipeline              | Pre-call estimation in tests    |
| Compliance or on-prem constraints  | SDK instrumentation             |

The typical progression is: **Gateway → SDK → Policy Engine**. Most teams get meaningful visibility within an hour of deploying the gateway, and layer in enforcement over the following weeks as they understand their spending patterns.

---

## Getting Started

AgentCost is open source, MIT-licensed for the community edition, and self-hosted.

```bash
# Pull and run
docker pull agentcost/agentcost:latest
docker compose up
```

The community edition covers Layers 1–4 with no license required. Enterprise features — cost centers, the policy engine, approval workflows, SSO/OIDC, and PostgreSQL backend — are available in the enterprise edition.

- **GitHub**: [github.com/agentcostin/agentcost](https://github.com/agentcostin/agentcost)
- **Live demo**: [demo.agentcost.in](https://demo.agentcost.in)
- **PyPI**: `pip install agentcostin`
- **Questions**: [open@agentcost.in](mailto:open@agentcost.in)

---

_AgentCost is actively developed. If your stack isn't covered above, open an issue or start a discussion — integration breadth is a priority on the roadmap._
