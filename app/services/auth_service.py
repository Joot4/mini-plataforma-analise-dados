from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.db.models import User


class EmailAlreadyExistsError(Exception):
    """Raised when register_user receives an email that already exists in the DB."""

    def __init__(self, email: str) -> None:
        super().__init__(f"email already exists: {email}")
        self.email = email


async def register_user(session: AsyncSession, email: str, plain_password: str) -> User:
    """Create a new user with a bcrypt-hashed password.

    Raises EmailAlreadyExistsError if the email is already taken (UNIQUE constraint).
    """
    user = User(email=email.lower().strip(), password_hash=hash_password(plain_password))
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise EmailAlreadyExistsError(email) from exc
    await session.refresh(user)
    return user


async def authenticate_user(session: AsyncSession, email: str, plain_password: str) -> User | None:
    """Return the User if credentials are valid and the user is active, else None."""
    stmt = select(User).where(User.email == email.lower().strip())
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_password(plain_password, user.password_hash):
        return None
    return user


async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    """Lookup a user by UUID4 string id."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


__all__ = [
    "EmailAlreadyExistsError",
    "register_user",
    "authenticate_user",
    "get_user_by_id",
]
