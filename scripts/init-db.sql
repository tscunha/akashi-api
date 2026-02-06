-- ============================================================================
-- AKASHI MAM - Database Initialization Script
-- This script runs automatically when PostgreSQL container starts
-- ============================================================================

-- ============================================================================
-- PART 1: Module 1 Core Foundation (from akashi-mam)
-- ============================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";  -- pgvector for embeddings

-- ============================================================================
-- TABLE: tenants
-- ============================================================================

CREATE TABLE tenants (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code                    VARCHAR(50) NOT NULL UNIQUE,
    name                    VARCHAR(255) NOT NULL,
    type                    VARCHAR(50) NOT NULL
                            CHECK (type IN ('broadcaster', 'production', 'agency', 'archive')),

    settings                JSONB DEFAULT '{}',
    metadata_schema         JSONB DEFAULT '{}',

    is_active               BOOLEAN DEFAULT true,
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- TABLE: taxonomies
-- ============================================================================

CREATE TABLE taxonomies (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL REFERENCES tenants(id),

    code                    VARCHAR(100) NOT NULL,
    name                    VARCHAR(255) NOT NULL,
    type                    VARCHAR(50) NOT NULL
                            CHECK (type IN ('editorial', 'genre', 'location', 'theme', 'custom')),

    description             TEXT,
    is_hierarchical         BOOLEAN DEFAULT true,
    is_active               BOOLEAN DEFAULT true,

    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE (tenant_id, code)
);

-- ============================================================================
-- TABLE: taxonomy_terms
-- ============================================================================

CREATE TABLE taxonomy_terms (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    taxonomy_id             UUID NOT NULL REFERENCES taxonomies(id) ON DELETE CASCADE,
    tenant_id               UUID NOT NULL REFERENCES tenants(id),
    parent_id               UUID REFERENCES taxonomy_terms(id),

    term                    VARCHAR(255) NOT NULL,
    slug                    VARCHAR(255),
    description             TEXT,

    external_mappings       JSONB DEFAULT '{}',

    sort_order              INTEGER DEFAULT 0,
    level                   INTEGER DEFAULT 0,
    path                    TEXT,

    is_active               BOOLEAN DEFAULT true,

    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE (taxonomy_id, slug)
);

CREATE INDEX idx_taxonomy_terms_taxonomy ON taxonomy_terms(taxonomy_id);
CREATE INDEX idx_taxonomy_terms_parent ON taxonomy_terms(parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX idx_taxonomy_terms_path ON taxonomy_terms(tenant_id, path);

-- ============================================================================
-- TABLE: assets (PARTITIONED)
-- ============================================================================

CREATE TABLE assets (
    id                      UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL REFERENCES tenants(id),
    parent_id               UUID,

    code                    VARCHAR(100),
    external_ids            JSONB DEFAULT '{}',

    asset_type              VARCHAR(50) NOT NULL
                            CHECK (asset_type IN ('video', 'audio', 'image', 'document', 'sequence')),
    derivative_type         VARCHAR(50)
                            CHECK (derivative_type IN ('proxy', 'thumbnail', 'clip', 'export', 'transcode')),

    title                   VARCHAR(500) NOT NULL,
    description             TEXT,
    slug                    VARCHAR(255),

    duration_ms             BIGINT,
    recorded_at             TIMESTAMP WITH TIME ZONE,

    primary_category_id     UUID,
    content_rating          VARCHAR(10)
                            CHECK (content_rating IN ('L', '10', '12', '14', '16', '18')),

    status                  VARCHAR(50) DEFAULT 'ingesting'
                            CHECK (status IN ('ingesting', 'processing', 'available', 'review', 'archived', 'deleted')),
    visibility              VARCHAR(50) DEFAULT 'internal'
                            CHECK (visibility IN ('private', 'internal', 'public')),
    publish_status          VARCHAR(50) DEFAULT 'draft'
                            CHECK (publish_status IN ('draft', 'ready', 'published', 'unpublished')),

    primary_storage_path    VARCHAR(1000),
    file_size_bytes         BIGINT,
    checksum_sha256         VARCHAR(64),

    extra                   JSONB DEFAULT '{}',

    created_by              UUID,
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at              TIMESTAMP WITH TIME ZONE,
    deleted_by              UUID,

    partition_date          DATE DEFAULT CURRENT_DATE,

    PRIMARY KEY (id, partition_date)
) PARTITION BY RANGE (partition_date);

-- Partitions
CREATE TABLE assets_2024_h1 PARTITION OF assets FOR VALUES FROM ('2024-01-01') TO ('2024-07-01');
CREATE TABLE assets_2024_h2 PARTITION OF assets FOR VALUES FROM ('2024-07-01') TO ('2025-01-01');
CREATE TABLE assets_2025_h1 PARTITION OF assets FOR VALUES FROM ('2025-01-01') TO ('2025-07-01');
CREATE TABLE assets_2025_h2 PARTITION OF assets FOR VALUES FROM ('2025-07-01') TO ('2026-01-01');
CREATE TABLE assets_2026_h1 PARTITION OF assets FOR VALUES FROM ('2026-01-01') TO ('2026-07-01');
CREATE TABLE assets_2026_h2 PARTITION OF assets FOR VALUES FROM ('2026-07-01') TO ('2027-01-01');

-- Indexes on assets
CREATE INDEX idx_assets_tenant_status ON assets(tenant_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_assets_tenant_type ON assets(tenant_id, asset_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_assets_parent ON assets(parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX idx_assets_created ON assets(tenant_id, created_at DESC);
CREATE INDEX idx_assets_title_trgm ON assets USING gin (title gin_trgm_ops);
CREATE INDEX idx_assets_category ON assets(tenant_id, primary_category_id) WHERE primary_category_id IS NOT NULL;

-- ============================================================================
-- TABLE: asset_technical_metadata
-- ============================================================================

CREATE TABLE asset_technical_metadata (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id                UUID NOT NULL UNIQUE,
    tenant_id               UUID NOT NULL REFERENCES tenants(id),

    width                   INTEGER,
    height                  INTEGER,
    frame_rate              DECIMAL(10,6),
    frame_rate_num          INTEGER,
    frame_rate_den          INTEGER,
    scan_type               VARCHAR(20),
    aspect_ratio            VARCHAR(20),
    pixel_aspect_ratio      VARCHAR(20),
    color_space             VARCHAR(50),
    bit_depth               INTEGER,
    hdr_format              VARCHAR(50),

    video_codec             VARCHAR(100),
    video_codec_profile     VARCHAR(100),
    video_bitrate_bps       BIGINT,

    audio_codec             VARCHAR(100),
    audio_sample_rate       INTEGER,
    audio_bit_depth         INTEGER,
    audio_channels          INTEGER,
    audio_channel_layout    VARCHAR(100),
    audio_bitrate_bps       BIGINT,
    loudness_integrated     DECIMAL(5,2),
    loudness_range          DECIMAL(5,2),
    loudness_peak           DECIMAL(5,2),

    container_format        VARCHAR(50),

    start_timecode          VARCHAR(20),
    start_timecode_frames   BIGINT,
    drop_frame              BOOLEAN DEFAULT false,

    image_format            VARCHAR(50),
    dpi                     INTEGER,

    page_count              INTEGER,

    resolution_category     VARCHAR(20),

    mediainfo_raw           JSONB DEFAULT '{}',
    ffprobe_raw             JSONB DEFAULT '{}',

    analyzed_at             TIMESTAMP WITH TIME ZONE,
    analyzer_version        VARCHAR(50),

    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_tech_meta_asset ON asset_technical_metadata(asset_id);
CREATE INDEX idx_tech_meta_resolution ON asset_technical_metadata(tenant_id, width, height);
CREATE INDEX idx_tech_meta_category ON asset_technical_metadata(tenant_id, resolution_category);
CREATE INDEX idx_tech_meta_codec ON asset_technical_metadata(tenant_id, video_codec);

-- ============================================================================
-- TABLE: asset_storage_locations
-- ============================================================================

CREATE TABLE asset_storage_locations (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id                UUID NOT NULL,
    tenant_id               UUID NOT NULL REFERENCES tenants(id),

    storage_type            VARCHAR(50) NOT NULL
                            CHECK (storage_type IN ('s3', 'lto', 'glacier', 'local', 'external_url')),
    storage_tier            VARCHAR(50)
                            CHECK (storage_tier IN ('hot', 'warm', 'cold', 'archive')),
    bucket                  VARCHAR(255),
    path                    VARCHAR(2000),
    filename                VARCHAR(500),
    url                     VARCHAR(2000),

    checksum_md5            VARCHAR(32),
    checksum_sha256         VARCHAR(64),
    file_size_bytes         BIGINT,
    verified_at             TIMESTAMP WITH TIME ZONE,
    verification_status     VARCHAR(50) DEFAULT 'pending'
                            CHECK (verification_status IN ('ok', 'mismatch', 'missing', 'pending')),

    is_primary              BOOLEAN DEFAULT false,
    is_accessible           BOOLEAN DEFAULT true,
    status                  VARCHAR(50) DEFAULT 'available'
                            CHECK (status IN ('available', 'migrating', 'restoring', 'error')),

    lto_tape_id             VARCHAR(50),
    lto_position            VARCHAR(100),

    purpose                 VARCHAR(50) DEFAULT 'original'
                            CHECK (purpose IN ('original', 'proxy', 'thumbnail', 'sprite', 'hls', 'dash')),

    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    migrated_at             TIMESTAMP WITH TIME ZONE,
    expires_at              TIMESTAMP WITH TIME ZONE,

    extra                   JSONB DEFAULT '{}'
);

CREATE INDEX idx_storage_asset ON asset_storage_locations(asset_id);
CREATE INDEX idx_storage_primary ON asset_storage_locations(asset_id) WHERE is_primary = true;
CREATE INDEX idx_storage_tier ON asset_storage_locations(tenant_id, storage_tier);
CREATE INDEX idx_storage_purpose ON asset_storage_locations(asset_id, purpose);

-- ============================================================================
-- TABLE: asset_production_metadata
-- ============================================================================

CREATE TABLE asset_production_metadata (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id                UUID NOT NULL UNIQUE,
    tenant_id               UUID NOT NULL REFERENCES tenants(id),

    reel                    VARCHAR(100),
    scene                   VARCHAR(100),
    shot                    VARCHAR(100),
    take                    VARCHAR(100),
    camera_name             VARCHAR(100),
    camera_angle            VARCHAR(100),

    log_note                TEXT,
    is_good_take            BOOLEAN,
    rating                  SMALLINT CHECK (rating >= 1 AND rating <= 5),

    start_timecode          VARCHAR(20),
    start_timecode_ms       BIGINT,

    video_role              VARCHAR(100),
    audio_role              VARCHAR(100),

    xmp_data                JSONB DEFAULT '{}',
    fcpxml_data             JSONB DEFAULT '{}',
    resolve_data            JSONB DEFAULT '{}',

    custom_fields           JSONB DEFAULT '{}',

    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_prod_meta_asset ON asset_production_metadata(asset_id);

-- ============================================================================
-- TABLE: asset_keywords
-- ============================================================================

CREATE TABLE asset_keywords (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id                UUID NOT NULL,
    tenant_id               UUID NOT NULL REFERENCES tenants(id),

    keyword                 VARCHAR(255) NOT NULL,
    keyword_normalized      VARCHAR(255),

    start_ms                INTEGER,
    end_ms                  INTEGER,

    note                    TEXT,

    source                  VARCHAR(50) DEFAULT 'manual'
                            CHECK (source IN ('manual', 'fcpx', 'resolve', 'premiere', 'ai', 'import')),
    confidence              DECIMAL(3,2),

    created_by              UUID,
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE (asset_id, keyword, start_ms)
);

CREATE INDEX idx_keywords_asset ON asset_keywords(asset_id);
CREATE INDEX idx_keywords_search ON asset_keywords(tenant_id, keyword_normalized);
CREATE INDEX idx_keywords_trgm ON asset_keywords USING gin (keyword gin_trgm_ops);

-- ============================================================================
-- TABLE: asset_markers
-- ============================================================================

CREATE TABLE asset_markers (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id                UUID NOT NULL,
    tenant_id               UUID NOT NULL REFERENCES tenants(id),

    marker_type             VARCHAR(50) DEFAULT 'comment'
                            CHECK (marker_type IN ('comment', 'chapter', 'todo', 'vfx', 'audio', 'approval', 'cut_point')),
    name                    VARCHAR(255),
    color                   VARCHAR(20),

    start_ms                INTEGER NOT NULL,
    duration_ms             INTEGER DEFAULT 0,

    note                    TEXT,
    keywords                TEXT[],

    source                  VARCHAR(50) DEFAULT 'manual',
    source_system_id        VARCHAR(255),

    created_by              UUID,
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    extra                   JSONB DEFAULT '{}'
);

CREATE INDEX idx_markers_asset ON asset_markers(asset_id);
CREATE INDEX idx_markers_temporal ON asset_markers(asset_id, start_ms);

-- ============================================================================
-- TABLE: asset_relationships
-- ============================================================================

CREATE TABLE asset_relationships (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL REFERENCES tenants(id),

    source_asset_id         UUID NOT NULL,
    target_asset_id         UUID NOT NULL,

    relationship_type       VARCHAR(50) NOT NULL
                            CHECK (relationship_type IN (
                                'derived_from', 'references', 'same_event', 'same_series',
                                'same_project', 'related', 'version_of', 'translation_of'
                            )),

    metadata                JSONB DEFAULT '{}',
    confidence              DECIMAL(3,2),

    created_by              UUID,
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE (source_asset_id, target_asset_id, relationship_type)
);

CREATE INDEX idx_relationships_source ON asset_relationships(source_asset_id);
CREATE INDEX idx_relationships_target ON asset_relationships(target_asset_id);

-- ============================================================================
-- TABLE: asset_taxonomy_assignments
-- ============================================================================

CREATE TABLE asset_taxonomy_assignments (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id                UUID NOT NULL,
    taxonomy_term_id        UUID NOT NULL REFERENCES taxonomy_terms(id) ON DELETE CASCADE,
    tenant_id               UUID NOT NULL REFERENCES tenants(id),

    is_primary              BOOLEAN DEFAULT false,
    confidence              DECIMAL(3,2),

    created_by              UUID,
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE (asset_id, taxonomy_term_id)
);

CREATE INDEX idx_asset_taxonomy_asset ON asset_taxonomy_assignments(asset_id);
CREATE INDEX idx_asset_taxonomy_term ON asset_taxonomy_assignments(taxonomy_term_id);

-- ============================================================================
-- TABLE: ingest_jobs (NEW - for tracking processing)
-- ============================================================================

CREATE TABLE ingest_jobs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id                UUID NOT NULL,
    tenant_id               UUID NOT NULL REFERENCES tenants(id),

    job_type                VARCHAR(50) NOT NULL
                            CHECK (job_type IN ('proxy', 'thumbnail', 'metadata', 'transcode', 'transcript')),
    status                  VARCHAR(50) DEFAULT 'pending'
                            CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    priority                INTEGER DEFAULT 5,

    input_path              VARCHAR(2000),
    output_path             VARCHAR(2000),

    progress                INTEGER DEFAULT 0,
    error_message           TEXT,

    worker_id               VARCHAR(100),

    started_at              TIMESTAMP WITH TIME ZONE,
    completed_at            TIMESTAMP WITH TIME ZONE,
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    config                  JSONB DEFAULT '{}',
    result                  JSONB DEFAULT '{}'
);

CREATE INDEX idx_jobs_asset ON ingest_jobs(asset_id);
CREATE INDEX idx_jobs_status ON ingest_jobs(status, priority DESC) WHERE status = 'pending';
CREATE INDEX idx_jobs_worker ON ingest_jobs(worker_id) WHERE worker_id IS NOT NULL;

-- ============================================================================
-- UTILITY FUNCTIONS
-- ============================================================================

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Resolution category computation
CREATE OR REPLACE FUNCTION compute_resolution_category(w INTEGER, h INTEGER)
RETURNS VARCHAR(20) AS $$
BEGIN
    IF w IS NULL OR h IS NULL THEN
        RETURN NULL;
    END IF;

    IF GREATEST(w, h) >= 7680 THEN
        RETURN '8K';
    ELSIF GREATEST(w, h) >= 3840 THEN
        RETURN '4K';
    ELSIF GREATEST(w, h) >= 2560 THEN
        RETURN 'QHD';
    ELSIF GREATEST(w, h) >= 1920 THEN
        RETURN 'FHD';
    ELSIF GREATEST(w, h) >= 1280 THEN
        RETURN 'HD';
    ELSE
        RETURN 'SD';
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Resolution category trigger
CREATE OR REPLACE FUNCTION trg_compute_resolution_category()
RETURNS TRIGGER AS $$
BEGIN
    NEW.resolution_category := compute_resolution_category(NEW.width, NEW.height);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER asset_tech_meta_resolution_category
    BEFORE INSERT OR UPDATE OF width, height ON asset_technical_metadata
    FOR EACH ROW EXECUTE FUNCTION trg_compute_resolution_category();

-- Keyword normalization
CREATE OR REPLACE FUNCTION normalize_keyword(input VARCHAR)
RETURNS VARCHAR AS $$
BEGIN
    RETURN lower(
        translate(
            input,
            'áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ',
            'aaaaaeeeeiiiioooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCN'
        )
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION trg_normalize_keyword()
RETURNS TRIGGER AS $$
BEGIN
    NEW.keyword_normalized := normalize_keyword(NEW.keyword);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER asset_keywords_normalize
    BEFORE INSERT OR UPDATE OF keyword ON asset_keywords
    FOR EACH ROW EXECUTE FUNCTION trg_normalize_keyword();

-- Updated_at triggers
CREATE TRIGGER trg_tenants_updated_at BEFORE UPDATE ON tenants FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_taxonomies_updated_at BEFORE UPDATE ON taxonomies FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_taxonomy_terms_updated_at BEFORE UPDATE ON taxonomy_terms FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_prod_meta_updated_at BEFORE UPDATE ON asset_production_metadata FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_tech_meta_updated_at BEFORE UPDATE ON asset_technical_metadata FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_markers_updated_at BEFORE UPDATE ON asset_markers FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- REFERENTIAL INTEGRITY (Triggers for partitioned table)
-- ============================================================================

CREATE OR REPLACE FUNCTION check_asset_exists(p_asset_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (SELECT 1 FROM assets WHERE id = p_asset_id);
END;
$$ LANGUAGE plpgsql STABLE;

-- Storage locations
CREATE OR REPLACE FUNCTION check_storage_asset_exists()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT check_asset_exists(NEW.asset_id) THEN
        RAISE EXCEPTION 'Asset % does not exist', NEW.asset_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_storage_asset
    BEFORE INSERT OR UPDATE OF asset_id ON asset_storage_locations
    FOR EACH ROW EXECUTE FUNCTION check_storage_asset_exists();

-- Technical metadata
CREATE OR REPLACE FUNCTION check_tech_meta_asset_exists()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT check_asset_exists(NEW.asset_id) THEN
        RAISE EXCEPTION 'Asset % does not exist', NEW.asset_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_tech_meta_asset
    BEFORE INSERT OR UPDATE OF asset_id ON asset_technical_metadata
    FOR EACH ROW EXECUTE FUNCTION check_tech_meta_asset_exists();

-- ============================================================================
-- TABLE: users
-- ============================================================================

CREATE TABLE users (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL REFERENCES tenants(id),

    email                   VARCHAR(255) NOT NULL,
    password_hash           VARCHAR(255) NOT NULL,
    full_name               VARCHAR(255),

    role                    VARCHAR(50) DEFAULT 'user'
                            CHECK (role IN ('admin', 'manager', 'editor', 'viewer', 'user')),

    is_active               BOOLEAN DEFAULT true,
    is_superuser            BOOLEAN DEFAULT false,

    last_login_at           TIMESTAMP WITH TIME ZONE,
    password_changed_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE (tenant_id, email)
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_active ON users(tenant_id, is_active) WHERE is_active = true;

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- TABLE: collections
-- ============================================================================

CREATE TABLE collections (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL REFERENCES tenants(id),

    name                    VARCHAR(255) NOT NULL,
    description             TEXT,
    slug                    VARCHAR(255),

    collection_type         VARCHAR(50) DEFAULT 'manual'
                            CHECK (collection_type IN ('manual', 'smart', 'system')),

    -- Smart collection filter (JSON query for dynamic collections)
    filter_query            JSONB,

    -- Display settings
    cover_asset_id          UUID,  -- Asset used as cover image
    color                   VARCHAR(20),  -- Hex color for UI
    icon                    VARCHAR(50),  -- Icon name

    is_public               BOOLEAN DEFAULT false,
    is_locked               BOOLEAN DEFAULT false,  -- Prevent modifications

    item_count              INTEGER DEFAULT 0,  -- Denormalized for performance

    created_by              UUID REFERENCES users(id),
    updated_by              UUID REFERENCES users(id),

    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE (tenant_id, slug)
);

CREATE INDEX idx_collections_tenant ON collections(tenant_id);
CREATE INDEX idx_collections_type ON collections(tenant_id, collection_type);
CREATE INDEX idx_collections_created_by ON collections(created_by);

CREATE TRIGGER trg_collections_updated_at BEFORE UPDATE ON collections FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- TABLE: collection_items
-- ============================================================================

CREATE TABLE collection_items (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id           UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    asset_id                UUID NOT NULL,
    tenant_id               UUID NOT NULL REFERENCES tenants(id),

    position                INTEGER DEFAULT 0,  -- For manual ordering
    added_by                UUID REFERENCES users(id),
    added_at                TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    note                    TEXT,  -- Optional note about why this asset is in the collection

    UNIQUE (collection_id, asset_id)
);

CREATE INDEX idx_collection_items_collection ON collection_items(collection_id);
CREATE INDEX idx_collection_items_asset ON collection_items(asset_id);
CREATE INDEX idx_collection_items_position ON collection_items(collection_id, position);

-- ============================================================================
-- FULL-TEXT SEARCH: Add tsvector column to assets
-- ============================================================================

-- Add search vector column
ALTER TABLE assets ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- Create GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_assets_search ON assets USING gin(search_vector);

-- Function to update search vector
CREATE OR REPLACE FUNCTION assets_search_vector_update() RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('portuguese', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('portuguese', coalesce(NEW.description, '')), 'B') ||
        setweight(to_tsvector('portuguese', coalesce(NEW.code, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update search vector
DROP TRIGGER IF EXISTS trg_assets_search_vector ON assets;
CREATE TRIGGER trg_assets_search_vector
    BEFORE INSERT OR UPDATE OF title, description, code ON assets
    FOR EACH ROW EXECUTE FUNCTION assets_search_vector_update();

-- Update existing assets (run once)
UPDATE assets SET search_vector =
    setweight(to_tsvector('portuguese', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('portuguese', coalesce(description, '')), 'B') ||
    setweight(to_tsvector('portuguese', coalesce(code, '')), 'C');

-- ============================================================================
-- SEED DATA: Development tenant
-- ============================================================================

INSERT INTO tenants (code, name, type, settings) VALUES
    ('dev', 'Development Tenant', 'production', '{"language": "pt-BR", "timezone": "America/Sao_Paulo"}'),
    ('gnc', 'Grupo Norte Comunicacao', 'broadcaster', '{"language": "pt-BR", "timezone": "America/Sao_Paulo"}');

-- ============================================================================
-- VERIFICATION
-- ============================================================================

DO $$
DECLARE
    table_count INT;
    partition_count INT;
BEGIN
    SELECT COUNT(*) INTO table_count FROM information_schema.tables WHERE table_schema = 'public';
    SELECT COUNT(*) INTO partition_count FROM pg_class c
        JOIN pg_inherits i ON c.oid = i.inhrelid
        JOIN pg_class p ON i.inhparent = p.oid
        WHERE p.relname = 'assets';

    RAISE NOTICE 'AKASHI MAM Database initialized successfully!';
    RAISE NOTICE 'Tables created: %', table_count;
    RAISE NOTICE 'Asset partitions: %', partition_count;
END $$;
