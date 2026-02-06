"""
Celery tasks for scene description and visual analysis.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from uuid import UUID

from celery import shared_task
from sqlalchemy import select, update, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.asset import Asset
from app.models.asset_storage import AssetStorageLocation
from app.models.scene import AssetSceneDescription, AIExtractedKeyword
from app.services.vision_service import vision_service
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)


@shared_task(
    name="scene.describe_scenes",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="ai",
)
def describe_scenes(
    self,
    asset_id: str,
    tenant_id: str,
    interval_seconds: int = 10,
) -> dict:
    """
    Analyze scenes in a video using Vision AI.

    Args:
        asset_id: UUID of the asset
        tenant_id: UUID of the tenant
        interval_seconds: Seconds between frame samples

    Returns:
        dict with analysis info
    """
    asset_uuid = UUID(asset_id)
    tenant_uuid = UUID(tenant_id)

    logger.info(f"Starting scene description for asset {asset_id}")

    with SessionLocal() as db:
        try:
            # Update asset status
            db.execute(
                update(Asset)
                .where(Asset.id == asset_uuid)
                .values(scene_description_status="processing")
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

            # Get asset info
            asset = db.execute(
                select(Asset).where(Asset.id == asset_uuid)
            ).scalar_one()

            if asset.asset_type not in ("video", "image"):
                raise ValueError(f"Scene description only for video/image, got {asset.asset_type}")

            # Download file to temp location
            temp_dir = Path(tempfile.gettempdir()) / "akashi_scenes"
            temp_dir.mkdir(exist_ok=True)

            local_path = temp_dir / location.filename
            storage_service.download_file(
                location.bucket,
                location.object_key,
                str(local_path),
            )

            logger.info(f"Downloaded file to {local_path}")

            # Run analysis
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                if asset.asset_type == "video":
                    analyses = loop.run_until_complete(
                        vision_service.analyze_video(
                            local_path,
                            interval_seconds=interval_seconds,
                        )
                    )
                else:
                    analysis = loop.run_until_complete(
                        vision_service.analyze_image(local_path.read_bytes())
                    )
                    analyses = [analysis]

                # Generate embeddings for descriptions
                for analysis in analyses:
                    if analysis.description:
                        try:
                            embedding = loop.run_until_complete(
                                vision_service.generate_embedding(analysis.description)
                            )
                            analysis.embedding = embedding
                        except Exception as e:
                            logger.warning(f"Failed to generate embedding: {e}")
                            analysis.embedding = None
            finally:
                loop.close()

            # Clean up temp file
            if local_path.exists():
                local_path.unlink()

            # Save scene descriptions
            saved_count = 0
            all_keywords = []

            for analysis in analyses:
                # Insert with embedding using raw SQL for vector type
                if hasattr(analysis, "embedding") and analysis.embedding:
                    db.execute(
                        text("""
                            INSERT INTO asset_scene_descriptions
                            (asset_id, tenant_id, timecode_start_ms, timecode_end_ms,
                             description, description_embedding, objects, actions,
                             emotions, text_ocr, model_version)
                            VALUES
                            (:asset_id, :tenant_id, :start_ms, :end_ms,
                             :description, :embedding::vector, :objects, :actions,
                             :emotions, :text_ocr, :model)
                        """),
                        {
                            "asset_id": asset_uuid,
                            "tenant_id": tenant_uuid,
                            "start_ms": analysis.timecode_start_ms,
                            "end_ms": analysis.timecode_end_ms,
                            "description": analysis.description,
                            "embedding": str(analysis.embedding),
                            "objects": str(analysis.objects),
                            "actions": str(analysis.actions),
                            "emotions": str(analysis.emotions),
                            "text_ocr": analysis.text_ocr,
                            "model": vision_service.model,
                        }
                    )
                else:
                    scene = AssetSceneDescription(
                        asset_id=asset_uuid,
                        tenant_id=tenant_uuid,
                        timecode_start_ms=analysis.timecode_start_ms,
                        timecode_end_ms=analysis.timecode_end_ms,
                        description=analysis.description,
                        objects=analysis.objects,
                        actions=analysis.actions,
                        emotions=analysis.emotions,
                        text_ocr=analysis.text_ocr,
                        model_version=vision_service.model,
                    )
                    db.add(scene)

                saved_count += 1

                # Collect objects and actions as keywords
                for obj in analysis.objects:
                    all_keywords.append({
                        "keyword": obj.get("object", ""),
                        "category": "object",
                        "confidence": obj.get("confidence", 0.5),
                        "start_ms": analysis.timecode_start_ms,
                        "end_ms": analysis.timecode_end_ms,
                    })

                for action in analysis.actions:
                    all_keywords.append({
                        "keyword": action.get("action", ""),
                        "category": "action",
                        "confidence": action.get("confidence", 0.5),
                        "start_ms": analysis.timecode_start_ms,
                        "end_ms": analysis.timecode_end_ms,
                    })

                for emotion in analysis.emotions:
                    all_keywords.append({
                        "keyword": emotion.get("emotion", ""),
                        "category": "emotion",
                        "confidence": emotion.get("confidence", 0.5),
                        "start_ms": analysis.timecode_start_ms,
                        "end_ms": analysis.timecode_end_ms,
                    })

            # Save unique keywords
            seen_keywords = set()
            for kw in all_keywords:
                keyword = kw["keyword"].strip().lower()
                if not keyword or keyword in seen_keywords:
                    continue
                seen_keywords.add(keyword)

                ai_keyword = AIExtractedKeyword(
                    asset_id=asset_uuid,
                    tenant_id=tenant_uuid,
                    keyword=kw["keyword"],
                    keyword_normalized=keyword,
                    category=kw["category"],
                    confidence=kw["confidence"],
                    source="vision",
                    start_ms=kw["start_ms"],
                    end_ms=kw["end_ms"],
                )
                db.add(ai_keyword)

            # Update asset status
            db.execute(
                update(Asset)
                .where(Asset.id == asset_uuid)
                .values(scene_description_status="completed")
            )
            db.commit()

            logger.info(
                f"Scene description completed for asset {asset_id}: "
                f"{saved_count} scenes, {len(seen_keywords)} keywords"
            )

            return {
                "success": True,
                "asset_id": asset_id,
                "scenes_analyzed": saved_count,
                "keywords_extracted": len(seen_keywords),
            }

        except Exception as e:
            logger.exception(f"Scene description failed for asset {asset_id}: {e}")

            db.execute(
                update(Asset)
                .where(Asset.id == asset_uuid)
                .values(scene_description_status="failed")
            )
            db.commit()

            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)

            return {
                "success": False,
                "asset_id": asset_id,
                "error": str(e),
            }


@shared_task(
    name="scene.analyze_single_frame",
    queue="ai",
)
def analyze_single_frame(
    asset_id: str,
    tenant_id: str,
    timecode_ms: int,
) -> dict:
    """
    Analyze a single frame from a video.

    Args:
        asset_id: UUID of the asset
        tenant_id: UUID of the tenant
        timecode_ms: Timecode in milliseconds

    Returns:
        dict with analysis result
    """
    import cv2
    import tempfile
    from pathlib import Path

    asset_uuid = UUID(asset_id)
    tenant_uuid = UUID(tenant_id)

    logger.info(f"Analyzing frame at {timecode_ms}ms for asset {asset_id}")

    with SessionLocal() as db:
        try:
            # Get original file
            location = db.execute(
                select(AssetStorageLocation)
                .where(AssetStorageLocation.asset_id == asset_uuid)
                .where(AssetStorageLocation.purpose == "original")
            ).scalar_one_or_none()

            if not location:
                raise ValueError("Original file not found")

            # Download file
            temp_dir = Path(tempfile.gettempdir()) / "akashi_frame"
            temp_dir.mkdir(exist_ok=True)
            local_path = temp_dir / location.filename

            storage_service.download_file(
                location.bucket,
                location.object_key,
                str(local_path),
            )

            # Extract specific frame
            cap = cv2.VideoCapture(str(local_path))
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_number = int((timecode_ms / 1000) * fps)

            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = cap.read()
            cap.release()

            if not ret:
                raise ValueError(f"Could not extract frame at {timecode_ms}ms")

            # Encode to JPEG
            _, frame_bytes = cv2.imencode(".jpg", frame)

            # Analyze
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                analysis = loop.run_until_complete(
                    vision_service.analyze_image(frame_bytes.tobytes())
                )
            finally:
                loop.close()

            # Clean up
            if local_path.exists():
                local_path.unlink()

            return {
                "success": True,
                "asset_id": asset_id,
                "timecode_ms": timecode_ms,
                "description": analysis.description,
                "objects": analysis.objects,
                "actions": analysis.actions,
            }

        except Exception as e:
            logger.exception(f"Frame analysis failed: {e}")
            return {
                "success": False,
                "asset_id": asset_id,
                "error": str(e),
            }
