-- AgentCost Migration 005: Goals, Heartbeat, Reactions, Templates
-- Persists data that was previously in-memory only.
-- This enables data to survive restarts — critical for enterprise deployments.

-- ── Goals (cost attribution by business objective) ───────────────────────────

CREATE TABLE IF NOT EXISTS goals (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    project         TEXT DEFAULT '',
    parent_goal_id  TEXT DEFAULT '',
    status          TEXT DEFAULT 'active',            -- active, completed, cancelled
    budget          DOUBLE PRECISION DEFAULT 0,       -- 0 = no limit
    org_id          TEXT DEFAULT 'default',
    created_at      DOUBLE PRECISION NOT NULL,
    updated_at      DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_goals_project ON goals(project);
CREATE INDEX IF NOT EXISTS idx_goals_parent ON goals(parent_goal_id);
CREATE INDEX IF NOT EXISTS idx_goals_org ON goals(org_id);
CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);

CREATE TABLE IF NOT EXISTS goal_spend (
    id              SERIAL PRIMARY KEY,
    goal_id         TEXT NOT NULL,
    cost            DOUBLE PRECISION NOT NULL DEFAULT 0,
    trace_id        TEXT,
    timestamp       DOUBLE PRECISION NOT NULL,
    org_id          TEXT DEFAULT 'default'
);

CREATE INDEX IF NOT EXISTS idx_gs_goal ON goal_spend(goal_id);
CREATE INDEX IF NOT EXISTS idx_gs_org ON goal_spend(org_id);

-- ── Heartbeat Cycles (per-cycle agent cost monitoring) ───────────────────────

CREATE TABLE IF NOT EXISTS heartbeat_cycles (
    id              TEXT PRIMARY KEY,                 -- cycle_id
    agent_id        TEXT NOT NULL,
    started_at      DOUBLE PRECISION NOT NULL,
    ended_at        DOUBLE PRECISION DEFAULT 0,
    cost            DOUBLE PRECISION DEFAULT 0,
    calls           INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'active',            -- active, completed, anomaly
    anomaly_reason  TEXT DEFAULT '',
    org_id          TEXT DEFAULT 'default'
);

CREATE INDEX IF NOT EXISTS idx_hb_agent ON heartbeat_cycles(agent_id);
CREATE INDEX IF NOT EXISTS idx_hb_status ON heartbeat_cycles(status);
CREATE INDEX IF NOT EXISTS idx_hb_org ON heartbeat_cycles(org_id);
CREATE INDEX IF NOT EXISTS idx_hb_started ON heartbeat_cycles(started_at);

CREATE TABLE IF NOT EXISTS heartbeat_budgets (
    id              SERIAL PRIMARY KEY,
    agent_id        TEXT UNIQUE NOT NULL,
    budget_limit    DOUBLE PRECISION NOT NULL,
    warning_pct     DOUBLE PRECISION DEFAULT 0.8,
    pause_pct       DOUBLE PRECISION DEFAULT 1.0,
    org_id          TEXT DEFAULT 'default',
    created_at      DOUBLE PRECISION NOT NULL,
    updated_at      DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hbb_org ON heartbeat_budgets(org_id);

-- ── Reactions (event-driven automation history) ──────────────────────────────

CREATE TABLE IF NOT EXISTS reaction_rules (
    id              TEXT PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,
    auto            BOOLEAN DEFAULT TRUE,
    actions         JSONB DEFAULT '[]',              -- JSON array of action strings
    condition       JSONB DEFAULT '{}',              -- JSON condition object
    cooldown_seconds DOUBLE PRECISION DEFAULT 0,
    escalate_after_seconds DOUBLE PRECISION DEFAULT 0,
    retries         INTEGER DEFAULT 0,
    enabled         BOOLEAN DEFAULT TRUE,
    source          TEXT DEFAULT 'custom',           -- 'default', 'custom', 'template'
    org_id          TEXT DEFAULT 'default',
    created_at      DOUBLE PRECISION NOT NULL,
    updated_at      DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rr_org ON reaction_rules(org_id);
CREATE INDEX IF NOT EXISTS idx_rr_enabled ON reaction_rules(enabled);

CREATE TABLE IF NOT EXISTS reaction_history (
    id              SERIAL PRIMARY KEY,
    reaction_name   TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    actions_executed JSONB DEFAULT '[]',
    actions_failed  JSONB DEFAULT '[]',
    skipped_reason  TEXT DEFAULT '',
    success         BOOLEAN DEFAULT TRUE,
    org_id          TEXT DEFAULT 'default',
    timestamp       DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rh_name ON reaction_history(reaction_name);
CREATE INDEX IF NOT EXISTS idx_rh_org ON reaction_history(org_id);
CREATE INDEX IF NOT EXISTS idx_rh_ts ON reaction_history(timestamp);

CREATE TABLE IF NOT EXISTS reaction_cooldowns (
    id              SERIAL PRIMARY KEY,
    reaction_name   TEXT UNIQUE NOT NULL,
    last_fired_at   DOUBLE PRECISION NOT NULL,
    org_id          TEXT DEFAULT 'default'
);

-- ── Templates (governance profiles — applied configurations) ─────────────────

CREATE TABLE IF NOT EXISTS templates (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    version         TEXT DEFAULT '1.0.0',
    author          TEXT DEFAULT 'AgentCost',
    tags            JSONB DEFAULT '[]',
    tier_restrictions JSONB DEFAULT '{}',
    budgets         JSONB DEFAULT '[]',
    policies        JSONB DEFAULT '[]',
    reactions       JSONB DEFAULT '{}',
    cost_centers    JSONB DEFAULT '[]',
    notifications   JSONB DEFAULT '[]',
    goals           JSONB DEFAULT '[]',
    settings        JSONB DEFAULT '{}',
    source          TEXT DEFAULT 'builtin',          -- 'builtin', 'custom', 'imported'
    org_id          TEXT DEFAULT 'default',
    created_at      DOUBLE PRECISION NOT NULL,
    updated_at      DOUBLE PRECISION NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tpl_name_org ON templates(name, org_id);
CREATE INDEX IF NOT EXISTS idx_tpl_org ON templates(org_id);

CREATE TABLE IF NOT EXISTS template_applications (
    id              SERIAL PRIMARY KEY,
    template_name   TEXT NOT NULL,
    applied_by      TEXT DEFAULT '',
    org_id          TEXT DEFAULT 'default',
    applied_at      DOUBLE PRECISION NOT NULL,
    rollback_data   JSONB DEFAULT '{}'               -- snapshot of previous config for undo
);

CREATE INDEX IF NOT EXISTS idx_ta_org ON template_applications(org_id);
CREATE INDEX IF NOT EXISTS idx_ta_ts ON template_applications(applied_at);

-- ── Record this migration ────────────────────────────────────────────────────

INSERT INTO schema_version (version, description)
VALUES (5, 'Persistent storage for goals, heartbeat cycles, reactions, and templates')
ON CONFLICT (version) DO NOTHING;
