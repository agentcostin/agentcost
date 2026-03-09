# How a 12-Engineer Team Cut AI Spend by 43% in One Week

**Published:** March 2026 · **Reading time:** 8 minutes

---

## The $14,000 wake-up call

A backend engineering team at a mid-stage SaaS company was building AI-powered features across their product — a document summarizer, a customer support chatbot, a code review assistant, and an internal knowledge search. Four projects, twelve engineers, all defaulting to premium models: Claude Opus 4.6 for code review, Claude Sonnet 4.6 for the chatbot, and GPT-4.1 everywhere else.

Their February invoice across OpenAI and Anthropic landed at **$14,200**. The previous month was $8,100. Nobody could explain the 75% increase. There was no breakdown by project, no way to tell which feature was responsible, and no visibility into whether the token usage was efficient or wasteful.

The CTO asked two questions:

1. *"Which project is burning the most money?"*
2. *"Are we using the right models for each use case?"*

Nobody had answers. They had logging — every request went to Datadog — but Datadog showed latency and error rates, not cost per call, not cost per project, not whether Claude Opus 4.6 at $5/1M input tokens was overkill for half their queries.

They needed cost governance, not more observability.

## Day 1: Install and instrument (45 minutes)

The platform lead installed AgentCost on a Monday morning:

```bash
docker run -d -p 8100:8100 -v agentcost_data:/data agentcost/agentcost:latest
```

Then added one line to each project's client initialization:

```python
from agentcost.sdk import trace
from openai import OpenAI
from anthropic import Anthropic

# OpenAI projects — one line change
client = trace(OpenAI(), project="knowledge-search")

# Anthropic projects — same pattern
client = trace(Anthropic(), project="code-reviewer")
```

Four projects, four `trace()` wrappers. Each engineer changed one line in their codebase. Total instrumentation time: 45 minutes including the PR reviews.

By Monday afternoon, the dashboard was populating:

- **doc-summarizer**: 2,400 calls/day on GPT-5.2, $38/day
- **support-chatbot**: 8,100 calls/day on Claude Sonnet 4.6, $112/day
- **code-reviewer**: 890 calls/day on Claude Opus 4.6, $67/day
- **knowledge-search**: 12,300 calls/day on GPT-4.1, $41/day

The support chatbot was making 8,100 calls per day — more than anyone expected. But the code reviewer, with only 890 calls, was costing $67/day. Something was wrong.

## Day 2: The cost breakdown reveals the problem

The AgentCost dashboard showed the cost-by-model breakdown:

| Project | Model | Daily Calls | Daily Cost | Avg Tokens/Call |
|---------|-------|------------|-----------|----------------|
| code-reviewer | claude-opus-4-6 | 890 | $67.40 | 4,200 |
| support-chatbot | claude-sonnet-4-6 | 8,100 | $112.00 | 580 |
| knowledge-search | gpt-4.1 | 12,300 | $41.00 | 320 |
| doc-summarizer | gpt-5.2 | 2,400 | $38.20 | 1,100 |

Two things jumped out immediately:

**The code reviewer was sending 4,200 tokens per call to Claude Opus 4.6.** At $5/1M input + $25/1M output, every wasted token costs 10x what it would on a cheaper model. The team investigated and found that the system prompt included the entire project's coding standards document (3,100 tokens) in every single request. It was copy-pasted during a prototype and never optimized.

**Knowledge search was making 12,300 calls per day on GPT-4.1.** At $2/1M input tokens, these were simple factual lookups — "What is our refund policy?", "How do I reset my password?", "What are the office hours?" — queries that GPT-4.1-nano at $0.10/1M input could handle perfectly.

## Day 3: The complexity router saves 40%

The team enabled AgentCost's **complexity router** on the knowledge search project. The router classifies each incoming prompt as SIMPLE, MEDIUM, COMPLEX, or REASONING, and routes to the cheapest model that can handle it:

- **SIMPLE** (factual lookups, classifications) → gpt-4.1-nano ($0.10/1M input)
- **MEDIUM** (summarization, standard generation) → gpt-4.1-mini ($0.40/1M input)
- **COMPLEX** (analysis, long-form) → gpt-4.1 ($2.00/1M input)
- **REASONING** (math, logic, multi-step) → o4-mini ($1.10/1M input)

The result on knowledge search after one day:

| Complexity | % of Queries | Model | Daily Cost |
|-----------|-------------|-------|-----------|
| SIMPLE | 73% | gpt-4.1-nano | $0.90 |
| MEDIUM | 21% | gpt-4.1-mini | $3.50 |
| COMPLEX | 6% | gpt-4.1 | $2.40 |

**Knowledge search dropped from $41/day to $6.80/day — an 83% reduction.** The simple queries (73% of traffic) were handled by GPT-4.1-nano at 1/20th the cost, with no user-visible quality difference. The team ran a blind evaluation on 200 queries and found GPT-4.1-nano answered simple factual questions with 97% accuracy versus GPT-4.1's 99%.

## Day 3 (continued): Fixing the token explosion

The **token analyzer** flagged the code reviewer's system prompt as a problem:

!!! warning "Token Analyzer Alert"
    **code-reviewer**: Context efficiency score **23/100**. System prompt consumes 74% of input tokens. Recommendation: Extract static content to a retrieval step or reduce system prompt length.

The team refactored the code reviewer to load coding standards via RAG instead of stuffing them into every prompt. System prompt dropped from 3,100 tokens to 280 tokens. Claude Opus 4.6 stayed as the model — code review quality matters — but the per-call cost dropped dramatically.

Result: code reviewer costs dropped from **$67.40/day to $19.80/day**.

## Day 4: Budget enforcement prevents a repeat

With costs now visible and optimized, the team set up **budget enforcement** to prevent future surprises:

```
Project: support-chatbot
  Daily budget: $150
  Monthly budget: $3,500
  Warning threshold: 80%
  Auto-downgrade at: 90%
  Block at: 100%
```

They configured the **budget gate** with auto-downgrade chains:

- At 90% of daily budget → automatically route from Claude Sonnet 4.6 to Claude Haiku 4.5 ($1/1M input — 3x cheaper)
- At 100% → block new requests, notify #ai-costs Slack channel

They also added a **policy rule** for the code reviewer:

```json
{
  "name": "code-reviewer-token-cap",
  "conditions": {
    "project": "code-reviewer",
    "input_tokens": { "gt": 2000 }
  },
  "action": "warn",
  "message": "Code reviewer input exceeds 2000 tokens — check system prompt"
}
```

This policy fires whenever a code reviewer call sends more than 2,000 input tokens — catching any future regression where someone accidentally bloats the prompt again.

## Day 5: Forecasting catches the next spike before it happens

On Friday, the AgentCost **forecast** showed something concerning:

!!! danger "Budget Exhaustion Alert"
    **support-chatbot**: At current trajectory, monthly budget of $3,500 will be exhausted by **March 22** (day 22 of 31). Ensemble forecast: $4,180 for the full month.

The team investigated and found that a new feature launch on Wednesday had increased chatbot usage by 35%. Without forecasting, they would have discovered this on the invoice at month-end. With AgentCost, they caught it on day 5 and proactively:

1. Enabled the complexity router on the support chatbot (routing simple FAQs to Claude Haiku 4.5 instead of Sonnet 4.6)
2. Adjusted the monthly budget to $4,000 to account for the growth
3. Set up a **reaction rule** to notify the team lead if the forecast-to-budget ratio exceeds 110%

## The results after one week

| Project | Model(s) | Before (Daily) | After (Daily) | Reduction |
|---------|----------|---------------|--------------|-----------|
| knowledge-search | GPT-4.1 → nano/mini/4.1 mix | $41.00 | $6.80 | 83% |
| code-reviewer | Claude Opus 4.6 (optimized prompts) | $67.40 | $19.80 | 71% |
| support-chatbot | Sonnet 4.6 → Haiku 4.5/Sonnet mix | $112.00 | $78.40 | 30% |
| doc-summarizer | GPT-5.2 (unchanged) | $38.20 | $34.50 | 10% |
| **Total** | | **$258.60** | **$139.50** | **46%** |

**Weekly spend dropped from $1,810 to $977 — a 46% reduction.** Projected monthly savings: **$3,330/month** or **$40,000/year**.

The breakdown of where the savings came from:

| Optimization | Monthly Savings | How |
|-------------|----------------|-----|
| Complexity routing on knowledge-search | $1,030 | 73% of queries routed to GPT-4.1-nano |
| System prompt fix on code-reviewer | $1,430 | RAG replaced 3,100-token system prompt in Claude Opus 4.6 calls |
| Complexity routing on support-chatbot | $1,010 | Simple FAQs routed from Sonnet 4.6 to Haiku 4.5 |
| **Total** | **$3,470** | |

## What they run today

Six weeks later, the team's AgentCost setup includes:

- **4 projects** tracked with per-project budgets and forecasting
- **Complexity router** on 3 of 4 projects (doc-summarizer stays on GPT-5.2 due to quality requirements)
- **Budget gate** with auto-downgrade chains: Opus 4.6 → Sonnet 4.6 → Haiku 4.5, and GPT-4.1 → GPT-4.1-mini → GPT-4.1-nano
- **5 policy rules** preventing token explosions, blocking deprecated models, and requiring approval for o3 usage (at $2/1M input, it needs justification)
- **Slack notifications** via the reactions engine for budget warnings, cost spikes, and weekly scorecard digests
- **Agent scorecards** grading each project monthly (knowledge-search earned an A, code-reviewer improved from D to B)
- **Goal-aware attribution** tagging costs to quarterly OKRs so the CTO can answer "how much did the Q1 AI features cost?"

The platform lead summarized it:

> *"We went from 'we have no idea what AI costs' to 'we know exactly what each feature costs, we forecast what it will cost next month, and the system automatically prevents overruns.' The complexity router alone paid for the setup time in the first hour."*

## Try it yourself

AgentCost is open-source (MIT) and self-hosted. One command to start:

```bash
docker run -d -p 8100:8100 -v agentcost_data:/data agentcost/agentcost:latest
```

Add cost tracking to your code with one line:

```python
from agentcost.sdk import trace
client = trace(OpenAI(), project="my-app")
```

**[Live Demo](https://demo.agentcost.in)** — see the dashboard with sample data, no install required.

**[GitHub](https://github.com/agentcostin/agentcost)** · **[Docs](https://docs.agentcost.in)** · **[Compare vs Langfuse/Helicone/Portkey](https://agentcost.in/docs/compare/)**

---

*This case study is based on composite scenarios from real-world AI cost patterns observed across engineering teams. Pricing reflects actual model costs as of March 2026: Claude Opus 4.6 ($5/$25 per 1M tokens), Claude Sonnet 4.6 ($3/$15), Claude Haiku 4.5 ($1/$5), GPT-5.2 ($1.75/$14), GPT-4.1 ($2/$8), GPT-4.1-mini ($0.40/$1.60), GPT-4.1-nano ($0.10/$0.40), o3 ($2/$8), o4-mini ($1.10/$4.40).*
