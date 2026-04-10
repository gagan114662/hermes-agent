-- Migration 003: Convert grader_reasoning from TEXT to JSONB
-- Enables querying individual dimension scores directly in SQL, e.g.:
--   SELECT quality_score, grader_reasoning->>'biggest_gap' FROM worker_actions WHERE ...
--   SELECT AVG((grader_reasoning->>'quantity_score')::int) FROM worker_actions WHERE task_type = 'lead_research'
--
-- Run when ready (non-destructive — existing text values cast automatically):
--   docker compose -f scale/docker-compose.scale.yml exec postgres \
--     psql -U hermes -d hermes -f /path/to/003_grader_reasoning_jsonb.sql

ALTER TABLE worker_actions
    ALTER COLUMN grader_reasoning TYPE JSONB
    USING grader_reasoning::JSONB;
