# Sprint 1: Core Schema

## Overview

The core schema establishes the foundation for the MAM system with multi-tenancy support, asset management, and job processing.

## Tables Created

### 1. tenants

Multi-tenant isolation for SaaS deployment.

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) NOT NULL UNIQUE,      -- Short identifier (e.g., 'acme')
    name VARCHAR(255) NOT NULL,            -- Display name
    settings JSONB DEFAULT '{}',           -- Tenant-specific settings
    storage_quota_bytes BIGINT,            -- Storage limit
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Indexes:**
- `idx_tenants_code` on `code`
- `idx_tenants_is_active` on `is_active`

---

### 2. assets (Partitioned)

Main asset registry, partitioned by `partition_date` for performance.

```sql
CREATE TABLE assets (
    id UUID DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,

    -- Basic info
    title VARCHAR(500) NOT NULL,
    description TEXT,
    asset_type VARCHAR(50) NOT NULL,       -- video, audio, image, document
    code VARCHAR(100),                     -- User-defined code
    slug VARCHAR(255),                     -- URL-friendly identifier

    -- Timing
    duration_ms INTEGER,
    recorded_at TIMESTAMP WITH TIME ZONE,

    -- Classification
    content_rating VARCHAR(20),
    visibility VARCHAR(20) DEFAULT 'internal',

    -- Hierarchy
    parent_id UUID,
    derivative_type VARCHAR(50),           -- proxy, thumbnail, etc.

    -- Status
    status VARCHAR(50) DEFAULT 'pending',
    publish_status VARCHAR(50) DEFAULT 'draft',

    -- Storage
    primary_storage_path TEXT,
    file_size_bytes BIGINT,
    checksum_sha256 VARCHAR(64),

    -- Metadata
    external_ids JSONB DEFAULT '{}',
    extra JSONB DEFAULT '{}',

    -- Audit
    created_by UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE,

    -- Partitioning
    partition_date DATE DEFAULT CURRENT_DATE,

    PRIMARY KEY (id, partition_date)
) PARTITION BY RANGE (partition_date);
```

**Partition Strategy:**
- Monthly partitions: `assets_2026_01`, `assets_2026_02`, etc.
- Default partition for edge cases

**Indexes:**
- `idx_assets_tenant_id` on `tenant_id`
- `idx_assets_status` on `status`
- `idx_assets_asset_type` on `asset_type`
- `idx_assets_created_at` on `created_at`

---

### 3. asset_storage_locations

Tracks file locations across multiple storage backends.

```sql
CREATE TABLE asset_storage_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    tenant_id UUID NOT NULL,

    -- Storage details
    storage_type VARCHAR(50) NOT NULL,     -- s3, azure, gcs, lto
    storage_tier VARCHAR(50) DEFAULT 'hot', -- hot, warm, cold, archive
    bucket VARCHAR(255),
    path TEXT NOT NULL,
    filename VARCHAR(500),
    url TEXT,

    -- File info
    file_size_bytes BIGINT,
    checksum_sha256 VARCHAR(64),
    content_type VARCHAR(100),

    -- Purpose
    purpose VARCHAR(50) DEFAULT 'original', -- original, proxy, thumbnail
    is_primary BOOLEAN DEFAULT FALSE,
    is_accessible BOOLEAN DEFAULT TRUE,

    -- Status
    status VARCHAR(50) DEFAULT 'available',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    verified_at TIMESTAMP WITH TIME ZONE,
    archived_at TIMESTAMP WITH TIME ZONE
);
```

**Indexes:**
- `idx_storage_asset_id` on `asset_id`
- `idx_storage_tenant_id` on `tenant_id`
- `idx_storage_purpose` on `purpose`

---

### 4. asset_technical_metadata

Stores FFprobe analysis results.

```sql
CREATE TABLE asset_technical_metadata (
    asset_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,

    -- Video
    width INTEGER,
    height INTEGER,
    frame_rate NUMERIC(10,4),
    frame_rate_num INTEGER,
    frame_rate_den INTEGER,
    video_codec VARCHAR(50),
    video_codec_profile VARCHAR(100),
    video_bitrate_bps BIGINT,

    -- Audio
    audio_codec VARCHAR(50),
    audio_channels INTEGER,
    audio_channel_layout VARCHAR(100),
    audio_sample_rate INTEGER,
    audio_bitrate_bps BIGINT,
    audio_bit_depth INTEGER,

    -- Container
    container_format VARCHAR(50),
    duration_ms BIGINT,

    -- Visual
    bit_depth INTEGER,
    color_space VARCHAR(50),
    aspect_ratio VARCHAR(20),
    resolution_category VARCHAR(20),       -- SD, HD, FHD, UHD, 4K, 8K

    -- Raw data
    ffprobe_raw JSONB,
    mediainfo_raw JSONB,

    -- Analysis info
    analyzed_at TIMESTAMP WITH TIME ZONE,
    analyzer_version VARCHAR(50),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

### 5. ingest_jobs

Job queue for async processing.

```sql
CREATE TABLE ingest_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    asset_id UUID,

    -- Job details
    job_type VARCHAR(50) NOT NULL,         -- metadata, proxy, thumbnail
    status VARCHAR(50) DEFAULT 'pending',  -- pending, processing, completed, failed
    priority INTEGER DEFAULT 5,

    -- I/O paths
    input_path TEXT,
    output_path TEXT,

    -- Progress
    progress INTEGER DEFAULT 0,            -- 0-100

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Error handling
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,

    -- Results
    result JSONB
);
```

**Indexes:**
- `idx_jobs_status` on `status`
- `idx_jobs_asset_id` on `asset_id`
- `idx_jobs_priority` on `priority DESC, created_at`

---

## Entity Relationship

```
tenants
    │
    ├──< assets (partitioned)
    │       │
    │       ├──< asset_storage_locations
    │       ├──< asset_technical_metadata (1:1)
    │       └──< ingest_jobs
    │
    └──< [other tenant-scoped tables]
```

## Notes

### Partitioning Considerations

Since `assets` is partitioned, foreign keys referencing it require special handling in SQLAlchemy:

```python
# In related models, use viewonly relationships
storage_locations = relationship(
    "AssetStorageLocation",
    primaryjoin="Asset.id == foreign(AssetStorageLocation.asset_id)",
    viewonly=True,
)
```

### Status Values

**Asset Status:**
- `pending` - Just created
- `ingesting` - Upload in progress
- `processing` - Being processed
- `available` - Ready for use
- `failed` - Processing failed
- `archived` - Moved to cold storage

**Job Status:**
- `pending` - Waiting to be processed
- `processing` - Currently running
- `completed` - Finished successfully
- `failed` - Failed (may retry)
