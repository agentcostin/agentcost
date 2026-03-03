# AgentCost Enterprise

This directory contains enterprise features licensed under the
Business Source License 1.1 (BSL 1.1). See [LICENSE](LICENSE).

## Enterprise Features

| Module | Feature |
|--------|---------|
| `agentcost/auth/` | SSO/SAML authentication (Keycloak) |
| `agentcost/org/` | Multi-tenant organization management |
| `agentcost/cost/` | Cost centers, allocations, budget enforcement |
| `agentcost/policy/` | Policy engine, approval workflows |
| `agentcost/notify/` | Notifications, scorecards |
| `agentcost/anomaly/` | ML-based anomaly detection |
| `agentcost/gateway/` | AI Gateway proxy |
| `agentcost/events/` | Event bus, webhooks, SSE |

## How It Works

The enterprise modules live in `agentcost/` alongside core modules.
The server detects their presence at startup:

- `AGENTCOST_EDITION=auto` (default): Enterprise features activate
  if the modules are importable
- `AGENTCOST_EDITION=community`: Force community mode
- `AGENTCOST_EDITION=enterprise`: Force enterprise mode

For community-only distribution, remove the enterprise module
directories from `agentcost/`.

## Enterprise Module Directories

These directories in `agentcost/` are covered by this license:

```
agentcost/auth/
agentcost/org/
agentcost/cost/
agentcost/policy/
agentcost/notify/
agentcost/anomaly/
agentcost/gateway/
agentcost/events/
```

All other directories in `agentcost/` are MIT-licensed.
