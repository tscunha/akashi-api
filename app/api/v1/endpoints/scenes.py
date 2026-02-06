"""
Scene description API endpoints.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_tenant_id
from app.models.asset import Asset
from app.models.scene import AssetSceneDescription, AIExtractedKeyword
from app.models.user import User
from app.schemas.scene import (
    AIKeywordRead,
    DescribeRequest,
    DescribeResponse,
    SceneDescriptionRead,
)

router = APIRouter()


@router.get("/{asset_id}/scenes", response_model=list[SceneDescriptionRead])
async def list_asset_scenes(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """List all scene descriptions for an asset."""
    result = await db.execute(
        select(AssetSceneDescription)
        .where(AssetSceneDescription.asset_id == asset_id)
        .where(AssetSceneDescription.tenant_id == tenant_id)
        .order_by(AssetSceneDescription.timecode_start_ms)
    )
    return result.scalars().all()


@router.get("/{asset_id}/scenes/{scene_id}", response_model=SceneDescriptionRead)
async def get_scene(
    asset_id: UUID,
    scene_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Get a specific scene description."""
    result = await db.execute(
        select(AssetSceneDescription)
        .where(AssetSceneDescription.id == scene_id)
        .where(AssetSceneDescription.asset_id == asset_id)
        .where(AssetSceneDescription.tenant_id == tenant_id)
    )
    scene = result.scalar_one_or_none()

    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found",
        )

    return scene


@router.post("/{asset_id}/describe", response_model=DescribeResponse)
async def start_scene_description(
    asset_id: UUID,
    request: DescribeRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Start scene description analysis for an asset."""
    from app.models.asset_storage import IngestJob

    # Verify asset exists
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id)
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )

    if asset.asset_type not in ("video", "image"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scene description only available for video and image assets",
        )

    # Create job
    job = IngestJob(
        asset_id=asset_id,
        tenant_id=tenant_id,
        job_type="scene_description",
        status="pending",
        priority=5,
        config={
            "interval_seconds": request.interval_seconds,
            "model": request.model,
        },
    )
    db.add(job)
    await db.flush()
    await db.commit()

    # Queue task
    from app.workers.tasks.scene_description import describe_scenes

    describe_scenes.delay(
        asset_id=str(asset_id),
        tenant_id=str(tenant_id),
        interval_seconds=request.interval_seconds,
    )

    return DescribeResponse(
        job_id=job.id,
        asset_id=asset_id,
        status="pending",
        message=f"Scene description started with {request.interval_seconds}s intervals",
    )


@router.get("/{asset_id}/ai-keywords", response_model=list[AIKeywordRead])
async def list_ai_keywords(
    asset_id: UUID,
    category: str | None = None,
    source: str | None = None,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """List AI-extracted keywords for an asset."""
    query = (
        select(AIExtractedKeyword)
        .where(AIExtractedKeyword.asset_id == asset_id)
        .where(AIExtractedKeyword.tenant_id == tenant_id)
    )

    if category:
        query = query.where(AIExtractedKeyword.category == category)

    if source:
        query = query.where(AIExtractedKeyword.source == source)

    query = query.order_by(AIExtractedKeyword.confidence.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{asset_id}/timeline")
async def get_asset_timeline(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """
    Get a combined timeline of all AI analyses for an asset.

    Returns scenes, faces, and transcription segments in chronological order.
    """
    from app.models.transcription import AssetTranscription
    from app.models.person import AssetFace

    # Get scenes
    scenes_result = await db.execute(
        select(AssetSceneDescription)
        .where(AssetSceneDescription.asset_id == asset_id)
        .where(AssetSceneDescription.tenant_id == tenant_id)
    )
    scenes = scenes_result.scalars().all()

    # Get faces
    faces_result = await db.execute(
        select(AssetFace)
        .where(AssetFace.asset_id == asset_id)
        .where(AssetFace.tenant_id == tenant_id)
    )
    faces = faces_result.scalars().all()

    # Get transcription segments
    transcription_result = await db.execute(
        select(AssetTranscription)
        .where(AssetTranscription.asset_id == asset_id)
        .where(AssetTranscription.tenant_id == tenant_id)
    )
    transcription = transcription_result.scalar_one_or_none()

    # Build timeline
    timeline = []

    for scene in scenes:
        timeline.append({
            "type": "scene",
            "start_ms": scene.timecode_start_ms,
            "end_ms": scene.timecode_end_ms,
            "data": {
                "id": str(scene.id),
                "description": scene.description,
                "objects": scene.objects,
            },
        })

    for face in faces:
        timeline.append({
            "type": "face",
            "start_ms": face.timecode_ms,
            "end_ms": face.timecode_ms + (face.duration_ms or 1000),
            "data": {
                "id": str(face.id),
                "person_id": str(face.person_id) if face.person_id else None,
                "thumbnail_url": face.thumbnail_url,
                "confidence": face.confidence,
            },
        })

    if transcription and transcription.segments:
        for segment in transcription.segments:
            timeline.append({
                "type": "transcription",
                "start_ms": segment.get("start_ms", 0),
                "end_ms": segment.get("end_ms", 0),
                "data": {
                    "text": segment.get("text", ""),
                    "confidence": segment.get("confidence"),
                },
            })

    # Sort by start time
    timeline.sort(key=lambda x: x["start_ms"])

    return {
        "asset_id": str(asset_id),
        "timeline": timeline,
        "stats": {
            "scenes": len(scenes),
            "faces": len(faces),
            "transcription_segments": len(transcription.segments) if transcription else 0,
        },
    }
