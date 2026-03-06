# Governance Templates

Pre-configured cost governance profiles that set up policies, budgets, tier restrictions, reactions, and notifications in one step. Inspired by Paperclip's Clipmart pattern.

## Built-in Templates

| Template | Description | Tier | Budgets | Policies |
|----------|-------------|------|---------|----------|
| **startup** | Cost-conscious, economy-focused | Economy + Standard | $500/month | Block premium in dev |
| **enterprise** | Full governance, 5 cost centers | All tiers, premium needs approval | $5K prod, $1K staging | Premium requires approval |
| **soc2-compliance** | Audit trail, no free-tier | No free tier | — | Block free, log premium |
| **agency** | Multi-client, per-client budgets | Economy + Standard | Per-client | Chargeback reports |
| **research-lab** | No restrictions, analytics focus | All tiers including free | $10K experiments | — |

## Using Templates

### Preview Before Applying

```python
from agentcost.templates import get_template_registry

reg = get_template_registry()

# List available templates
for t in reg.list_templates():
    print(f"{t['name']}: {t['description']}")

# Preview what would change
preview = reg.preview("startup")
print(preview["tier_restrictions"])  # {'allowed_tiers': ['economy', 'standard']}
print(preview["budgets"])            # [{'project': 'default', 'monthly_limit': 500}]
```

### Apply a Template

```python
result = reg.apply("enterprise")
print(result)
# {'template': 'enterprise', 'sections': [
#   {'section': 'tier_restrictions', 'items': 1},
#   {'section': 'budgets', 'items': 3},
#   {'section': 'policies', 'items': 2},
#   {'section': 'cost_centers', 'items': 5},
#   ...
# ]}
```

## Custom Templates

### Create from YAML

```yaml
# my-team.yaml
name: my-team
description: Custom setup for our ML team
version: "1.0.0"
tags: [ml, research]

tier_restrictions:
  allowed_tiers: [economy, standard, premium]
  require_approval_for: [premium]

budgets:
  - project: training
    monthly_limit: 3000.0
    alert_threshold: 0.80
  - project: inference
    monthly_limit: 1000.0

policies:
  - name: Log all premium usage
    conditions:
      - field: tier
        op: eq
        value: premium
    action: log_only
    priority: 20

reactions:
  budget-warning:
    auto: true
    actions: [notify, log]
    cooldown: 2h

goals:
  - id: reduce-cost-30pct
    name: Reduce inference cost by 30%
    budget: 2000

settings:
  complexity_routing: true
  token_analyzer_enabled: true
```

### Load and Apply

```python
reg.load_from_file("my-team.yaml")
reg.apply("my-team")
```

### Export Current Config

```python
yaml_str = reg.export_current("my-backup", "Snapshot of current config")
with open("backup.yaml", "w") as f:
    f.write(yaml_str)
```

## Template Sections

Each template can configure:

| Section | What it sets up |
|---------|----------------|
| `tier_restrictions` | Allowed tiers, approval requirements |
| `budgets` | Per-project monthly/daily limits |
| `policies` | Policy engine rules (deny, approve, log) |
| `reactions` | Event-driven automation (YAML reactions) |
| `cost_centers` | Cost center definitions with ERP codes |
| `notifications` | Slack, PagerDuty, webhook channels |
| `goals` | Business objectives with budgets |
| `settings` | Feature flags (complexity routing, audit, etc.) |
