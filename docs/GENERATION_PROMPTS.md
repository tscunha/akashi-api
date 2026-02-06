# AKASHI MAM API - Generation Prompts

Este documento registra os prompts e instruções utilizados para gerar cada sprint do projeto, permitindo replicar ou estender o desenvolvimento.

---

## Contexto Inicial

### Objetivo do Projeto

> **AKASHI MAM** (Media Asset Management) é uma API backend para gerenciamento de ativos de mídia (vídeo, áudio, imagens) com foco em:
> - Multi-tenancy (SaaS)
> - Ingest pipeline (upload, processamento, storage)
> - Metadata extraction (FFprobe)
> - Proxy/thumbnail generation (FFmpeg)
> - Full-text search
> - JWT Authentication
> - Production-ready (99.99% MTBF target)

### Stack Tecnológico

- **Backend**: Python 3.11+, FastAPI, async SQLAlchemy 2.0
- **Database**: PostgreSQL 15+ (partitioning, full-text search)
- **Storage**: MinIO (S3-compatible)
- **Queue**: Celery + RabbitMQ
- **Cache**: Redis
- **Processing**: FFmpeg/FFprobe

---

## Sprint 1: MVP Ingest Pipeline

### Prompt Base

```
Crie uma API FastAPI para gerenciamento de ativos de mídia (MAM) com:

1. Multi-tenancy via tenant_id em todas as tabelas
2. Tabela assets particionada por data
3. Suporte a upload de arquivos para MinIO (S3)
4. Job queue para processamento assíncrono
5. Endpoints CRUD completos para assets

Tecnologias:
- FastAPI com async/await
- SQLAlchemy 2.0 async
- PostgreSQL com UUID, JSONB
- MinIO para object storage

Estrutura de pastas:
app/
├── api/v1/endpoints/
├── core/ (config, database)
├── models/
├── schemas/
└── services/
```

### Detalhes Técnicos Especificados

```
Para a tabela assets:
- Particionamento por RANGE (partition_date)
- Status: pending, ingesting, processing, available, failed
- Tipos: video, audio, image, document
- Checksum SHA256 para integridade

Para storage:
- Buckets: akashi-originals, akashi-proxies, akashi-thumbnails
- Path pattern: {tenant}/{year}/{month}/{asset_id}/{purpose}/{filename}

Para jobs:
- Tipos: metadata, proxy, thumbnail
- Prioridade numérica (menor = maior prioridade)
- Retry com backoff
```

---

## Sprint 2: Keywords & Markers API

### Prompt

```
Adicione ao projeto AKASHI:

1. Sistema de keywords (tags) para assets:
   - Keyword com category e confidence score
   - Source: manual, ai, import
   - Busca global por keywords

2. Sistema de markers (timecode):
   - Tipos: chapter, segment, highlight, comment, scene
   - timecode_in_ms e timecode_out_ms
   - Duration calculada automaticamente

Endpoints REST completos para ambos.
Mantenha tenant isolation.
```

### Considerações

```
- Keywords devem ser normalizadas (lowercase, trim)
- Unique constraint em (asset_id, normalized_keyword)
- Markers ordenados por timecode
- Duration como GENERATED ALWAYS column
```

---

## Sprint 3: JWT Authentication

### Prompt

```
Implemente autenticação JWT no AKASHI:

1. Tabela users com:
   - email (único por tenant)
   - password_hash (bcrypt)
   - role: admin, manager, editor, viewer, user
   - is_superuser para acesso cross-tenant

2. Endpoints:
   - POST /auth/register
   - POST /auth/login (retorna JWT)
   - GET /auth/me
   - PATCH /auth/me
   - POST /auth/me/change-password

3. User management (admin):
   - CRUD de usuários
   - Soft delete (is_active = false)

4. Dependencies:
   - get_current_user
   - get_current_active_user
   - get_current_superuser

Token expira em 30 minutos.
Use python-jose para JWT.
Use bcrypt para password hashing.
```

### Notas de Implementação

```
- bcrypt tem limite de 72 bytes, truncar password
- Não usar passlib (deprecated warnings)
- Token payload: sub, tenant_id, role, exp, iat, type
- Verificar is_active antes de autorizar
```

---

## Sprint 4: Collections & Full-Text Search

### Prompt

```
Adicione ao AKASHI:

1. Collections (playlists/folders):
   - Tipos: manual, smart, system
   - Ownership (created_by)
   - Visibility (is_public)
   - Item ordering (position)
   - item_count denormalizado

2. Full-text search (PostgreSQL):
   - tsvector column em assets
   - Pesos: A=title, B=description, C=code
   - GIN index para performance
   - Trigger para auto-update
   - Idioma: portuguese

Endpoints:
- Collections CRUD + items management
- Search: basic, suggestions, advanced
```

### Detalhes de Search

```sql
-- Estrutura do search_vector
setweight(to_tsvector('portuguese', title), 'A') ||
setweight(to_tsvector('portuguese', description), 'B') ||
setweight(to_tsvector('portuguese', code), 'C')

-- Query com ranking
WHERE search_vector @@ plainto_tsquery('portuguese', $1)
ORDER BY ts_rank(search_vector, query) DESC
```

---

## Sprint 5: Security & Background Processing

### Prompt

```
Finalize a segurança do AKASHI:

1. Refresh Tokens:
   - Tabela refresh_tokens
   - Token rotation (novo token a cada refresh)
   - Revogação (logout, logout-all)
   - Metadata: ip_address, user_agent
   - Hash do token (nunca armazenar plaintext)

2. Rate Limiting:
   - Redis-based sliding window
   - Configurável por .env
   - Headers: X-RateLimit-Limit, Remaining, Reset
   - Fail-open (permite se Redis cair)

3. Celery Workers completos:
   - Tasks: metadata, proxy, thumbnail
   - Ingest pipeline orchestration
   - Maintenance: cleanup, stuck jobs, health check
   - Beat scheduler para tasks periódicas
```

### Configuração

```python
# Refresh tokens
jwt_refresh_token_expire_days = 7
jwt_refresh_token_rotate = True

# Rate limiting
rate_limit_enabled = True
rate_limit_requests = 100
rate_limit_window_seconds = 60
```

---

## Prompts de Debug e Correção

### Problema: bcrypt + passlib

```
Erro: "password cannot be longer than 72 bytes"

Solução: Substituir passlib por bcrypt direto:
- password.encode("utf-8")[:72]
- bcrypt.gensalt() + bcrypt.hashpw()
```

### Problema: SQLAlchemy MissingGreenlet

```
Erro ao acessar relacionamento lazy após operação async

Solução:
- await db.refresh(object) após flush
- Ou usar lazy="joined" no relationship
```

### Problema: Partitioned table + ForeignKey

```
Erro: FK não pode referenciar tabela particionada

Solução: viewonly relationship com primaryjoin explícito:
relationship(
    "Model",
    primaryjoin="Asset.id == foreign(Model.asset_id)",
    viewonly=True,
)
```

---

## Prompt para Testes

```
Crie testes de integração usando pytest + httpx:

1. Fixtures em conftest.py:
   - async client
   - database session
   - test tenant
   - authenticated user

2. Teste cada endpoint:
   - Happy path
   - Validation errors
   - Not found
   - Authentication required

Use pytest-asyncio.
Database isolada por teste.
```

---

## Prompt para Documentação

```
Gere documentação técnica do banco de dados:

1. Por sprint:
   - Tabelas criadas
   - Campos com tipos
   - Indexes
   - Relacionamentos
   - Exemplos de uso

2. Formato Markdown com:
   - SQL de criação
   - Diagramas ER (texto)
   - Exemplos de queries
   - Notas de performance
```

---

## Comandos Úteis para Desenvolvimento

### Iniciar ambiente

```bash
# Subir infraestrutura
docker compose up -d

# Rodar API
uvicorn app.main:app --reload

# Rodar testes
pytest -v

# Processar jobs pendentes
curl -X POST "http://localhost:8000/api/v1/jobs/process-pending?sync=true"
```

### Debug

```bash
# Ver logs do PostgreSQL
docker compose logs -f postgres

# Conectar ao banco
psql postgresql://akashi:akashi_dev_2025@localhost:5432/akashi_mam

# Ver buckets MinIO
mc ls local/
```

---

## Próximas Sprints (Sugestões de Prompts)

### Sprint 6: Audit Logging

```
Implemente audit logging para todas as operações:
- Tabela audit_logs
- Campos: user_id, action, resource_type, resource_id, changes (JSONB)
- Trigger ou decorator para captura automática
- Endpoints para consulta de histórico
```

### Sprint 7: Webhooks

```
Sistema de webhooks para eventos:
- Tabela webhook_subscriptions
- Eventos: asset.created, asset.processed, job.completed
- Retry com exponential backoff
- Signature verification (HMAC)
```

### Sprint 8: Streaming

```
Suporte a HLS/DASH streaming:
- Geração de manifests
- Segmentação de vídeo
- CDN-ready URLs
- Adaptive bitrate profiles
```

---

## Notas Finais

Este documento serve como referência para:
1. Entender as decisões tomadas em cada sprint
2. Replicar o desenvolvimento em outro contexto
3. Treinar outros desenvolvedores ou IAs
4. Manter consistência em futuras extensões

**Versão**: 0.1.0
**Data**: 2026-02-06
**Autor**: Claude (Anthropic) + Tiago Cunha
