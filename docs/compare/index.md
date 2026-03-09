# Compare AgentCost

AgentCost is the first purpose-built **AI cost governance** platform. While other tools focus on observability, evaluation, or gateway routing, AgentCost focuses on controlling what you spend next — with forecasting, budget enforcement, smart routing, and policy controls.

Here's how AgentCost compares to the leading platforms:

| Platform | Primary Focus | AgentCost Differentiator |
|----------|--------------|--------------------------|
| **[Langfuse](langfuse.md)** | LLM observability & evals | AgentCost adds forecasting, budget enforcement, policy engine, smart routing |
| **[Helicone](helicone.md)** | AI gateway & analytics | AgentCost adds forecasting, auto-downgrade, complexity routing, governance |
| **[Portkey](portkey.md)** | AI gateway & guardrails | AgentCost adds org-level governance, approval workflows, scorecards, goal attribution |

## The Governance Gap

Every competitor answers **"how much did we spend?"**

AgentCost is the only platform that answers **"how do we control what we spend next?"**

| Capability | Langfuse | Helicone | Portkey | AgentCost |
|-----------|----------|----------|---------|-----------|
| Cost Forecasting | ❌ | ❌ | ❌ | ✅ |
| Budget Enforcement + Auto-Downgrade | ❌ | ❌ | Partial | ✅ |
| Complexity-Based Routing | ❌ | ❌ | ❌ | ✅ |
| Policy Engine | ❌ | ❌ | ❌ | ✅ |
| Approval Workflows | ❌ | ❌ | ❌ | ✅ |
| Agent Scorecards | ❌ | ❌ | ❌ | ✅ |
| Goal-Aware Attribution | ❌ | ❌ | ❌ | ✅ |
| Governance Templates | ❌ | ❌ | ❌ | ✅ |
| Event-Driven Reactions | ❌ | ❌ | ❌ | ✅ |
| CI/CD Cost Checks | ❌ | ❌ | ❌ | ✅ |

## Try AgentCost

```bash
docker run -d -p 8100:8100 agentcost/agentcost:latest
```

**[Live Demo](https://demo.agentcost.in)** · **[GitHub](https://github.com/agentcostin/agentcost)** · **[Docs](https://docs.agentcost.in)**
