# AKASHI MAM API - Database Documentation

## Overview

AKASHI uses PostgreSQL 15+ with the following features:
- UUID primary keys (gen_random_uuid)
- Table partitioning for assets (by date)
- Full-text search with tsvector/tsquery
- GIN indexes for JSONB and text search
- Triggers for automatic updates

## Database Statistics

| Metric | Value |
|--------|-------|
| Total Tables | 22 |
| Partitioned Tables | 1 (assets) |
| Indexes | ~40 |
| Triggers | 2 |

## Schema Evolution by Sprint

- [Sprint 1: Core Schema](./sprint-1-core.md) - Tenants, Assets, Storage, Jobs
- [Sprint 2: Keywords & Markers](./sprint-2-keywords-markers.md) - Metadata extensions
- [Sprint 3: Authentication](./sprint-3-auth.md) - Users table
- [Sprint 4: Collections & Search](./sprint-4-collections-search.md) - Collections, Full-text search
- [Sprint 5: Security & Background](./sprint-5-security.md) - Refresh tokens

## Quick Reference

### Core Tables
```
tenants              - Multi-tenant isolation
assets               - Main asset registry (partitioned)
asset_storage_locations - File storage locations
asset_technical_metadata - FFprobe metadata
ingest_jobs          - Processing job queue
```

### User & Auth Tables
```
users                - User accounts
refresh_tokens       - JWT refresh token storage
```

### Metadata Tables
```
asset_keywords       - Asset tagging
asset_markers        - Timecode markers (chapters, segments)
```

### Organization Tables
```
collections          - Asset collections/playlists
collection_items     - Collection membership
```

## Connection String

```bash
postgresql+asyncpg://akashi:akashi_dev_2025@localhost:5432/akashi_mam
```

## Migrations

Migrations are in `scripts/migrations/`:

```
scripts/migrations/
├── 001_add_users_table.sql      # Sprint 3
├── 002_add_collections_and_search.sql  # Sprint 4
└── 003_add_refresh_tokens.sql   # Sprint 5
```

Initial schema is in `scripts/init-db.sql`.
