# AKASHI MAM API

**REST API for AKASHI Media Asset Management System**

FastAPI-based backend for managing media assets with support for ingest, processing, and search.

## Features

- **Asset Management**: CRUD operations for media assets
- **File Upload**: Direct upload to MinIO/S3 storage
- **Processing Pipeline**: Celery workers for proxy generation, thumbnails, and metadata extraction
- **Multi-tenant**: Built-in tenant isolation
- **OpenAPI Docs**: Auto-generated API documentation

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        AKASHI API                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ POST /assets│  │POST /ingest │  │ GET /assets             │  │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────────────┘  │
│         └────────────────┴──────────────────────────────────────│
└─────────────────────────────────────────────────────────────────┘
         │                │                    │
         ▼                ▼                    ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────────┐
│ PostgreSQL  │    │   MinIO     │    │   RabbitMQ      │
│ (pgvector)  │    │ (S3)        │    │ (job queue)     │
└─────────────┘    └─────────────┘    └─────────────────┘
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- FFmpeg (for media processing)

### 1. Start Infrastructure

```bash
docker compose up -d
```

This starts:
- PostgreSQL 16 with pgvector (port 5432)
- MinIO S3-compatible storage (ports 9000, 9001)
- Redis (port 6379)
- RabbitMQ (ports 5672, 15672)

### 2. Setup Python Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -e ".[dev]"
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env if needed
```

### 4. Run API

```bash
# Development mode with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Run Workers (optional)

```bash
# In a separate terminal
celery -A app.workers.celery_app worker --loglevel=info
```

## API Endpoints

### Health
- `GET /api/v1/health` - Health check

### Assets
- `GET /api/v1/assets` - List assets
- `POST /api/v1/assets` - Create asset (metadata only)
- `GET /api/v1/assets/{id}` - Get asset
- `PATCH /api/v1/assets/{id}` - Update asset
- `DELETE /api/v1/assets/{id}` - Delete asset

### Upload
- `POST /api/v1/ingest` - Upload file and create asset
- `POST /api/v1/assets/{id}/upload` - Upload file to existing asset

## API Documentation

When running in development mode:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
akashi-api/
├── app/
│   ├── api/v1/endpoints/    # API endpoints
│   ├── core/                # Config, database
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # Business logic
│   └── workers/             # Celery tasks
├── scripts/                 # Database init scripts
├── tests/                   # Test files
├── docker-compose.yml       # Dev infrastructure
└── pyproject.toml          # Dependencies
```

## Configuration

Environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| DATABASE_URL | PostgreSQL connection string | postgresql+asyncpg://... |
| S3_ENDPOINT_URL | MinIO/S3 endpoint | http://localhost:9000 |
| CELERY_BROKER_URL | RabbitMQ URL | amqp://... |

## Development

### Run Tests

```bash
pytest
```

### Code Quality

```bash
# Linting
ruff check .

# Type checking
mypy app
```

## License

Proprietary - © 2025 Tiago Cunha

## Links

- [AKASHI MAM](https://github.com/tscunha/akashi-mam) - Documentation
- [AKASHI Ingest Client](https://github.com/tscunha/akashi-ingest-client) - Desktop client
