-- Hermes Scale Architecture — PostgreSQL Schema
-- Run: psql -U hermes -d hermes -f schema.sql

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Tenants = customers (restaurants, businesses)
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    active BOOLEAN DEFAULT true,

    -- LLM config
    model TEXT DEFAULT 'openrouter/google/gemini-2.5-flash-preview',
    api_key_encrypted TEXT,
    max_turns INT DEFAULT 90,
    temperature FLOAT DEFAULT 0.7,

    -- Rate limiting
    rate_limit_per_minute INT DEFAULT 20,
    rate_limit_burst INT DEFAULT 5,

    -- Per-tenant AI config
    system_prompt_template TEXT,
    enabled_toolsets TEXT[] DEFAULT ARRAY['web', 'search', 'image_gen', 'booking']
);

-- Platform connections per tenant
CREATE TABLE tenant_platforms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    bot_token TEXT NOT NULL,
    webhook_url TEXT,
    config JSONB DEFAULT '{}',
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(tenant_id, platform)
);

-- Sessions = conversations
CREATE TABLE sessions (
    session_key TEXT PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    session_id TEXT UNIQUE NOT NULL,
    platform TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    user_id TEXT,
    chat_type TEXT DEFAULT 'dm',
    chat_name TEXT,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    system_prompt TEXT,
    conversation_history JSONB DEFAULT '[]',

    total_tokens INT DEFAULT 0,
    last_prompt_tokens INT DEFAULT 0,
    last_completion_tokens INT DEFAULT 0,

    reset_mode TEXT DEFAULT 'both',
    reset_at_hour INT DEFAULT 4,
    reset_idle_minutes INT DEFAULT 1440
);

-- Memory = per-tenant knowledge base
CREATE TABLE tenant_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(tenant_id, memory_type)
);

-- Message log (billing + debugging)
CREATE TABLE message_log (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    session_key TEXT,
    direction TEXT NOT NULL,
    platform TEXT,
    user_id TEXT,
    message_text TEXT,
    response_text TEXT,
    input_tokens INT,
    output_tokens INT,
    cost_usd FLOAT,
    duration_ms INT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_sessions_tenant ON sessions(tenant_id);
CREATE INDEX idx_sessions_updated ON sessions(updated_at);
CREATE INDEX idx_message_log_tenant ON message_log(tenant_id, created_at);
CREATE INDEX idx_tenant_platforms_token ON tenant_platforms(bot_token);
CREATE INDEX idx_tenant_memory_tenant ON tenant_memory(tenant_id);
