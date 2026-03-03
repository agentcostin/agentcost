# Introducing AgentCost: Open-Source AI Cost Governance

*Know what your AI actually costs.*

---

We're launching AgentCost, an open-source platform to track, control, and optimize
AI spending across any provider — OpenAI, Anthropic, Google, or open-source models.

## The Problem

AI costs are the new cloud costs. Teams deploy agents across multiple LLM providers
with zero visibility into actual spending. According to Gartner, only 39% of
organizations report measurable ROI from their AI investments. The rest are spending
blindly.

We've seen this firsthand: a single misconfigured agent running GPT-4 in a loop
can burn through $500 in an afternoon. A team of 10 developers each picking their
favorite model creates a sprawl nobody can track. And when the CFO asks "what are
we spending on AI?" — nobody has a good answer.

## The Solution

AgentCost gives you that answer in one line of code:

```python
from agentcost.sdk import trace
from openai import OpenAI

client = trace(OpenAI(), project="my-app")
# That's it. Every call is now tracked.
```

From there, you get:

**A real-time dashboard** with six intelligence views — cost breakdown, forecasts,
optimization recommendations, analytics, and pre-call cost estimation.

**Cost forecasting** that predicts your next 30 days of spending and warns you
before budgets are exhausted.

**An optimizer** that analyzes your usage patterns and tells you which calls could
use cheaper models without quality loss.

**Framework integrations** for LangChain, CrewAI, AutoGen, and LlamaIndex — one
callback and you're done.

**A plugin system** for custom exporters, alerting, and analytics.

**OpenTelemetry and Prometheus exporters** to feed into your existing Grafana
dashboards.

## Open Source, Commercially Sustainable

The core platform is MIT-licensed: SDK, dashboard, CLI, forecasting, optimizer,
analytics, estimator, plugins, and exporters. No restrictions. Fork it, embed it,
sell it.

Enterprise features — SSO/SAML, budget enforcement, policy engine, approval
workflows, notifications, anomaly detection, and AI gateway — are source-available
under BSL 1.1 (the same model used by MariaDB and CockroachDB). Source is visible,
free for dev/test, and converts to Apache 2.0 after 3 years.

## Get Started

```bash
pip install agentcostin
```

GitHub: https://github.com/agentcostin/agentcost
Docs: https://docs.agentcost.in
npm: @agentcost/sdk
Docker: ghcr.io/agentcostin/agentcost

We'd love your feedback. Star us on GitHub, try it on your projects, and tell us
what you think.

---

*AgentCost is built by engineers who got tired of surprise AI bills.*
