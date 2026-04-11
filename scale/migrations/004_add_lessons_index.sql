-- Migration 004: Add partial index on tenant_memory for fast lesson lookups
-- Lessons are permanent lints written when quality_score < 60.
-- This index makes the "LIKE 'lesson_%'" query in _run_autonomous_decision fast
-- even when tenant_memory grows to thousands of rows.
--
-- Run: docker compose -f scale/docker-compose.scale.yml exec postgres \
--   psql -U hermes -d hermes -f /path/to/004_add_lessons_index.sql

CREATE INDEX IF NOT EXISTS idx_worker_memory_lessons
    ON tenant_memory(tenant_id, memory_type)
    WHERE memory_type LIKE 'lesson_%';
