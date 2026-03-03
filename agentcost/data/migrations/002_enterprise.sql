-- AgentCost Migration 002: Enterprise Tables (Phase 3)
-- Creates all tables needed for SSO, RBAC, budgets, audit, cost allocation,
-- policies, approvals, and integrations. Tables are empty until features ship.

-- ── Organizations ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS orgs (
    id          TEXT PRIMARY KEY,                    -- UUID
    name        TEXT NOT NULL,
    slug        TEXT UNIQUE,                         -- URL-safe identifier
    sso_provider TEXT,                               -- 'workos', 'auth0', 'none'
    sso_config  TEXT,                                -- JSON: provider-specific config
    plan        TEXT DEFAULT 'free',                 -- 'free', 'pro', 'enterprise'
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Users ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,                -- UUID
    email           TEXT UNIQUE NOT NULL,
    name            TEXT,
    org_id          TEXT REFERENCES orgs(id),
    role            TEXT DEFAULT 'viewer',           -- admin, manager, viewer, agent_dev
    sso_provider_id TEXT,                            -- External ID from SSO provider
    avatar_url      TEXT,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_org   ON users(org_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ── API Keys ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS api_keys (
    id          TEXT PRIMARY KEY,                    -- UUID
    org_id      TEXT NOT NULL REFERENCES orgs(id),
    key_prefix  TEXT NOT NULL,                       -- First 8 chars for display: ac_live_xxxx
    key_hash    TEXT UNIQUE NOT NULL,                -- bcrypt hash of full key
    name        TEXT DEFAULT 'Default',              -- Human-friendly label
    scopes      TEXT DEFAULT '*',                    -- Comma-separated: 'traces.write,budgets.read'
    created_by  TEXT REFERENCES users(id),
    last_used   TIMESTAMPTZ,
    expires_at  TIMESTAMPTZ,                         -- NULL = no expiry
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_keys_org ON api_keys(org_id);

-- ── Invites ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS invites (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL REFERENCES orgs(id),
    email       TEXT NOT NULL,
    role        TEXT DEFAULT 'viewer',
    invited_by  TEXT REFERENCES users(id),
    status      TEXT DEFAULT 'pending',              -- pending, accepted, expired, revoked
    expires_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invites_org ON invites(org_id);

-- ── Audit Log (immutable, hash-chained) ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_log (
    id              SERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL,                   -- 'llm_call', 'login', 'budget.set', etc.
    actor_id        TEXT,                            -- user or agent who performed action
    actor_type      TEXT DEFAULT 'user',             -- 'user', 'agent', 'system'
    org_id          TEXT,
    resource_type   TEXT,                            -- 'project', 'agent', 'budget', 'policy'
    resource_id     TEXT,
    action          TEXT,                            -- 'create', 'update', 'delete', 'execute'
    details         TEXT,                            -- JSON payload
    prev_hash       TEXT,                            -- Hash of previous entry (chain)
    entry_hash      TEXT,                            -- SHA-256(prev_hash + entry_data)
    timestamp       TIMESTAMPTZ DEFAULT NOW(),
    retention_until TIMESTAMPTZ                      -- When this entry can be archived
);

CREATE INDEX IF NOT EXISTS idx_audit_org_ts   ON audit_log(org_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_type     ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_actor    ON audit_log(actor_id);

-- ── Cost Centers (for chargeback) ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cost_centers (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL REFERENCES orgs(id),
    name            TEXT NOT NULL,
    code            TEXT,                            -- ERP/finance code: 'ENG-001'
    manager_email   TEXT,
    monthly_budget  DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cc_org ON cost_centers(org_id);

-- ── Cost Allocations (project/agent → cost center mapping) ───────────────────

CREATE TABLE IF NOT EXISTS cost_allocations (
    id              SERIAL PRIMARY KEY,
    org_id          TEXT NOT NULL,
    project         TEXT,                            -- project name from trace_events
    agent_id        TEXT,                            -- agent from agent registry
    cost_center_id  TEXT REFERENCES cost_centers(id),
    allocation_pct  DOUBLE PRECISION DEFAULT 100.0,  -- 0-100, for split allocations
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ca_org ON cost_allocations(org_id);

-- ── Policies ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS policies (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL REFERENCES orgs(id),
    name        TEXT NOT NULL,
    description TEXT,
    enabled     BOOLEAN DEFAULT TRUE,
    priority    INTEGER DEFAULT 100,                 -- Lower = higher priority
    conditions  TEXT NOT NULL,                        -- JSON: rule conditions
    action      TEXT NOT NULL DEFAULT 'deny',         -- 'allow', 'deny', 'require_approval', 'log_only'
    message     TEXT,                                 -- Shown to user on policy violation
    created_by  TEXT REFERENCES users(id),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_policies_org ON policies(org_id);

-- ── Approval Requests ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS approval_requests (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    requester_type  TEXT DEFAULT 'agent',             -- 'agent', 'user'
    requester_id    TEXT,                             -- agent_id or user_id
    request_type    TEXT NOT NULL,                    -- 'budget_overage', 'policy_override', 'high_cost'
    context         TEXT,                             -- JSON: what triggered the request
    estimated_cost  DOUBLE PRECISION,
    status          TEXT DEFAULT 'pending',           -- pending, approved, denied, expired
    decided_by      TEXT REFERENCES users(id),
    decided_at      TIMESTAMPTZ,
    unlock_amount   DOUBLE PRECISION,                 -- How much budget to unlock if approved
    expires_at      TIMESTAMPTZ,                      -- Auto-deny after this time
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_approvals_org    ON approval_requests(org_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approval_requests(status);

-- ── Notification Channels ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS notification_channels (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL REFERENCES orgs(id),
    channel_type TEXT NOT NULL,                       -- 'email', 'slack', 'webhook', 'pagerduty'
    name        TEXT NOT NULL,
    config      TEXT NOT NULL,                        -- JSON: URL, API key, channel, etc.
    events      TEXT DEFAULT '*',                     -- Comma-separated event types to subscribe to
    enabled     BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nc_org ON notification_channels(org_id);

-- ── Agent Scorecards (multi-agent governance) ────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_scorecards (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    period          TEXT NOT NULL,                    -- '2026-02' (monthly)
    quality_score   DOUBLE PRECISION,
    cost_efficiency DOUBLE PRECISION,                 -- cost per quality point
    total_cost      DOUBLE PRECISION,
    total_tasks     INTEGER,
    error_rate      DOUBLE PRECISION,
    uptime_pct      DOUBLE PRECISION,
    grade           TEXT,                             -- 'A', 'B', 'C', 'D', 'F'
    recommendations TEXT,                             -- JSON: optimization suggestions
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sc_org_agent ON agent_scorecards(org_id, agent_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sc_unique ON agent_scorecards(org_id, agent_id, period);

-- ── Record this migration ────────────────────────────────────────────────────

INSERT INTO schema_version (version, description)
VALUES (2, 'Enterprise tables: orgs, users, api_keys, audit_log, cost_centers, policies, approvals, notifications, scorecards')
ON CONFLICT (version) DO NOTHING;
