"""
Face detection and person management API endpoints.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_tenant_id
from app.models.asset import Asset
from app.models.person import AssetFace, Person
from app.models.user import User
from app.schemas.person import (
    FaceCreate,
    FaceIdentifyRequest,
    FaceRead,
    FaceSearchRequest,
    FaceSearchResult,
    PersonCreate,
    PersonRead,
    PersonSummary,
    PersonUpdate,
)

router = APIRouter()


# ======================
# Persons CRUD
# ======================


@router.get("/persons", response_model=list[PersonRead])
async def list_persons(
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """List all known persons."""
    query = select(Person).where(Person.tenant_id == tenant_id)

    if search:
        query = query.where(Person.name.ilike(f"%{search}%"))

    query = query.order_by(Person.name).offset(skip).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/persons", response_model=PersonRead, status_code=status.HTTP_201_CREATED)
async def create_person(
    person_in: PersonCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Create a new person."""
    person = Person(
        tenant_id=tenant_id,
        name=person_in.name,
        role=person_in.role,
        external_id=person_in.external_id,
        metadata_=person_in.metadata,
    )
    db.add(person)
    await db.commit()
    await db.refresh(person)
    return person


@router.get("/persons/{person_id}", response_model=PersonRead)
async def get_person(
    person_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Get a person by ID."""
    result = await db.execute(
        select(Person)
        .where(Person.id == person_id)
        .where(Person.tenant_id == tenant_id)
    )
    person = result.scalar_one_or_none()

    if not person:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found",
        )

    return person


@router.patch("/persons/{person_id}", response_model=PersonRead)
async def update_person(
    person_id: UUID,
    person_in: PersonUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Update a person."""
    result = await db.execute(
        select(Person)
        .where(Person.id == person_id)
        .where(Person.tenant_id == tenant_id)
    )
    person = result.scalar_one_or_none()

    if not person:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found",
        )

    update_data = person_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "metadata":
            setattr(person, "metadata_", value)
        else:
            setattr(person, field, value)

    await db.commit()
    await db.refresh(person)
    return person


@router.delete("/persons/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_person(
    person_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Delete a person."""
    result = await db.execute(
        select(Person)
        .where(Person.id == person_id)
        .where(Person.tenant_id == tenant_id)
    )
    person = result.scalar_one_or_none()

    if not person:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found",
        )

    await db.delete(person)
    await db.commit()


@router.get("/persons/{person_id}/appearances", response_model=list[FaceRead])
async def get_person_appearances(
    person_id: UUID,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Get all appearances of a person across assets."""
    result = await db.execute(
        select(AssetFace)
        .where(AssetFace.person_id == person_id)
        .where(AssetFace.tenant_id == tenant_id)
        .order_by(AssetFace.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


# ======================
# Asset Faces
# ======================


@router.get("/assets/{asset_id}/faces", response_model=list[FaceRead])
async def list_asset_faces(
    asset_id: UUID,
    identified_only: bool = False,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """List all detected faces in an asset."""
    query = (
        select(AssetFace)
        .where(AssetFace.asset_id == asset_id)
        .where(AssetFace.tenant_id == tenant_id)
    )

    if identified_only:
        query = query.where(AssetFace.person_id.isnot(None))

    query = query.order_by(AssetFace.timecode_ms)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/assets/{asset_id}/detect-faces")
async def start_face_detection(
    asset_id: UUID,
    sample_interval: float = 1.0,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Start face detection for an asset."""
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

    # Create job
    job = IngestJob(
        asset_id=asset_id,
        tenant_id=tenant_id,
        job_type="face_detection",
        status="pending",
        priority=5,
        config={"sample_interval": sample_interval},
    )
    db.add(job)
    await db.flush()
    await db.commit()

    # Queue task
    from app.workers.tasks.face_detection import detect_faces

    detect_faces.delay(
        asset_id=str(asset_id),
        tenant_id=str(tenant_id),
        sample_interval=sample_interval,
    )

    return {
        "job_id": str(job.id),
        "asset_id": str(asset_id),
        "status": "pending",
        "message": "Face detection started",
    }


@router.post("/faces/{face_id}/identify")
async def identify_face(
    face_id: UUID,
    request: FaceIdentifyRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Manually identify a face as a known person."""
    from sqlalchemy import update

    # Verify face exists
    result = await db.execute(
        select(AssetFace)
        .where(AssetFace.id == face_id)
        .where(AssetFace.tenant_id == tenant_id)
    )
    face = result.scalar_one_or_none()

    if not face:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Face not found",
        )

    # Verify person exists
    result = await db.execute(
        select(Person)
        .where(Person.id == request.person_id)
        .where(Person.tenant_id == tenant_id)
    )
    person = result.scalar_one_or_none()

    if not person:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found",
        )

    # Update face
    face.person_id = request.person_id
    person.appearance_count += 1

    await db.commit()

    # Trigger embedding update for person
    from app.workers.tasks.face_detection import update_person_embedding
    update_person_embedding.delay(str(request.person_id))

    return {
        "face_id": str(face_id),
        "person_id": str(request.person_id),
        "person_name": person.name,
        "message": "Face identified",
    }


@router.post("/faces/search", response_model=list[FaceSearchResult])
async def search_by_face(
    request: FaceSearchRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Search for similar faces using an image."""
    from app.services.face_service import face_service

    # Get embedding from uploaded image
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        embedding = await face_service.get_embedding_from_image(request.image_base64)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Search for similar faces using pgvector
    result = await db.execute(
        text("""
            SELECT
                af.id,
                af.asset_id,
                af.person_id,
                af.timecode_ms,
                af.thumbnail_url,
                af.confidence,
                1 - (af.face_embedding <=> :embedding::vector) as similarity,
                a.title as asset_title
            FROM asset_faces af
            JOIN assets a ON a.id = af.asset_id
            WHERE af.tenant_id = :tenant_id
            AND af.face_embedding IS NOT NULL
            ORDER BY af.face_embedding <=> :embedding::vector
            LIMIT :limit
        """),
        {
            "tenant_id": tenant_id,
            "embedding": str(embedding),
            "limit": request.limit,
        }
    )

    results = []
    for row in result.fetchall():
        if row.similarity >= request.min_confidence:
            results.append(FaceSearchResult(
                face=FaceRead(
                    id=row.id,
                    asset_id=row.asset_id,
                    tenant_id=tenant_id,
                    person_id=row.person_id,
                    timecode_ms=row.timecode_ms,
                    duration_ms=None,
                    bbox=None,
                    thumbnail_url=row.thumbnail_url,
                    confidence=row.confidence,
                    person=None,
                    created_at=None,
                ),
                similarity=row.similarity,
                asset_id=row.asset_id,
                asset_title=row.asset_title,
            ))

    return results
