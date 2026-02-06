"""
Celery tasks for face detection and identification.
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
from app.models.person import AssetFace, Person
from app.services.face_service import face_service
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)


@shared_task(
    name="face.detect_faces",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="ai",
)
def detect_faces(
    self,
    asset_id: str,
    tenant_id: str,
    sample_interval: float = 1.0,
) -> dict:
    """
    Detect faces in an asset (video or image).

    Args:
        asset_id: UUID of the asset
        tenant_id: UUID of the tenant
        sample_interval: Seconds between video frame samples

    Returns:
        dict with detection info
    """
    asset_uuid = UUID(asset_id)
    tenant_uuid = UUID(tenant_id)

    logger.info(f"Starting face detection for asset {asset_id}")

    with SessionLocal() as db:
        try:
            # Update asset status
            db.execute(
                update(Asset)
                .where(Asset.id == asset_uuid)
                .values(face_detection_status="processing")
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

            # Download file to temp location
            temp_dir = Path(tempfile.gettempdir()) / "akashi_faces"
            temp_dir.mkdir(exist_ok=True)

            local_path = temp_dir / location.filename
            storage_service.download_file(
                location.bucket,
                location.object_key,
                str(local_path),
            )

            logger.info(f"Downloaded file to {local_path}")

            # Run face detection
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                if asset.asset_type == "video":
                    faces = loop.run_until_complete(
                        face_service.detect_faces_in_video(
                            local_path,
                            sample_interval=sample_interval,
                        )
                    )
                else:
                    faces = loop.run_until_complete(
                        face_service.detect_faces_in_image(local_path)
                    )
            finally:
                loop.close()

            # Clean up temp file
            if local_path.exists():
                local_path.unlink()

            # Save faces to database
            saved_count = 0
            for face in faces:
                # Upload face thumbnail to storage
                thumbnail_url = None
                if face.thumbnail:
                    thumb_key = f"{tenant_id}/{asset_id}/faces/{saved_count}.jpg"
                    storage_service.upload_bytes(
                        "akashi-thumbnails",
                        thumb_key,
                        face.thumbnail,
                        content_type="image/jpeg",
                    )
                    thumbnail_url = storage_service.get_presigned_url(
                        "akashi-thumbnails",
                        thumb_key,
                    )

                # Insert face with embedding using raw SQL for vector type
                db.execute(
                    text("""
                        INSERT INTO asset_faces
                        (asset_id, tenant_id, timecode_ms, duration_ms,
                         bbox_x, bbox_y, bbox_w, bbox_h,
                         face_embedding, thumbnail_url, confidence)
                        VALUES
                        (:asset_id, :tenant_id, :timecode_ms, :duration_ms,
                         :bbox_x, :bbox_y, :bbox_w, :bbox_h,
                         :embedding::vector, :thumbnail_url, :confidence)
                    """),
                    {
                        "asset_id": asset_uuid,
                        "tenant_id": tenant_uuid,
                        "timecode_ms": face.timecode_ms or 0,
                        "duration_ms": None,
                        "bbox_x": face.bbox[0],
                        "bbox_y": face.bbox[1],
                        "bbox_w": face.bbox[2],
                        "bbox_h": face.bbox[3],
                        "embedding": str(face.embedding),
                        "thumbnail_url": thumbnail_url,
                        "confidence": face.confidence,
                    }
                )
                saved_count += 1

            # Update asset status
            db.execute(
                update(Asset)
                .where(Asset.id == asset_uuid)
                .values(face_detection_status="completed")
            )
            db.commit()

            logger.info(f"Face detection completed for asset {asset_id}: {saved_count} faces")

            return {
                "success": True,
                "asset_id": asset_id,
                "faces_detected": saved_count,
            }

        except Exception as e:
            logger.exception(f"Face detection failed for asset {asset_id}: {e}")

            # Update asset status
            db.execute(
                update(Asset)
                .where(Asset.id == asset_uuid)
                .values(face_detection_status="failed")
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
    name="face.identify_faces",
    queue="ai",
)
def identify_faces(
    asset_id: str,
    tenant_id: str,
    min_similarity: float = 0.6,
) -> dict:
    """
    Try to identify detected faces by matching with known persons.

    Args:
        asset_id: UUID of the asset
        tenant_id: UUID of the tenant
        min_similarity: Minimum similarity threshold

    Returns:
        dict with identification results
    """
    asset_uuid = UUID(asset_id)
    tenant_uuid = UUID(tenant_id)

    logger.info(f"Starting face identification for asset {asset_id}")

    with SessionLocal() as db:
        try:
            # Get all unidentified faces for this asset
            faces = db.execute(
                select(AssetFace)
                .where(AssetFace.asset_id == asset_uuid)
                .where(AssetFace.person_id.is_(None))
            ).scalars().all()

            if not faces:
                return {
                    "success": True,
                    "asset_id": asset_id,
                    "identified": 0,
                    "message": "No unidentified faces found",
                }

            # Get all known persons for this tenant with embeddings
            persons = db.execute(
                text("""
                    SELECT id, name, reference_embedding::text
                    FROM persons
                    WHERE tenant_id = :tenant_id
                    AND reference_embedding IS NOT NULL
                """),
                {"tenant_id": tenant_uuid}
            ).fetchall()

            if not persons:
                return {
                    "success": True,
                    "asset_id": asset_id,
                    "identified": 0,
                    "message": "No known persons to match against",
                }

            # Match faces to persons
            identified_count = 0

            for face in faces:
                # Get face embedding
                face_embedding_result = db.execute(
                    text("""
                        SELECT face_embedding::text
                        FROM asset_faces
                        WHERE id = :face_id
                    """),
                    {"face_id": face.id}
                ).scalar()

                if not face_embedding_result:
                    continue

                face_embedding = _parse_vector(face_embedding_result)

                # Find best matching person
                best_match = None
                best_similarity = 0

                for person in persons:
                    person_embedding = _parse_vector(person[2])
                    similarity = face_service.compute_similarity(
                        face_embedding,
                        person_embedding,
                    )

                    if similarity > best_similarity and similarity >= min_similarity:
                        best_similarity = similarity
                        best_match = person

                if best_match:
                    # Update face with person_id
                    db.execute(
                        update(AssetFace)
                        .where(AssetFace.id == face.id)
                        .values(person_id=best_match[0])
                    )

                    # Update person appearance count
                    db.execute(
                        update(Person)
                        .where(Person.id == best_match[0])
                        .values(appearance_count=Person.appearance_count + 1)
                    )

                    identified_count += 1
                    logger.debug(
                        f"Face {face.id} identified as {best_match[1]} "
                        f"(similarity: {best_similarity:.2f})"
                    )

            db.commit()

            logger.info(
                f"Face identification completed for asset {asset_id}: "
                f"{identified_count}/{len(faces)} identified"
            )

            return {
                "success": True,
                "asset_id": asset_id,
                "total_faces": len(faces),
                "identified": identified_count,
            }

        except Exception as e:
            logger.exception(f"Face identification failed: {e}")
            return {
                "success": False,
                "asset_id": asset_id,
                "error": str(e),
            }


@shared_task(
    name="face.update_person_embedding",
    queue="ai",
)
def update_person_embedding(person_id: str) -> dict:
    """
    Update a person's reference embedding by averaging all their face embeddings.

    Args:
        person_id: UUID of the person

    Returns:
        dict with update result
    """
    import numpy as np

    person_uuid = UUID(person_id)

    logger.info(f"Updating embedding for person {person_id}")

    with SessionLocal() as db:
        try:
            # Get all face embeddings for this person
            results = db.execute(
                text("""
                    SELECT face_embedding::text
                    FROM asset_faces
                    WHERE person_id = :person_id
                    AND face_embedding IS NOT NULL
                """),
                {"person_id": person_uuid}
            ).fetchall()

            if not results:
                return {
                    "success": False,
                    "person_id": person_id,
                    "error": "No faces found for this person",
                }

            # Parse and average embeddings
            embeddings = [_parse_vector(r[0]) for r in results]
            avg_embedding = np.mean(embeddings, axis=0).tolist()

            # Update person's reference embedding
            db.execute(
                text("""
                    UPDATE persons
                    SET reference_embedding = :embedding::vector,
                        updated_at = NOW()
                    WHERE id = :person_id
                """),
                {
                    "person_id": person_uuid,
                    "embedding": str(avg_embedding),
                }
            )
            db.commit()

            logger.info(f"Updated embedding for person {person_id} from {len(embeddings)} faces")

            return {
                "success": True,
                "person_id": person_id,
                "faces_used": len(embeddings),
            }

        except Exception as e:
            logger.exception(f"Failed to update person embedding: {e}")
            return {
                "success": False,
                "person_id": person_id,
                "error": str(e),
            }


def _parse_vector(vector_str: str) -> list[float]:
    """Parse PostgreSQL vector string to list of floats."""
    # Vector format: [0.1,0.2,0.3,...] or (0.1,0.2,0.3,...)
    clean = vector_str.strip("[]()").replace(" ", "")
    return [float(x) for x in clean.split(",") if x]
