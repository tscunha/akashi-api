# AKASHI API - Changelog

## [0.1.0] - 2026-02-05

### Sprint 1: MVP Ingest Pipeline

#### Infraestrutura
- **Docker Compose** com PostgreSQL 16 (pgvector), MinIO, Redis, RabbitMQ
- **Buckets MinIO**: `akashi-originals`, `akashi-proxies`, `akashi-thumbnails`
- **Schema DB**: Module 1 completo (18 tabelas) via `scripts/init-db.sql`
- **Tenants seed**: `dev`, `gnc`

#### API REST (FastAPI)
- `GET /` - Root info
- `GET /api/v1/health` - Health check (DB + Storage)
- **Assets CRUD**:
  - `GET /api/v1/assets` - Listar (paginado, filtros)
  - `GET /api/v1/assets/{id}` - Detalhe com storage_locations
  - `POST /api/v1/assets` - Criar (metadata only)
  - `PATCH /api/v1/assets/{id}` - Atualizar
  - `DELETE /api/v1/assets/{id}` - Soft delete
- **Upload/Ingest**:
  - `POST /api/v1/ingest` - Upload + criar asset + queue jobs
  - `POST /api/v1/assets/{id}/upload` - Upload para asset existente
- **Jobs**:
  - `GET /api/v1/jobs` - Listar jobs (filtros: status, type, asset_id)
  - `GET /api/v1/jobs/{id}` - Detalhe do job
  - `POST /api/v1/jobs/{id}/retry` - Retry job failed
  - `POST /api/v1/jobs/process-pending` - Processar jobs (sync ou async)

#### Models SQLAlchemy
- `Asset` - Tabela particionada com relationships via `foreign()`
- `AssetStorageLocation` - Locais de armazenamento
- `AssetTechnicalMetadata` - Metadata técnico (codec, resolução, etc)
- `IngestJob` - Jobs de processamento
- `Tenant` - Multi-tenancy

#### Services
- `StorageService` - Upload/download MinIO com presigned URLs
- `ProcessingService` - Gerenciamento de jobs
- `AssetService` - CRUD de assets

#### Workers Celery
- `extract_metadata` - Extração via FFprobe
- `generate_proxy` - Proxy H.264 720p via FFmpeg
- `generate_thumbnail` - Thumbnail JPG via FFmpeg
- Processamento síncrono via endpoint quando Celery indisponível

#### Correções Técnicas
- **SQLAlchemy + Partitioned Tables**: Uso de `primaryjoin` com `foreign()` e `viewonly=True` para relacionamentos com tabela particionada
- **Exception Handler**: Logging detalhado de erros

---

## Componentes Afetados (para sincronização)

### akashi-ingest-client
**Precisa atualizar:**
- URL da API: `http://localhost:8000`
- Endpoint de upload: `POST /api/v1/ingest`
- Formato: multipart/form-data com fields: `file`, `title`, `asset_type`, `tenant_code`

### akashi-mam (Documentação)
**Precisa atualizar:**
- Adicionar documentação da API REST
- Schema OpenAPI disponível em `/docs`

---

## Próximos Passos

### Pendente Sprint 1
- [ ] Integrar com Redis + RabbitMQ (problema de rede)
- [ ] Implementar extração real de metadata via FFprobe
- [ ] Implementar geração real de proxy/thumbnail via FFmpeg
- [ ] Testar com akashi-ingest-client

### Sprint 2 (Proposta)
- [ ] Feature 2.3: Metadata API (Keywords, Markers, Relationships)
- [ ] Feature 2.5: Basic Search (Elasticsearch)
- [ ] Autenticação JWT
- [ ] Testes automatizados
