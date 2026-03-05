# Enterprise Features

AgentCost Enterprise adds governance, security, and compliance features for teams and organizations.

**License:** Business Source License 1.1 (source-available, converts to Apache 2.0 after 3 years)

## Feature Overview

### SSO/SAML Authentication

Integrate with any standards-compliant identity provider:

- **OIDC** — Works with Okta, Auth0, Azure AD, Google, AWS Cognito, Keycloak, Authentik
- **SAML 2.0** — Enterprise SAML for Active Directory, Okta, Ping Identity, OneLogin
- **Role-based access** — Admin, Manager, Agent Developer, Viewer
- **Auto-discovery** — Set `OIDC_ISSUER_URL` and endpoints are auto-configured

### Multi-Tenant Organizations

- Team management with invites and role assignment
- Org-level data isolation
- API key management with scoped permissions

### Budget Enforcement

- **Cost centers** with ERP integration codes
- **Allocation rules** — Map projects to cost centers (including split allocations)
- **Pre-call validation** — Block calls that would exceed budgets
- **Chargeback reports** — Internal cost attribution

### Policy Engine

JSON-based rules with priority evaluation:

```json
{
  "name": "Block Premium Models in Staging",
  "conditions": [
    {"field": "model", "op": "in", "value": ["gpt-5.2-pro", "claude-opus-4-6"]},
    {"field": "project", "op": "eq", "value": "staging"}
  ],
  "action": "deny",
  "priority": 10
}
```

Actions: `allow`, `deny`, `require_approval`, `log_only`

### Approval Workflows

Human-in-the-loop approval for policy exceptions:

- Agents request approval when a policy blocks them
- Managers approve/deny with context
- Automatic expiration of stale requests
- Unlock amounts for budget overages

### Notifications

Multi-channel alerting:

| Channel | Use Case |
|---------|----------|
| **Slack** | Budget warnings, anomaly alerts |
| **Email** | Weekly reports, approval requests |
| **Webhook** | Custom integrations |
| **PagerDuty** | Critical cost alerts |

### Agent Scorecards

Monthly performance grading for each AI agent:

- Quality score (0–1)
- Cost efficiency metric
- Error rate
- Uptime percentage
- Grade (A–F) with actionable recommendations

### Audit Log

Hash-chained, tamper-evident audit trail:

- All configuration changes tracked
- User actions logged with actor, resource, and timestamp
- Cryptographic hash chain for compliance verification

### Anomaly Detection

ML-based detection of unusual patterns:

- Cost spikes per model/project
- Latency anomalies
- Error rate increases
- Configurable sensitivity thresholds

### AI Gateway

Transparent LLM proxy that enforces policies:

- Drop-in replacement for OpenAI API endpoint
- Policy enforcement before forwarding calls
- Automatic cost tracking without SDK changes

## Getting Started

```bash
# Start enterprise stack
docker compose up -d

# Configure with any OIDC provider
export AGENTCOST_EDITION=enterprise
export AGENTCOST_AUTH_ENABLED=true
export OIDC_ISSUER_URL=https://your-idp.example.com/realms/agentcost
export OIDC_CLIENT_ID=agentcost-api
export OIDC_CLIENT_SECRET=your-secret
```

Or use legacy Keycloak env vars (still supported):

```bash
export KEYCLOAK_URL=http://localhost:8180
export KEYCLOAK_REALM=agentcost
```

See [Self-Hosting Guide](../guides/self-hosting.md) for full setup.

## Contact

- **Email:** open@agentcost.in
- **Docs:** [docs.agentcost.in](https://docs.agentcost.in)
