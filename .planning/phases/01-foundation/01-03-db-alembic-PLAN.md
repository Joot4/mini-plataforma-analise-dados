---
name: db-models-session-alembic
phase: 01-foundation
plan: 03
type: execute
wave: 2
depends_on: [01]
files_modified:
  - app/db/__init__.py
  - app/db/models.py
  - app/db/session.py
  - alembic.ini
  - app/db/migrations/env.py
  - app/db/migrations/script.py.mako
  - app/db/migrations/versions/__init__.py
  - app/db/migrations/versions/0001_create_users.py
autonomous: true
requirements: [AUTH-01, AUTH-04, OPS-05]
must_haves:
  truths:
    - "Users table exists after `alembic upgrade head` with: id (UUID4 PK), email (unique indexed), password_hash, created_at, updated_at, is_active"
    - "get_db_session() yields an AsyncSession usable in FastAPI Depends"
    - "alembic env.py reads DATABASE_URL from Settings, never hardcoded"
    - "Migration is reversible: `alembic downgrade base` drops the users table cleanly"
  artifacts:
    - path: "app/db/models.py"
      provides: "SQLAlchemy 2.x declarative User model"
      exports: ["Base", "User"]
    - path: "app/db/session.py"
      provides: "Async engine + session factory + get_db_session() FastAPI dep"
      exports: ["engine", "AsyncSessionLocal", "get_db_session"]
    - path: "app/db/migrations/versions/0001_create_users.py"
      provides: "Initial migration creating users table"
      contains: "op.create_table('users'"
    - path: "alembic.ini"
      provides: "Alembic configuration pointing at app/db/migrations"
      contains: "script_location = app/db/migrations"
  key_links:
    - from: "app/db/migrations/env.py"
      to: "app/core/config.get_settings"
      via: "reads DATABASE_URL at migration time"
      pattern: "get_settings\\(\\)\\.DATABASE_URL"
    - from: "app/db/session.py"
      to: "app/db/models.Base"
      via: "Shared Base for models + metadata"
      pattern: "from app.db.models import Base"
---

<objective>
Build the persistence layer: SQLAlchemy 2.x async `User` model with UUID4 PK per PITFALLS.md#11, async engine + session factory, alembic fully wired with an initial migration that creates the `users` table. This unblocks the auth service (Plan 05), the API deps (Plan 06 `get_db_session`), and the Docker entrypoint that runs `alembic upgrade head` on startup (Plan 08).

Purpose: Everything user-facing auth needs a real `users` table that alembic manages deterministically. Running `alembic upgrade head` must be idempotent and work from a clean volume.
Output: `app/db/{models,session}.py`, complete `alembic/` skeleton under `app/db/migrations/`, first migration committed.
</objective>

<execution_context>
@/Users/junioralmeida/Desktop/Projetos/.claude/get-shit-done/workflows/execute-plan.md
@/Users/junioralmeida/Desktop/Projetos/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/phases/01-foundation/01-CONTEXT.md
@.planning/research/STACK.md
@.planning/research/ARCHITECTURE.md
@.planning/research/PITFALLS.md
@.planning/phases/01-foundation/01-01-SUMMARY.md

<interfaces>
<!-- Plan 05 (auth_service) and Plan 06 (api/deps + routers) import these directly. -->

From app/db/models.py:
```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Boolean, DateTime
import uuid
from datetime import datetime

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), ...)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), ...)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

From app/db/session.py:
```python
engine: AsyncEngine
AsyncSessionLocal: async_sessionmaker[AsyncSession]

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency. Yields a session, commits on success, rolls back on exception, always closes."""
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: app/db/models.py + app/db/session.py (SQLAlchemy 2.x async)</name>
  <behavior>
    - Importing app.db.models imports Base + User with no errors
    - User.__tablename__ == "users"
    - User has columns: id (UUID4 PK), email (str, unique, indexed), password_hash, created_at, updated_at, is_active
    - get_db_session() is an async generator yielding an AsyncSession
    - On exception inside the session usage, rollback is called; on success commit is called
    - engine.url matches Settings.DATABASE_URL
  </behavior>
  <read_first>
    - .planning/phases/01-foundation/01-CONTEXT.md §Claude's Discretion — Users table (UUID4 PK via uuid.uuid4, Mapped[] typing)
    - .planning/research/PITFALLS.md §Pitfall 11 (never sequential IDs; UUID4 only)
    - .planning/research/STACK.md (SQLAlchemy 2.0 async)
    - .planning/research/ARCHITECTURE.md §Recommended Project Structure (app/db/ layout)
    - app/core/config.py (just written — get_settings().DATABASE_URL shape)
  </read_first>
  <files>app/db/__init__.py, app/db/models.py, app/db/session.py</files>
  <action>
Create `app/db/__init__.py` as an empty file.

Write `app/db/models.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models. Used by alembic autogenerate."""


class User(Base):
    __tablename__ = "users"

    # UUID4 PK — never sequential integers (PITFALLS.md#11 — enumeration attack prevention).
    # Stored as string on SQLite (36-char UUID); SQLAlchemy handles the conversion.
    id: Mapped[uuid.UUID] = mapped_column(
        String(36), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
```

Notes:
- `String(36)` for UUID on SQLite (SQLite has no native UUID type; SQLAlchemy serializes `uuid.UUID` → string). On a future Postgres migration this becomes `PG_UUID(as_uuid=True)` — trivial change, not blocking.
- `DateTime(timezone=True)` keeps UTC intent even though SQLite stores naive strings; aiosqlite round-trips the tz-aware values.

Write `app/db/session.py`:

```python
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db.models import Base  # re-exported for alembic env.py convenience

settings = get_settings()

# `future=True` is default in 2.x but we set it for clarity.
# `echo=settings.DEBUG` surfaces SQL in dev; silent in prod.
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    # SQLite-specific: allow same thread checks to relax (aiosqlite handles concurrency).
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency.

    Yields an async SQLAlchemy session, commits on success, rolls back on exception,
    always closes in finally. Plan 06 (app/api/deps.py) re-exports this.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


__all__ = ["Base", "engine", "AsyncSessionLocal", "get_db_session"]
```

Notes:
- `expire_on_commit=False` so objects remain usable after commit without re-fetch (FastAPI-friendly).
- `connect_args={"check_same_thread": False}` is required for SQLite + aiosqlite in async contexts; pydantic URL detection is simple string prefix check.
- `Base` is re-exported so alembic env.py can do `from app.db.session import Base` with just one import line.
  </action>
  <verify>
    <automated>uv run python -c "from app.db.models import Base, User; from app.db.session import engine, AsyncSessionLocal, get_db_session; assert User.__tablename__ == 'users'; cols = {c.name for c in User.__table__.columns}; assert cols == {'id','email','password_hash','created_at','updated_at','is_active'}, cols; print('ok')" | grep -q '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'class User(Base):' app/db/models.py`
    - `grep -q '__tablename__ = "users"' app/db/models.py`
    - `grep -q 'uuid.uuid4' app/db/models.py` (UUID4 PK — PITFALLS.md#11)
    - `grep -q 'from sqlalchemy.ext.asyncio import' app/db/session.py`
    - `grep -q 'async def get_db_session' app/db/session.py`
    - `grep -q 'expire_on_commit=False' app/db/session.py`
    - Automated verify above prints `ok` (column set is exactly the 6 required fields)
  </acceptance_criteria>
</task>

<task type="auto" tdd="true">
  <name>Task 2: alembic init + env.py (Async) + initial migration 0001_create_users</name>
  <behavior>
    - `alembic.ini` exists at repo root, with `script_location = app/db/migrations` and `sqlalchemy.url` either empty or resolved from env (env.py handles it)
    - `app/db/migrations/env.py` reads DATABASE_URL from Settings at runtime (no hardcoded URL)
    - `alembic upgrade head` against a fresh SQLite DB creates the `users` table with the correct schema
    - `alembic downgrade base` drops the users table cleanly
    - Running `alembic upgrade head` twice in a row is a no-op the second time (idempotent)
    - Initial migration file exists at `app/db/migrations/versions/0001_create_users.py` with revision id `0001` and down_revision `None`
  </behavior>
  <read_first>
    - .planning/phases/01-foundation/01-CONTEXT.md §Claude's Discretion — Alembic (env.py reads DATABASE_URL from Settings)
    - .planning/research/ARCHITECTURE.md §Recommended Project Structure (app/db/migrations/)
    - app/db/models.py + app/db/session.py (just written — Base lives in models, re-exported from session)
    - .planning/research/STACK.md §uv Workflow Reference (`uv run alembic ...`)
  </read_first>
  <files>
    alembic.ini,
    app/db/migrations/env.py,
    app/db/migrations/script.py.mako,
    app/db/migrations/versions/__init__.py,
    app/db/migrations/versions/0001_create_users.py
  </files>
  <action>
Do NOT use `uv run alembic init` directly — it generates a default layout we then have to edit. Instead, create files explicitly so the layout is deterministic and reviewable:

**1. `alembic.ini` at repo root:**

```ini
[alembic]
script_location = app/db/migrations
prepend_sys_path = .
# Migration filenames: 0001_create_users.py, 0002_xxx.py, etc.
file_template = %%(rev)s_%%(slug)s
# URL is loaded from Settings in env.py — leave blank here.
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

**2. `app/db/migrations/script.py.mako` (minimal template — copy of alembic default with our header):**

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

**3. `app/db/migrations/versions/__init__.py`:** empty file.

**4. `app/db/migrations/env.py` — async mode, Settings-driven URL:**

```python
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.db.models import Base

# Alembic Config object (reads alembic.ini).
config = context.config

# Inject DATABASE_URL from Settings (overrides the empty sqlalchemy.url in alembic.ini).
config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)

# Python logging from alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate target — Base.metadata covers every model imported from app.db.models.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite column alters
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

**5. `app/db/migrations/versions/0001_create_users.py`:**

```python
"""create users table

Revision ID: 0001
Revises:
Create Date: 2026-04-24

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
```

Run `uv run alembic upgrade head` to smoke-test (creates the SQLite DB + table). On success, the SQLite file appears at `./data/db/app.sqlite` — which is gitignored.

After smoke-test, also run `uv run alembic downgrade base` to verify reverse path, then `uv run alembic upgrade head` again so the migration is applied for any downstream task.

Notes:
- `render_as_batch=True` is required for SQLite because it doesn't support standard `ALTER TABLE` — batch mode emulates it via table rebuild. Mandatory even if Phase 1 doesn't alter, so future migrations inherit it.
- Explicit migration file (hand-written, not `--autogenerate`) avoids the "autogen picked up a random extra" surprise. With only one model (User) and a deterministic column list, hand-writing is clearer.
- `server_default=sa.true()` on `is_active` ensures existing rows (none now, but future-safe) get `is_active=true` on a column add.
  </action>
  <verify>
    <automated>rm -f ./data/db/app.sqlite &amp;&amp; uv run alembic upgrade head 2>&amp;1 | tee /tmp/alembic_up.log &amp;&amp; uv run python -c "import sqlite3; con = sqlite3.connect('./data/db/app.sqlite'); cur = con.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='users'\"); assert cur.fetchone() is not None, 'users table missing'; cur = con.execute(\"PRAGMA table_info(users)\"); cols = {row[1] for row in cur.fetchall()}; assert cols == {'id','email','password_hash','created_at','updated_at','is_active'}, cols; print('ok')" | grep -q '^ok$' &amp;&amp; uv run alembic downgrade base &amp;&amp; uv run alembic upgrade head