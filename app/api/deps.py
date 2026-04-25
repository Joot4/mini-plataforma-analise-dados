from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import get_db_session
from app.services.auth_service import get_user_by_id

# tokenUrl is informational for OpenAPI/Swagger; routes mounted at /api/v1.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

_INVALID_TOKEN_DETAIL = {
    "error_type": "invalid_token",
    "message": "Token inválido ou expirado. Faça login novamente.",
}


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_INVALID_TOKEN_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """Resolve the authenticated User from the Authorization Bearer header.

    Raises HTTPException(401) on missing token, decode failure, or unknown/inactive user.
    """
    if token is None:
        raise _unauthorized()
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise _unauthorized() from exc

    user = await get_user_by_id(session, payload.sub)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


__all__ = ["get_current_user", "CurrentUser", "DbSession"]
