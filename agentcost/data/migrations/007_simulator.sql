-- Migration 007: Simulator scenarios
-- Stores saved chaos simulation scenarios for replay and sharing.

CREATE TABLE IF NOT EXISTS simulator_scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL,
    description TEXT,
    architecture TEXT NOT NULL,      -- JSON: node positions, connections, configs
    chaos_events TEXT NOT NULL,       -- JSON: active event IDs and parameters
    traffic INTEGER NOT NULL DEFAULT 50,
    budget REAL NOT NULL DEFAULT 5000,
    results TEXT,                     -- JSON: simulation results if saved
    tags TEXT,                        -- JSON: array of tag strings
    is_template BOOLEAN DEFAULT 0,   -- 1 = built-in template, 0 = user-created
    created_by TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sim_scenarios_org ON simulator_scenarios(org_id);
CREATE INDEX IF NOT EXISTS idx_sim_scenarios_template ON simulator_scenarios(is_template);

-- Insert schema version
INSERT INTO schema_version (version, name, applied_at)
VALUES (7, '007_simulator', datetime('now'));
