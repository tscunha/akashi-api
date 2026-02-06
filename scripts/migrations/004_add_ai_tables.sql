-- Migration: 004_add_ai_tables.sql
-- Description: Add tables for AI processing (transcription, faces, scene descriptions)
-- Date: 2026-02-06

-- =====================================================
-- TRANSCRIPTIONS
-- =====================================================

CREATE TABLE IF NOT EXISTS asset_transcriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    -- Language
    language VARCHAR(10) NOT NULL DEFAULT 'pt',

    -- Content
    full_text TEXT,
    segments JSONB DEFAULT '[]',  -- [{start_ms, end_ms, text, confidence}]

    -- Generated subtitles
    srt_content TEXT,
    vtt_content TEXT,

    -- Metadata
    duration_ms BIGINT,
    word_count INTEGER,
    confidence_avg NUMERIC(4,3),

    -- Processing info
    model_version VARCHAR(50),
    processing_time_ms INTEGER,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_transcriptions_asset_id ON asset_transcriptions(asset_id);
CREATE INDEX idx_transcriptions_tenant_id ON asset_transcriptions(tenant_id);
CREATE INDEX idx_transcriptions_language ON asset_transcriptions(language);

-- Full-text search on transcriptions
ALTER TABLE asset_transcriptions ADD COLUMN search_vector TSVECTOR;

CREATE OR REPLACE FUNCTION update_transcription_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := to_tsvector('portuguese', COALESCE(NEW.full_text, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_transcription_search_vector
    BEFORE INSERT OR UPDATE ON asset_transcriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_transcription_search_vector();

CREATE INDEX idx_transcriptions_search_vector ON asset_transcriptions USING GIN(search_vector);

-- =====================================================
-- PERSONS (Known people for face recognition)
-- =====================================================

CREATE TABLE IF NOT EXISTS persons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    -- Identity
    name VARCHAR(255) NOT NULL,
    role VARCHAR(100),  -- actor, presenter, interviewer, etc
    external_id VARCHAR(255),  -- IMDB, LinkedIn, etc

    -- Reference embedding (average of known embeddings)
    reference_embedding vector(512),

    -- Metadata
    metadata JSONB DEFAULT '{}',
    thumbnail_url TEXT,

    -- Stats
    appearance_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_persons_tenant_id ON persons(tenant_id);
CREATE INDEX idx_persons_name ON persons(name);
CREATE INDEX idx_persons_embedding ON persons USING ivfflat (reference_embedding vector_cosine_ops) WITH (lists = 100);

-- =====================================================
-- ASSET FACES (Detected faces in assets)
-- =====================================================

CREATE TABLE IF NOT EXISTS asset_faces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    -- Identity (if known)
    person_id UUID REFERENCES persons(id) ON DELETE SET NULL,

    -- Temporal location
    timecode_ms BIGINT NOT NULL,
    duration_ms BIGINT,  -- how long this face appears

    -- Bounding box (normalized 0-1)
    bbox_x NUMERIC(5,4),
    bbox_y NUMERIC(5,4),
    bbox_w NUMERIC(5,4),
    bbox_h NUMERIC(5,4),

    -- Face embedding for similarity search
    face_embedding vector(512),

    -- Thumbnail of the face
    thumbnail_url TEXT,

    -- Confidence
    confidence NUMERIC(4,3),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_faces_asset_id ON asset_faces(asset_id);
CREATE INDEX idx_faces_tenant_id ON asset_faces(tenant_id);
CREATE INDEX idx_faces_person_id ON asset_faces(person_id);
CREATE INDEX idx_faces_timecode ON asset_faces(timecode_ms);
CREATE INDEX idx_faces_embedding ON asset_faces USING ivfflat (face_embedding vector_cosine_ops) WITH (lists = 100);

-- =====================================================
-- SCENE DESCRIPTIONS (AI-generated descriptions)
-- =====================================================

CREATE TABLE IF NOT EXISTS asset_scene_descriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    -- Timing
    timecode_start_ms BIGINT NOT NULL,
    timecode_end_ms BIGINT NOT NULL,

    -- Description
    description TEXT NOT NULL,
    description_embedding vector(1536),  -- text-embedding-ada-002 or similar

    -- Detections
    objects JSONB DEFAULT '[]',   -- [{object, confidence, bbox}]
    actions JSONB DEFAULT '[]',   -- [{action, confidence}]
    emotions JSONB DEFAULT '[]',  -- [{emotion, confidence}]
    text_ocr TEXT,                -- detected text on screen

    -- Model info
    model_version VARCHAR(100),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_scenes_asset_id ON asset_scene_descriptions(asset_id);
CREATE INDEX idx_scenes_tenant_id ON asset_scene_descriptions(tenant_id);
CREATE INDEX idx_scenes_timecode ON asset_scene_descriptions(timecode_start_ms);
CREATE INDEX idx_scenes_embedding ON asset_scene_descriptions USING ivfflat (description_embedding vector_cosine_ops) WITH (lists = 100);

-- Full-text search on descriptions
ALTER TABLE asset_scene_descriptions ADD COLUMN search_vector TSVECTOR;

CREATE OR REPLACE FUNCTION update_scene_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := to_tsvector('portuguese', COALESCE(NEW.description, '') || ' ' || COALESCE(NEW.text_ocr, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_scene_search_vector
    BEFORE INSERT OR UPDATE ON asset_scene_descriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_scene_search_vector();

CREATE INDEX idx_scenes_search_vector ON asset_scene_descriptions USING GIN(search_vector);

-- =====================================================
-- AI EXTRACTED KEYWORDS (from transcription/vision)
-- =====================================================

CREATE TABLE IF NOT EXISTS ai_extracted_keywords (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    keyword VARCHAR(255) NOT NULL,
    keyword_normalized VARCHAR(255) NOT NULL,
    category VARCHAR(100),  -- topic, entity, action, emotion, object
    confidence NUMERIC(4,3),
    source VARCHAR(50) DEFAULT 'ai',  -- whisper, vision, llm

    -- Temporal context (optional)
    start_ms BIGINT,
    end_ms BIGINT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    UNIQUE(asset_id, keyword_normalized, source)
);

CREATE INDEX idx_ai_keywords_asset_id ON ai_extracted_keywords(asset_id);
CREATE INDEX idx_ai_keywords_tenant_id ON ai_extracted_keywords(tenant_id);
CREATE INDEX idx_ai_keywords_normalized ON ai_extracted_keywords(keyword_normalized);
CREATE INDEX idx_ai_keywords_category ON ai_extracted_keywords(category);

-- =====================================================
-- WORKFLOWS (React Flow based)
-- =====================================================

CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- React Flow data
    nodes JSONB NOT NULL DEFAULT '[]',
    edges JSONB NOT NULL DEFAULT '[]',
    viewport JSONB DEFAULT '{"x": 0, "y": 0, "zoom": 1}',

    -- Configuration
    is_active BOOLEAN DEFAULT TRUE,
    trigger_type VARCHAR(50),  -- upload, schedule, webhook, manual
    trigger_config JSONB DEFAULT '{}',

    -- Stats
    run_count INTEGER DEFAULT 0,
    last_run_at TIMESTAMP WITH TIME ZONE,
    avg_duration_ms INTEGER,

    -- Ownership
    created_by UUID REFERENCES users(id),
    updated_by UUID REFERENCES users(id),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_workflows_tenant_id ON workflows(tenant_id);
CREATE INDEX idx_workflows_is_active ON workflows(is_active);
CREATE INDEX idx_workflows_trigger_type ON workflows(trigger_type);

-- =====================================================
-- WORKFLOW RUNS (Execution history)
-- =====================================================

CREATE TABLE IF NOT EXISTS workflow_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    -- Context
    trigger_data JSONB DEFAULT '{}',
    asset_id UUID,  -- related asset if any

    -- Status
    status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed, cancelled
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Progress
    current_node_id VARCHAR(100),
    nodes_completed JSONB DEFAULT '[]',  -- [{node_id, status, output, duration_ms, completed_at}]

    -- Error info
    error_message TEXT,
    error_node_id VARCHAR(100),
    error_details JSONB,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_workflow_runs_workflow_id ON workflow_runs(workflow_id);
CREATE INDEX idx_workflow_runs_tenant_id ON workflow_runs(tenant_id);
CREATE INDEX idx_workflow_runs_asset_id ON workflow_runs(asset_id);
CREATE INDEX idx_workflow_runs_status ON workflow_runs(status);
CREATE INDEX idx_workflow_runs_created_at ON workflow_runs(created_at DESC);

-- =====================================================
-- API KEYS (for MCP and external integrations)
-- =====================================================

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    user_id UUID NOT NULL REFERENCES users(id),

    name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(255) NOT NULL,  -- SHA-256 hash
    key_prefix VARCHAR(10) NOT NULL,  -- ak_xxxx for identification

    scopes TEXT[] DEFAULT ARRAY['read'],  -- read, write, admin

    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_api_keys_tenant_id ON api_keys(tenant_id);
CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_is_active ON api_keys(is_active);

-- =====================================================
-- Update assets table with AI processing status
-- =====================================================

ALTER TABLE assets ADD COLUMN IF NOT EXISTS transcription_status VARCHAR(50) DEFAULT 'pending';
ALTER TABLE assets ADD COLUMN IF NOT EXISTS face_detection_status VARCHAR(50) DEFAULT 'pending';
ALTER TABLE assets ADD COLUMN IF NOT EXISTS scene_description_status VARCHAR(50) DEFAULT 'pending';

-- =====================================================
-- DONE
-- =====================================================
