"""
AKASHI MAM API - Authentication Endpoints
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import (
    CurrentActiveUser,
    CurrentSuperuser,
    DbSession,
    get_tenant_by_code,
)
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_token_pair,
    get_password_hash,
    get_refresh_token_expiration,
    get_refresh_token_expiration_seconds,
    get_token_expiration_seconds,
    hash_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User
from app.schemas import (
    LoginRequest,
    LoginResponse,
    MessageResponse,
    PasswordChange,
    RefreshTokenRequest,
    TokenPair,
    UserCreate,
    UserRead,
    UserUpdate,
)


logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Authentication Endpoints
# =============================================================================


@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    request: Request,
    db: DbSession,
):
    """
    Authenticate user and return JWT token with refresh token.

    - **email**: User email address
    - **password**: User password
    """
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == data.email)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(user)

    # Create token pair
    token_data = create_token_pair(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        role=user.role,
    )

    # Store refresh token in database
    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=token_data["refresh_token_hash"],
        expires_at=get_refresh_token_expiration(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(refresh_token_record)
    await db.commit()

    logger.info(f"User {user.email} logged in successfully")

    return LoginResponse(
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        token_type="bearer",
        expires_in=get_token_expiration_seconds(),
        refresh_expires_in=get_refresh_token_expiration_seconds(),
        user=UserRead.model_validate(user),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh_tokens(
    data: RefreshTokenRequest,
    request: Request,
    db: DbSession,
):
    """
    Refresh access token using refresh token.

    - **refresh_token**: The refresh token from login
    """
    # Hash the provided token
    token_hash = hash_refresh_token(data.refresh_token)

    # Find the refresh token
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked == False,
        )
    )
    refresh_token = result.scalar_one_or_none()

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check expiration
    if datetime.now(timezone.utc) > refresh_token.expires_at:
        # Mark as revoked
        refresh_token.is_revoked = True
        refresh_token.revoked_at = datetime.now(timezone.utc)
        refresh_token.revoked_reason = "expired"
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user
    user = await db.get(User, refresh_token.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Update last used
    refresh_token.last_used_at = datetime.now(timezone.utc)

    # Create new token pair
    token_data = create_token_pair(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        role=user.role,
    )

    # Token rotation: revoke old token and create new one
    if settings.jwt_refresh_token_rotate:
        # Revoke old token
        refresh_token.is_revoked = True
        refresh_token.revoked_at = datetime.now(timezone.utc)
        refresh_token.revoked_reason = "rotated"

        # Create new refresh token
        new_refresh_token = RefreshToken(
            user_id=user.id,
            token_hash=token_data["refresh_token_hash"],
            expires_at=get_refresh_token_expiration(),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(new_refresh_token)

    await db.commit()

    logger.info(f"Tokens refreshed for user {user.email}")

    return TokenPair(
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        token_type="bearer",
        expires_in=get_token_expiration_seconds(),
        refresh_expires_in=get_refresh_token_expiration_seconds(),
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    data: RefreshTokenRequest,
    db: DbSession,
    current_user: CurrentActiveUser,
):
    """
    Logout and revoke refresh token.

    - **refresh_token**: The refresh token to revoke
    """
    # Hash the provided token
    token_hash = hash_refresh_token(data.refresh_token)

    # Find and revoke the refresh token
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == current_user.id,
        )
    )
    refresh_token = result.scalar_one_or_none()

    if refresh_token and not refresh_token.is_revoked:
        refresh_token.is_revoked = True
        refresh_token.revoked_at = datetime.now(timezone.utc)
        refresh_token.revoked_reason = "logout"
        await db.commit()

    logger.info(f"User {current_user.email} logged out")
    return MessageResponse(message="Successfully logged out")


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all_devices(
    db: DbSession,
    current_user: CurrentActiveUser,
):
    """
    Logout from all devices by revoking all refresh tokens.
    """
    # Find all active refresh tokens for user
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == current_user.id,
            RefreshToken.is_revoked == False,
        )
    )
    tokens = result.scalars().all()

    revoked_count = 0
    for token in tokens:
        token.is_revoked = True
        token.revoked_at = datetime.now(timezone.utc)
        token.revoked_reason = "logout_all"
        revoked_count += 1

    await db.commit()

    logger.info(f"User {current_user.email} logged out from all devices ({revoked_count} sessions)")
    return MessageResponse(message=f"Logged out from {revoked_count} devices")


@router.get("/me", response_model=UserRead)
async def get_current_user_info(
    current_user: CurrentActiveUser,
):
    """
    Get current authenticated user information.
    """
    return UserRead.model_validate(current_user)


@router.patch("/me", response_model=UserRead)
async def update_current_user(
    data: UserUpdate,
    current_user: CurrentActiveUser,
    db: DbSession,
):
    """
    Update current user's own profile.
    Note: Cannot change own role or active status.
    """
    # Only allow updating email and full_name
    if data.email is not None:
        # Check if email is taken by another user
        existing = await db.execute(
            select(User).where(
                User.email == data.email,
                User.id != current_user.id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        current_user.email = data.email

    if data.full_name is not None:
        current_user.full_name = data.full_name

    await db.flush()
    await db.refresh(current_user)

    logger.info(f"User {current_user.email} updated their profile")
    return UserRead.model_validate(current_user)


@router.post("/me/change-password", response_model=MessageResponse)
async def change_password(
    data: PasswordChange,
    current_user: CurrentActiveUser,
    db: DbSession,
):
    """
    Change current user's password.
    """
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.password_hash = get_password_hash(data.new_password)
    current_user.password_changed_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(f"User {current_user.email} changed their password")
    return MessageResponse(message="Password changed successfully")


# =============================================================================
# User Management Endpoints (Admin only)
# =============================================================================


@router.post("/register", response_model=UserRead, status_code=201)
async def register_user(
    data: UserCreate,
    db: DbSession,
):
    """
    Register a new user.

    **Note**: In production, this endpoint should be protected.
    For development, it's open to allow creating users easily.
    """
    # Get tenant
    tenant = await get_tenant_by_code(db, data.tenant_code)

    # Check if email already exists for this tenant
    existing = await db.execute(
        select(User).where(
            User.tenant_id == tenant.id,
            User.email == data.email,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered for this tenant",
        )

    # Create user
    user = User(
        tenant_id=tenant.id,
        email=data.email,
        password_hash=get_password_hash(data.password),
        full_name=data.full_name,
        role=data.role,
        is_active=True,
        is_superuser=False,
    )

    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info(f"New user registered: {user.email}")
    return UserRead.model_validate(user)


@router.get("/users", response_model=list[UserRead])
async def list_users(
    db: DbSession,
    current_user: CurrentSuperuser,
    tenant_code: str | None = None,
    include_inactive: bool = False,
):
    """
    List all users (superuser only).
    """
    query = select(User)

    if tenant_code:
        tenant = await get_tenant_by_code(db, tenant_code)
        query = query.where(User.tenant_id == tenant.id)

    if not include_inactive:
        query = query.where(User.is_active == True)

    query = query.order_by(User.created_at.desc())

    result = await db.execute(query)
    users = result.scalars().all()

    return [UserRead.model_validate(u) for u in users]


@router.get("/users/{user_id}", response_model=UserRead)
async def get_user(
    user_id: str,
    db: DbSession,
    current_user: CurrentSuperuser,
):
    """
    Get user by ID (superuser only).
    """
    from uuid import UUID

    result = await db.execute(
        select(User).where(User.id == UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserRead.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    data: UserUpdate,
    db: DbSession,
    current_user: CurrentSuperuser,
):
    """
    Update user (superuser only).
    """
    from uuid import UUID

    result = await db.execute(
        select(User).where(User.id == UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    await db.flush()
    await db.refresh(user)

    logger.info(f"User {user.email} updated by superuser")
    return UserRead.model_validate(user)


@router.delete("/users/{user_id}", response_model=MessageResponse)
async def deactivate_user(
    user_id: str,
    db: DbSession,
    current_user: CurrentSuperuser,
):
    """
    Deactivate a user (superuser only).
    Does not delete, just sets is_active to False.
    """
    from uuid import UUID

    result = await db.execute(
        select(User).where(User.id == UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate yourself",
        )

    user.is_active = False
    await db.flush()

    logger.info(f"User {user.email} deactivated by superuser")
    return MessageResponse(message="User deactivated", id=user.id)
