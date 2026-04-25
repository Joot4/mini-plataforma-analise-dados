from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Final

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# pwdlib PasswordHash with bcrypt backend only (default cost factor = 12 — FastAPI rec).
# CLAUDE.md non-negotiable: only pwdlib is allowed for password hashing.
_password_hash: Final[PasswordHash] = PasswordHash((BcryptHasher(),))


# Module-level cache of the secret key used for signing.
# Set on first call; reused thereafter. Tests can reset via _reset_secret().
_secret_cache: str | None = None


def _get_secret() -> str:
    """Return JWT secret, generating an ephemeral one (with warning) if unset."""
    global _secret_cache
    if _secret_cache is not None:
        return _secret_cache

    settings = get_settings()
    if settings.JWT_SECRET_KEY:
        _secret_cache = settings.JWT_SECRET_KEY
    else:
        _secret_cache = secrets.token_hex(32)
        logger.warning(
            "jwt.ephemeral_key_generated",
            message=(
                "JWT_SECRET_KEY not set; generated an ephemeral key. "
                "All issued tokens will be invalidated on process restart."
            ),
        )
    return _secret_cache


def _reset_secret() -> None:
    """Test-only: clear the cached secret so the next call re-reads settings."""
    global _secret_cache
    _secret_cache = None


# --- Password hashing ---


def hash_password(plain: str) -> str:
    """Hash a plaintext password with pwdlib bcrypt."""
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if the plaintext matches the bcrypt hash."""
    return _password_hash.verify(plain, hashed)


# --- JWT ---


class TokenPayload(BaseModel):
    """Decoded JWT payload. `sub` is the user id (UUID4 string)."""

    sub: str
    exp: int
    iat: int


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """Sign a JWT access token for the given subject (user_id)."""
    settings = get_settings()
    minutes = (
        expires_minutes if expires_minutes is not None else settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    now = datetime.now(tz=UTC)
    exp = now + timedelta(minutes=minutes)
    payload: dict[str, int | str] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, _get_secret(), algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> TokenPayload:
    """Decode and validate a JWT. Raises jwt.PyJWTError subclasses on failure."""
    settings = get_settings()
    decoded = jwt.decode(
        token,
        _get_secret(),
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["sub", "exp", "iat"]},
    )
    return TokenPayload(**decoded)
