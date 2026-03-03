# REST API Reference

Base URL: `http://localhost:8500` (configurable via `AGENTCOST_PORT`)

Full interactive docs available at `/docs` (Swagger UI) when the server is running.

## Core Endpoints

### Health

```
GET /api/health
```

Returns server status, edition, and feature flags.

```json
{
  "status": "ok",
  "version": "1.0.0",
  "edition": "community",
  "auth_enabled": false,
  "features": { "auth": false, "org": false, ... },
  "core": { "tracing": true, "dashboard": true, ... }
}
```

### Traces

#### Ingest a trace

```
POST /api/trace
Content-Type: application/json

{
  "project": "my-app",
  "model": "gpt-4o",
  "provider": "openai",
  "input_tokens": 150,
  "output_tokens": 80,
  "cost": 0.0035,
  "latency_ms": 450,
  "status": "success",
  "agent_id": "chatbot",
  "session_id": "conv-123"
}
```

#### Batch ingest

```
POST /api/trace/batch
Content-Type: application/json

{
  "events": [
    { "project": "my-app", "model": "gpt-4o", "cost": 0.003, ... },
    { "project": "my-app", "model": "gpt-4o-mini", "cost": 0.0005, ... }
  ]
}
```

#### List traces

```
GET /api/traces?project=my-app&model=gpt-4o&limit=100
```

#### Trace count

```
GET /api/traces/count?project=my-app
```

### Cost Analysis

#### Summary

```
GET /api/summary?project=my-app
```

#### Cost by model

```
GET /api/cost/by-model?project=my-app
```

#### Cost by project

```
GET /api/cost/by-project
```

#### Cost over time

```
GET /api/cost/over-time?project=my-app&interval=hour&since_hours=48
```

`interval`: `minute`, `hour`, `day`

### Projects

```
GET /api/projects
```

### Budgets

#### Get budget status

```
GET /api/budget/{project}
```

#### Set budget

```
POST /api/budget/{project}?daily=50&monthly=1000
```

### Benchmarks

```
GET /api/benchmarks/leaderboard
GET /api/benchmarks/runs?limit=50
GET /api/benchmarks/run/{run_id}
```

### Cost Intelligence

#### Forecast

```
GET /api/forecast/{project}?days=30&method=ensemble
```

`method`: `linear`, `ema`, `ensemble`

#### Budget exhaustion

```
GET /api/forecast/{project}/budget-exhaustion?budget=1000
```

#### Cost estimation

```
POST /api/estimate
Content-Type: application/json

{
  "model": "gpt-4o",
  "prompt": "Analyze this report...",
  "task_type": "analysis",
  "max_output_tokens": 2000
}
```

#### Model comparison

```
GET /api/estimate/compare?prompt=Hello&task_type=chat
```

#### Optimizer

```
GET /api/optimizer/{project}
```

#### Analytics

```
GET /api/analytics/{project}/summary
GET /api/analytics/{project}/top-spenders?by=model&limit=10
GET /api/analytics/{project}/efficiency
GET /api/analytics/{project}/chargeback?group_by=project
```

### Seed Data

```
POST /api/seed
Content-Type: application/json

{
  "days": 14,
  "clear": true,
  "calls_per_day": 120,
  "project": null
}
```

## Enterprise Endpoints

Available when `AGENTCOST_EDITION=enterprise`.

### Authentication

```
GET  /auth/login         → Redirect to Keycloak
GET  /auth/callback      → OIDC callback
GET  /auth/me            → Current user info
POST /auth/logout        → Logout
GET  /auth/saml/metadata → SAML SP metadata
POST /auth/saml/acs      → SAML assertion consumer
```

### Organization

```
GET  /org/members        → List team members
POST /org/members/invite → Invite user
GET  /org/invites        → List invites
```

### Cost Governance

```
GET  /cost/budgets       → List budgets
GET  /cost/centers       → List cost centers
GET  /cost/utilization   → Budget utilization
GET  /cost/chargeback    → Chargeback reports
```

### Policies

```
GET    /policy/policies     → List policies
POST   /policy/policies     → Create policy
GET    /policy/approvals    → List approvals
POST   /policy/approvals/{id}/approve
POST   /policy/approvals/{id}/deny
GET    /policy/approvals/stats
```

### Notifications

```
GET  /notify/channels     → List channels
POST /notify/channels     → Create channel
GET  /notify/scorecards   → Agent scorecards
```
