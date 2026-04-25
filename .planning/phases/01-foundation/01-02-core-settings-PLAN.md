---
name: core-settings-security-logging
phase: 01-foundation
plan: 02
type: execute
wave: 2
depends_on: [01]
files_modified:
  - app/__init__.py
  - app/core/__init__.py
  - app/core/config.py
  - app/core/security.py
  - app/core/logging.py
autonomous: true
requirements: [AUTH-01, AUTH-02, AUTH-03]
must_haves:
  truths:
    - "Settings loads from .env + environment, env wins over .env"
    - "hash_password returns a pwdlib bcrypt hash; verify_password round-trips correctly"
    - "JWT encode/decode round-trips; expired token raises jwt.ExpiredSignatureError"
    - "Missing JWT_SECRET_KEY triggers ephemeral key + WARNING log at first get_settings() call"
    - "structlog configured to emit JSON to stdout with timestamp/level/event fields"
  artifacts:
    - path: "app/core/config.py"
      provides: "Settings(BaseSettings) + get_settings() lru_cache singleton"
      exports: ["Settings", "get_settings"]
    - path: "app/core/security.py"
      provides: "Password hashing + JWT encode/decode"
      exports: ["hash_password", "verify_password", "create_access_token", "decode_access_token", "TokenPayload"]
    - path: "app/core/logging.py"
      provides: "structlog JSON configuration"
      exports: ["configure_logging", "get_logger"]
  key_links:
    - from: "app/core/security.py"
      to: "app/core/config.py"
      via: "get_settings() for JWT_SECRET_KEY + JWT_ALGORITHM + JWT_ACCESS_TOKEN_EXPIRE_MINUTES"
      pattern: "get_settings\\(\\)\\.JWT_"
    - from: "app/core/security.py"
      to: "pwdlib"
      via: "PasswordHash + BcryptHasher (NOT passlib)"
      pattern: "from pwdlib"
---

<objective>
Build the cross-cutting infrastructure layer: typed `Settings` via `pydantic-settings`, password hashing + JWT helpers via `pwdlib[bcrypt]` + `PyJWT`, and `structlog` JSON logging. These are consumed by the auth service, the API deps layer, the DB session module, `main.py` middleware, and every future LLM call log (Phase 4, OPS-03).

Purpose: Centralize config + security primitives + logging once so no other module re-implements them. Cements the "passlib is banned, pwdlib is the only password hasher" rule at the lowest layer.
Output: `app/core/{config,security,logging}.py` + package `__init__.py` files.
</objective>

<execution_context>
@/Users/junioralmeida/Desktop/Projetos/.claude/get-shit-done/workflows/execute-plan.md
@/Users/junioralmeida/Desktop/Projetos/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/phases/01-foundation/01-CONTEXT.md
@.planning/research/STACK.md
@.planning/research/PITFALLS.md
@.planning/research/ARCHITECTURE.md
@.planning/phases/01-foundation/01-01-SUMMARY.md

<interfaces>
<!-- Downstream plans (03 db, 04 tasks, 05 schemas+service, 06 api) will import these. -->
<!-- Treat these signatures as the public contract of this plan. -->

From app/core/config.py:
```python
class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str | None = None   # None means ephemeral
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    UPLOADS_DIR: str = "/data/uploads"
    MAX_UPLOAD_BYTES: int = 52_428_800
    MAX_UPLOAD_ROWS: int = 500_000
    SESSION_TTL_SECONDS: int = 3600
    OPENAI_API_KEY: str | None = None
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

def get_settings() -> Settings: ...   # @lru_cache singleton
```

From app/core/security.py:
```python
def hash_password(plain: str) -> str: ...
def verify_password(plain: str, hashed: str) -> bool: ...

class TokenPayload(BaseModel):
    sub: str           # user_id as string (UUID4)
    exp: int           # unix timestamp
    iat: int           # unix timestamp

def create_access_token(subject: str, expires_minutes: int | None = None) -> str: ...
def decode_access_token(token: str) -> TokenPayload: ...   # raises jwt.PyJWTError on invalid
```

From app/core/logging.py:
```python
def configure_logging(level: str = "INFO", debug: bool = False) -> None: ...
def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger: ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: app/core/config.py + Settings + get_settings() singleton</name>
  <behavior>
    - Given valid env vars (JWT_SECRET_KEY set, DATABASE_URL set) → Settings loads with those values
    - Given .env file with JWT_SECRET_KEY=fromfile and env var JWT_SECRET_KEY=fromenv → Settings.JWT_SECRET_KEY == "fromenv" (env wins)
    - Given no JWT_SECRET_KEY set (neither .env nor env) → Settings.JWT_SECRET_KEY is None (ephemeral handled in security.py layer, not here)
    - get_settings() returns the same object across calls (lru_cache); clearing the cache returns a new instance
    - DEBUG defaults False, LOG_LEVEL defaults "INFO", JWT_ALGORITHM defaults "HS256", JWT_ACCESS_TOKEN_EXPIRE_MINUTES defaults 30
  </behavior>
  <read_first>
    - app/core/config.py (will not exist — greenfield; read the interfaces block above for shape)
    - .planning/phases/01-foundation/01-CONTEXT.md §D-06 (full Settings field list)
    - .planning/research/STACK.md §Supporting Libraries (python-dotenv + pydantic-settings)
    - .planning/research/PITFALLS.md §Pitfall 12 (secret from env, never hardcoded, ephemeral fallback logs warning)
  </read_first>
  <files>app/__init__.py, app/core/__init__.py, app/core/config.py</files>
  <action>
Create `app/__init__.py` and `app/core/__init__.py` as empty files.

Write `app/core/config.py`:

```python
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Loads from environment variables; falls back to .env file.
    Environment variables take precedence over .env (standard pydantic-settings behavior).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Database ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/db/app.sqlite"

    # --- JWT / Auth ---
    # None => ephemeral key generated in security.py with WARNING log (see PITFALLS.md#12).
    JWT_SECRET_KEY: str | None = None
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1, le=1440)

    # --- Uploads (Phase 2 consumes) ---
    UPLOADS_DIR: str = "/data/uploads"
    MAX_UPLOAD_BYTES: int = 52_428_800  # 50 MB
    MAX_UPLOAD_ROWS: int = 500_000
    SESSION_TTL_SECONDS: int = 3600

    # --- OpenAI (Phase 4 consumes) ---
    OPENAI_API_KEY: str | None = None

    # --- App ---
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor. Cache is cleared by calling get_settings.cache_clear() (used in tests)."""
    return Settings()  # type: ignore[call-arg]
```

Notes:
- `Field(..., ge=1, le=1440)` bounds the JWT TTL at 1 minute min / 24 hours max — defensive.
- `extra="ignore"` ensures unrelated env vars (like PATH) don't crash the app at startup.
- `case_sensitive=True` matches the `.env.example` casing.
  </action>
  <verify>
    <automated>uv run python -c "from app.core.config import get_settings; s = get_settings(); assert s.JWT_ALGORITHM == 'HS256'; assert s.JWT_ACCESS_TOKEN_EXPIRE_MINUTES == 30; assert s.DEBUG is False; print('ok')" | grep -q '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'from pydantic_settings import BaseSettings' app/core/config.py`
    - `grep -q 'JWT_SECRET_KEY' app/core/config.py`
    - `grep -q '@lru_cache' app/core/config.py`
    - Import test succeeds: `uv run python -c "from app.core.config import Settings, get_settings"` exits 0
    - Default JWT_ACCESS_TOKEN_EXPIRE_MINUTES is 30 (assertion above)
    - `grep -q 'passlib' app/core/config.py` MUST return exit 1
  </acceptance_criteria>
</task>

<task type="auto" tdd="true">
  <name>Task 2: app/core/security.py — pwdlib + PyJWT helpers</name>
  <behavior>
    - hash_password("hunter2") returns a string starting with "$2b$" (bcrypt marker) and NOT equal to "hunter2"
    - verify_password("hunter2", hash_password("hunter2")) returns True
    - verify_password("wrong", hash_password("hunter2")) returns False
    - create_access_token(subject="user-uuid") returns a 3-part JWT; decode_access_token on it yields TokenPayload with sub == "user-uuid"
    - decode_access_token on a token signed with a different secret raises jwt.InvalidSignatureError
    - decode_access_token on a token whose exp is in the past raises jwt.ExpiredSignatureError
    - When settings.JWT_SECRET_KEY is None, a call to create_access_token triggers an ephemeral key and emits a WARNING log with event name "jwt.ephemeral_key_generated" (structlog captured)
  </behavior>
  <read_first>
    - app/core/config.py (just written — interfaces)
    - .planning/research/PITFALLS.md §Pitfall 12 (pwdlib usage, bcrypt backend, ephemeral secret warning pattern)
    - .planning/research/STACK.md §Recommended Stack (PyJWT 2.12, pwdlib 0.3)
    - CLAUDE.md (pwdlib NOT passlib — non-negotiable)
  </read_first>
  <files>app/core/security.py</files>
  <action>
Write `app/core/security.py`:

```python
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Final

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# pwdlib PasswordHash with bcrypt backend only (default cost factor = 12 — FastAPI rec).
# Do NOT import passlib anywhere — banned per CLAUDE.md.
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
    minutes = expires_minutes if expires_minutes is not None else settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(tz=timezone.utc)
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
```

Notes:
- Secret is cached at module level with an explicit `_reset_secret()` test hook rather than re-reading settings on every token operation. Avoids a race where `get_settings.cache_clear()` in a fixture mid-test generates a fresh ephemeral key between encode and decode.
- `jwt.decode(..., options={"require": [...]})` enforces that expired/unsigned tokens get rejected with the correct exception class (ExpiredSignatureError / MissingRequiredClaimError).
- `datetime.now(tz=timezone.utc)` — never `datetime.utcnow()` (deprecated in 3.12).
  </action>
  <verify>
    <automated>uv run python -c "from app.core.security import hash_password, verify_password, create_access_token, decode_access_token; h = hash_password('hunter2'); assert h.startswith('\$2b\$'); assert verify_password('hunter2', h); assert not verify_password('wrong', h); t = create_access_token('u-1'); p = decode_access_token(t); assert p.sub == 'u-1'; print('ok')" | grep -q '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'from pwdlib import PasswordHash' app/core/security.py`
    - `grep -q 'from pwdlib.hashers.bcrypt import BcryptHasher' app/core/security.py`
    - `grep -q 'import jwt' app/core/security.py` (PyJWT)
    - `grep -qE 'passlib|python-jose' app/core/security.py` MUST return exit 1 (both banned)
    - Inline round-trip in verify block passes (hash/verify/encode/decode)
    - `grep -q 'jwt.ephemeral_key_generated' app/core/security.py` (the warning event name — test_security.py in plan 07 will assert on it)
  </acceptance_criteria>
</task>

<task type="auto" tdd="true">
  <name>Task 3: app/core/logging.py — structlog JSON to stdout</name>
  <behavior>
    - configure_logging("INFO") sets up structlog to emit JSON
    - get_logger("test").info("hello", foo=1) writes a JSON line to stdout with fields: event=hello, foo=1, level=info, timestamp (ISO8601)
    - In DEBUG mode (configure_logging(debug=True)), output is human-readable colored lines instead of JSON (developer-friendly)
    - structlog stdlib integration allows `logger = get_logger(__name__)` in any module
  </behavior>
  <read_first>
    - CLAUDE.md (JSON structured logs to stdout, never `print`)
    - .planning/research/STACK.md §Supporting Libraries (structlog 24.0)
    - .planning/phases/01-foundation/01-CONTEXT.md §Claude's Discretion (LLM call log fields — to be honored starting Phase 4)
  </read_first>
  <files>app/core/logging.py</files>
  <action>
Write `app/core/logging.py`:

```python
from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO", *, debug: bool = False) -> None:
    """Configure structlog + stdlib logging to emit JSON (or pretty in DEBUG) to stdout.

    Idempotent: safe to call multiple times (tests, uvicorn reload).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Route stdlib logging → stdout at the chosen level.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if debug:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger, optionally namespaced."""
    return structlog.get_logger(name)
```

Notes:
- `structlog.contextvars.merge_contextvars` is what lets Plan 06's middleware bind `request_id` / `user_id` once per request and have every subsequent log line inside that request automatically include those fields.
- `force=True` on `basicConfig` prevents duplicate handlers if uvicorn reload re-imports the module.
- The `logger` import in `app/core/security.py` relies on this module existing — configure_logging is idempotent and the get_logger returned is lazy-bound, so importing security.py before configure_logging() is called still works.
  </action>
  <verify>
    <automated>uv run python -c "from app.core.logging import configure_logging, get_logger; configure_logging('INFO'); log = get_logger('test'); log.info('hello', foo=1)" 2>/dev/null | python -c "import json,sys; line = sys.stdin.read().strip(); d = json.loads(line); assert d['event']=='hello'; assert d['foo']==1; assert d['level']=='info'; assert 'timestamp' in d; print('ok')" | grep -q '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'import structlog' app/core/logging.py`
    - `grep -q 'JSONRenderer' app/core/logging.py`
    - `grep -q 'merge_contextvars' app/core/logging.py` (needed by middleware in plan 06)
    - `grep -q 'force=True' app/core/logging.py` (idempotent under uvicorn reload)
    - The automated verify above outputs exactly `ok` (valid JSON with event/foo/level/timestamp)
    - No `print(` call in app/core/logging.py (CLAUDE.md: never print)
  </acceptance_criteria>
</task>

</tasks>

<verification>
After all 3 tasks:
1. `uv run python -c "from app.core.config import get_settings; from app.core.security import hash_password, verify_password, create_access_token, decode_access_token; from app.core.logging import configure_logging, get_logger"` exits 0.
2. `grep -r passlib app/core/` returns empty (exit 1) — non-negotiable.
3. `grep -r "print(" app/core/` returns empty (exit 1) — JSON logs only.
4. Password round-trip + JWT round-trip both work (verified inline above).
</verification>

<success_criteria>
- Core layer provides a clean import surface for all downstream modules (db, auth service, api)
- Password hashing uses pwdlib bcrypt (not passlib, not hashlib, not sha*) — AUTH-01 foundation
- JWT encode/decode works per AUTH-02 foundation; expired/invalid tokens raise typed PyJWT errors per AUTH-03
- Ephemeral-key warning fires when JWT_SECRET_KEY is absent (PITFALLS.md#12)
- structlog JSON logging is configured and consumable by `configure_logging()` from `main.py` in Plan 06 (OPS-03 foundation)
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundation/01-02-SUMMARY.md` with: exact symbol list exported by each `app/core/*.py` file, any deviations from the interfaces block above and why.
</output>
