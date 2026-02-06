# =============================================================================
# AKASHI MAM API - Makefile
# =============================================================================
# Uso: make <comando>
# =============================================================================

.PHONY: help install dev test lint format docker-up docker-down clean

# Default target
help:
	@echo "AKASHI MAM API - Comandos disponíveis:"
	@echo ""
	@echo "  Desenvolvimento:"
	@echo "    make install      - Instalar dependências"
	@echo "    make dev          - Iniciar servidor de desenvolvimento"
	@echo "    make test         - Rodar testes"
	@echo "    make test-fast    - Rodar testes (falha rápida)"
	@echo "    make lint         - Verificar código"
	@echo "    make format       - Formatar código"
	@echo ""
	@echo "  Docker:"
	@echo "    make up           - Subir infraestrutura (DB, MinIO, Redis)"
	@echo "    make down         - Parar infraestrutura"
	@echo "    make logs         - Ver logs dos containers"
	@echo "    make docker-all   - Subir tudo (infra + app + workers)"
	@echo "    make docker-mon   - Subir com monitoring (Grafana, Prometheus)"
	@echo ""
	@echo "  Workers:"
	@echo "    make worker       - Rodar Celery worker"
	@echo "    make api          - Rodar API"
	@echo ""
	@echo "  Banco de Dados:"
	@echo "    make db-reset     - Resetar banco (CUIDADO!)"
	@echo "    make buckets      - Criar buckets MinIO"
	@echo ""
	@echo "  Debug:"
	@echo "    make debug-start  - Iniciar ambiente de debug (Windows)"
	@echo "    make debug-mon    - Monitor de banco"
	@echo "    make debug-watch  - Folder watcher"
	@echo "    make health       - Verificar saúde dos serviços"
	@echo ""

# =============================================================================
# DESENVOLVIMENTO
# =============================================================================

install:
	pip install -e ".[dev]"
	pre-commit install || true

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

api:
	python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	python scripts/run_worker.py

worker-proxy:
	python scripts/run_worker.py proxy

worker-metadata:
	python scripts/run_worker.py metadata

worker-thumbnail:
	python scripts/run_worker.py thumbnail

test:
	pytest tests/ -v --cov=app --cov-report=term-missing

test-fast:
	pytest tests/ -v -x --ff

lint:
	ruff check app/ tests/
	mypy app/ --ignore-missing-imports

format:
	black app/ tests/
	ruff check --fix app/ tests/

# =============================================================================
# DOCKER
# =============================================================================

up:
	docker compose up -d postgres minio redis rabbitmq minio-setup
	@echo "Waiting for services to be healthy..."
	@sleep 5
	@docker compose ps

down:
	docker compose down

logs:
	docker compose logs -f

docker-all:
	docker compose --profile all up -d

docker-mon:
	docker compose --profile monitoring up -d

docker-build:
	docker compose build

# Backwards compatibility
up-minimal:
	docker compose -f docker-compose.minimal.yml up -d 2>/dev/null || docker compose up -d postgres minio redis rabbitmq

# =============================================================================
# BANCO DE DADOS
# =============================================================================

db-reset:
	@echo "CUIDADO: Isso vai apagar todos os dados!"
	docker compose down -v
	docker compose up -d postgres
	@echo "Waiting for PostgreSQL..."
	@sleep 10
	@echo "Database reset complete."

buckets:
	docker exec akashi-minio mc alias set local http://localhost:9000 akashi akashi_minio_2025 || true
	docker exec akashi-minio mc mb local/akashi-originals --ignore-existing || true
	docker exec akashi-minio mc mb local/akashi-proxies --ignore-existing || true
	docker exec akashi-minio mc mb local/akashi-thumbnails --ignore-existing || true
	docker exec akashi-minio mc ls local/

# =============================================================================
# DEBUG
# =============================================================================

debug-start:
	scripts/start_debug.bat

debug-mon:
	python scripts/db_monitor.py

debug-watch:
	python scripts/folder_watcher.py

health:
	@echo "=== Docker Containers ==="
	@docker compose ps
	@echo ""
	@echo "=== API Health ==="
	@curl -s http://localhost:8000/api/v1/health | python -m json.tool 2>/dev/null || echo "API not running"
	@echo ""

# =============================================================================
# PRODUÇÃO
# =============================================================================

build:
	docker build -t akashi-api:latest .

push:
	docker tag akashi-api:latest ghcr.io/tscunha/akashi-api:latest
	docker push ghcr.io/tscunha/akashi-api:latest

# =============================================================================
# UTILITÁRIOS
# =============================================================================

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

shell:
	ipython
