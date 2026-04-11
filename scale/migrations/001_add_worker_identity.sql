-- Migration 001: Add worker identity columns and worker_actions table
-- Run: docker compose -f scale/docker-compose.scale.yml exec postgres \
--   psql -U hermes -d hermes -f /path/to/001_add_worker_identity.sql

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS tenant_config JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS worker_email TEXT;

CREATE TABLE IF NOT EXISTS worker_actions (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    full_output TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_worker_actions_tenant
    ON worker_actions(tenant_id, created_at DESC);
