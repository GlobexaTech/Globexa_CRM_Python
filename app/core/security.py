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

from app.core.config import get_settings

settings = get_settings()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.security.bcrypt_rounds)


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
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.security.access_token_expire_minutes)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.security.secret_key, algorithm=settings.security.algorithm)


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.security.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.security.secret_key, algorithm=settings.security.algorithm)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, settings.security.secret_key, algorithms=[settings.security.algorithm], options={"require": ["exp", "sub", "tenant_id", "type"]})
        return payload
    except JWTError:
        return None


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def generate_verification_code(length: int = 6) -> str:
    """Generate a numeric verification code."""
    return "".join(secrets.choice("0123456789") for _ in range(length))