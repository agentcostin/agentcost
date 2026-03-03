-- AgentCost Migration 001: Initial PostgreSQL Schema
-- Mirrors the SQLite schema with Postgres-native types and org_id added.
-- Run via: python -m agentcost.data.migrations.migrate

-- ── Schema versioning ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    description TEXT
);

-- ── Trace events (Phase 2: SDK cost tracking) ────────────────────────────────

CREATE TABLE IF NOT EXISTS trace_events (
    id              SERIAL PRIMARY KEY,
    trace_id        TEXT NOT NULL,
    project         TEXT DEFAULT 'default',
    agent_id        TEXT,
    session_id      TEXT,
    model           TEXT NOT NULL,
    provider        TEXT,
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    cost            DOUBLE PRECISION DEFAULT 0,
    latency_ms      DOUBLE PRECISION DEFAULT 0,
    status          TEXT DEFAULT 'success',
    error           TEXT,
    metadata        TEXT,                          -- JSON string
    timestamp       TEXT NOT NULL,                  -- ISO 8601 string (matches SDK output)
    org_id          TEXT                            -- NULL for self-hosted/free tier
);

CREATE INDEX IF NOT EXISTS idx_te_project   ON trace_events(project);
CREATE INDEX IF NOT EXISTS idx_te_model     ON trace_events(model);
CREATE INDEX IF NOT EXISTS idx_te_ts        ON trace_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_te_org       ON trace_events(org_id);
CREATE INDEX IF NOT EXISTS idx_te_org_proj  ON trace_events(org_id, project);

-- ── Budgets (Phase 2: basic budget limits) ───────────────────────────────────

CREATE TABLE IF NOT EXISTS budgets (
    id              SERIAL PRIMARY KEY,
    project         TEXT UNIQUE NOT NULL,
    daily_limit     DOUBLE PRECISION,
    monthly_limit   DOUBLE PRECISION,
    total_limit     DOUBLE PRECISION,
    alert_threshold DOUBLE PRECISION DEFAULT 0.8,
    created_at      TEXT,
    updated_at      TEXT,
    org_id          TEXT
);

-- ── Benchmark results (Phase 1: economic benchmarking) ───────────────────────

CREATE TABLE IF NOT EXISTS task_results (
    id               SERIAL PRIMARY KEY,
    run_id           TEXT NOT NULL,
    task_id          TEXT NOT NULL,
    model            TEXT NOT NULL,
    sector           TEXT,
    occupation       TEXT,
    quality_score    DOUBLE PRECISION,
    max_payment      DOUBLE PRECISION,
    actual_payment   DOUBLE PRECISION,
    input_tokens     INTEGER,
    output_tokens    INTEGER,
    llm_cost         DOUBLE PRECISION,
    eval_cost        DOUBLE PRECISION,
    total_cost       DOUBLE PRECISION,
    duration_seconds DOUBLE PRECISION,
    roi              DOUBLE PRECISION,
    work_output      TEXT,
    timestamp        TEXT,
    org_id           TEXT
);

CREATE INDEX IF NOT EXISTS idx_task_results_run   ON task_results(run_id);
CREATE INDEX IF NOT EXISTS idx_task_results_model ON task_results(model);
CREATE INDEX IF NOT EXISTS idx_tr_org             ON task_results(org_id);

-- ── Run summaries (Phase 1: aggregated benchmark runs) ───────────────────────

CREATE TABLE IF NOT EXISTS run_summaries (
    id                  SERIAL PRIMARY KEY,
    run_id              TEXT UNIQUE NOT NULL,
    model               TEXT NOT NULL,
    total_tasks         INTEGER,
    completed_tasks     INTEGER,
    avg_quality         DOUBLE PRECISION,
    total_income        DOUBLE PRECISION,
    total_cost          DOUBLE PRECISION,
    net_profit          DOUBLE PRECISION,
    profit_margin       DOUBLE PRECISION,
    avg_roi             DOUBLE PRECISION,
    total_input_tokens  INTEGER,
    total_output_tokens INTEGER,
    total_duration      DOUBLE PRECISION,
    started_at          TEXT,
    finished_at         TEXT,
    org_id              TEXT
);

CREATE INDEX IF NOT EXISTS idx_run_summaries_model ON run_summaries(model);
CREATE INDEX IF NOT EXISTS idx_rs_org              ON run_summaries(org_id);

-- ── Record this migration ────────────────────────────────────────────────────

INSERT INTO schema_version (version, description)
VALUES (1, 'Initial schema: trace_events, budgets, task_results, run_summaries')
ON CONFLICT (version) DO NOTHING;
