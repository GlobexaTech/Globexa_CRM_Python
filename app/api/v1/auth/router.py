"""
Authentication API routes for Globexa CRM.
Register, login, Google OAuth, token refresh, current user.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.api.deps import get_current_user, get_current_active_user
from app.schemas import (
    UserRegister,
    UserLogin,
    TokenResponse,
    RefreshTokenRequest,
    GoogleAuthRequest,
    UserResponse,
    UserUpdate,
)
from app.services.auth.service import AuthService
from app.models import User, Membership

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user and create their first tenant."""
    auth_service = AuthService(db)
    try:
        user, tenant = await auth_service.register_user(
            email=data.email,
            password=data.password,
            full_name=data.full_name,
            tenant_name=data.tenant_name,
            tenant_slug=data.tenant_slug,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    tokens = await auth_service.create_tokens(user, tenant.id)
    return tokens


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login with email and password (OAuth2 compatible)."""
    auth_service = AuthService(db)
    user = await auth_service.authenticate_user(form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user's default tenant
    default_membership = next(
        (m for m in user.memberships if m.is_default),
        user.memberships[0] if user.memberships else None,
    )
    if not default_membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no tenant membership",
        )

    tokens = await auth_service.create_tokens(user, default_membership.tenant_id)
    return tokens


@router.post("/google", response_model=TokenResponse)
async def google_auth(
    data: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with Google OAuth."""
    auth_service = AuthService(db)
    try:
        user, tenant = await auth_service.google_login(data.code)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not user or not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google authentication failed",
        )

    tokens = await auth_service.create_tokens(user, tenant.id)
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token."""
    auth_service = AuthService(db)
    tokens = await auth_service.refresh_tokens(data.refresh_token)

    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return tokens


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: tuple[User, Membership] = Depends(get_current_active_user),
):
    """Get current user info with membership details."""
    user, membership = current_user
    return user


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    data: UserUpdate,
    current_user: tuple[User, Membership] = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile."""
    user, _ = current_user

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


@router.post("/logout")
async def logout(
    response: Response,
    current_user: tuple[User, Membership] = Depends(get_current_active_user),
):
    """Logout - client should discard tokens."""
    # For stateless JWT, logout is client-side
    # Could add token blacklist here if needed
    return {"message": "Successfully logged out"}


# Tenant switching endpoint
@router.post("/switch-tenant/{tenant_id}", response_model=TokenResponse)
async def switch_tenant(
    tenant_id: str,
    current_user: tuple[User, Membership] = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Switch to a different tenant (user must be a member)."""
    from uuid import UUID
    from sqlalchemy import select

    auth_service = AuthService(db)
    user, _ = current_user

    # Verify membership
    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.tenant_id == UUID(tenant_id),
        )
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this tenant",
        )

    tokens = await auth_service.create_tokens(user, membership.tenant_id)
    return tokens


@router.get("/tenants", response_model=list[dict])
async def list_user_tenants(
    current_user: tuple[User, Membership] = Depends(get_current_active_user),
):
    """List all tenants the current user belongs to."""
    user, _ = current_user
    return [
        {
            "id": str(m.tenant_id),
            "name": m.tenant.name,
            "slug": m.tenant.slug,
            "role": m.role.value,
            "is_default": m.is_default,
        }
        for m in user.memberships
    ]