---
phase: 01-foundation
plan: 02
subsystem: core
tags: [pydantic-settings, pwdlib, bcrypt, pyjwt, structlog, jwt, logging, config, settings]

# Dependency graph
requires:
  - phase: 01-foundation
    plan: 01
    provides: locked deps (pydantic-settings, pwdlib[bcrypt], pyjwt, structlog) + .env.example documenting Settings fields
provides:
  - Settings(BaseSettings) with all v1 fields + get_settings() lru_cache singleton
  - hash_password / verify_password (pwdlib bcrypt) — AUTH-01 foundation
  - create_access_token / decode_access_token / TokenPayload (PyJWT HS256) — AUTH-02/03 foundation
  - JWT secret resolution: env var first, ephemeral fallback with structured WARNING (PITFALLS.md#12)
  - configure_logging() + get_logger() — structlog JSON to stdout (debug=True for human-readable)
  - structlog.contextvars.merge_contextvars wired in so Plan 06 middleware can bind request_id/user_id per-request
affects: [01-03-db-alembic, 01-04-auth-service, 01-05-api-deps-routes, 01-06-main-middleware, 04-llm-call-logs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-level secret cache in app.core.security with _reset_secret() test hook — avoids ephemeral key being regenerated mid-test if get_settings.cache_clear() runs between encode/decode"
    - "datetime.now(tz=timezone.utc) — never the deprecated utcnow() (CLAUDE.md Python 3.12)"
    - "jwt.decode(..., options={'require': ['sub','exp','iat']}) — explicit claim enforcement so MissingRequiredClaim raises typed errors"
    - "structlog cache_logger_on_first_use=True + force=True on basicConfig — idempotent under uvicorn reload"
    - "Field(default=30, ge=1, le=1440) on JWT_ACCESS_TOKEN_EXPIRE_MINUTES — defensive bound (1 min to 24h)"

key-files:
  created:
    - "app/__init__.py — empty package marker"
    - "app/core/__init__.py — empty package marker"
    - "app/core/config.py — Settings(BaseSettings) + get_settings() lru_cache; 49 lines"
    - "app/core/security.py — pwdlib bcrypt + PyJWT helpers + TokenPayload; 101 lines"
    - "app/core/logging.py — structlog JSON config + get_logger; 48 lines"
  modified: []

key-decisions:
  - "Secret resolution caches in security.py module state (not in Settings) so a test that calls get_settings.cache_clear() doesn't accidentally rotate the ephemeral key between encode and decode in the same test"
  - "Executed Task 3 (logging) before Task 2 (security): security.py imports get_logger from logging.py; the plan's nominal order would have left a broken-import state at the Task 2 commit. Reordering keeps every commit green."
  - "Comment in security.py was reworded to avoid the literal banned tokens (passlib / python-jose) so that the plan's grep -qE 'passlib|python-jose' acceptance check passes — the wording change preserves the 'pwdlib only' rule's intent"

patterns-established:
  - "Pattern: All app/core/* modules import logging via app.core.logging.get_logger — structured JSON observability is now the project default; never use print() or stdlib logging directly downstream"
  - "Pattern: pwdlib + bcrypt is the ONLY password hasher allowed (CLAUDE.md non-negotiable, verified absent in app/core after this plan)"
  - "Pattern: env-driven secrets — JWT_SECRET_KEY pulled from Settings, ephemeral fallback emits a structured warning with stable event name `jwt.ephemeral_key_generated` (Phase 1 Plan 07 tests will assert on it)"

requirements-completed: [AUTH-01-foundation, AUTH-02-foundation, AUTH-03-foundation]

# Metrics
duration: 5min
completed: 2026-04-25
---

# Phase 1 Plan 02: Core Settings + Security + Logging Summary

**Cross-cutting infrastructure layer: typed Settings via pydantic-settings, pwdlib bcrypt + PyJWT helpers with ephemeral-key WARNING, and structlog JSON logging to stdout — three modules totalling ~200 lines that every downstream plan (db, auth, api, main, LLM) consumes.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-25T00:23:48Z
- **Completed:** 2026-04-25T00:28:19Z
- **Tasks:** 3 / 3
- **Files modified:** 5 created, 0 modified

## Symbols Exported

### `app/core/config.py`

| Symbol | Kind | Signature |
|--------|------|-----------|
| `Settings` | class | `BaseSettings` subclass; fields: `DATABASE_URL: str`, `JWT_SECRET_KEY: str \| None`, `JWT_ALGORITHM: str = "HS256"`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30 (1..1440)`, `UPLOADS_DIR: str = "/data/uploads"`, `MAX_UPLOAD_BYTES: int = 52_428_800`, `MAX_UPLOAD_ROWS: int = 500_000`, `SESSION_TTL_SECONDS: int = 3600`, `OPENAI_API_KEY: str \| None`, `DEBUG: bool = False`, `LOG_LEVEL: str = "INFO"`. Reads `.env` (utf-8) then env-var override; `case_sensitive=True`; `extra="ignore"`. |
| `get_settings` | function | `() -> Settings` — `@lru_cache(maxsize=1)` singleton; tests call `get_settings.cache_clear()` to force re-read. |

### `app/core/security.py`

| Symbol | Kind | Signature |
|--------|------|-----------|
| `hash_password` | function | `(plain: str) -> str` — bcrypt via pwdlib; output starts with `$2b$`. |
| `verify_password` | function | `(plain: str, hashed: str) -> bool` — pwdlib roundtrip. |
| `TokenPayload` | class | `BaseModel` with `sub: str`, `exp: int`, `iat: int`. |
| `create_access_token` | function | `(subject: str, expires_minutes: int \| None = None) -> str` — HS256 JWT signed with `_get_secret()`; uses `settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES` when no override; UTC iat/exp via `datetime.now(tz=timezone.utc)`. |
| `decode_access_token` | function | `(token: str) -> TokenPayload` — enforces `require=['sub','exp','iat']`; raises `jwt.InvalidSignatureError` / `jwt.ExpiredSignatureError` / `jwt.MissingRequiredClaimError` via `jwt.PyJWTError` hierarchy. |
| `_get_secret` | private | Module-internal cached secret resolver; logs `jwt.ephemeral_key_generated` warning when `JWT_SECRET_KEY` unset. |
| `_reset_secret` | private | Test-only hook to clear the cached secret. |

### `app/core/logging.py`

| Symbol | Kind | Signature |
|--------|------|-----------|
| `configure_logging` | function | `(level: str = "INFO", *, debug: bool = False) -> None` — idempotent (`force=True`); shared processors include `merge_contextvars`, `add_logger_name`, `add_log_level`, ISO UTC `TimeStamper`, `StackInfoRenderer`, `format_exc_info`; renderer is `JSONRenderer` (default) or `ConsoleRenderer(colors=True)` when `debug=True`. |
| `get_logger` | function | `(name: str \| None = None) -> structlog.stdlib.BoundLogger`. |

## Task Commits

1. **Task 1: app/core/config.py + Settings + get_settings()** — `e706fcf` (feat)
   - Created: `app/__init__.py`, `app/core/__init__.py`, `app/core/config.py`
   - DPE message: `feat(core):[GSD-102] - Add Settings via pydantic-settings + get_settings cache`
2. **Task 3 (executed before Task 2 — see Deviations): app/core/logging.py** — `5f97339` (feat)
   - Created: `app/core/logging.py`
   - DPE message: `feat(core):[GSD-103] - Configure structlog JSON logger for stdout`
3. **Task 2: app/core/security.py — pwdlib + PyJWT** — `dcd5940` (feat)
   - Created: `app/core/security.py`
   - DPE message: `feat(core):[GSD-104] - Add pwdlib bcrypt and PyJWT helpers with ephemeral key`

## Files Created/Modified

- `app/__init__.py` — empty (package marker for `app.*` imports)
- `app/core/__init__.py` — empty (package marker for `app.core.*` imports)
- `app/core/config.py` — Settings, get_settings (49 lines)
- `app/core/security.py` — password + JWT helpers, TokenPayload (101 lines)
- `app/core/logging.py` — structlog JSON config (48 lines)

## Behavior Verified

### Settings (Task 1)
- Env var `JWT_SECRET_KEY=fromenv-test` → `Settings().JWT_SECRET_KEY == "fromenv-test"` (env wins)
- No env var, no `.env` → `Settings().JWT_SECRET_KEY is None` (ephemeral handled in security layer)
- `get_settings()` returns the same object across calls; `cache_clear()` returns a fresh instance
- Defaults exact: `JWT_ALGORITHM="HS256"`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30`, `DEBUG=False`, `LOG_LEVEL="INFO"`

### Security (Task 2)
- `hash_password("hunter2")` returns `$2b$...` and `!= "hunter2"`
- `verify_password("hunter2", h) is True`; `verify_password("wrong", h) is False`
- JWT round-trip: `decode_access_token(create_access_token("u-1")).sub == "u-1"`
- JWT is 3-part (`header.payload.signature`)
- Wrong-secret token raises `jwt.InvalidSignatureError`
- Past-exp token raises `jwt.ExpiredSignatureError`
- Missing `JWT_SECRET_KEY` triggers ephemeral key + structured warning with `event="jwt.ephemeral_key_generated"`, `level="warning"`, `logger="app.core.security"` (verified via captured stdout JSON)

### Logging (Task 3)
- `configure_logging("INFO")` + `get_logger("test").info("hello", foo=1)` emits one JSON line on stdout with `event=hello`, `foo=1`, `level=info`, `logger=test`, ISO-UTC `timestamp`
- `configure_logging("DEBUG", debug=True)` switches to ConsoleRenderer (output not parseable as JSON — pretty colored format)
- Idempotent under multiple `configure_logging()` calls (no duplicate handlers, thanks to `force=True`)

## Decisions Made

- **Order swap (Task 3 before Task 2):** `app/core/security.py` imports `from app.core.logging import get_logger` at module load. Committing Task 2 before Task 3 would have left an `ImportError` state at the intermediate commit — `from app.core.security import ...` in Task 2's verify would fail. Swapping order keeps every intermediate commit importable. Documented as Deviation 1 (Rule 3 — blocking).
- **Comment rewording in security.py:** The plan's Task 2 acceptance criteria includes `grep -qE 'passlib|python-jose' app/core/security.py MUST return exit 1`. The original action block contained a comment `# Do NOT import passlib anywhere — banned per CLAUDE.md.` which contains the literal banned token and would fail the grep. Reworded to `# CLAUDE.md non-negotiable: only pwdlib is allowed for password hashing.` Same intent, satisfies the AC. Documented as Deviation 2 (Rule 3).
- **Module-level `_secret_cache` in security.py:** Keeping the secret in a module-level variable (not re-reading `get_settings()` on every encode/decode call) is intentional — it prevents a race where a test that does `get_settings.cache_clear()` mid-test would rotate the ephemeral key between create_access_token and decode_access_token, breaking the round-trip. Test-only `_reset_secret()` hook is provided for any test that genuinely wants a fresh secret.
- **`Field(ge=1, le=1440)` on JWT TTL:** Defensive bound — 1 min lower (any shorter is operationally useless) / 24h upper (anything longer should use a refresh token). Plan called for it explicitly; kept as written.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Reordered Task 2 / Task 3 to satisfy import dependency**
- **Found during:** between Task 1 commit and Task 2 implementation
- **Issue:** `app/core/security.py` (Task 2) imports `from app.core.logging import get_logger` at module load. `app/core/logging.py` does not exist until Task 3. Committing Task 2 in isolation would leave the working tree at an `ImportError` state — Task 2's own verify block would fail (`from app.core.security import ...` triggers the missing-module import). The plan note in Task 3's `<action>` even acknowledged this dependency.
- **Fix:** Executed and committed Task 3 (logging.py — `5f97339`) before Task 2 (security.py — `dcd5940`). Logical order in the plan is preserved in this SUMMARY (Task 1 / Task 2 / Task 3 in symbol listing); only the commit timeline was swapped.
- **Files modified:** N/A — same files, different commit order
- **Verification:** `git log --oneline -3` shows `dcd5940 (Task 2 / GSD-104) -> 5f97339 (Task 3 / GSD-103) -> e706fcf (Task 1 / GSD-102)`. Every commit is independently importable.
- **Committed in:** `5f97339` (Task 3 first), `dcd5940` (Task 2 after)

**2. [Rule 3 - Blocking] Reworded comment in security.py to satisfy literal grep AC**
- **Found during:** Task 2 acceptance criteria check
- **Issue:** Plan AC #4 for Task 2: `grep -qE 'passlib|python-jose' app/core/security.py MUST return exit 1` (i.e., banned tokens must be ABSENT). Original action block contained the comment `# Do NOT import passlib anywhere — banned per CLAUDE.md.` That comment contains the literal token `passlib` (in a "do not use" context, but `grep` doesn't read context) and tripped the AC.
- **Fix:** Reworded the comment to `# CLAUDE.md non-negotiable: only pwdlib is allowed for password hashing.` Preserves the intent (forbidding the banned hasher) without the literal token.
- **Files modified:** `app/core/security.py` (1-line comment change before commit)
- **Verification:** `grep -qE 'passlib|python-jose' app/core/security.py` exits 1 (no match). Behavior verify still passes (pwdlib hash + roundtrip + JWT roundtrip + ephemeral warning).
- **Committed in:** `dcd5940` (the only Task 2 commit; the change happened pre-commit)

**3. [Rule 3 - Tooling] Adjusted commit messages to corporate DPE single-line format**
- **Found during:** every commit attempt
- **Issue:** Repository's `PreToolUse:Bash` hook enforces the corporate DPE pattern `<Tipo>[(Escopo)]:[COD] - <Descrição ≤72 chars>` on a single line and rejects multi-line conventional commits + the `Co-Authored-By` trailer specified in the GSD task-commit protocol. Plan 01-01 already encountered this and adopted `[GSD-101]`.
- **Fix:** Used the precedent. Allocated sequential codes: `[GSD-102]` (Task 1), `[GSD-103]` (Task 3 — logging), `[GSD-104]` (Task 2 — security). One-line `feat(core):[GSD-NNN] - <imperative description>` for each. Bullet points dropped from message body; no `Co-Authored-By` trailer. The hook also rejected one initial wording (`...JSON logger to stdout configure`) for grammatical incompleteness — corrected to `Configure structlog JSON logger for stdout` and accepted on retry.
- **Files modified:** N/A — only commit message text
- **Verification:** All three commits landed (`e706fcf`, `5f97339`, `dcd5940`). `git log --oneline -3` confirms conformance.
- **Committed in:** N/A — applies to all three commits

---

**Total deviations:** 3 auto-fixed (2 Rule 3 blocking, 1 Rule 3 tooling)
**Impact on plan:** All deviations are tooling/ordering concerns, not scope or correctness changes. The behavior, signatures, and contracts in the plan's `<interfaces>` block were implemented exactly as specified. Every plan-level acceptance criterion (after the comment rewording in deviation 2) passes.

## Issues Encountered

- The plan's verify command for Task 3 uses bare `python` after the pipe (`... | python -c ...`). On this machine the canonical project pattern is `uv run python` (no system `python` available). Using `uv run python` on both sides of the pipe, the verify passes. Documented here for future executors — the plan command is portability-fragile, the result is correct.
- `contextlib.redirect_stdout(buf)` does not capture structlog output because structlog writes via stdlib `logging` whose `StreamHandler(sys.stdout)` is bound to the original stdout at handler creation, not the redirected one. Verification was done via `> /tmp/log_out.txt` shell redirection instead, which captures correctly.

## User Setup Required

None. The user can run any of the following without further configuration:

- `uv run python -c "from app.core.config import get_settings; print(get_settings())"` — defaults visible
- `uv run python -c "from app.core.security import hash_password; print(hash_password('test'))"` — works (will emit ephemeral key warning to stdout if `JWT_SECRET_KEY` is unset, which is correct behavior)
- `uv run python -c "from app.core.logging import configure_logging, get_logger; configure_logging(); get_logger('demo').info('hello', x=1)"` — emits one JSON line

To suppress the ephemeral-key warning in development, copy `.env.example` to `.env` and set `JWT_SECRET_KEY=$(openssl rand -hex 32)`.

## Next Phase Readiness

- **Plan 01-03 (db + alembic):** Ready. `Settings.DATABASE_URL` and `get_settings()` are the canonical source for the alembic env.py SQLAlchemy URL.
- **Plan 01-04 (auth service):** Ready. `hash_password`, `verify_password`, `create_access_token`, `decode_access_token`, `TokenPayload` are the exact signatures the service layer will call.
- **Plan 01-05/06 (api deps + main):** Ready. `get_current_user` will call `decode_access_token` and catch `jwt.PyJWTError` subclasses; `main.py` will call `configure_logging(settings.LOG_LEVEL, debug=settings.DEBUG)` in the lifespan startup.
- **Plan 01-07 (auth tests):** Ready. The plan can assert on the stable event name `jwt.ephemeral_key_generated` and use `_reset_secret()` + `get_settings.cache_clear()` to construct deterministic per-test fixtures.
- **Phase 4 (LLM call logs):** The structlog setup with `merge_contextvars` is exactly what the OPS-03 LLM call log pattern (CLAUDE.md mandate) needs — Phase 4 just calls `get_logger("llm").info("openai.call", provider="openai", model=..., tokens_in=..., ...)`.

No blockers. Plan 01-03 (wave 2 sibling) can run in parallel with this plan — they don't share files.

## Self-Check

```
[x] app/__init__.py exists (FOUND — empty)
[x] app/core/__init__.py exists (FOUND — empty)
[x] app/core/config.py exists (FOUND, 49 lines)
[x] app/core/security.py exists (FOUND, 101 lines)
[x] app/core/logging.py exists (FOUND, 48 lines)
[x] Commit e706fcf in git log (FOUND — Task 1)
[x] Commit 5f97339 in git log (FOUND — Task 3 / logging)
[x] Commit dcd5940 in git log (FOUND — Task 2 / security)
[x] passlib absent in app/core/* (PASS — non-negotiable held)
[x] print( absent in app/core/* (PASS — JSON logs only)
[x] Combined import smoke test passes (PASS)
[x] pwdlib hash + verify roundtrip works (PASS, $2b$ prefix)
[x] JWT encode + decode roundtrip works (PASS, 3-part token, sub preserved)
[x] Wrong-secret token => jwt.InvalidSignatureError (PASS)
[x] Past-exp token => jwt.ExpiredSignatureError (PASS)
[x] Ephemeral-key warning fires with event "jwt.ephemeral_key_generated" (PASS)
[x] structlog emits JSON with event/level/timestamp/foo (PASS)
[x] structlog debug=True switches to ConsoleRenderer (PASS, output not JSON-parseable)
[x] Settings env-var override beats .env (PASS)
[x] get_settings() lru_cache identity holds; cache_clear returns new instance (PASS)
```

## Self-Check: PASSED

---
*Phase: 01-foundation*
*Completed: 2026-04-25*
