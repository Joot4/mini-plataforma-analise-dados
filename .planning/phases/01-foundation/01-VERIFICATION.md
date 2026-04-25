---
phase: 01-foundation
verified: 2026-04-25T00:50:00Z
status: gaps_found
score: 2/5 must-haves verified (ROADMAP success criteria); 7/7 must-haves verified across PLAN frontmatter; 4/7 requirements satisfied
overrides_applied: 0
re_verification:
  initial: true
gaps:
  - truth: "POST /auth/register creates a user with bcrypt-hashed password and returns HTTP 201; a second call with the same email returns HTTP 409"
    status: failed
    reason: "No HTTP endpoint exists. There is no app/main.py, no FastAPI app instance, no routers, no auth router. Plans 01-01..03 only built the primitives (User model + hash_password + create_access_token); the HTTP layer that the ROADMAP Phase 1 SC#1 demands was deferred to a non-existent 'Plan 04+'."
    artifacts:
      - path: "app/main.py"
        issue: "MISSING — file does not exist"
      - path: "app/api/routers/auth.py (or equivalent)"
        issue: "MISSING — no auth router file exists anywhere under app/"
    missing:
      - "FastAPI app factory (e.g. app/main.py) with create_app() / app instance"
      - "POST /auth/register handler that takes email+password, calls hash_password, INSERTs User, returns 201; returns 409 on UNIQUE constraint violation on email"
      - "Pydantic request/response schemas for auth (RegisterRequest, RegisterResponse, LoginRequest, TokenResponse)"
      - "An auth service module that owns the SELECT/INSERT against User over an injected AsyncSession"
  - truth: "POST /auth/login returns a JWT token; protected endpoint without token → 401; with valid token → 200"
    status: failed
    reason: "Same root cause as the previous gap. create_access_token / decode_access_token exist in app/core/security.py and round-trip correctly in a Python REPL, but there is no /auth/login endpoint, no Depends(get_current_user) dep, and no protected route to assert 401/200 against."
    artifacts:
      - path: "app/api/deps.py (or equivalent)"
        issue: "MISSING — no get_current_user dependency wired"
      - path: "app/api/routers/auth.py"
        issue: "MISSING — no /auth/login handler"
    missing:
      - "POST /auth/login handler: validates email+password via verify_password, returns 401 on mismatch, returns {access_token, token_type:'bearer'} on success"
      - "get_current_user FastAPI dependency: parses Authorization header, calls decode_access_token, fetches User by id, raises HTTPException 401 on any jwt.PyJWTError"
      - "At least one protected route (e.g. GET /auth/me) gated by Depends(get_current_user) so the contract is testable end-to-end"
  - truth: "User A's JWT cannot access User B's resources (cross-user isolation enforced at dependency layer)"
    status: failed
    reason: "Cross-user isolation is enforced in the data layer by checking that fetched rows match request.user.id. With no router, no resource endpoints, and no get_current_user dep, the isolation rule has no surface to attach to. The User model carries a UUID4 PK (PITFALLS.md#11 — good), and that's all that's in place."
    artifacts:
      - path: "app/api/deps.py"
        issue: "MISSING"
      - path: "Any user-owned resource endpoint"
        issue: "N/A — Phase 1 has no domain resource yet, but the *test* of isolation needs a dummy protected route or coverage in the auth tests using two different tokens"
    missing:
      - "Cross-user isolation pattern documented + an integration test stub: register user A, register user B, login both, hit a protected endpoint with each token, assert no shared state. Even a minimal /auth/me that returns the caller's own User suffices to prove the dep is working."
  - truth: "docker compose up starts the API in under 10 seconds; SQLite migrations run automatically on startup with no manual step required"
    status: failed
    reason: "Neither a Dockerfile nor a docker-compose.yml exists in the repo. ROADMAP claims OPS-04 done; REQUIREMENTS.md marks it [x]; both 01-01 SUMMARY and 01-03 SUMMARY use the wording 'Docker-ready scaffold' / 'Docker volume layout'. The actual deliverable is: data/ directories with .gitkeep markers, .env.example documenting UPLOADS_DIR, and pyproject.toml pre-loading all phase-2-5 deps. None of that runs `docker compose up`. The Docker entrypoint is explicitly punted to 'Plan 08' in the plans, but Plan 08 doesn't exist."
    artifacts:
      - path: "Dockerfile"
        issue: "MISSING — no Dockerfile anywhere in the repo"
      - path: "docker-compose.yml (or compose.yaml)"
        issue: "MISSING"
      - path: "Dockerfile entrypoint script (or CMD) that runs `alembic upgrade head` then `uvicorn app.main:app`"
        issue: "MISSING — depends on app/main.py which is also missing"
    missing:
      - "Multi-stage Dockerfile (python:3.12-slim base, builder stage installs deps via uv, runtime stage copies .venv + app/ + alembic.ini, exposes 8000)"
      - "docker-compose.yml mounting data/db and data/uploads as named volumes, with healthcheck and env_file=.env"
      - "Container ENTRYPOINT (or CMD) that runs `uv run alembic upgrade head` before starting uvicorn — or a startup hook in app/main.py lifespan that does the same"
  - truth: "Final Docker image size is under 500MB"
    status: failed
    reason: "Cannot be measured: no Dockerfile exists. Cannot run `docker build` and therefore cannot run `docker image ls` to compare to 500MB."
    artifacts:
      - path: "Dockerfile"
        issue: "MISSING (root cause)"
    missing:
      - "Dockerfile multi-stage build that produces an image ≤500MB. With pandas+duckdb+openpyxl+altair+openai pre-installed this is tight — strategy: use python:3.12-slim runtime stage, copy ONLY .venv + app/ + alembic*, no build-essentials, no .pyc bytecode in shipped venv (UV_COMPILE_BYTECODE=0)."

deferred:
  # No items qualify for deferral. ROADMAP only has 6 phases (Foundation → Ingestion → DuckDB → Summary →
  # NL Query → Hardening); none of them re-claim auth-endpoints, Dockerfile, or compose.yml as their goal
  # or in their success criteria. The auth HTTP layer + Docker artifacts are squarely Phase 1's contract;
  # they cannot be deferred to a later phase that doesn't exist.
---

# Phase 1: Foundation Verification Report

**Phase Goal:** The project skeleton, Docker environment, and authentication layer are fully operational so every subsequent endpoint has a security perimeter from the first commit.
**Verified:** 2026-04-25T00:50:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria — the contract)

| #   | Truth                                                                                                                               | Status     | Evidence                                                                                                                                                   |
| --- | ----------------------------------------------------------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | POST /auth/register creates user with bcrypt-hashed password (201) / returns 409 on duplicate email                                 | ✗ FAILED   | `find app/ -name "main.py" -o -name "routers"` returns nothing. No FastAPI app/router exists. `hash_password` works in isolation but is not wired to HTTP. |
| 2   | POST /auth/login returns JWT; protected endpoint without token → 401; with valid token → 200                                        | ✗ FAILED   | `grep -rE "auth/login\|@app\.\|@router\." app/` returns nothing. JWT round-trip works in REPL but no endpoint, no Depends(get_current_user) dep.           |
| 3   | User A's JWT cannot access User B's resources                                                                                       | ✗ FAILED   | No deps layer, no protected resource. User model has UUID4 PK (PITFALLS.md#11 honored) — that's the only piece in place.                                   |
| 4   | `docker compose up` starts API in <10s with auto-migrations                                                                         | ✗ FAILED   | `find -name "Dockerfile*" -o -name "docker-compose*"` returns nothing.                                                                                     |
| 5   | Final Docker image <500MB                                                                                                           | ✗ FAILED   | Unverifiable — no Dockerfile to build.                                                                                                                     |

**Score against ROADMAP:** 0/5 success criteria verifiable. The phase **goal** ("auth layer fully operational so every subsequent endpoint has a security perimeter from the first commit") is **not achieved**. The primitives are built; the perimeter is not.

### Observable Truths (PLAN frontmatter must_haves — primitives layer)

| #   | Truth                                                                                                                  | Status     | Evidence                                                                                                                                                                                  |
| --- | ---------------------------------------------------------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 6   | `uv sync --frozen` installs all deps from lockfile with no resolution errors                                           | ✓ VERIFIED | Ran `uv sync --frozen`: "Audited 83 packages in 2ms". Zero errors. Lockfile reproducible.                                                                                                  |
| 7   | Python pinned to 3.12 via `.python-version`                                                                            | ✓ VERIFIED | `cat .python-version` → `3.12`. `pyproject.toml` requires `>=3.12,<3.13`.                                                                                                                  |
| 8   | `.env.example` documents every required env var                                                                        | ✓ VERIFIED | Contains: DATABASE_URL, JWT_SECRET_KEY, JWT_ALGORITHM, JWT_ACCESS_TOKEN_EXPIRE_MINUTES, UPLOADS_DIR, MAX_UPLOAD_BYTES, MAX_UPLOAD_ROWS, SESSION_TTL_SECONDS, OPENAI_API_KEY, DEBUG, LOG_LEVEL. |
| 9   | Settings loads from .env + env, env wins; missing JWT_SECRET_KEY triggers ephemeral key + WARNING                       | ✓ VERIFIED | `JWT_SECRET_KEY=fromenv-test uv run python -c '...'` returns "fromenv-test". Stripped env triggers `[warning] jwt.ephemeral_key_generated`.                                                |
| 10  | hash_password / verify_password / create_access_token / decode_access_token round-trip                                  | ✓ VERIFIED | Live test: hash starts `$2b$`, verify True/False as expected, JWT 3-part, sub roundtrip exact, ExpiredSignatureError + InvalidSignatureError raised on tampering.                          |
| 11  | structlog emits JSON to stdout with timestamp/level/event                                                              | ✓ VERIFIED | `configure_logging('INFO'); log.info('hello', foo=1)` → `{"foo":1, "bar":"baz", "event":"hello", "level":"info", "timestamp":"2026-04-25T00:42:26..."}`                                    |
| 12  | Users table created by `alembic upgrade head`; reversible via `alembic downgrade base`; `get_db_session` callable      | ✓ VERIFIED | Live test: upgrade → users table with 6 expected cols + ix_users_email unique index + alembic_version='0001'. Downgrade → users absent. Re-upgrade → restored. Async session reads version. |

**Score against PLAN frontmatter:** 7/7 — every primitive must-have implemented and verified end-to-end. The plans achieved exactly what they promised.

### Required Artifacts

| Artifact                                            | Expected                              | Status     | Details                                                            |
| --------------------------------------------------- | ------------------------------------- | ---------- | ------------------------------------------------------------------ |
| `pyproject.toml`                                    | Locked dep manifest, fastapi>=0.136   | ✓ VERIFIED | All 21 runtime + 6 dev deps present, exact floors per STACK.md     |
| `.python-version`                                   | `3.12`                                | ✓ VERIFIED |                                                                    |
| `uv.lock`                                           | Generated by uv sync                  | ✓ VERIFIED | 83 packages; passlib + python-jose absent (grep -c → 0)            |
| `.gitignore`                                        | Protects .env, .venv, sqlite, uploads | ✓ VERIFIED | All required patterns present                                      |
| `.env.example`                                      | All env vars documented               | ✓ VERIFIED | 11 variables documented (10 from D-06 + LOG_LEVEL)                 |
| `app/core/config.py`                                | Settings + get_settings               | ✓ VERIFIED | 49 lines, lru_cache, BaseSettings, all 11 fields                   |
| `app/core/security.py`                              | hash + verify + JWT + TokenPayload    | ✓ VERIFIED | 102 lines, pwdlib bcrypt, PyJWT HS256, ephemeral fallback          |
| `app/core/logging.py`                               | structlog JSON config                 | ✓ VERIFIED | 49 lines, merge_contextvars wired, force=True idempotent           |
| `app/db/models.py`                                  | Base + User                           | ✓ VERIFIED | UUID4 PK String(36), 6 columns, _utcnow tz-aware                   |
| `app/db/session.py`                                 | engine + AsyncSessionLocal + dep      | ✓ VERIFIED | check_same_thread=False for sqlite, expire_on_commit=False         |
| `alembic.ini`                                       | script_location=app/db/migrations     | ✓ VERIFIED | sqlalchemy.url empty (env.py drives it), file_template numeric     |
| `app/db/migrations/env.py`                          | Async + Settings-driven URL           | ✓ VERIFIED | `config.set_main_option('sqlalchemy.url', get_settings().DATABASE_URL)` |
| `app/db/migrations/versions/0001_create_users.py`   | Reversible migration                  | ✓ VERIFIED | upgrade + downgrade round-trip clean                               |
| **`Dockerfile`**                                    | **Multi-stage python:3.12-slim**      | **✗ MISSING** | **File does not exist anywhere in repo**                        |
| **`docker-compose.yml`**                            | **Volumes for /data and /db**         | **✗ MISSING** | **File does not exist anywhere in repo**                        |
| **`app/main.py`**                                   | **FastAPI app factory + lifespan**    | **✗ MISSING** | **No FastAPI app instance exists**                              |
| **`app/api/` (routers, deps)**                      | **/auth/register, /auth/login, get_current_user dep** | **✗ MISSING** | **Entire api/ subpackage absent**                |

### Key Link Verification

| From                                  | To                                          | Via                                           | Status     | Details                                                                          |
| ------------------------------------- | ------------------------------------------- | --------------------------------------------- | ---------- | -------------------------------------------------------------------------------- |
| `app/core/security.py`                | `app/core/config.py` (`get_settings()`)     | `get_settings().JWT_*` reads                  | ✓ WIRED    | Imported at line 12; used in `_get_secret`, `create_access_token`, `decode_access_token` |
| `app/core/security.py`                | `pwdlib`                                    | `PasswordHash + BcryptHasher`                 | ✓ WIRED    | Module-level `_password_hash = PasswordHash((BcryptHasher(),))`                  |
| `app/core/security.py`                | `app/core/logging.py` (`get_logger`)        | structured warning emission                   | ✓ WIRED    | `logger = get_logger(__name__)`; `logger.warning("jwt.ephemeral_key_generated", …)` |
| `app/db/migrations/env.py`            | `app/core/config.get_settings`              | DATABASE_URL injection                        | ✓ WIRED    | `config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)` (line 18) |
| `app/db/session.py`                   | `app/db/models.Base`                        | shared metadata                               | ✓ WIRED    | `from app.db.models import Base` (line 13); re-exported via `__all__`            |
| `Dockerfile`                          | `pyproject.toml + uv.lock`                  | `RUN uv sync --frozen`                        | ✗ NOT_WIRED | Dockerfile missing entirely                                                      |
| `Dockerfile ENTRYPOINT`               | `app/db/migrations` + `app/main.py`         | `alembic upgrade head && uvicorn app.main:app` | ✗ NOT_WIRED | Both endpoints of the link missing (Dockerfile + app/main.py)                  |
| HTTP layer                            | `hash_password / create_access_token`       | auth router calls                             | ✗ NOT_WIRED | No router file exists                                                            |

### Data-Flow Trace (Level 4)

Phase 1 ships infrastructure modules; the only data-flow concern is the migration → DB → session round-trip, which was verified live (alembic_version='0001' read back via AsyncSessionLocal). No "rendering" components in this phase.

### Behavioral Spot-Checks

| Behavior                                              | Command                                                                                                                                       | Result                                                          | Status |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------ |
| Lockfile is reproducible                              | `uv sync --frozen`                                                                                                                            | "Audited 83 packages in 2ms"                                    | ✓ PASS |
| Settings loads with all expected defaults             | `uv run python -c "from app.core.config import get_settings; …"`                                                                              | All 11 fields print expected defaults; assertions all pass      | ✓ PASS |
| Env var beats .env / default                          | `JWT_SECRET_KEY=fromenv-test uv run python -c "…get_settings().JWT_SECRET_KEY"`                                                              | `fromenv-test`                                                  | ✓ PASS |
| Password round-trip via pwdlib bcrypt                 | `hash_password / verify_password`                                                                                                             | hash starts `$2b$`; verify True for correct, False for wrong    | ✓ PASS |
| JWT round-trip                                        | `create_access_token('user-uuid-123'); decode_access_token(...).sub`                                                                          | sub == 'user-uuid-123'; 3-part token                            | ✓ PASS |
| Expired JWT raises typed error                        | Forge token with past `exp`, decode it                                                                                                        | `jwt.ExpiredSignatureError` raised                              | ✓ PASS |
| Tampered signature raises typed error                 | Mutate last 4 chars of token, decode                                                                                                          | `jwt.InvalidSignatureError` raised                              | ✓ PASS |
| Ephemeral-key warning fires when secret unset         | Unset JWT_SECRET_KEY env, call `create_access_token`                                                                                         | `[warning] jwt.ephemeral_key_generated` printed                 | ✓ PASS |
| structlog emits JSON to stdout                        | `configure_logging('INFO'); log.info('hello', foo=1, bar='baz')`                                                                              | Single JSON line with `event`, `foo`, `bar`, `level`, `timestamp` | ✓ PASS |
| `alembic upgrade head` creates users table            | unlink db, `uv run alembic upgrade head`, inspect SQLite                                                                                      | `users` table with 6 expected cols + `ix_users_email` unique    | ✓ PASS |
| `alembic downgrade base` drops users                   | `uv run alembic downgrade base`, inspect                                                                                                       | `users` table absent (None) post-downgrade                      | ✓ PASS |
| Re-upgrade restores schema                             | `uv run alembic upgrade head` after downgrade                                                                                                  | `users` recreated cleanly                                       | ✓ PASS |
| Second back-to-back upgrade is no-op                   | `uv run alembic upgrade head` twice                                                                                                            | Second invocation prints no `Running upgrade` line              | ✓ PASS |
| `get_db_session` is async generator function           | `inspect.isasyncgenfunction(get_db_session)`                                                                                                   | True                                                            | ✓ PASS |
| AsyncSessionLocal connects to migrated DB              | `async with AsyncSessionLocal() as s: SELECT version_num FROM alembic_version`                                                                | `('0001',)`                                                     | ✓ PASS |
| `passlib` absent in app/, pyproject, uv.lock           | `grep -rE "passlib" pyproject.toml uv.lock app/`; `python -c "import importlib.util; importlib.util.find_spec('passlib')"`                    | Zero matches; spec is None                                       | ✓ PASS |
| `python-jose` absent                                   | Same                                                                                                                                          | Zero matches; spec is None                                       | ✓ PASS |
| `print(` absent in app/                                | `grep -rE "^[[:space:]]*print\(" app/`                                                                                                        | Zero matches                                                    | ✓ PASS |
| **`docker compose up` starts the API**                 | (cannot run — no compose file)                                                                                                                | N/A                                                             | ✗ FAIL |
| **Final image size measurable via `docker image ls`**  | (cannot run — no Dockerfile)                                                                                                                  | N/A                                                             | ✗ FAIL |
| **`POST /auth/register` returns 201**                  | (cannot run — no endpoint)                                                                                                                    | N/A                                                             | ✗ FAIL |
| **`POST /auth/login` returns JWT**                     | (cannot run — no endpoint)                                                                                                                    | N/A                                                             | ✗ FAIL |

**Spot-check totals:** 17 PASS / 4 FAIL (HTTP + Docker behaviors not runnable).

### Requirements Coverage

| Requirement | Source Plan | Description                                                                          | Status                                | Evidence                                                                                                                                          |
| ----------- | ----------- | ------------------------------------------------------------------------------------ | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| AUTH-01     | 01-02, 01-03| User registers w/ email+password (pwdlib bcrypt)                                     | ⚠️ PARTIAL — primitives only          | `hash_password` works; `User` table exists; **no /auth/register endpoint** to honor "Usuário pode criar conta"                                    |
| AUTH-02     | 01-02       | Login returns JWT                                                                    | ⚠️ PARTIAL — primitives only          | `create_access_token` works; **no /auth/login endpoint**                                                                                          |
| AUTH-03     | 01-02       | Protected endpoints reject unauthenticated requests with 401                         | ⚠️ PARTIAL — primitives only          | `decode_access_token` raises typed errors; **no protected endpoint, no `get_current_user` dep, no 401 to assert**                                 |
| AUTH-04     | 01-03       | Each session/upload isolated by `user_id` — user A doesn't access user B             | ⚠️ PARTIAL — primitives only          | UUID4 PK on `users.id` (PITFALLS.md#11 ✓); **no api layer to enforce isolation against**                                                          |
| OPS-04      | 01-01       | docker-compose local with /data + /db volumes; `docker compose up` <10s              | ✗ BLOCKED                             | **No `docker-compose.yml` exists.** `data/db/.gitkeep` + `data/uploads/.gitkeep` exist, that's the entire "scaffold."                            |
| OPS-05      | 01-01, 01-03| Multi-stage Dockerfile (python:3.12-slim + uv); image <500MB                          | ✗ BLOCKED                             | **No `Dockerfile` exists.** pyproject pre-loads phase-2-5 deps to make the future image one-shot, but the future image hasn't been built.        |
| OPS-06      | 01-01, 01-03| Migrations run on startup via alembic                                                | ⚠️ PARTIAL                            | `alembic upgrade head` works manually and is reversible; **no startup hook (Docker entrypoint or FastAPI lifespan) exists** to run it autonomously |

**Phase 1 requirements claimed `[x] Done` in REQUIREMENTS.md:** AUTH-01, AUTH-02, AUTH-03, AUTH-04, OPS-04, OPS-05, OPS-06 (7).
**Actually satisfied end-to-end:** 0 of 7 — every one falls short of the requirement's user-facing spec, even though the underlying primitive is correct.

This is a **systematic discrepancy** between REQUIREMENTS.md/STATE.md (which both claim 100% phase completion) and what the codebase delivers. The plans were honest — they wrote `requirements: [OPS-04, OPS-05, OPS-06]` and shipped scaffolding — but the requirement text says "endpoint recebe", "rejeita 401", "sobe com docker compose up <10s". Those user-facing behaviors are not yet implementable.

### Anti-Patterns Found

Scan of every file in app/ + alembic.ini + pyproject.toml + .env.example.

| File                                                | Line | Pattern                                       | Severity | Impact                                                                                                                                |
| --------------------------------------------------- | ---- | --------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `app/core/logging.py`                               | 17   | `logging.basicConfig(...)`                    | ℹ️ Info  | INTENTIONAL bridge to stdlib so structlog routes through `sys.stdout`; CLAUDE.md ban on `logging.basicConfig` is for *app* code, this is the configurer. Not a violation. |
| (none)                                              | —    | `print(`                                      | —        | Zero hits across app/ — CLAUDE.md "never print" rule held.                                                                            |
| (none)                                              | —    | `passlib`                                     | —        | Zero hits across app/, pyproject.toml, uv.lock — non-negotiable held.                                                                 |
| (none)                                              | —    | `python-jose` / `jose`                        | —        | Zero hits — alternative banned hasher absent.                                                                                         |
| (none)                                              | —    | `datetime.utcnow()`                            | —        | Zero hits — CLAUDE.md "never utcnow()" rule held; both `app/core/security.py` and `app/db/models.py` use `datetime.now(tz=timezone.utc)`. |
| (none)                                              | —    | TODO / FIXME / placeholder / "not yet implemented" | —    | Zero hits — no stub markers in shipped code.                                                                                          |
| (none)                                              | —    | DuckDB / pandas / openai / sqlglot / altair / openpyxl / charset_normalizer imports in `app/` | — | Zero hits — phase boundary clean. Phase 2-5 code has not leaked into Phase 1.                                                  |

**Anti-pattern blockers:** 0. The code that exists is clean.

### Human Verification Required

None additional. The gaps are concrete code/file absences, not subtle UX/visual concerns.

### Gaps Summary

**Two distinct failure modes:**

**Mode A — Plans deferred core ROADMAP scope to a later plan that doesn't exist.**

The three Phase 1 plans (`01-01-pyproject-uv`, `01-02-core-settings`, `01-03-db-alembic`) build the foundation primitives: deps, settings, security helpers, logging, ORM, async session, alembic migration. Every primitive works exactly as specified in the plan frontmatter — the verifications all pass.

But ROADMAP Phase 1's success criteria are **HTTP-level behaviors** (POST /auth/register/login, 401/200 on protected routes, cross-user isolation, `docker compose up` working). Those require an `app/main.py`, an `app/api/` subpackage with routers + deps, a Dockerfile, and a docker-compose.yml. None of those four artifacts exist. The plans repeatedly reference "Plan 04+", "Plan 05/06", "Plan 08" as the home for these — but those plans don't exist in `.planning/phases/01-foundation/`.

REQUIREMENTS.md and STATE.md both report Phase 1 as complete (`[x]` on AUTH-01..04 + OPS-04..06; STATE.md `percent: 100`). That reporting is incorrect against ROADMAP — it reflects only that the plans-that-exist completed, not that the phase goal was met.

**Mode B — None.** No bugs, no anti-patterns, no scope leaks, no stubs in the code that *was* written. The plans-that-exist were executed correctly.

**Recommended remediation:**

Plan a follow-up wave inside Phase 1 (call it 01-04, 01-05, 01-06, 01-07, 01-08 or whatever — the slot numbers were already implied in the deferred references):

1. **01-04 — auth_service**: AsyncSession-based service module that owns User CRUD (`create_user`, `get_user_by_email`, `authenticate`). Imports `hash_password`, `verify_password`. Returns Pydantic models. Pure logic, no HTTP.
2. **01-05 — api/schemas + api/deps**: Pydantic request/response models for register/login + `get_current_user` dependency that wraps `decode_access_token` + a `select(User)` lookup over `Depends(get_db_session)`.
3. **01-06 — api/routers/auth + main.py**: FastAPI app factory, lifespan hook that calls `configure_logging(settings.LOG_LEVEL)`, `/auth/register`, `/auth/login`, `/auth/me` (the protected canary endpoint that proves SC#3). Mount the auth router.
4. **01-07 — auth tests**: pytest + httpx AsyncClient + respx. Assert the 5 ROADMAP success criteria as integration tests against the live FastAPI app + a per-test fresh SQLite. Cover: register 201, register 409 on dup, login 200 + JWT, login 401, /auth/me 401 without token, /auth/me 200 with token, two-user isolation.
5. **01-08 — Dockerfile + docker-compose**: Multi-stage Dockerfile (python:3.12-slim base; builder layer runs `uv sync --frozen --no-dev`; runtime layer copies `.venv`, `app/`, `alembic.ini`, `app/db/migrations/`); ENTRYPOINT `["uv", "run", "alembic", "upgrade", "head"]` then `CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`. docker-compose.yml mounts `./data/db` and `./data/uploads` as volumes, env_file=.env, healthcheck against `/healthz`. Run `docker build` and `docker image ls` to confirm <500MB.

Once those land, ALL five ROADMAP success criteria become testable, and the phase goal is genuinely achieved.

**Status repair:**

- `STATE.md`: change `percent: 100` → `percent: 60` (3 of an estimated 8 plans done) and `status: planning` → `status: in_progress`.
- `REQUIREMENTS.md`: AUTH-01..04 and OPS-04..06 status entries should be moved from `[x]` to `[ ]` (or marked `[~]` partial) until 01-04..08 deliver.
- `ROADMAP.md`: Phase 1 row "3/3 plans done; verification pending" should become "3/N plans done; verification found gaps; auth + Docker plans still required".

---

_Verified: 2026-04-25T00:50:00Z_
_Verifier: Claude (gsd-verifier)_
