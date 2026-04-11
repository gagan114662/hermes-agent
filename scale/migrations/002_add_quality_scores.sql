-- Migration 002: Add quality scoring columns to worker_actions
-- Run: docker compose -f scale/docker-compose.scale.yml exec postgres \
--   psql -U hermes -d hermes -f /path/to/002_add_quality_scores.sql

ALTER TABLE worker_actions
    ADD COLUMN IF NOT EXISTS quality_score INTEGER,      -- 0-100
    ADD COLUMN IF NOT EXISTS task_type TEXT,             -- 'lead_research' | 'content' | 'outreach' | 'research' | 'ops' | 'other'
    ADD COLUMN IF NOT EXISTS grader_reasoning TEXT;      -- JSON: dimension scores + best_thing + biggest_gap + beat_this_next_time

-- Index for fetching historical scores by task type (hill-climbing queries)
CREATE INDEX IF NOT EXISTS idx_worker_actions_type_score
    ON worker_actions(tenant_id, task_type, created_at DESC);
