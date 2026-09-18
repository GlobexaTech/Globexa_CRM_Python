"""
Security utilities for Globexa CRM.
Password hashing, JWT tokens, and cryptographic helpers.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
from jwt import InvalidTokenError as JWTError
from passlib.context import CryptContext
import secrets
from uuid import UUID, uuid4

from app.core.config import get_settings

settings = get_settings()

# Password hashing
pwd_context = CryptContext(
    schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.security.bcrypt_rounds
)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.security.access_token_expire_minutes
        )
    session_expiry = int(
        to_encode.get(
            "session_exp",
            (
                datetime.now(timezone.utc)
                + timedelta(days=settings.security.refresh_token_expire_days)
            ).timestamp(),
        )
    )
    to_encode.update(
        {
            "exp": min(int(expire.timestamp()), session_expiry),
            "type": "access",
            "jti": uuid4().hex,
            "sid": to_encode.get("sid") or uuid4().hex,
            "session_exp": session_expiry,
        }
    )
    return jwt.encode(
        to_encode, settings.security.secret_key, algorithm=settings.security.algorithm
    )


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.security.refresh_token_expire_days
        )
    session_expiry = int(to_encode.get("session_exp", expire.timestamp()))
    to_encode.update(
        {
            "exp": min(int(expire.timestamp()), session_expiry),
            "type": "refresh",
            "jti": uuid4().hex,
            "sid": to_encode.get("sid") or uuid4().hex,
            "session_exp": session_expiry,
        }
    )
    return jwt.encode(
        to_encode, settings.security.secret_key, algorithm=settings.security.algorithm
    )


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.security.secret_key,
            algorithms=[settings.security.algorithm],
            options={"require": ["exp", "sub", "tenant_id", "type", "jti", "sid", "session_exp"]},
        )
        for field in ("sub", "tenant_id", "jti", "sid"):
            UUID(payload[field])
        if (
            payload["type"] not in {"access", "refresh"}
            or not isinstance(payload["session_exp"], int)
            or payload["exp"] > payload["session_exp"]
            or payload["session_exp"] <= datetime.now(timezone.utc).timestamp()
        ):
            return None
        return payload
    except (JWTError, ValueError, TypeError, AttributeError):
        return None


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def generate_verification_code(length: int = 6) -> str:
    """Generate a numeric verification code."""
    return "".join(secrets.choice("0123456789") for _ in range(length))
