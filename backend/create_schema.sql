-- AI Ranker V2 - Prompter Schema
-- Phase-1: Core tables only (no legacy features)

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Drop existing tables (for clean setup)
DROP TABLE IF EXISTS runs CASCADE;
DROP TABLE IF EXISTS batches CASCADE;
DROP TABLE IF EXISTS prompt_templates CASCADE;
DROP TABLE IF EXISTS countries CASCADE;
DROP TABLE IF EXISTS provider_version_cache CASCADE;
DROP TABLE IF EXISTS idempotency_keys CASCADE;

-- Templates table with immutability
CREATE TABLE prompt_templates (
    template_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_name VARCHAR(255) NOT NULL,
    template_sha256 VARCHAR(64) NOT NULL,
    canonical_json JSONB NOT NULL,
    org_id VARCHAR(255) NOT NULL DEFAULT 'default',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    record_hmac VARCHAR(64),
    UNIQUE(org_id, template_sha256)
);

-- Runs table with full provenance
CREATE TABLE runs (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id UUID REFERENCES prompt_templates(template_id),
    batch_id UUID,
    batch_run_index INTEGER,
    run_sha256 VARCHAR(64) NOT NULL,
    locale_selected VARCHAR(10),
    grounding_mode VARCHAR(20),
    grounded_effective BOOLEAN,
    model_version_effective VARCHAR(100),
    model_fingerprint VARCHAR(255),
    output TEXT,
    response_output_sha256 VARCHAR(64),
    output_json_valid BOOLEAN,
    als_block_sha256 VARCHAR(64),
    als_block_text TEXT,
    als_variant_id VARCHAR(100),
    seed_key_id VARCHAR(20),
    provoker_value VARCHAR(100),
    usage JSONB,
    latency_ms INTEGER,
    why_not_grounded TEXT,
    step2_tools_invoked BOOLEAN,
    step2_source_ref VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Batches table
CREATE TABLE batches (
    batch_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id UUID REFERENCES prompt_templates(template_id),
    batch_sha256 VARCHAR(64),
    preflight_model_version VARCHAR(100),
    preflight_model_fingerprint VARCHAR(255),
    parameters JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    created_by VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Countries for ALS
CREATE TABLE countries (
    id SERIAL PRIMARY KEY,
    code VARCHAR(2) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    emoji VARCHAR(10),
    vat_rate DECIMAL(5,2),
    plug_types VARCHAR(50),
    emergency_numbers VARCHAR(50),
    locale_code VARCHAR(10),
    is_active BOOLEAN DEFAULT true
);

-- Provider version cache with TTL
CREATE TABLE provider_version_cache (
    provider VARCHAR(50) PRIMARY KEY,
    versions JSONB,
    current VARCHAR(100),
    last_checked_utc TIMESTAMP WITH TIME ZONE,
    expires_at_utc TIMESTAMP WITH TIME ZONE,
    etag VARCHAR(100),
    source VARCHAR(20)
);

-- Idempotency keys
CREATE TABLE idempotency_keys (
    key VARCHAR(100) NOT NULL,
    org_id VARCHAR(255) NOT NULL,
    body_sha256 VARCHAR(64) NOT NULL,
    result JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (org_id, key)
);

-- Indexes
CREATE INDEX idx_template_runs ON runs(template_id, created_at DESC);
CREATE INDEX idx_output_hash ON runs(response_output_sha256);
CREATE INDEX idx_batch_status ON batches(status, created_at DESC);
CREATE INDEX idx_batch_runs ON runs(batch_id, batch_run_index);
CREATE INDEX idx_idempotency_expires ON idempotency_keys(expires_at);

-- Insert countries
INSERT INTO countries (code, name, emoji, vat_rate, plug_types, emergency_numbers, locale_code) VALUES
('US', 'United States', '🇺🇸', 0, 'A,B', '911', 'en-US'),
('GB', 'United Kingdom', '🇬🇧', 20, 'G', '999,112', 'en-GB'),
('DE', 'Germany', '🇩🇪', 19, 'F,C', '112,110', 'de-DE'),
('CH', 'Switzerland', '🇨🇭', 8.1, 'J,C', '112,117,118', 'de-CH'),
('FR', 'France', '🇫🇷', 20, 'E,F,C', '112,15,17,18', 'fr-FR'),
('IT', 'Italy', '🇮🇹', 22, 'L,F,C', '112,113,115,118', 'it-IT'),
('AE', 'UAE', '🇦🇪', 5, 'G,C,D', '999,997,998', 'ar-AE'),
('SG', 'Singapore', '🇸🇬', 9, 'G', '999,995', 'en-SG')
ON CONFLICT (code) DO NOTHING;
