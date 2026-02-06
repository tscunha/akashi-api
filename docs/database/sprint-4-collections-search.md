# Sprint 4: Collections & Full-Text Search

## Overview

Implements asset collections (playlists/folders) and PostgreSQL full-text search capabilities.

## Migration File

`scripts/migrations/002_add_collections_and_search.sql`

## Tables Created

### 1. collections

Asset grouping system with ownership and visibility.

```sql
CREATE TABLE collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    -- Basic info
    name VARCHAR(255) NOT NULL,
    description TEXT,
    slug VARCHAR(255),

    -- Type
    collection_type VARCHAR(50) NOT NULL DEFAULT 'manual',  -- manual, smart, system

    -- Smart collection filter (for type='smart')
    filter_query JSONB,

    -- Visual
    cover_asset_id UUID,
    color VARCHAR(20),
    icon VARCHAR(50),

    -- Visibility
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,

    -- Stats
    item_count INTEGER NOT NULL DEFAULT 0,

    -- Ownership
    created_by UUID REFERENCES users(id),
    updated_by UUID REFERENCES users(id),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
```

**Indexes:**
- `idx_collections_tenant_id` on `tenant_id`
- `idx_collections_created_by` on `created_by`
- `idx_collections_is_public` on `is_public`
- `idx_collections_slug` on `slug`

---

### 2. collection_items

Junction table for collection membership with ordering.

```sql
CREATE TABLE collection_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    -- Ordering
    position INTEGER NOT NULL DEFAULT 0,

    -- Metadata
    added_by UUID REFERENCES users(id),
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    note TEXT,

    -- Unique constraint
    UNIQUE (collection_id, asset_id)
);
```

**Indexes:**
- `idx_collection_items_collection_id` on `collection_id`
- `idx_collection_items_asset_id` on `asset_id`
- `idx_collection_items_position` on `collection_id, position`

---

## Full-Text Search

### search_vector Column

Added to the `assets` table:

```sql
ALTER TABLE assets ADD COLUMN search_vector TSVECTOR;

-- Populate existing data
UPDATE assets SET search_vector =
    setweight(to_tsvector('portuguese', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('portuguese', coalesce(description, '')), 'B') ||
    setweight(to_tsvector('portuguese', coalesce(code, '')), 'C');
```

### GIN Index

```sql
CREATE INDEX idx_assets_search_vector
ON assets USING GIN (search_vector);
```

### Auto-Update Trigger

```sql
CREATE OR REPLACE FUNCTION update_asset_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('portuguese', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('portuguese', coalesce(NEW.description, '')), 'B') ||
        setweight(to_tsvector('portuguese', coalesce(NEW.code, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_asset_search_vector
    BEFORE INSERT OR UPDATE ON assets
    FOR EACH ROW
    EXECUTE FUNCTION update_asset_search_vector();
```

---

## Collection Types

| Type | Description |
|------|-------------|
| `manual` | User-created, manually managed |
| `smart` | Auto-populated based on `filter_query` |
| `system` | System-managed (favorites, recent, etc.) |

### Smart Collection Example

```json
{
  "collection_type": "smart",
  "filter_query": {
    "asset_type": "video",
    "status": "available",
    "created_after": "2026-01-01"
  }
}
```

---

## Search Weights

| Weight | Field | Priority |
|--------|-------|----------|
| A | `title` | Highest |
| B | `description` | Medium |
| C | `code` | Lowest |

### Search Query Examples

```sql
-- Basic search
SELECT * FROM assets
WHERE search_vector @@ plainto_tsquery('portuguese', 'palm tree')
ORDER BY ts_rank(search_vector, plainto_tsquery('portuguese', 'palm tree')) DESC;

-- With highlighting
SELECT
    title,
    ts_headline('portuguese', description,
        plainto_tsquery('portuguese', 'palm'),
        'StartSel=<mark>, StopSel=</mark>'
    ) as snippet
FROM assets
WHERE search_vector @@ plainto_tsquery('portuguese', 'palm');
```

---

## API Endpoints

### Collections

```
GET    /api/v1/collections                           - List collections
POST   /api/v1/collections                           - Create collection
GET    /api/v1/collections/{id}                      - Get with items
PATCH  /api/v1/collections/{id}                      - Update
DELETE /api/v1/collections/{id}                      - Delete

POST   /api/v1/collections/{id}/items                - Add asset
POST   /api/v1/collections/{id}/items/bulk           - Add multiple
DELETE /api/v1/collections/{id}/items/{asset_id}     - Remove asset
POST   /api/v1/collections/{id}/items/reorder        - Reorder items
```

### Search

```
GET /api/v1/search?q={query}                         - Full-text search
GET /api/v1/search/suggestions?q={prefix}            - Autocomplete
GET /api/v1/search/advanced?asset_type=video&...     - Multi-filter
```

---

## Example Responses

### Search

```json
{
  "query": "palm tree",
  "total": 3,
  "page": 1,
  "page_size": 20,
  "results": [
    {
      "id": "5b494e4f-...",
      "title": "Light Sunlight Leaf Palm",
      "asset_type": "video",
      "rank": 0.0759909,
      "headline": "Light Sunlight Leaf <mark>Palm</mark>"
    }
  ],
  "search_time_ms": 12
}
```

### Collection with Items

```json
{
  "id": "f80cb74a-...",
  "name": "Nature Collection",
  "collection_type": "manual",
  "item_count": 5,
  "items": [
    {
      "id": "item-uuid",
      "asset_id": "asset-uuid",
      "position": 0,
      "asset": {
        "title": "Palm Tree Video",
        "thumbnail_url": "..."
      }
    }
  ]
}
```

---

## Performance Notes

1. **GIN Index**: Enables fast full-text search
2. **Denormalized Count**: `item_count` in collections avoids COUNT queries
3. **Position Field**: Enables drag-and-drop reordering
4. **Portuguese Language**: Use `'portuguese'` for pt-BR content, change to `'english'` if needed
