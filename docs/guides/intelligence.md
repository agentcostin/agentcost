# Cost Intelligence

AgentCost's intelligence layer provides cost-aware decision making for AI workloads. It classifies models into tiers, analyzes token efficiency, gates budget overruns, and auto-routes prompts to the right cost tier.

## Cost Tiers

Every model in the 2,610+ vendored pricing database is automatically classified into a tier:

```python
from agentcost.intelligence import get_tier_registry

reg = get_tier_registry()
print(reg.classify("gpt-4o"))          # CostTier.STANDARD
print(reg.classify("gpt-4o-mini"))     # CostTier.ECONOMY
print(reg.classify("o1"))              # CostTier.PREMIUM
print(reg.tier_summary())              # {'economy': 949, 'standard': 925, 'premium': 160, 'free': 229}
```

### Tier Thresholds

| Tier | Input Cost (per 1M tokens) |
|------|---------------------------|
| Economy | < $0.50 |
| Standard | $0.50 – $5.00 |
| Premium | > $5.00 |
| Free | $0.00 |

### Tier Policies

Restrict agents to specific tiers:

```python
result = reg.check_tier_policy("o1", allowed_tiers=["economy", "standard"])
# {'allowed': False, 'tier': 'premium', 'suggested_alternative': 'gpt-4o-mini'}
```

## Complexity Router

Auto-classify prompts and route to the appropriate cost tier:

```python
from agentcost.intelligence import ComplexityRouter

router = ComplexityRouter()

# Simple question → economy tier
result = router.classify("What is the capital of France?")
# level=SIMPLE, tier=economy, model=gpt-4o-mini

# Complex reasoning → premium tier
result = router.classify("Prove that sqrt(2) is irrational by contradiction")
# level=REASONING, tier=premium, model=o1

# One-shot routing
model = router.route("Summarize this report", provider="anthropic")
# "claude-3-5-sonnet-20241022"
```

### Classification Levels

| Level | Routes To | Triggers |
|-------|-----------|----------|
| SIMPLE | Economy | Short questions, lookups, yes/no |
| MEDIUM | Standard | Summarization, moderate generation |
| COMPLEX | Standard | Code review, architecture, analysis |
| REASONING | Premium | Proofs, chain-of-thought, math |

## Budget Gates

Pre-execution budget checks that automatically downgrade or block expensive calls:

```python
from agentcost.intelligence import BudgetGate

gate = BudgetGate(budget=10.00)

# Fresh budget → allow
decision = gate.check("gpt-4o", estimated_tokens=5000)
# action=allow, model=gpt-4o

# Record spend
gate.record_spend(8.50)  # 85% used

# Now warns
decision = gate.check("gpt-4o")
# action=warn, reason="Budget warning: 85.0% used"

# At 95% → auto-downgrade
gate.spent = 9.50
decision = gate.check("gpt-4o", provider="openai")
# action=downgrade, model=gpt-4o-mini

# At 100% → block
gate.spent = 10.00
decision = gate.check("gpt-4o")
# action=block, reason="Budget exhausted"
```

### Downgrade Chains

| Provider | Chain |
|----------|-------|
| OpenAI | gpt-4o → gpt-4o-mini → gpt-3.5-turbo |
| Anthropic | claude-3-5-sonnet → claude-3-haiku |

## Token Analyzer

Measure how efficiently agents use their context windows:

```python
from agentcost.intelligence import TokenAnalyzer

analyzer = TokenAnalyzer()

# Record LLM calls
analyzer.record_call(
    model="gpt-4o", input_tokens=50000, output_tokens=200,
    max_context=128000, system_tokens=40000, project="my-app",
)

# Get efficiency report
report = analyzer.analyze("my-app")
print(report.efficiency_score)    # 0-100
print(report.warnings)            # ["System prompts average 80% of input tokens"]
print(report.recommendations)     # ["Consider shortening system prompts..."]
```

### What It Detects

| Pattern | Threshold | Recommendation |
|---------|-----------|----------------|
| Excessive system prompts | > 30% of input | Shorten prompts, use few-shot selectively |
| Under-utilized context | < 5% of window | Use smaller/cheaper model |
| Near context limit | > 90% of window | Summarize context or use larger model |
| Low output ratio | < 2% of total | Review if all input context is necessary |

## Combining Components

The intelligence components work together:

```python
from agentcost.intelligence import ComplexityRouter, TierRegistry, BudgetGate

router = ComplexityRouter()
tiers = TierRegistry()
gate = BudgetGate(budget=50.00)

# 1. Classify the prompt
prompt = "Analyze our Q3 revenue trends"
result = router.classify(prompt)
model = router.route(prompt, provider="openai")

# 2. Check tier policy
policy = tiers.check_tier_policy(model, allowed_tiers=["economy", "standard"])
if not policy["allowed"]:
    model = policy["suggested_alternative"]

# 3. Budget gate
decision = gate.check(model, estimated_tokens=5000, provider="openai")
if decision.action == "downgrade":
    model = decision.model
elif decision.action == "block":
    raise Exception("Budget exhausted")

# 4. Make the call with the approved model
print(f"Using: {model}")
```
