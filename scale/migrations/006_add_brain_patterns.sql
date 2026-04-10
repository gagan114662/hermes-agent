-- Migration 006: Add last_dream_at column and stale-page index to brain_pages
-- Supports the nightly dream cycle in scale/dream.py
--
-- Run:
--   docker compose -f scale/docker-compose.scale.yml exec postgres \
--     psql -U hermes -d hermes -f /path/to/006_add_brain_patterns.sql

ALTER TABLE brain_pages
    ADD COLUMN IF NOT EXISTS last_dream_at TIMESTAMPTZ;

-- Index for dream cycle: find stale pages efficiently (oldest-updated first)
CREATE INDEX IF NOT EXISTS brain_pages_stale_idx
    ON brain_pages(tenant_id, updated_at ASC)
    WHERE page_type = 'memory';
