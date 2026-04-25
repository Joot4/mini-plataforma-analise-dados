---
name: auth-service
phase: 01-foundation
plan: 04
type: execute
wave: 3
depends_on: [03]
files_modified:
  - app/services/__init__.py
  - app/services/auth_service.py
autonomous: true
requirements: [AUTH-01, AUTH-02, AUTH-04]
must_haves:
  truths:
    - "register_user(session, email, plain_password) inserts a User row whose password_hash starts with $2b$ (pwdlib bcrypt) and returns the persisted User"
    - "register_user with a duplicate (case-normalized) email raises EmailAlreadyExistsError, never lets the SQLAlchemy IntegrityError leak out"
    - "authenticate_user returns the User on a correct (email, password); returns None on wrong password OR unknown email (timing-equivalent — never reveal which one failed)"
    - "register_user normalizes email to lowercase + .strip() before hashing/insert so 'Foo@Bar.com' and 'foo@bar.com' collide on UNIQUE"
    - "All bcrypt + DB I/O happens inside one AsyncSession boundary; the service never opens its own session"
  artifacts:
    - path: "app/services/__init__.py"
      provides: "services package marker"
      contains: ""
    - path: "app/services/auth_service.py"
      provides: "Pure-logic auth service: register_user, authenticate_user, EmailAlreadyExistsError"
      exports: ["register_user", "authenticate_user", "EmailAlreadyExistsError"]
  key_links:
    - from: "app/services/auth_service.py"
      to: "app/core/security.hash_password / verify_password"
      via: "pwdlib bcrypt round-trip (NOT passlib)"
      pattern: "from app.core.security import hash_password"
    - from: "app/services/auth_service.py"
      to: "app/db/models.User"
      via: "SQLAlchemy 2.x select() / session.add()"
      pattern: "from app.db.models import User"
    - from: "app/services/auth_service.py"
      to: "sqlalchemy.exc.IntegrityError"
      via: "UNIQUE(email) violation -> EmailAlreadyExistsError"
      pattern: "except IntegrityError"
---

<objective>
Build the pure-logic auth service that owns all DB I/O against the `users` table for registration and login. No HTTP, no Pydantic schemas, no FastAPI dependencies — that all belongs to plans 05 and 06. The service signature is the contract every later layer (router in 06, tests in 07) consumes.

Purpose: Cleanly separates "how do I create a user / authenticate a user" from "how does the HTTP layer expose it". The router in plan 06 calls `register_user(session, email, password)` and translates whatever it returns or raises into HTTP. This is the seam that makes plan 07's service-layer tests possible without spinning up FastAPI.
Output: `app/services/__init__.py` (empty marker) + `app/services/auth_service.py` exporting `register_user`, `authenticate_user`, `EmailAlreadyExistsError`.

ROADMAP success criteria addressed (with downstream plans):
- SC#1 (register 201/409) — this plan owns the INSERT + UNIQUE-violation translation; plan 06 wires the HTTP status codes.
- SC#2 (login 200/401) — this plan owns the bcrypt verify; plan 06 wires the JWT issuance + 401.
- SC#3 (cross-user isolation) — UUID4 PK already in place from plan 03; this plan returns the User by id so plan 05's `get_current_user` can build on it.

Reserved commit codes: GSD-108, GSD-109.
</objective>

<execution_context>
@/Users/junioralmeida/Desktop/Projetos/.claude/get-shit-done/workflows/execute-plan.md
@/Users/junioralmeida/Desktop/Projetos/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/phases/01-foundation/01-CONTEXT.md
@.planning/research/PITFALLS.md
@.planning/phases/01-foundation/01-02-SUMMARY.md
@.planning/phases/01-foundation/01-03-SUMMARY.md

<interfaces>
<!-- Plans 06 and 07 import from this file. Treat the signatures below as the public contract. -->

From app/core/security.py (already shipped by plan 02):
```python
def hash_password(plain: str) -> str: ...        # returns bcrypt hash starting with "$2b$"
def verify_password(plain: str, hashed: str) -> bool: ...
```

From app/db/models.py (already shipped by plan 03):
```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID]            # String(36) on SQLite
    email: Mapped[str]               # unique, indexed, max 255
    password_hash: Mapped[str]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    is_active: Mapped[bool]          # default True
```

From app/db/session.py (already shipped by plan 03):
```python
async def get_db_session() -> AsyncGenerator[AsyncSession, None]: ...
# yields a session, commits on success, rolls back on exception, closes in finally
```

This plan's exports (consumed by plans 06 + 07):
```python
class EmailAlreadyExistsError(Exception):
    """Raised by register_user when a row with the same (normalized) email already exists."""

async def register_user(
    session: AsyncSession, email: str, plain_password: str
) -> User: ...

async def authenticate_user(
    session: AsyncSession, email: str, plain_password: str
) -> User | None: ...   # None on either unknown email or wrong password
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: app/services/__init__.py + auth_service.register_user with IntegrityError -> EmailAlreadyExistsError translation</name>
  <read_first>
    - .planning/phases/01-foundation/01-02-SUMMARY.md §Symbols Exported (`hash_password` signature)
    - .planning/phases/01-foundation/01-03-SUMMARY.md §Symbols Exported (`User` columns + `AsyncSessionLocal`)
    - .planning/phases/01-foundation/01-CONTEXT.md §Claude's Discretion — Registro (email lowercase normalization, 409 on duplicate)
    - .planning/research/PITFALLS.md §Pitfall 12 (pwdlib bcrypt usage)
    - CLAUDE.md (pwdlib NOT passlib; never raw print; PT-BR locale only at boundaries)
  </read_first>
  <files>app/services/__init__.py, app/services/auth_service.py</files>
  <behavior>
    - register_user(session, "User@Example.com  ", "hunter2") inserts a User with email="user@example.com" (lowercased + stripped) and password_hash starting "$2b$"
    - The returned User has a non-None UUID4 id (assigned by the model default, visible after `await session.flush()`)
    - Calling register_user a second time with the same email (any case) raises EmailAlreadyExistsError — NOT sqlalchemy.exc.IntegrityError; the IntegrityError must be caught and translated
    - On the duplicate path, the function calls `await session.rollback()` so the surrounding `get_db_session()` context can keep going (the dep's outer commit-on-success is still safe)
    - register_user does NOT issue its own commit; it relies on the FastAPI dep `get_db_session()` to commit at the end of the request. This keeps the service composable inside a larger transaction.
    - hash_password is called BEFORE session.add (we want the bcrypt cost paid only when the email looks new — early `select()` check is a deliberate optimization here, see action notes)
  </behavior>
  <action>
Create `app/services/__init__.py` as an empty file (package marker only).

Write `app/services/auth_service.py`:

```python
"""Auth service.

Pure-logic boundary owning user CRUD against the `users` table for registration
and login. No HTTP, no Pydantic, no FastAPI deps — those live in app/api/.

The router (plan 06) translates the exceptions raised here into HTTP status codes:
- EmailAlreadyExistsError -> 409 Conflict (D-01..D-04 envelope, error_type="email_already_exists")
- authenticate_user returning None -> 401 Unauthorized (error_type="invalid_credentials")
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.db.models import User

logger = get_logger(__name__)


class EmailAlreadyExistsError(Exception):
    """Raised by register_user when the email is already taken (UNIQUE violation)."""

    def __init__(self, email: str) -> None:
        super().__init__(f"email already registered: {email}")
        self.email = email


def _normalize_email(email: str) -> str:
    """Lowercase + strip — must happen at every read AND every write site."""
    return email.strip().lower()


async def register_user(
    session: AsyncSession, email: str, plain_password: str
) -> User:
    """Create a new user.

    Email is normalized (lowercase + stripped) before any DB contact and before
    the bcrypt hash is computed. On UNIQUE(email) collision we translate the
    SQLAlchemy IntegrityError into EmailAlreadyExistsError so the router can
    map it cleanly to HTTP 409 without leaking ORM internals.

    The session is NOT committed here — the FastAPI dep `get_db_session()` is
    responsible for the surrounding commit/rollback. We DO `flush()` so the
    PK + timestamps are populated on the returned User instance.
    """
    normalized = _normalize_email(email)

    # Cheap pre-check first: avoid paying bcrypt cost on a known-duplicate email.
    # Note: this is an optimization, not the source of truth — the UNIQUE
    # constraint + IntegrityError handler below is what guarantees correctness
    # under any race between this select and the insert.
    existing = await session.execute(
        select(User.id).where(User.email == normalized)
    )
    if existing.scalar_one_or_none() is not None:
        logger.info("auth.register.duplicate_email", email=normalized)
        raise EmailAlreadyExistsError(normalized)

    user = User(
        email=normalized,
        password_hash=hash_password(plain_password),
    )
    session.add(user)
    try:
        # flush() forces the INSERT now so we can catch IntegrityError here
        # and so the returned User has its server/default-assigned id populated.
        await session.flush()
    except IntegrityError as exc:
        # Race: another request inserted the same email between our select
        # and our flush. Rollback so the outer dep doesn't try to commit a
        # tainted transaction; surface the typed domain exception.
        await session.rollback()
        logger.info("auth.register.race_duplicate_email", email=normalized)
        raise EmailAlreadyExistsError(normalized) from exc

    logger.info("auth.register.success", user_id=str(user.id), email=normalized)
    return user
```

Notes:
- The `select()` pre-check is a perf hack to avoid a 200ms+ bcrypt hash on a known-duplicate email. Correctness is owned by the UNIQUE constraint + the `except IntegrityError` block — the pre-check is purely an optimization. Both paths raise the same typed exception so the router never has to disambiguate.
- We log every register attempt outcome so plan 07's tests can assert on log events if needed (and so OPS-03 phase-4 has prior art).
- `await session.rollback()` on the race path is mandatory — without it, the surrounding `get_db_session()` dep would try to commit a transaction that already errored, raising `InvalidRequestError`. This is the same reason plan 03's session dep has the rollback in `except`.
- We deliberately do NOT call `session.commit()` here. The dep owns the outer transaction boundary. This keeps the service composable.

**Commit (after task verifies):** `feat(services):[GSD-108] - Add register_user with email-already-exists guard`
  </action>
  <verify>
    <automated>uv run python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.db.models import Base
from app.services.auth_service import register_user, EmailAlreadyExistsError

async def main():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        u = await register_user(s, '  Foo@Bar.com  ', 'hunter2')
        await s.commit()
        assert u.email == 'foo@bar.com', u.email
        assert u.password_hash.startswith('\$2b\$'), u.password_hash[:6]
        assert u.id is not None
    async with Session() as s:
        try:
            await register_user(s, 'foo@bar.com', 'whatever')
        except EmailAlreadyExistsError as e:
            assert e.email == 'foo@bar.com'
            print('ok')
        else:
            raise SystemExit('expected EmailAlreadyExistsError')

asyncio.run(main())
" | grep -q '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'class EmailAlreadyExistsError' app/services/auth_service.py`
    - `grep -q 'from app.core.security import hash_password' app/services/auth_service.py`
    - `grep -qE 'passlib|python-jose' app/services/auth_service.py` MUST return exit 1 (banned hashers absent)
    - `grep -q 'from sqlalchemy.exc import IntegrityError' app/services/auth_service.py`
    - `grep -q '\.strip()\.lower()' app/services/auth_service.py` (email normalization present)
    - `grep -q 'await session.rollback()' app/services/auth_service.py` (race-path rollback present)
    - The verify block passes (round-trip register + duplicate raise on in-memory SQLite)
    - `test -f app/services/__init__.py` (package marker exists)
  </acceptance_criteria>
</task>

<task type="auto" tdd="true">
  <name>Task 2: auth_service.authenticate_user (timing-equivalent failure path)</name>
  <read_first>
    - app/services/auth_service.py (just written — _normalize_email helper, logger)
    - .planning/phases/01-foundation/01-02-SUMMARY.md §Symbols Exported (`verify_password` signature)
    - .planning/phases/01-foundation/01-CONTEXT.md §Claude's Discretion — invalid_credentials envelope (D-01..D-04: never reveal whether the email or the password was wrong)
  </read_first>
  <files>app/services/auth_service.py</files>
  <behavior>
    - authenticate_user(session, "foo@bar.com", correct_password) returns the User
    - authenticate_user with the right email but wrong password returns None
    - authenticate_user with an unknown email returns None — and to make timing comparable, still calls verify_password against a constant dummy bcrypt hash so the wall-clock cost is similar to a real verify (best-effort timing equalization; not a true constant-time guarantee, but better than an early `return None`)
    - authenticate_user is case-insensitive on email (normalizes the same way register_user does)
    - On `is_active=False` users, authenticate_user returns None (deactivated accounts can't log in even with the right password)
  </behavior>
  <action>
Append to `app/services/auth_service.py`:

```python
# Constant dummy bcrypt hash used to equalize timing on the unknown-email path.
# Generated once at import time so the cost factor matches real hashes.
# (We don't import this at module top because hash_password() is itself in this
#  module — declared after register_user so module init order is unsurprising.)
_DUMMY_HASH: str = hash_password("__dummy_password_never_matches__")


async def authenticate_user(
    session: AsyncSession, email: str, plain_password: str
) -> User | None:
    """Authenticate by (email, password).

    Returns the User on success. Returns None on EITHER unknown email or wrong
    password — the router (plan 06) maps None -> HTTP 401 with
    error_type="invalid_credentials" (D-01..D-04). Never disambiguate which one
    failed; that leaks user enumeration to attackers.

    Inactive users (is_active=False) also return None — deactivated accounts
    cannot log in even with the correct password.

    Timing: when the email is unknown, we still call verify_password against a
    constant dummy hash so the wall-clock cost is comparable to a real verify.
    This is best-effort timing equalization, not a strict constant-time
    guarantee, but it removes the trivial "no email -> instant 401, real email
    + wrong password -> 200ms 401" enumeration signal.
    """
    normalized = _normalize_email(email)

    result = await session.execute(
        select(User).where(User.email == normalized)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # Equalize timing: pay the bcrypt verify cost anyway, then return None.
        verify_password(plain_password, _DUMMY_HASH)
        logger.info("auth.login.unknown_email", email=normalized)
        return None

    if not user.is_active:
        # Same timing concern as above — but we already paid the SELECT cost,
        # so the call to verify_password keeps the inactive-vs-wrong-password
        # paths shape-equivalent.
        verify_password(plain_password, user.password_hash)
        logger.info("auth.login.inactive_user", user_id=str(user.id))
        return None

    if not verify_password(plain_password, user.password_hash):
        logger.info("auth.login.wrong_password", user_id=str(user.id))
        return None

    logger.info("auth.login.success", user_id=str(user.id))
    return user
```

Notes:
- `_DUMMY_HASH` is module-level and computed once at import. The cost is paid once at startup (~50-200ms depending on bcrypt cost factor) and amortized across every login. This keeps the unknown-email path's wall-clock latency in the same order of magnitude as the wrong-password path. Plan 07's `tests/services/test_auth_service.py` (a future addition; out of scope for plan 07 which is API-only) could measure this.
- Logging discriminates between unknown_email / inactive_user / wrong_password / success — these are diagnostic logs (visible to operators), NOT response details. The router (plan 06) returns the same `invalid_credentials` envelope for all three failure cases.
- `is_active` defaults to True in the User model (plan 03), so this gate is effectively no-op for v1 self-registered users. It's wired now so a future "ban user" admin endpoint (v2) is a one-column update with no service changes.

**Commit (after task verifies):** `feat(services):[GSD-109] - Add authenticate_user with timing-equivalent failure`
  </action>
  <verify>
    <automated>uv run python -c "
import asyncio, time
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models import Base
from app.services.auth_service import register_user, authenticate_user

async def main():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        u = await register_user(s, 'a@b.com', 'pw1234567')
        await s.commit()
        uid = u.id
    async with Session() as s:
        # right credentials -> User
        u = await authenticate_user(s, 'A@B.com', 'pw1234567')
        assert u is not None and u.id == uid, u
        # wrong password -> None
        u = await authenticate_user(s, 'a@b.com', 'wrong')
        assert u is None
        # unknown email -> None
        u = await authenticate_user(s, 'nope@nope.com', 'pw1234567')
        assert u is None
    print('ok')

asyncio.run(main())
" | grep -q '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'async def authenticate_user' app/services/auth_service.py`
    - `grep -q '_DUMMY_HASH' app/services/auth_service.py` (timing equalization present)
    - `grep -q 'is_active' app/services/auth_service.py` (deactivated-user gate present)
    - `grep -q '\.scalar_one_or_none()' app/services/auth_service.py` (SQLAlchemy 2.x select() pattern, not legacy `.first()` on a Query)
    - The verify block passes: right creds → User, wrong password → None, unknown email → None
    - `grep -qE 'passlib' app/services/auth_service.py` MUST return exit 1
  </acceptance_criteria>
</task>

</tasks>

<verification>
After both tasks:
1. `uv run python -c "from app.services.auth_service import register_user, authenticate_user, EmailAlreadyExistsError"` exits 0.
2. The two automated verify scripts above both print `ok`.
3. `grep -rE 'passlib|python-jose' app/services/` returns empty (exit 1) — banned hashers absent.
4. `grep -rE '^[[:space:]]*print\(' app/services/` returns empty — JSON logs only (CLAUDE.md).
5. The service file fits on one screen of context for plan 06's executor (~120 lines including docstrings).
</verification>

<success_criteria>
- AUTH-01 path closed at the service layer: register flow (insert + duplicate guard) is testable without HTTP.
- AUTH-02 path closed at the service layer: authenticate flow (verify password, deactivated check) is testable without HTTP.
- AUTH-04 (cross-user isolation) foundation: `authenticate_user` returns the actual User (with its UUID4 id), so plan 05's `get_current_user` can fetch by `User.id` and plan 06 can scope every protected route by `current_user.id`.
- All ROADMAP SC#1–3 are now implementable in plans 05 and 06; this plan unblocks them by providing the only seam where bcrypt + DB I/O happen.
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundation/01-04-SUMMARY.md` with: exact public surface (signatures of `register_user`, `authenticate_user`, `EmailAlreadyExistsError`), commit hashes (GSD-108, GSD-109), any deviations from the interfaces block above and why.
</output>
