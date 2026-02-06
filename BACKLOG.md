# AKASHI API - Backlog

## Status Atual
**Versão:** 0.1.0
**Data:** 2026-02-06 (atualizado 04:15)
**Sprint:** 5 - Security & Background Processing ✅

---

## ✅ Concluído

### Sprint 1: MVP Ingest Pipeline

#### Infraestrutura
- [x] Docker Compose (PostgreSQL + MinIO)
- [x] Schema Module 1 no banco (18 tabelas)
- [x] Buckets MinIO criados
- [x] Redis + RabbitMQ no compose

#### API
- [x] FastAPI setup com async SQLAlchemy
- [x] Health check endpoint
- [x] Assets CRUD completo
- [x] Upload/Ingest endpoint
- [x] Jobs endpoints
- [x] Processamento síncrono (fallback)

#### Models
- [x] Asset (particionado)
- [x] AssetStorageLocation
- [x] AssetTechnicalMetadata
- [x] IngestJob
- [x] Tenant

#### Debug Tools
- [x] `scripts/db_monitor.py` - Monitor de banco em tempo real
- [x] `scripts/folder_watcher.py` - Watcher de pasta para ingest
- [x] `scripts/start_debug.bat` - Launcher do ambiente debug

### Sprint 1.5: DevOps Foundation + FFmpeg Workers

#### CI/CD
- [x] `.github/workflows/ci.yml` - Pipeline GitHub Actions
- [x] Dockerfile multi-stage (production-ready)
- [x] docker-compose.yml com profiles (workers, monitoring)
- [x] `.env.example` atualizado

#### FFmpeg Workers
- [x] FFprobe metadata extraction (codec, fps, resolution, duration)
- [x] FFmpeg proxy generation (H.264 720p)
- [x] FFmpeg thumbnail generation (JPEG 320x180)
- [x] Configuração de paths no .env

#### Testes
- [x] `tests/conftest.py` - Fixtures pytest
- [x] `tests/test_health.py` - Testes de health check
- [x] `tests/test_assets.py` - Testes de assets

#### Monitoring
- [x] `infra/prometheus/prometheus.yml` - Config Prometheus
- [x] `infra/grafana/provisioning/` - Config Grafana

### Sprint 2: Keywords & Markers API ✅

#### Keywords API
- [x] `app/models/keyword.py` - Model AssetKeyword
- [x] `app/schemas/keyword.py` - Schemas Pydantic
- [x] `app/api/v1/endpoints/keywords.py` - Endpoints REST
- [x] CRUD completo + busca global

#### Markers API
- [x] `app/models/marker.py` - Model AssetMarker
- [x] `app/schemas/marker.py` - Schemas Pydantic
- [x] `app/api/v1/endpoints/markers.py` - Endpoints REST
- [x] CRUD completo + filtro por tipo

### Sprint 3: JWT Authentication ✅

#### Database
- [x] Tabela `users` criada (migration 001)
- [x] Campos: email, password_hash, role, is_active, is_superuser
- [x] Roles: admin, manager, editor, viewer, user

#### Security
- [x] `app/core/security.py` - JWT + bcrypt password hashing
- [x] Token expiration configurável (default: 30 min)

#### Auth Endpoints
- [x] `POST /api/v1/auth/register` - Criar usuário
- [x] `POST /api/v1/auth/login` - Login (retorna JWT)
- [x] `GET /api/v1/auth/me` - Info do usuário atual
- [x] `PATCH /api/v1/auth/me` - Atualizar perfil
- [x] `POST /api/v1/auth/me/change-password` - Trocar senha

#### User Management (Admin)
- [x] `GET /api/v1/auth/users` - Listar usuários (superuser)
- [x] `GET /api/v1/auth/users/{id}` - Detalhes (superuser)
- [x] `PATCH /api/v1/auth/users/{id}` - Atualizar (superuser)
- [x] `DELETE /api/v1/auth/users/{id}` - Desativar (superuser)

### Sprint 4: Collections & Full-Text Search ✅

#### Database
- [x] Tabelas `collections` e `collection_items` (migration 002)
- [x] Coluna `search_vector` (tsvector) na tabela assets
- [x] Índice GIN para full-text search
- [x] Trigger para auto-update do search_vector

#### Collections API
- [x] `app/models/collection.py` - Model Collection e CollectionItem
- [x] `app/schemas/collection.py` - Schemas completos
- [x] `app/api/v1/endpoints/collections.py` - Endpoints REST

**Endpoints Collections:**
- [x] `GET /api/v1/collections` - Listar (público + próprias)
- [x] `POST /api/v1/collections` - Criar (auth required)
- [x] `GET /api/v1/collections/{id}` - Detalhes com items
- [x] `PATCH /api/v1/collections/{id}` - Atualizar
- [x] `DELETE /api/v1/collections/{id}` - Remover
- [x] `POST /api/v1/collections/{id}/items` - Adicionar asset
- [x] `POST /api/v1/collections/{id}/items/bulk` - Adicionar múltiplos
- [x] `DELETE /api/v1/collections/{id}/items/{asset_id}` - Remover asset
- [x] `POST /api/v1/collections/{id}/items/reorder` - Reordenar

#### Search API
- [x] `app/schemas/search.py` - Schemas de busca
- [x] `app/api/v1/endpoints/search.py` - Endpoints de busca

**Endpoints Search:**
- [x] `GET /api/v1/search?q=` - Full-text search com ranking
- [x] `GET /api/v1/search/suggestions?q=` - Autocomplete
- [x] `GET /api/v1/search/advanced` - Busca avançada com múltiplos filtros

#### Testes
- [x] `tests/test_collections.py` - 9 testes
- [x] `tests/test_search.py` - 8 testes
- [x] **51 testes totais passando!**

### Sprint 5: Security & Background Processing ✅ (CONCLUÍDO!)

#### Celery Workers
- [x] `app/workers/celery_app.py` - Configuração Celery
- [x] `app/workers/tasks/ingest.py` - Pipeline de ingest
- [x] `app/workers/tasks/maintenance.py` - Tasks de manutenção
- [x] Celery Beat scheduler configurado

**Tasks Celery:**
- [x] `process_ingest` - Orquestra pipeline de ingest
- [x] `run_ingest_pipeline` - Pipeline completo com tracking
- [x] `finalize_ingest` - Finaliza ingest e atualiza status
- [x] `cleanup_old_jobs` - Remove jobs antigos (agendado)
- [x] `check_stuck_jobs` - Detecta jobs travados (agendado)
- [x] `health_check` - Verifica saúde do sistema (agendado)
- [x] `calculate_storage_stats` - Estatísticas de storage (agendado)

#### Refresh Tokens
- [x] Tabela `refresh_tokens` (migration 003)
- [x] `app/models/refresh_token.py` - Model RefreshToken
- [x] Token rotation automática
- [x] Revogação de tokens

**Endpoints Refresh:**
- [x] `POST /api/v1/auth/refresh` - Renovar access token
- [x] `POST /api/v1/auth/logout` - Revogar refresh token
- [x] `POST /api/v1/auth/logout-all` - Logout de todos os dispositivos

#### Rate Limiting
- [x] `app/core/rate_limit.py` - Rate limiter com Redis
- [x] Sliding window algorithm
- [x] Middleware global
- [x] Dependency para rotas específicas
- [x] Headers X-RateLimit-*
- [x] Configuração via .env

**Configuração Rate Limit:**
- Default: 100 requests/minuto
- Fail-open: permite requests se Redis falhar
- Headers de resposta: Limit, Remaining, Reset, Retry-After

---

## 🔄 Em Progresso

*Nenhuma tarefa em progresso no momento*

---

## 📋 Backlog (Priorizado)

### P1 - Importante (Sprint 6)
1. **Integrar ingest-client** - Testar desktop client
2. **Audit logging** - Rastrear ações dos usuários
3. **Webhook events** - Notificações de eventos

### P2 - Desejável (Sprint 7)
4. **Waveform generation** - Para áudio
5. **Sprite sheets** - Para scrubbing de vídeo
6. **HLS/DASH** - Streaming adaptativo

### P3 - Futuro
7. **Admin UI** - React/Vue dashboard
8. **MCP Server** - Integração com AI agents
9. **Multi-storage** - LTO, Glacier, etc
10. **Kubernetes manifests** - Deploy em escala

---

## 🐛 Bugs Conhecidos

| ID | Descrição | Status |
|----|-----------|--------|
| - | Nenhum bug crítico no momento | - |

---

## 📝 Notas Técnicas

### SQLAlchemy + Tabelas Particionadas
A tabela `assets` é particionada por `partition_date`. Isso causa problemas com ForeignKeys porque PostgreSQL não permite FK para tabelas particionadas.

**Solução aplicada:**
```python
storage_locations = relationship(
    "AssetStorageLocation",
    primaryjoin="Asset.id == foreign(AssetStorageLocation.asset_id)",
    viewonly=True,
)
```

### Full-Text Search (PostgreSQL)
Busca utiliza `tsvector` com pesos:
- **A**: título (maior relevância)
- **B**: descrição
- **C**: código

```sql
-- Query de busca
SELECT *, ts_rank(search_vector, plainto_tsquery('portuguese', 'termo')) as rank
FROM assets
WHERE search_vector @@ plainto_tsquery('portuguese', 'termo')
ORDER BY rank DESC;
```

### Collections
- **manual**: coleções criadas manualmente
- **smart**: coleções baseadas em filtros (futuro)
- **system**: coleções do sistema (favoritos, recentes)

### JWT Authentication com Refresh Tokens
```bash
# Login (retorna access + refresh token)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'

# Usar access token
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <access_token>"

# Renovar tokens
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'

# Logout
curl -X POST http://localhost:8000/api/v1/auth/logout \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'
```

### Rate Limiting
```bash
# Verificar headers de rate limit
curl -I http://localhost:8000/api/v1/health

# Headers de resposta:
# X-RateLimit-Limit: 100
# X-RateLimit-Remaining: 99
# X-RateLimit-Reset: 60
```

### Celery Workers
```bash
# Iniciar worker
celery -A app.workers.celery_app worker --loglevel=info

# Iniciar beat (scheduler)
celery -A app.workers.celery_app beat --loglevel=info

# Ou via Docker Compose
docker compose --profile workers up -d
```

### Docker Compose Profiles
```bash
docker compose up -d                      # Core apenas
docker compose --profile workers up -d    # Com Celery
docker compose --profile monitoring up -d # Com Grafana/Prometheus
docker compose --profile all up -d        # Tudo
```

---

## 📊 Estatísticas do Projeto

| Métrica | Valor |
|---------|-------|
| Tabelas no banco | 22 |
| Endpoints REST | ~50 |
| Testes de integração | 51 |
| Sprints concluídas | 5 |
| Tempo estimado economizado | ~6 semanas |

---

## 🔗 Links

- **API Docs**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001
- **RabbitMQ**: http://localhost:15672
- **Grafana**: http://localhost:3000 (com profile monitoring)
- **Prometheus**: http://localhost:9090 (com profile monitoring)
