-- ============================================================================
-- Migration 002: Add Collections and Full-Text Search
-- Run this on existing databases
-- ============================================================================

-- ============================================================================
-- TABLE: collections
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'collections') THEN

        CREATE TABLE collections (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id               UUID NOT NULL REFERENCES tenants(id),

            name                    VARCHAR(255) NOT NULL,
            description             TEXT,
            slug                    VARCHAR(255),

            collection_type         VARCHAR(50) DEFAULT 'manual'
                                    CHECK (collection_type IN ('manual', 'smart', 'system')),

            filter_query            JSONB,

            cover_asset_id          UUID,
            color                   VARCHAR(20),
            icon                    VARCHAR(50),

            is_public               BOOLEAN DEFAULT false,
            is_locked               BOOLEAN DEFAULT false,

            item_count              INTEGER DEFAULT 0,

            created_by              UUID REFERENCES users(id),
            updated_by              UUID REFERENCES users(id),

            created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

            UNIQUE (tenant_id, slug)
        );

        CREATE INDEX idx_collections_tenant ON collections(tenant_id);
        CREATE INDEX idx_collections_type ON collections(tenant_id, collection_type);
        CREATE INDEX idx_collections_created_by ON collections(created_by);

        CREATE TRIGGER trg_collections_updated_at
            BEFORE UPDATE ON collections
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();

        RAISE NOTICE 'Collections table created successfully!';
    ELSE
        RAISE NOTICE 'Collections table already exists, skipping...';
    END IF;
END $$;

-- ============================================================================
-- TABLE: collection_items
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'collection_items') THEN

        CREATE TABLE collection_items (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collection_id           UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
            asset_id                UUID NOT NULL,
            tenant_id               UUID NOT NULL REFERENCES tenants(id),

            position                INTEGER DEFAULT 0,
            added_by                UUID REFERENCES users(id),
            added_at                TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

            note                    TEXT,

            UNIQUE (collection_id, asset_id)
        );

        CREATE INDEX idx_collection_items_collection ON collection_items(collection_id);
        CREATE INDEX idx_collection_items_asset ON collection_items(asset_id);
        CREATE INDEX idx_collection_items_position ON collection_items(collection_id, position);

        RAISE NOTICE 'Collection items table created successfully!';
    ELSE
        RAISE NOTICE 'Collection items table already exists, skipping...';
    END IF;
END $$;

-- ============================================================================
-- FULL-TEXT SEARCH: Add tsvector to assets
-- ============================================================================

DO $$
BEGIN
    -- Add search_vector column if not exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'assets' AND column_name = 'search_vector'
    ) THEN
        ALTER TABLE assets ADD COLUMN search_vector tsvector;
        RAISE NOTICE 'Added search_vector column to assets';
    END IF;
END $$;

-- Create GIN index for full-text search
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

-- Update existing assets with search vectors
UPDATE assets SET search_vector =
    setweight(to_tsvector('portuguese', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('portuguese', coalesce(description, '')), 'B') ||
    setweight(to_tsvector('portuguese', coalesce(code, '')), 'C')
WHERE search_vector IS NULL;

RAISE NOTICE 'Full-text search configured successfully!';

-- ============================================================================
-- Verification
-- ============================================================================

SELECT 'collections' as table_name, COUNT(*) as count FROM collections
UNION ALL
SELECT 'collection_items', COUNT(*) FROM collection_items;
