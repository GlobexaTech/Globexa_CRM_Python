"""
Authentication service for Globexa CRM.
Handles user registration, login, JWT tokens, Google OAuth, and password reset.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from authlib.integrations.starlette_client import OAuth
from authlib.oauth2.rfc7523 import PrivateKeyJWT
import httpx

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_secure_token,
    hash_password,
    verify_password,
)
from app.models import User, Membership, Tenant, RoleEnum, AuditLog

settings = get_settings()


class AuthService:
    """Authentication and authorization service."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._oauth = None

    @property
    def oauth(self) -> OAuth:
        """Lazy-initialize OAuth client."""
        if self._oauth is None:
            self._oauth = OAuth()
            if settings.google_oauth.configured:
                self._oauth.register(
                    name="google",
                    client_id=settings.google_oauth.client_id,
                    client_secret=settings.google_oauth.client_secret,
                    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                    client_kwargs={"scope": " ".join(settings.google_oauth.scopes)},
                )
        return self._oauth

    async def register_user(
        self,
        email: str,
        password: str,
        full_name: str,
        tenant_name: Optional[str] = None,
        tenant_slug: Optional[str] = None,
    ) -> Tuple[User, Tenant]:
        """Register a new user and create their first tenant."""
        # Check if user exists
        existing = await self.db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            raise ValueError("Email already registered")

        # Create user
        hashed_password = hash_password(password)
        user = User(
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
        )
        self.db.add(user)
        await self.db.flush()

        # Create tenant for the user
        if not tenant_slug:
            tenant_slug = email.split("@")[0].lower().replace(".", "-")
            # Ensure unique slug
            base_slug = tenant_slug
            counter = 1
            while True:
                existing_tenant = await self.db.execute(
                    select(Tenant).where(Tenant.slug == tenant_slug)
                )
                if not existing_tenant.scalar_one_or_none():
                    break
                tenant_slug = f"{base_slug}-{counter}"
                counter += 1

        tenant = Tenant(
            name=tenant_name or f"{full_name}'s Workspace",
            slug=tenant_slug,
        )
        self.db.add(tenant)
        await self.db.flush()

        # Create owner membership
        membership = Membership(
            user_id=user.id,
            tenant_id=tenant.id,
            role=RoleEnum.OWNER,
            is_default=True,
        )
        self.db.add(membership)

        # Create default subscription (trial)
        from app.models import Subscription, SubscriptionStatusEnum, PackageEnum
        subscription = Subscription(
            tenant_id=tenant.id,
            package=PackageEnum.STARTER,
            status=SubscriptionStatusEnum.TRIALING,
            trial_end=datetime.now(timezone.utc) + timedelta(days=14),
        )
        self.db.add(subscription)

        # Create default feature entitlements from package config
        await self._create_default_entitlements(tenant.id, PackageEnum.STARTER)

        await self.db.commit()
        await self.db.refresh(user)
        await self.db.refresh(tenant)

        # Audit log
        await self._audit_log(
            tenant_id=tenant.id,
            user_id=user.id,
            action="user_registered",
            resource_type="user",
            resource_id=str(user.id),
            new_values={"email": email, "full_name": full_name},
        )

        return user, tenant

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password."""
        result = await self.db.execute(
            select(User)
            .where(User.email == email)
            .options(selectinload(User.memberships).selectinload(Membership.tenant))
        )
        user = result.scalar_one_or_none()

        if not user or not user.hashed_password:
            return None

        if not verify_password(password, user.hashed_password):
            return None

        if not user.is_active:
            return None

        # Update last login
        user.last_login_at = datetime.now(timezone.utc)
        await self.db.commit()

        return user

    async def google_login(self, code: str) -> Tuple[Optional[User], Optional[Tenant]]:
        """Handle Google OAuth callback."""
        if not settings.google_oauth.configured:
            raise ValueError("Google OAuth not configured")

        # Exchange code for token
        token = await self.oauth.google.authorize_access_token(
            redirect_uri=settings.google_oauth.redirect_uri,
            code=code,
        )

        # Get user info from Google
        userinfo = token.get("userinfo")
        if not userinfo:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {token['access_token']}"},
                )
                userinfo = resp.json()

        google_id = userinfo.get("sub")
        email = userinfo.get("email")
        full_name = userinfo.get("name", "")
        avatar_url = userinfo.get("picture")

        if not email or not google_id:
            raise ValueError("Invalid Google response")

        # Find existing user by Google ID
        result = await self.db.execute(
            select(User)
            .where(User.google_id == google_id)
            .options(selectinload(User.memberships).selectinload(Membership.tenant))
        )
        user = result.scalar_one_or_none()

        if user:
            # Update avatar if changed
            if avatar_url and user.avatar_url != avatar_url:
                user.avatar_url = avatar_url
            user.last_login_at = datetime.now(timezone.utc)
            await self.db.commit()
            # Get default tenant
            default_membership = next((m for m in user.memberships if m.is_default), user.memberships[0] if user.memberships else None)
            tenant = default_membership.tenant if default_membership else None
            return user, tenant

        # Find by email (might be existing account without Google)
        result = await self.db.execute(
            select(User)
            .where(User.email == email)
            .options(selectinload(User.memberships).selectinload(Membership.tenant))
        )
        user = result.scalar_one_or_none()

        if user:
            # Link Google account
            user.google_id = google_id
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
            user.email_verified = True
            user.last_login_at = datetime.now(timezone.utc)
            await self.db.commit()
            default_membership = next((m for m in user.memberships if m.is_default), user.memberships[0] if user.memberships else None)
            tenant = default_membership.tenant if default_membership else None
            return user, tenant

        # Create new user via Google
        user = User(
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
            google_id=google_id,
            email_verified=True,
            hashed_password=None,  # No password for Google-only accounts
        )
        self.db.add(user)
        await self.db.flush()

        # Create tenant
        tenant_slug = email.split("@")[0].lower().replace(".", "-")
        base_slug = tenant_slug
        counter = 1
        while True:
            existing_tenant = await self.db.execute(
                select(Tenant).where(Tenant.slug == tenant_slug)
            )
            if not existing_tenant.scalar_one_or_none():
                break
            tenant_slug = f"{base_slug}-{counter}"
            counter += 1

        tenant = Tenant(name=f"{full_name}'s Workspace", slug=tenant_slug)
        self.db.add(tenant)
        await self.db.flush()

        # Owner membership
        membership = Membership(
            user_id=user.id,
            tenant_id=tenant.id,
            role=RoleEnum.OWNER,
            is_default=True,
        )
        self.db.add(membership)

        # Trial subscription
        from app.models import Subscription, SubscriptionStatusEnum, PackageEnum
        subscription = Subscription(
            tenant_id=tenant.id,
            package=PackageEnum.STARTER,
            status=SubscriptionStatusEnum.TRIALING,
            trial_end=datetime.now(timezone.utc) + timedelta(days=14),
        )
        self.db.add(subscription)

        await self._create_default_entitlements(tenant.id, PackageEnum.STARTER)

        await self.db.commit()
        await self.db.refresh(user)
        await self.db.refresh(tenant)

        await self._audit_log(
            tenant_id=tenant.id,
            user_id=user.id,
            action="user_registered_google",
            resource_type="user",
            resource_id=str(user.id),
            new_values={"email": email, "full_name": full_name},
        )

        return user, tenant

    async def create_tokens(self, user: User, tenant_id: UUID) -> dict:
        """Create access and refresh tokens for user in a tenant."""
        # Verify membership
        result = await self.db.execute(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.tenant_id == tenant_id,
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            raise ValueError("User not a member of this tenant")

        token_data = {
            "sub": str(user.id),
            "tenant_id": str(tenant_id),
            "role": membership.role.value,
            "email": user.email,
        }

        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.security.access_token_expire_minutes * 60,
        }

    async def refresh_tokens(self, refresh_token: str) -> Optional[dict]:
        """Refresh access token using refresh token."""
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None

        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")

        # Verify user still exists and is active
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active == True)
        )
        user = result.scalar_one_or_none()
        if not user:
            return None

        # Verify membership still valid
        result = await self.db.execute(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.tenant_id == tenant_id,
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            return None

        return await self.create_tokens(user, UUID(tenant_id))

    async def get_current_user(self, token: str) -> Optional[Tuple[User, Membership]]:
        """Get current user and membership from access token."""
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            return None

        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")

        result = await self.db.execute(
            select(User)
            .where(User.id == user_id, User.is_active == True)
            .options(selectinload(User.memberships).selectinload(Membership.tenant))
        )
        user = result.scalar_one_or_none()
        if not user:
            return None

        membership = next(
            (m for m in user.memberships if str(m.tenant_id) == tenant_id),
            None,
        )
        if not membership:
            return None

        return user, membership

    async def _create_default_entitlements(self, tenant_id: UUID, package: "PackageEnum") -> None:
        """Create default feature entitlements for a package."""
        from app.models import FeatureEntitlement
        from app.core.config import settings

        package_config = getattr(settings.packages, package.value.upper(), None)
        if not package_config:
            return

        # Features
        for feature_key, enabled in package_config.features.items():
            entitlement = FeatureEntitlement(
                tenant_id=tenant_id,
                feature_key=feature_key,
                enabled=enabled,
            )
            self.db.add(entitlement)

        # Limits
        for limit_key, limit_value in package_config.limits.items():
            entitlement = FeatureEntitlement(
                tenant_id=tenant_id,
                feature_key=f"limit_{limit_key}",
                enabled=True,
                limit_value=limit_value,
            )
            self.db.add(entitlement)

    async def _audit_log(
        self,
        tenant_id: UUID,
        user_id: UUID,
        action: str,
        resource_type: str,
        resource_id: str,
        old_values: Optional[dict] = None,
        new_values: Optional[dict] = None,
    ) -> None:
        """Create audit log entry."""
        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_values=old_values,
            new_values=new_values,
            success=True,
        )
        self.db.add(audit)
        await self.db.flush()