# Sprint 2: Keywords & Markers

## Overview

Adds metadata extensions for asset tagging and timecode-based markers.

## Tables Created

### 1. asset_keywords

Tagging system for assets with confidence scores.

```sql
CREATE TABLE asset_keywords (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    tenant_id UUID NOT NULL,

    -- Keyword data
    keyword VARCHAR(255) NOT NULL,
    normalized_keyword VARCHAR(255) NOT NULL,  -- Lowercase, trimmed
    category VARCHAR(100),                      -- person, location, object, etc.
    confidence NUMERIC(5,4),                    -- 0.0000 to 1.0000

    -- Source
    source VARCHAR(50) DEFAULT 'manual',        -- manual, ai, import

    -- Audit
    created_by UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Unique constraint
    UNIQUE (asset_id, normalized_keyword)
);
```

**Indexes:**
- `idx_keywords_asset_id` on `asset_id`
- `idx_keywords_tenant_id` on `tenant_id`
- `idx_keywords_normalized` on `normalized_keyword`
- `idx_keywords_category` on `category`

**Use Cases:**
- Manual tagging by editors
- AI-generated tags with confidence scores
- Import from external systems

---

### 2. asset_markers

Timecode-based markers for video/audio.

```sql
CREATE TABLE asset_markers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    tenant_id UUID NOT NULL,

    -- Marker type
    marker_type VARCHAR(50) NOT NULL,           -- chapter, segment, highlight, comment, scene

    -- Timing (in milliseconds)
    timecode_in_ms BIGINT NOT NULL,
    timecode_out_ms BIGINT,                     -- NULL for point markers
    duration_ms BIGINT GENERATED ALWAYS AS (timecode_out_ms - timecode_in_ms) STORED,

    -- Content
    title VARCHAR(255),
    description TEXT,
    thumbnail_url TEXT,

    -- Classification
    color VARCHAR(20),                          -- Hex color for UI
    icon VARCHAR(50),                           -- Icon identifier
    tags TEXT[],                                -- Array of tags

    -- Metadata
    extra JSONB DEFAULT '{}',

    -- Audit
    created_by UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Indexes:**
- `idx_markers_asset_id` on `asset_id`
- `idx_markers_tenant_id` on `tenant_id`
- `idx_markers_type` on `marker_type`
- `idx_markers_timecode` on `timecode_in_ms`

**Marker Types:**

| Type | Description |
|------|-------------|
| `chapter` | Navigation chapters |
| `segment` | Defined time ranges |
| `highlight` | Notable moments |
| `comment` | Time-based comments |
| `scene` | Scene boundaries |

---

## Entity Relationship

```
assets
    │
    ├──< asset_keywords
    │       - Multiple keywords per asset
    │       - Unique by (asset_id, normalized_keyword)
    │
    └──< asset_markers
            - Multiple markers per asset
            - Ordered by timecode_in_ms
```

## API Endpoints

### Keywords

```
GET    /api/v1/assets/{asset_id}/keywords
POST   /api/v1/assets/{asset_id}/keywords
PATCH  /api/v1/keywords/{keyword_id}
DELETE /api/v1/keywords/{keyword_id}
GET    /api/v1/keywords/search?q={query}
```

### Markers

```
GET    /api/v1/assets/{asset_id}/markers
POST   /api/v1/assets/{asset_id}/markers
PATCH  /api/v1/markers/{marker_id}
DELETE /api/v1/markers/{marker_id}
```

## Example Data

### Keywords

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "asset_id": "123e4567-e89b-12d3-a456-426614174000",
  "keyword": "Palm Tree",
  "normalized_keyword": "palm tree",
  "category": "object",
  "confidence": 0.9542,
  "source": "ai"
}
```

### Markers

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "asset_id": "123e4567-e89b-12d3-a456-426614174000",
  "marker_type": "chapter",
  "timecode_in_ms": 0,
  "timecode_out_ms": 15000,
  "duration_ms": 15000,
  "title": "Introduction",
  "color": "#FF5733",
  "tags": ["intro", "opening"]
}
```

## Notes

### Keyword Normalization

Keywords are normalized on insert:
- Convert to lowercase
- Trim whitespace
- Remove special characters

This ensures consistent matching regardless of input format.

### Marker Precision

Timecodes are stored in milliseconds for precision:
- `timecode_in_ms = 1500` = 1.5 seconds
- `duration_ms` is auto-calculated via GENERATED ALWAYS
