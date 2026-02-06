# AKASHI MAM - Estratégia DevOps

**Data:** 2026-02-05
**Autor:** DevOps Strategy AI
**Versão:** 1.0

---

## 1. Visão Geral

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    AKASHI DevOps Maturity Roadmap                            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ATUAL ──────────────────────────────────────────────────────────> ALVO     ║
║                                                                              ║
║  [Dev Local]  →  [CI/CD]  →  [Staging]  →  [Prod]  →  [Scale]               ║
║   Sprint 1       Sprint 1.5   Sprint 2     Sprint 3    Sprint 4+            ║
║                                                                              ║
║  ✅ Você está                                                               ║
║     aqui                                                                     ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## 2. Sprint 1.5: DevOps Foundation

### 2.1 Objetivos
- [ ] CI Pipeline funcionando (GitHub Actions)
- [ ] Testes automatizados básicos
- [ ] Docker image production-ready
- [ ] Documentação de operação

### 2.2 Entregáveis Criados

| Arquivo | Descrição | Status |
|---------|-----------|--------|
| `.github/workflows/ci.yml` | Pipeline CI/CD | ✅ Criado |
| `Dockerfile` | Multi-stage build | ✅ Criado |
| `docker-compose.yml` | Compose production-ready | ✅ Atualizado |
| `.env.example` | Template de configuração | ✅ Atualizado |
| `tests/conftest.py` | Fixtures de teste | ✅ Criado |
| `tests/test_*.py` | Testes iniciais | ✅ Criados |
| `infra/prometheus/` | Config de métricas | ✅ Criado |
| `infra/grafana/` | Config de dashboards | ✅ Criado |
| `Makefile` | Automação de comandos | ✅ Atualizado |

---

## 3. Arquitetura de Ambientes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEVELOPMENT (Local)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  docker compose up                                                           │
│  ├── PostgreSQL (pgvector) :5433                                            │
│  ├── MinIO :9000/:9001                                                      │
│  ├── Redis :6379                                                            │
│  └── RabbitMQ :5672/:15672                                                  │
│                                                                              │
│  uvicorn app.main:app --reload :8000                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ git push
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CI/CD (GitHub Actions)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  Triggers: push to main/develop, pull requests                              │
│                                                                              │
│  Jobs:                                                                       │
│  ├── lint      → Ruff, Black, MyPy                                         │
│  ├── test      → Pytest com services (Postgres, MinIO)                     │
│  ├── security  → Trivy vulnerability scan                                   │
│  └── build     → Docker build + push to GHCR                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ docker image
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STAGING (Futuro)                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  docker compose --profile all up                                            │
│  ├── Todos os services                                                      │
│  ├── API containerizada                                                     │
│  ├── Workers Celery                                                         │
│  └── Monitoring (Prometheus, Grafana, Loki)                                │
│                                                                              │
│  URL: staging.akashi.example.com                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ aprovação
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PRODUCTION (Futuro)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  Kubernetes / Docker Swarm                                                  │
│  ├── API (replicas: 3)                                                     │
│  ├── Workers (replicas: 5)                                                 │
│  ├── Managed PostgreSQL (RDS, Cloud SQL)                                   │
│  ├── Managed Redis (ElastiCache)                                           │
│  └── S3/MinIO (persistent storage)                                         │
│                                                                              │
│  URL: api.akashi.example.com                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Pipeline CI/CD

### 4.1 Fluxo

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Commit  │───▶│   Lint   │───▶│  Tests   │───▶│ Security │───▶│  Build   │
│          │    │          │    │          │    │          │    │          │
│  (push)  │    │ ruff     │    │ pytest   │    │ trivy    │    │ docker   │
│          │    │ black    │    │ coverage │    │          │    │ push     │
│          │    │ mypy     │    │          │    │          │    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                     │               │               │               │
                     ▼               ▼               ▼               ▼
                  ❌ Fail         ❌ Fail        ⚠️ Warn         ✅ Pass
                 (block PR)     (block PR)    (continue)      (merge OK)
```

### 4.2 Branches

| Branch | Propósito | Deploy |
|--------|-----------|--------|
| `main` | Produção | Auto para prod |
| `develop` | Integração | Auto para staging |
| `feature/*` | Desenvolvimento | Apenas CI |
| `hotfix/*` | Correções urgentes | Manual |

---

## 5. Comandos Principais

### 5.1 Desenvolvimento Local

```bash
# Setup inicial
make install

# Subir infraestrutura
make up

# Rodar API
make dev

# Ver logs
make logs

# Health check
make health
```

### 5.2 Docker

```bash
# Core services apenas
docker compose up -d

# Com workers
docker compose --profile workers up -d

# Com monitoring
docker compose --profile monitoring up -d

# Tudo
docker compose --profile all up -d
```

### 5.3 Testes

```bash
# Todos os testes
make test

# Testes rápidos (para no primeiro erro)
make test-fast

# Com coverage
pytest tests/ -v --cov=app --cov-report=html
```

### 5.4 Debug Dashboard

```bash
# Windows (abre 3 terminais)
scripts\start_debug.bat

# Linux/Mac
make dev &
make debug-mon &
make debug-watch &
```

---

## 6. Próximos Passos

### 6.1 Imediato (Esta Semana)

1. **Validar CI Pipeline**
   ```bash
   # Criar branch de teste
   git checkout -b test/ci-pipeline
   git push -u origin test/ci-pipeline
   # Verificar GitHub Actions
   ```

2. **Baixar imagens Docker**
   ```bash
   # Resolver problema de rede
   docker pull redis:7-alpine
   docker pull rabbitmq:3-management-alpine
   ```

3. **Rodar testes localmente**
   ```bash
   make install
   make test
   ```

### 6.2 Sprint 2

1. **Staging Environment**
   - Deploy automatizado
   - Testes de integração
   - Smoke tests

2. **Secrets Management**
   - GitHub Secrets
   - Vault ou similar

3. **Alerting**
   - Prometheus alerts
   - Slack/Discord integration

### 6.3 Sprint 3+

1. **Production Deploy**
   - Blue/green deployment
   - Rollback automation
   - Health monitoring

2. **Scaling**
   - Kubernetes manifests
   - Horizontal pod autoscaling
   - Database read replicas

---

## 7. Métricas de Sucesso

| Métrica | Atual | Alvo Sprint 1.5 | Alvo Sprint 3 |
|---------|-------|-----------------|---------------|
| Test Coverage | 0% | 30% | 70% |
| Build Time | N/A | <5 min | <3 min |
| Deploy Frequency | Manual | 1/dia | On demand |
| Lead Time | Dias | Horas | Minutos |
| MTTR | N/A | <1 hora | <15 min |

---

## 8. Arquivos Criados

```
akashi-api/
├── .github/
│   └── workflows/
│       └── ci.yml              # Pipeline CI/CD
├── infra/
│   ├── prometheus/
│   │   └── prometheus.yml      # Config de métricas
│   └── grafana/
│       └── provisioning/
│           └── datasources/
│               └── datasources.yml
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Fixtures de teste
│   ├── test_health.py          # Testes de health check
│   └── test_assets.py          # Testes de assets
├── Dockerfile                   # Multi-stage build
├── docker-compose.yml           # Production-ready compose
├── .env.example                 # Template de configuração
├── Makefile                     # Automação de comandos
└── docs/
    └── DEVOPS_STRATEGY.md       # Este documento
```

---

## 9. Checklist de Validação

- [ ] `docker compose up` funciona sem erros
- [ ] `make test` passa (ou pelo menos roda)
- [ ] `docker build .` completa com sucesso
- [ ] GitHub Actions executa na primeira push
- [ ] Health check retorna dados de DB e Storage

---

*Documento gerado como parte da estratégia DevOps do AKASHI MAM*
