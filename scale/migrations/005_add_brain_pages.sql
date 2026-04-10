-- Migration 005: Add brain_pages table for gbrain-style hybrid memory
-- Requires: postgres with pgvector extension installed
--   (e.g. pgvector/pgvector:pg16 Docker image)
--
-- Run: docker compose -f scale/docker-compose.scale.yml exec postgres \
--   psql -U hermes -d hermes -f /path/to/005_add_brain_pages.sql

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Brain pages: compiled_truth + timeline pattern (gbrain architecture)
CREATE TABLE IF NOT EXISTS brain_pages (
    id             BIGSERIAL PRIMARY KEY,
    tenant_id      UUID REFERENCES tenants(id) ON DELETE CASCADE,
    slug           TEXT NOT NULL,               -- e.g. "lead_research/b2b_saas"
    page_type      TEXT NOT NULL DEFAULT 'memory', -- memory | lesson | brief | skill
    compiled_truth TEXT,                         -- current best understanding, rewritten on synthesis
    timeline       TEXT,                         -- append-only evidence trail, never edited
    embedding      vector(384),                 -- sentence-transformers all-MiniLM-L6-v2 (local, free)
    search_vector  tsvector GENERATED ALWAYS AS (
        to_tsvector('english',
            coalesce(compiled_truth, '') || ' ' || coalesce(timeline, ''))
    ) STORED,
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ DEFAULT now(),
    UNIQUE(tenant_id, slug)
);

-- HNSW index for fast approximate nearest-neighbour vector search
CREATE INDEX IF NOT EXISTS brain_pages_embedding_idx
    ON brain_pages USING hnsw (embedding vector_cosine_ops);

-- GIN index for full-text keyword search
CREATE INDEX IF NOT EXISTS brain_pages_search_idx
    ON brain_pages USING gin(search_vector);

-- Covering index for tenant + page_type scans
CREATE INDEX IF NOT EXISTS brain_pages_tenant_type_idx
    ON brain_pages(tenant_id, page_type);
