# Self-Hosting

Run AgentCost on your own infrastructure.

## Community Edition (Quick Start)

Zero-dependency local setup with SQLite:

```bash
git clone https://github.com/agentcostin/agentcost.git
cd agentcost

# Option 1: Docker
docker compose -f docker-compose.dev.yml up

# Option 2: Direct
pip install -e ".[server]"
agentcost dashboard
```

Dashboard at [http://localhost:8100](http://localhost:8100).

## Enterprise Edition

Full stack with PostgreSQL, Keycloak SSO, and all enterprise features:

```bash
git clone https://github.com/agentcostin/agentcost.git
cd agentcost

# Start all services
docker compose up -d
```

This starts:

| Service | Port | Purpose |
|---------|------|---------|
| AgentCost API | 8100 | Dashboard + REST API |
| PostgreSQL | 5432 | Application data |
| Keycloak | 8180 | SSO/SAML authentication |

### Environment Variables

```bash
# Required for enterprise
AGENTCOST_EDITION=enterprise
AGENTCOST_PORT=8100
AGENTCOST_AUTH_ENABLED=true
KEYCLOAK_URL=http://localhost:8180
KEYCLOAK_PUBLIC_URL=http://localhost:8180

# PostgreSQL (optional, defaults to SQLite)
AGENTCOST_DB_URL=postgresql://agentcost:agentcost@localhost:5432/agentcost
```

### Default Credentials

| User | Email | Password |
|------|-------|----------|
| Admin | open@agentcost.in | admin123 |
| User | care@agentcost.in | user123 |

!!! warning "Change default credentials"
    These are for development only. Change all passwords before production deployment.

## Production Deployment

### Recommended Architecture

```
                    ┌──────────────┐
                    │  Load        │
                    │  Balancer    │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼──┐  ┌─────▼──┐  ┌─────▼──┐
        │ API #1 │  │ API #2 │  │ API #3 │
        └───┬────┘  └───┬────┘  └───┬────┘
            │            │            │
            └────────────┼────────────┘
                         │
                  ┌──────▼──────┐
                  │ PostgreSQL  │
                  │ (primary)   │
                  └─────────────┘
```

### Checklist

- [ ] PostgreSQL with connection pooling (PgBouncer)
- [ ] Keycloak connected to your identity provider (LDAP, SAML, OIDC)
- [ ] TLS termination at load balancer
- [ ] `SESSION_SECRET` set to a strong random value (32+ bytes)
- [ ] Default passwords changed
- [ ] Database backups configured
- [ ] Prometheus monitoring enabled
