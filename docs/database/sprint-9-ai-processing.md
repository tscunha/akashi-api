# Sprint 9: AI Processing (Transcription, Face Detection, Scene Analysis)

## Overview

Implements AI-powered content analysis including:
- Speech-to-text transcription (Whisper)
- Face detection and recognition (InsightFace/DeepFace)
- Scene description (GPT-4 Vision)
- Multimodal search across all data sources

## Migration File

`scripts/migrations/004_add_ai_tables.sql`

## Tables Created

### 1. asset_transcriptions

Stores transcriptions from audio/video content.

```sql
CREATE TABLE asset_transcriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    -- Language
    language VARCHAR(10) NOT NULL DEFAULT 'pt',

    -- Content
    full_text TEXT,
    segments JSONB DEFAULT '[]',  -- [{start_ms, end_ms, text, confidence}]

    -- Generated subtitles
    srt_content TEXT,
    vtt_content TEXT,

    -- Metadata
    duration_ms BIGINT,
    word_count INTEGER,
    confidence_avg NUMERIC(4,3),

    -- Processing info
    model_version VARCHAR(50),
    processing_time_ms INTEGER,

    -- Full-text search
    search_vector TSVECTOR,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Indexes:**
- `idx_transcriptions_asset_id` on `asset_id`
- `idx_transcriptions_tenant_id` on `tenant_id`
- `idx_transcriptions_search_vector` GIN index for full-text search

---

### 2. persons

Stores known people for face recognition.

```sql
CREATE TABLE persons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    name VARCHAR(255) NOT NULL,
    role VARCHAR(100),           -- actor, presenter, interviewer
    external_id VARCHAR(255),    -- IMDB, LinkedIn, etc

    -- Reference embedding (average of known faces)
    reference_embedding vector(512),

    metadata JSONB DEFAULT '{}',
    thumbnail_url TEXT,
    appearance_count INTEGER DEFAULT 0,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Indexes:**
- `idx_persons_tenant_id` on `tenant_id`
- `idx_persons_name` on `name`
- `idx_persons_embedding` ivfflat index for similarity search

---

### 3. asset_faces

Stores detected faces in assets.

```sql
CREATE TABLE asset_faces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    -- Identity (if known)
    person_id UUID REFERENCES persons(id) ON DELETE SET NULL,

    -- Temporal location
    timecode_ms BIGINT NOT NULL,
    duration_ms BIGINT,

    -- Bounding box (normalized 0-1)
    bbox_x NUMERIC(5,4),
    bbox_y NUMERIC(5,4),
    bbox_w NUMERIC(5,4),
    bbox_h NUMERIC(5,4),

    -- Face embedding for similarity search
    face_embedding vector(512),

    thumbnail_url TEXT,
    confidence NUMERIC(4,3),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Indexes:**
- `idx_faces_asset_id` on `asset_id`
- `idx_faces_person_id` on `person_id`
- `idx_faces_embedding` ivfflat index for similarity search

---

### 4. asset_scene_descriptions

Stores AI-generated scene descriptions.

```sql
CREATE TABLE asset_scene_descriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    -- Timing
    timecode_start_ms BIGINT NOT NULL,
    timecode_end_ms BIGINT NOT NULL,

    -- Description
    description TEXT NOT NULL,
    description_embedding vector(1536),  -- for semantic search

    -- Detections
    objects JSONB DEFAULT '[]',   -- [{object, confidence, bbox}]
    actions JSONB DEFAULT '[]',   -- [{action, confidence}]
    emotions JSONB DEFAULT '[]',  -- [{emotion, confidence}]
    text_ocr TEXT,                -- detected text on screen

    model_version VARCHAR(100),
    search_vector TSVECTOR,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Indexes:**
- `idx_scenes_asset_id` on `asset_id`
- `idx_scenes_timecode` on `timecode_start_ms`
- `idx_scenes_embedding` ivfflat index for semantic search
- `idx_scenes_search_vector` GIN index for full-text search

---

### 5. ai_extracted_keywords

Stores keywords extracted by AI.

```sql
CREATE TABLE ai_extracted_keywords (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    keyword VARCHAR(255) NOT NULL,
    keyword_normalized VARCHAR(255) NOT NULL,
    category VARCHAR(100),        -- topic, entity, action, emotion, object
    confidence NUMERIC(4,3),
    source VARCHAR(50) DEFAULT 'ai',  -- whisper, vision, llm

    -- Temporal context
    start_ms BIGINT,
    end_ms BIGINT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(asset_id, keyword_normalized, source)
);
```

---

## Services

### WhisperService

Transcription using OpenAI Whisper (local or API).

```python
from app.services.whisper_service import whisper_service

# Transcribe a file
result = await whisper_service.transcribe_file(
    "video.mp4",
    language="pt",
    model="large-v3"
)

# Result contains:
# - full_text: Complete transcription
# - segments: [{start_ms, end_ms, text, confidence}]
# - to_srt(): Generate SRT subtitles
# - to_vtt(): Generate WebVTT subtitles
```

### FaceService

Face detection and recognition using InsightFace.

```python
from app.services.face_service import face_service

# Detect faces in video
faces = await face_service.detect_faces_in_video(
    "video.mp4",
    sample_interval=1.0  # seconds
)

# Each face contains:
# - bbox: (x, y, w, h) normalized
# - embedding: 512-dim vector
# - confidence: detection score
# - timecode_ms: position in video
# - thumbnail: JPEG bytes
```

### VisionService

Scene analysis using GPT-4 Vision.

```python
from app.services.vision_service import vision_service

# Analyze video frames
analyses = await vision_service.analyze_video(
    "video.mp4",
    interval_seconds=10
)

# Each analysis contains:
# - description: Natural language description
# - objects: Detected objects with confidence
# - actions: Detected actions
# - emotions: Detected emotions
# - text_ocr: Text visible in frame
```

### SearchService

Multimodal search across all data sources.

```python
from app.services.search_service import search_service

# Search across transcriptions, scenes, faces, keywords
response = await search_service.search(
    db,
    MultimodalSearchRequest(
        query="homem de terno falando sobre economia",
        modes=SearchMode(
            transcription=True,
            scene=True,
            face=True,
            keywords=True,
        ),
        face_image="base64...",  # optional
    ),
    tenant_id
)
```

---

## API Endpoints

### Transcription

```
GET    /api/v1/assets/{id}/transcription      - Get transcription
POST   /api/v1/assets/{id}/transcribe         - Start transcription
GET    /api/v1/assets/{id}/subtitles.srt      - Download SRT
GET    /api/v1/assets/{id}/subtitles.vtt      - Download VTT
DELETE /api/v1/assets/{id}/transcription      - Delete transcription
```

### Face Detection

```
GET    /api/v1/persons                        - List persons
POST   /api/v1/persons                        - Create person
GET    /api/v1/persons/{id}                   - Get person
PATCH  /api/v1/persons/{id}                   - Update person
DELETE /api/v1/persons/{id}                   - Delete person
GET    /api/v1/persons/{id}/appearances       - Get appearances

GET    /api/v1/assets/{id}/faces              - List detected faces
POST   /api/v1/assets/{id}/detect-faces       - Start face detection
POST   /api/v1/faces/{id}/identify            - Identify a face
POST   /api/v1/faces/search                   - Search by face image
```

### Scene Description

```
GET    /api/v1/assets/{id}/scenes             - List scene descriptions
GET    /api/v1/assets/{id}/scenes/{scene_id}  - Get scene
POST   /api/v1/assets/{id}/describe           - Start scene analysis
GET    /api/v1/assets/{id}/ai-keywords        - Get AI keywords
GET    /api/v1/assets/{id}/timeline           - Get combined timeline
```

### Multimodal Search

```
POST   /api/v1/search/multimodal              - Search all sources
GET    /api/v1/search/multimodal/suggestions  - Get suggestions
```

---

## Configuration

```python
# .env

# Whisper
WHISPER_MODE=local              # local or api
WHISPER_MODEL=base              # tiny, base, small, medium, large-v3
WHISPER_LANGUAGE=pt
WHISPER_DEVICE=cpu              # cuda or cpu

# Face Recognition
FACE_MODEL=buffalo_l
FACE_MIN_CONFIDENCE=0.5
FACE_SAMPLE_INTERVAL=1.0

# Vision AI
VISION_MODE=api
VISION_MODEL=gpt-4-vision-preview
VISION_SAMPLE_INTERVAL=10

# OpenAI API (required for API modes)
OPENAI_API_KEY=sk-...
```

---

## Celery Tasks

| Task | Queue | Description |
|------|-------|-------------|
| `transcription.transcribe_asset` | ai | Run Whisper transcription |
| `transcription.extract_keywords_from_transcription` | ai | Extract keywords from text |
| `face.detect_faces` | ai | Detect faces in video/image |
| `face.identify_faces` | ai | Match faces to known persons |
| `face.update_person_embedding` | ai | Update person reference embedding |
| `scene.describe_scenes` | ai | Analyze scenes with Vision AI |
| `scene.analyze_single_frame` | ai | Analyze single frame |

---

## Example: Multimodal Search

### Request

```bash
curl -X POST http://localhost:8000/api/v1/search/multimodal \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "entrevista sobre economia",
    "modes": {
      "transcription": true,
      "scene": true,
      "keywords": true
    },
    "filters": {
      "asset_type": "video",
      "date_from": "2026-01-01"
    },
    "limit": 20
  }'
```

### Response

```json
{
  "query": "entrevista sobre economia",
  "total": 5,
  "limit": 20,
  "offset": 0,
  "search_time_ms": 45,
  "modes_used": ["transcription", "scene", "keyword"],
  "results": [
    {
      "asset_id": "550e8400-...",
      "title": "Entrevista Economia 2026",
      "asset_type": "video",
      "status": "available",
      "thumbnail_url": "...",
      "duration_ms": 360000,
      "combined_score": 0.89,
      "matches": [
        {
          "type": "transcription",
          "timecode_ms": 45000,
          "text": "...falando sobre <mark>economia</mark> brasileira...",
          "score": 0.92
        },
        {
          "type": "scene",
          "timecode_ms": 44000,
          "description": "Homem de terno em estúdio de TV",
          "score": 0.85
        },
        {
          "type": "keyword",
          "keyword": "economia",
          "score": 1.0
        }
      ]
    }
  ]
}
```

---

## Performance Notes

1. **Vector Indexes**: Using ivfflat for approximate nearest neighbor search
2. **Async Processing**: All AI tasks run in Celery workers
3. **Embeddings**: Using pgvector for efficient similarity search
4. **RRF Ranking**: Reciprocal Rank Fusion combines scores from multiple sources
5. **Full-Text Search**: PostgreSQL tsvector with Portuguese stemming
