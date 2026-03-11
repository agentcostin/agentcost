-- Migration 004: Prompt Management & Versioning
-- Adds prompts, prompt_versions, and prompt_deployments tables

CREATE TABLE IF NOT EXISTS prompts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    project TEXT NOT NULL DEFAULT 'default',
    description TEXT DEFAULT '',
    tags JSONB DEFAULT '[]',
    latest_version INTEGER DEFAULT 0,
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL,
    org_id TEXT NOT NULL DEFAULT 'default'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_prompts_name_project
    ON prompts(name, project, org_id);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL REFERENCES prompts(id),
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    model TEXT DEFAULT '',
    variables JSONB DEFAULT '[]',
    config JSONB DEFAULT '{}',
    author TEXT DEFAULT '',
    commit_message TEXT DEFAULT '',
    created_at DOUBLE PRECISION NOT NULL,
    UNIQUE(prompt_id, version)
);
CREATE INDEX IF NOT EXISTS idx_pv_prompt ON prompt_versions(prompt_id);

CREATE TABLE IF NOT EXISTS prompt_deployments (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL REFERENCES prompts(id),
    version_id TEXT NOT NULL REFERENCES prompt_versions(id),
    version INTEGER NOT NULL,
    environment TEXT NOT NULL DEFAULT 'production',
    deployed_at DOUBLE PRECISION NOT NULL,
    deployed_by TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pd_prompt_env
    ON prompt_deployments(prompt_id, environment);
CREATE INDEX IF NOT EXISTS idx_pd_prompt ON prompt_deployments(prompt_id);
