-- AgentCost Migration 006: User Feedback on Traces
-- Stores thumbs-up/down and comments linked to trace_events.

CREATE TABLE IF NOT EXISTS trace_feedback (
    id              TEXT PRIMARY KEY,
    trace_id        TEXT NOT NULL,
    score           INTEGER NOT NULL,
    comment         TEXT DEFAULT '',
    source          TEXT DEFAULT 'user',
    user_id         TEXT DEFAULT '',
    tags            JSONB DEFAULT '[]',
    metadata        JSONB DEFAULT '{}',
    org_id          TEXT NOT NULL DEFAULT 'default',
    created_at      DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fb_trace ON trace_feedback(trace_id);
CREATE INDEX IF NOT EXISTS idx_fb_org ON trace_feedback(org_id);
CREATE INDEX IF NOT EXISTS idx_fb_created ON trace_feedback(created_at);
CREATE INDEX IF NOT EXISTS idx_fb_score ON trace_feedback(score);

INSERT INTO schema_version (version, description)
VALUES (6, 'User feedback on traces: thumbs up/down, comments, quality analytics')
ON CONFLICT (version) DO NOTHING;
