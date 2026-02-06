"""
Transcription API endpoints.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_tenant_id
from app.models.asset import Asset
from app.models.transcription import AssetTranscription
from app.models.user import User
from app.schemas.transcription import (
    TranscribeRequest,
    TranscribeResponse,
    TranscriptionRead,
    TranscriptionSummary,
)

router = APIRouter()


@router.get("/{asset_id}/transcription", response_model=TranscriptionRead | None)
async def get_asset_transcription(
    asset_id: UUID,
    language: str = "pt",
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Get the transcription for an asset."""
    # Verify asset exists and belongs to tenant
    asset = await db.execute(
        select(Asset).where(Asset.id == asset_id)
    )
    asset = asset.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )

    # Get transcription
    result = await db.execute(
        select(AssetTranscription)
        .where(AssetTranscription.asset_id == asset_id)
        .where(AssetTranscription.tenant_id == tenant_id)
        .where(AssetTranscription.language == language)
    )
    transcription = result.scalar_one_or_none()

    if not transcription:
        return None

    return transcription


@router.post("/{asset_id}/transcribe", response_model=TranscribeResponse)
async def start_transcription(
    asset_id: UUID,
    request: TranscribeRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Start transcription of an asset."""
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

    # Check if asset is video or audio
    if asset.asset_type not in ("video", "audio"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcription only available for video and audio assets",
        )

    # Create a job for transcription
    job = IngestJob(
        asset_id=asset_id,
        tenant_id=tenant_id,
        job_type="transcription",
        status="pending",
        priority=5,
        config={
            "language": request.language,
            "model": request.model,
        },
    )
    db.add(job)
    await db.flush()
    await db.commit()

    # Queue the Celery task
    from app.workers.tasks.transcription import transcribe_asset

    transcribe_asset.delay(
        asset_id=str(asset_id),
        tenant_id=str(tenant_id),
        language=request.language,
        model=request.model,
    )

    return TranscribeResponse(
        job_id=job.id,
        asset_id=asset_id,
        status="pending",
        message=f"Transcription started with model {request.model}",
    )


@router.get("/{asset_id}/subtitles.srt")
async def get_srt_subtitles(
    asset_id: UUID,
    language: str = "pt",
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Download SRT subtitle file for an asset."""
    result = await db.execute(
        select(AssetTranscription)
        .where(AssetTranscription.asset_id == asset_id)
        .where(AssetTranscription.tenant_id == tenant_id)
        .where(AssetTranscription.language == language)
    )
    transcription = result.scalar_one_or_none()

    if not transcription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcription not found",
        )

    srt_content = transcription.srt_content or transcription.to_srt()

    return Response(
        content=srt_content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{asset_id}_{language}.srt"'
        },
    )


@router.get("/{asset_id}/subtitles.vtt")
async def get_vtt_subtitles(
    asset_id: UUID,
    language: str = "pt",
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Download WebVTT subtitle file for an asset."""
    result = await db.execute(
        select(AssetTranscription)
        .where(AssetTranscription.asset_id == asset_id)
        .where(AssetTranscription.tenant_id == tenant_id)
        .where(AssetTranscription.language == language)
    )
    transcription = result.scalar_one_or_none()

    if not transcription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcription not found",
        )

    vtt_content = transcription.vtt_content or transcription.to_vtt()

    return Response(
        content=vtt_content,
        media_type="text/vtt",
        headers={
            "Content-Disposition": f'attachment; filename="{asset_id}_{language}.vtt"'
        },
    )


@router.delete("/{asset_id}/transcription")
async def delete_transcription(
    asset_id: UUID,
    language: str = "pt",
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Delete a transcription."""
    result = await db.execute(
        select(AssetTranscription)
        .where(AssetTranscription.asset_id == asset_id)
        .where(AssetTranscription.tenant_id == tenant_id)
        .where(AssetTranscription.language == language)
    )
    transcription = result.scalar_one_or_none()

    if not transcription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcription not found",
        )

    await db.delete(transcription)
    await db.commit()

    return {"message": "Transcription deleted"}
