-- Recreate runs table with complete Phase-1 columns
CREATE TABLE runs (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id UUID REFERENCES prompt_templates(template_id),
    batch_id UUID,
    batch_run_index INTEGER,
    run_sha256 VARCHAR(64) NOT NULL,
    
    -- Core execution fields
    vendor TEXT,
    model TEXT,
    grounded_requested BOOLEAN NOT NULL DEFAULT FALSE,
    grounded_effective BOOLEAN NOT NULL DEFAULT FALSE,
    json_mode BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Request/Response tracking
    request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_text TEXT NOT NULL DEFAULT '',
    response_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_output_sha256 VARCHAR(64),
    output_json_valid BOOLEAN,
    
    -- Performance metrics
    latency_ms INTEGER NOT NULL DEFAULT 0,
    tokens_input INTEGER NOT NULL DEFAULT 0,
    tokens_output INTEGER NOT NULL DEFAULT 0,
    tokens_reasoning INTEGER NOT NULL DEFAULT 0,
    usage JSONB,
    
    -- Status tracking
    status TEXT NOT NULL DEFAULT 'succeeded',
    error_message TEXT,
    why_not_grounded TEXT,
    
    -- Model versioning
    model_version_effective VARCHAR(100),
    model_fingerprint VARCHAR(255),
    
    -- Locale/ALS fields
    locale_selected VARCHAR(10),
    grounding_mode VARCHAR(20),
    als_block_sha256 VARCHAR(64),
    als_block_text TEXT,
    als_variant_id VARCHAR(100),
    seed_key_id VARCHAR(20),
    provoker_value VARCHAR(100),
    
    -- Gemini two-step attestation
    step2_tools_invoked BOOLEAN,
    step2_source_ref VARCHAR(64),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes
CREATE INDEX idx_template_runs ON runs(template_id, created_at DESC);
CREATE INDEX idx_runs_model_created ON runs(model, created_at DESC);
CREATE INDEX idx_runs_vendor_created ON runs(vendor, created_at DESC);
CREATE INDEX idx_output_hash ON runs(response_output_sha256);
CREATE INDEX idx_batch_runs ON runs(batch_id, batch_run_index);