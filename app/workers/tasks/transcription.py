"""
Celery tasks for audio/video transcription using Whisper.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from celery import shared_task
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.asset import Asset
from app.models.asset_storage import AssetStorageLocation
from app.models.transcription import AssetTranscription
from app.services.whisper_service import whisper_service
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)


@shared_task(
    name="transcription.transcribe_asset",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="ai",
)
def transcribe_asset(
    self,
    asset_id: str,
    tenant_id: str,
    language: str = "pt",
    model: str = "base",
) -> dict:
    """
    Transcribe an asset's audio/video content.

    Args:
        asset_id: UUID of the asset
        tenant_id: UUID of the tenant
        language: Language code (pt, en, es, etc)
        model: Whisper model to use

    Returns:
        dict with transcription info
    """
    asset_uuid = UUID(asset_id)
    tenant_uuid = UUID(tenant_id)

    logger.info(f"Starting transcription for asset {asset_id}")

    with SessionLocal() as db:
        try:
            # Update asset status
            db.execute(
                update(Asset)
                .where(Asset.id == asset_uuid)
                .values(transcription_status="processing")
            )
            db.commit()

            # Get original file location
            location = db.execute(
                select(AssetStorageLocation)
                .where(AssetStorageLocation.asset_id == asset_uuid)
                .where(AssetStorageLocation.purpose == "original")
            ).scalar_one_or_none()

            if not location:
                raise ValueError(f"No original file found for asset {asset_id}")

            # Download file to temp location
            import tempfile
            from pathlib import Path

            temp_dir = Path(tempfile.gettempdir()) / "akashi_transcribe"
            temp_dir.mkdir(exist_ok=True)

            local_path = temp_dir / location.filename
            storage_service.download_file(
                location.bucket,
                location.object_key,
                str(local_path),
            )

            logger.info(f"Downloaded file to {local_path}")

            # Run transcription
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    whisper_service.transcribe_file(
                        local_path,
                        language=language,
                        model=model,
                    )
                )
            finally:
                loop.close()

            # Clean up temp file
            if local_path.exists():
                local_path.unlink()

            # Check for existing transcription
            existing = db.execute(
                select(AssetTranscription)
                .where(AssetTranscription.asset_id == asset_uuid)
                .where(AssetTranscription.language == result.language)
            ).scalar_one_or_none()

            if existing:
                # Update existing
                existing.full_text = result.full_text
                existing.segments = [s.to_dict() for s in result.segments]
                existing.srt_content = result.to_srt()
                existing.vtt_content = result.to_vtt()
                existing.duration_ms = result.duration_ms
                existing.word_count = result.word_count
                existing.confidence_avg = result.confidence_avg
                existing.model_version = result.model_version
                existing.processing_time_ms = result.processing_time_ms
                existing.updated_at = datetime.now(timezone.utc)
                transcription_id = existing.id
            else:
                # Create new
                transcription = AssetTranscription(
                    asset_id=asset_uuid,
                    tenant_id=tenant_uuid,
                    language=result.language,
                    full_text=result.full_text,
                    segments=[s.to_dict() for s in result.segments],
                    srt_content=result.to_srt(),
                    vtt_content=result.to_vtt(),
                    duration_ms=result.duration_ms,
                    word_count=result.word_count,
                    confidence_avg=result.confidence_avg,
                    model_version=result.model_version,
                    processing_time_ms=result.processing_time_ms,
                )
                db.add(transcription)
                db.flush()
                transcription_id = transcription.id

            # Update asset status
            db.execute(
                update(Asset)
                .where(Asset.id == asset_uuid)
                .values(transcription_status="completed")
            )
            db.commit()

            logger.info(
                f"Transcription completed for asset {asset_id}: "
                f"{result.word_count} words, {result.processing_time_ms}ms"
            )

            return {
                "success": True,
                "asset_id": asset_id,
                "transcription_id": str(transcription_id),
                "language": result.language,
                "word_count": result.word_count,
                "duration_ms": result.duration_ms,
                "processing_time_ms": result.processing_time_ms,
            }

        except Exception as e:
            logger.exception(f"Transcription failed for asset {asset_id}: {e}")

            # Update asset status
            db.execute(
                update(Asset)
                .where(Asset.id == asset_uuid)
                .values(transcription_status="failed")
            )
            db.commit()

            # Retry if retries remaining
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)

            return {
                "success": False,
                "asset_id": asset_id,
                "error": str(e),
            }


@shared_task(
    name="transcription.extract_keywords_from_transcription",
    queue="ai",
)
def extract_keywords_from_transcription(
    asset_id: str,
    tenant_id: str,
    transcription_id: str,
) -> dict:
    """
    Extract keywords from transcription using NLP.

    Args:
        asset_id: UUID of the asset
        tenant_id: UUID of the tenant
        transcription_id: UUID of the transcription

    Returns:
        dict with extracted keywords
    """
    from app.models.scene import AIExtractedKeyword

    asset_uuid = UUID(asset_id)
    tenant_uuid = UUID(tenant_id)
    transcription_uuid = UUID(transcription_id)

    logger.info(f"Extracting keywords from transcription {transcription_id}")

    with SessionLocal() as db:
        try:
            # Get transcription
            transcription = db.execute(
                select(AssetTranscription)
                .where(AssetTranscription.id == transcription_uuid)
            ).scalar_one_or_none()

            if not transcription or not transcription.full_text:
                return {"success": False, "error": "No transcription text found"}

            # Simple keyword extraction using word frequency
            # In production, use spaCy or a proper NLP library
            keywords = _extract_simple_keywords(transcription.full_text)

            # Save keywords
            saved_keywords = []
            for kw, count in keywords[:50]:  # Top 50 keywords
                keyword = AIExtractedKeyword(
                    asset_id=asset_uuid,
                    tenant_id=tenant_uuid,
                    keyword=kw,
                    keyword_normalized=kw.lower(),
                    category="topic",
                    confidence=min(count / 10, 1.0),  # Simple confidence
                    source="whisper",
                )
                db.add(keyword)
                saved_keywords.append(kw)

            db.commit()

            logger.info(f"Extracted {len(saved_keywords)} keywords from transcription")

            return {
                "success": True,
                "asset_id": asset_id,
                "keyword_count": len(saved_keywords),
                "keywords": saved_keywords[:10],  # Return top 10
            }

        except Exception as e:
            logger.exception(f"Keyword extraction failed: {e}")
            return {"success": False, "error": str(e)}


def _extract_simple_keywords(text: str) -> list[tuple[str, int]]:
    """
    Simple keyword extraction based on word frequency.
    Filters out common stop words.
    """
    import re
    from collections import Counter

    # Portuguese and English stop words
    stop_words = {
        # Portuguese
        "a", "o", "e", "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
        "um", "uma", "uns", "umas", "para", "por", "com", "sem", "que", "se", "não",
        "mais", "muito", "também", "como", "mas", "ou", "já", "quando", "onde", "qual",
        "quem", "porque", "então", "esse", "essa", "este", "esta", "isso", "isto",
        "ele", "ela", "eles", "elas", "eu", "você", "nós", "vocês", "meu", "seu",
        "ter", "ser", "estar", "fazer", "foi", "são", "está", "tem", "vai", "era",
        # English
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
        "with", "by", "from", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could", "should",
        "it", "its", "this", "that", "these", "those", "i", "you", "he", "she", "we",
        "they", "what", "which", "who", "when", "where", "why", "how", "all", "each",
    }

    # Tokenize
    words = re.findall(r'\b[a-záàâãéêíóôõúç]{3,}\b', text.lower())

    # Filter and count
    filtered = [w for w in words if w not in stop_words]
    counts = Counter(filtered)

    return counts.most_common()
