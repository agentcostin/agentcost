# Show HN: AgentCost — Open-Source AI Cost Governance

Title: Show HN: AgentCost – Track, control, and optimize your AI spending (MIT)

URL: https://github.com/agentcostin/agentcost

---

Text:

Hi HN,

We built AgentCost to solve a problem we kept running into: nobody knows what
their AI agents actually cost.

One line wraps your OpenAI/Anthropic client:

    from agentcost.sdk import trace
    client = trace(OpenAI(), project="my-app")

From there you get a dashboard with cost forecasting, model optimization
recommendations, and pre-call cost estimation across 42 models.

What's included (MIT):
- Python + TypeScript SDKs
- Real-time dashboard with 6 views
- Cost forecasting (linear, EMA, ensemble)
- Optimizer: "switch these calls from GPT-4 to GPT-4-mini, save $X/day"
- Prompt cost estimator for 42 models
- LangChain/CrewAI/AutoGen/LlamaIndex integrations
- Plugin system
- OTel + Prometheus exporters
- CLI with model benchmarking

Enterprise features (BSL 1.1): SSO, budgets, policies, approvals,
notifications, anomaly detection, AI gateway proxy.

Tech stack: Python/FastAPI, SQLite (community) or PostgreSQL (enterprise),
React dashboard, TypeScript SDK.

GitHub: https://github.com/agentcostin/agentcost
Docs: https://docs.agentcost.in
pip install agentcostin

Would love feedback from anyone managing AI costs at scale.
