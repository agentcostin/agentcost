-- AgentCost Migration 003: Seed default organization
-- Ensures the 'default' org exists for auto-provisioning on first login.
-- This runs idempotently — safe to run multiple times.

INSERT INTO orgs (id, name, slug, plan, created_at, updated_at)
VALUES ('default', 'Default', 'default', 'free', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

-- Record this migration
INSERT INTO schema_version (version, description)
VALUES (3, 'Seed default organization for auto-provisioning')
ON CONFLICT (version) DO NOTHING;