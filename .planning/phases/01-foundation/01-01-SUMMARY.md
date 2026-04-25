---
phase: 01-foundation
plan: 01
subsystem: infra
tags: [uv, pyproject, python-3.12, fastapi, pwdlib, bcrypt, pyjwt, sqlalchemy, alembic, pandas, duckdb, sqlglot, openai, structlog, ruff, mypy, pytest]

# Dependency graph
requires:
  - phase: 00-bootstrap
    provides: GSD planning artifacts (CLAUDE.md, research/STACK.md, research/PITFALLS.md, ROADMAP.md)
provides:
  - Locked Python 3.12 venv via uv with all v1 runtime + dev deps installed
  - pyproject.toml as the single source of truth for dependency floors (mirrors STACK.md)
  - uv.lock for reproducible installs (CI / Docker / fresh clone)
  - .gitignore covering .env, .venv, SQLite WAL files, user-uploaded data
  - .env.example documenting every Settings field consumed by the app (D-06)
  - data/db/ and data/uploads/ directories pre-created with .gitkeep markers (Phase 2/3 mount targets)
  - README quick-start (cp .env.example, uv sync, alembic upgrade, uvicorn)
affects: [01-02-core-settings, 01-03-db-alembic, all phase-2/3/4/5 plans, docker-compose, dockerfile]

# Tech tracking
tech-stack:
  added:
    - "fastapi[standard]==0.136.1 (API framework)"
    - "uvicorn[standard]==0.46.0 (ASGI server, uvloop+httptools)"
    - "pydantic==2.13.3 + pydantic-settings==2.14.0 (validation + Settings)"
    - "pyjwt==2.12.1 (JWT encode/decode)"
    - "pwdlib[bcrypt]==0.3.0 + bcrypt==5.0.0 (password hashing — replaces abandoned passlib)"
    - "sqlalchemy[asyncio]==2.0.49 + aiosqlite==0.22.1 (async SQLite ORM)"
    - "alembic==1.18.4 (DB migrations)"
    - "structlog==25.5.0 (JSON structured logs)"
    - "python-dotenv==1.2.2, anyio==4.13.0, python-multipart==0.0.26"
    - "pandas==3.0.2 (CoW default — Phase 2 cleaning pipeline)"
    - "openpyxl==3.1.5 (xlsx engine, NOT xlrd)"
    - "duckdb==1.5.2 (Phase 3 query engine)"
    - "sqlglot==30.6.0 (SELECT-only AST validator)"
    - "charset-normalizer==3.4.7 (PT-BR encoding detection)"
    - "altair==6.1.0 (Vega-Lite spec generation)"
    - "openai==2.32.0 (Phase 4-5 LLM client)"
    - "Dev: pytest==9.0.3, pytest-asyncio==1.3.0, httpx==0.28.1, respx==0.23.1, ruff==0.15.12, mypy==1.20.2"
  patterns:
    - "uv-only dependency management (uv add / uv sync / uv run / uv.lock committed) — never pip/poetry"
    - "PEP 735 [dependency-groups.dev] for dev deps (not [project.optional-dependencies])"
    - "Python pin via .python-version (3.12 floor, <3.13 ceiling — pwdlib + pandas 3.x compatibility window)"
    - ".env.example committed; .env always gitignored; all Settings fields documented up front"
    - "Phase 2-5 deps pre-declared in Phase 1 so Docker image is final from the start (no incremental rebuild per phase)"

key-files:
  created:
    - "pyproject.toml — full v1 dep manifest + ruff/mypy/pytest config"
    - ".python-version — pinned to 3.12"
    - "uv.lock — 83 resolved packages (sha256 prefix 25487264515b)"
    - ".gitignore — .env, .venv, __pycache__, .pytest_cache, .ruff_cache, .mypy_cache, data/db/*.sqlite*, data/uploads/*"
    - ".env.example — DATABASE_URL, JWT_*, UPLOADS_*, MAX_UPLOAD_*, SESSION_TTL_SECONDS, OPENAI_API_KEY, DEBUG, LOG_LEVEL"
    - "README.md — quick-start stub"
    - "data/db/.gitkeep, data/uploads/.gitkeep — empty volume mount targets"
  modified: []

key-decisions:
  - "Pinned Python 3.12 floor and <3.13 ceiling to dodge the pwdlib-on-3.13 edge case flagged in PITFALLS.md while keeping pandas 3.x compatibility (>=3.11)."
  - "Pre-declared all Phase 2-5 runtime deps (pandas, duckdb, sqlglot, openai, charset-normalizer, altair, openpyxl) in this plan so Docker image build at Phase 1 wave-2 is the final image — no incremental rebuilds across phases."
  - "Used pydantic-settings>=2.6 as a separate package (not pydantic v2 core) per the v2 split — needed for D-06 Settings(BaseSettings)."
  - "Added aiosqlite>=0.20 for the async SQLAlchemy + SQLite combination required by D-07 (async get_db_session dependency)."
  - "Added LOG_LEVEL to .env.example beyond the strict D-06 list — structlog config in 01-02 needs it; documenting now is cheaper than amending later."

patterns-established:
  - "Pattern: uv canonical commands. `uv sync` for installs, `uv sync --frozen` for reproducible builds, `uv run <cmd>` for any in-venv invocation. Never invoke pip/python directly."
  - "Pattern: dependency floors mirror research/STACK.md exactly — any deviation must be documented as a deviation in the plan SUMMARY."
  - "Pattern: passlib is forbidden across the codebase (CLAUDE.md non-negotiable). Verified absent at install time; phases 2+ MUST NOT reintroduce it."
  - "Pattern: data/db and data/uploads are git-tracked-empty via .gitkeep so Docker volume mounts have a guaranteed bind point even on fresh clone."

requirements-completed: [OPS-04, OPS-05, OPS-06]

# Metrics
duration: 6min
completed: 2026-04-25
---

# Phase 1 Plan 01: pyproject + uv scaffold Summary

**Locked-version Python 3.12 dependency manifest via uv (83 packages including pandas 3.0.2, fastapi 0.136.1, pwdlib 0.3.0, duckdb 1.5.2) plus .env.example, .gitignore, README stub, and committed-empty data/ directories.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-04-25T00:13:11Z
- **Completed:** 2026-04-25T00:19:11Z
- **Tasks:** 2 / 2
- **Files modified:** 8 created, 0 modified

## Accomplishments

- `uv sync` produces a clean, reproducible venv with all 83 packages resolved (no version conflicts) under Python 3.12.13
- `uv.lock` committed → fresh clones / Docker builds will install identical bytes
- `pwdlib[bcrypt]==0.3.0` installed; `passlib` confirmed absent (CLAUDE.md non-negotiable holds)
- `.env.example` documents every Settings field from D-06 (DATABASE_URL, JWT_SECRET_KEY, JWT_ALGORITHM, JWT_ACCESS_TOKEN_EXPIRE_MINUTES, UPLOADS_DIR, MAX_UPLOAD_BYTES, MAX_UPLOAD_ROWS, SESSION_TTL_SECONDS, OPENAI_API_KEY, DEBUG, plus LOG_LEVEL)
- `.gitignore` blocks `.env` (exact match), `.venv/`, all SQLite WAL files, and user-uploaded data while preserving directory structure via `.gitkeep`
- All Phase 2-5 deps (pandas, duckdb, sqlglot, charset-normalizer, altair, openai, openpyxl) pre-declared so plan 01-04 (Docker) builds the final image without rebuilds in subsequent phases
- Smoke import passes: `import fastapi, pydantic, pwdlib, jwt, sqlalchemy, alembic, structlog, aiosqlite, pandas, duckdb, sqlglot, altair, openpyxl, openai` exits 0

## Task Commits

1. **Task 1: Initialize uv project + Python 3.12 pin + full dependency set** — `341eb2a` (feat)
   - Created: `pyproject.toml`, `.python-version`, `uv.lock`
2. **Task 2: .gitignore, .env.example, README stub, data dirs** — `127b0a2` (chore)
   - Created: `.gitignore`, `.env.example`, `README.md`, `data/db/.gitkeep`, `data/uploads/.gitkeep`

## Files Created/Modified

- `pyproject.toml` — locked dep manifest (runtime + dev), ruff/mypy/pytest config
- `.python-version` — `3.12`
- `uv.lock` — 1,314 lines, sha256 prefix `25487264515b`, 83 packages
- `.gitignore` — Python caches, .venv, .env*, SQLite WAL artifacts, data/uploads/* with .gitkeep allowlist
- `.env.example` — all v1 Settings fields with PT-BR-aware comments and JWT secret generation hint
- `README.md` — quick-start (cp .env.example → uv sync → alembic upgrade head → uvicorn)
- `data/db/.gitkeep`, `data/uploads/.gitkeep` — empty markers so Docker volume mounts have guaranteed bind targets

## Decisions Made

- **Python 3.12 + <3.13 ceiling:** pandas 3.x requires >=3.11 (lower bound) and pwdlib has known issues entering Python 3.13 territory (PITFALLS.md #12 and stack research notes). 3.12 is the only stable intersection.
- **All future-phase deps declared up front:** pandas, duckdb, sqlglot, openai, charset-normalizer, altair, openpyxl. Cost is trivial in build time; benefit is that the Phase 1 wave-2 Docker image is the final image — no rebuild churn during Phases 2-5.
- **`pydantic-settings` as a separate dep (>=2.6):** pydantic v2 split BaseSettings into a separate package; the plan listed it explicitly because D-06 depends on it.
- **`aiosqlite` added (>=0.20):** SQLAlchemy 2.x async engine talking to SQLite needs an async driver. Plan didn't enumerate it but D-06's `DATABASE_URL=sqlite+aiosqlite:///` requires it.
- **`alembic` pinned to >=1.13:** latest stable line that supports SQLAlchemy 2.0 async migrations templates (which 01-03 will consume).
- **`LOG_LEVEL=INFO` added to .env.example:** D-06 mentions structlog in 01-02 but doesn't itemise the env var. Documenting it now (cost: 1 line) avoids amending .env.example in 01-02.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Project commit hook enforces DPE single-line format with `[CODE]` token**
- **Found during:** Task 1 commit
- **Issue:** Workplace `PreToolUse:Bash` hook (corporate Pulse-toolkit governance) blocked the multi-line conventional commit (`feat(01-01): scaffold pyproject + uv lock + python 3.12 pin\n\n- ...`) because it expects the DPE pattern `<Tipo>[(Escopo)]:[COD] - <Descrição>` on a single line ≤72 chars. Even with `Co-Authored-By` trailer the body lines were rejected.
- **Fix:** Adopted the precedent already in the repo (commit 19419e6 used `[GSD-001]`). Used `[GSD-101]` for plan 01-01 (phase 1, plan 01) and condensed messages to the single-line DPE form. The Co-Authored-By trailer was dropped to satisfy the hook.
- **Files modified:** N/A — only commit message text changed
- **Verification:** Both task commits succeeded. Compliance with both the DPE hook AND the GSD task-commit protocol verified.
- **Committed in:** `341eb2a` (Task 1), `127b0a2` (Task 2)

**2. [Rule 2 - Missing Critical] Added `aiosqlite>=0.20` to runtime deps**
- **Found during:** Task 1 (pyproject.toml authoring)
- **Issue:** Plan listed it in Rationale notes but not in the explicit dep list. SQLAlchemy 2.x async + SQLite literally cannot connect without it (`sqlite+aiosqlite://` URL is the D-06 default).
- **Fix:** Added `aiosqlite>=0.20` to `[project.dependencies]` in pyproject.toml.
- **Files modified:** `pyproject.toml`
- **Verification:** `uv run python -c "import aiosqlite"` exits 0. Resolved to 0.22.1.
- **Committed in:** `341eb2a`

**3. [Rule 2 - Missing Critical] Added `pydantic-settings>=2.6` to runtime deps**
- **Found during:** Task 1 (pyproject.toml authoring)
- **Issue:** Same — plan rationale mentioned it but the dep list (line 82-104) didn't include it. D-06 requires `Settings(BaseSettings)` from pydantic-settings; without it, plan 01-02 cannot import.
- **Fix:** Added `pydantic-settings>=2.6` to `[project.dependencies]`.
- **Files modified:** `pyproject.toml`
- **Verification:** `uv run python -c "from pydantic_settings import BaseSettings"` exits 0. Resolved to 2.14.0.
- **Committed in:** `341eb2a`

**4. [Rule 2 - Missing Critical] Added `LOG_LEVEL` env var to .env.example**
- **Found during:** Task 2 (.env.example authoring)
- **Issue:** D-06 Settings list didn't enumerate LOG_LEVEL but structlog config in 01-02 will need it. Adding now is cheap; amending .env.example mid-phase would force a follow-up commit.
- **Fix:** Added `LOG_LEVEL=INFO` to .env.example under the App section.
- **Files modified:** `.env.example`
- **Verification:** `grep -q "^LOG_LEVEL" .env.example` exits 0.
- **Committed in:** `127b0a2`

---

**Total deviations:** 4 auto-fixed (1 Rule 3 blocking, 3 Rule 2 missing-critical)
**Impact on plan:** Deviations 2 and 3 are dependencies the plan rationale already named but forgot in the explicit list — adding them is correctness, not scope creep. Deviation 4 is a 1-line .env documentation addition that prevents thrash in 01-02. Deviation 1 is a tooling-environment adaptation with no code impact. Plan goal achieved exactly as specified.

## Issues Encountered

- `uv` resolved `pytest` to 9.0.3 (the floor was `>=8.0`). pytest 9.x is 100% backwards-compatible with 8.x test code per the upstream changelog; no action needed. Documenting here so future debugging knows pytest 9.x is intentional, not accidental.
- `uv` resolved `structlog` to 25.5.0 (floor `>=24.0`). Newer than STACK.md noted; no breaking changes affecting our usage (JSON renderer + processors API stable since 22.x).

## User Setup Required

None. The user can run `cp .env.example .env`, optionally fill in `JWT_SECRET_KEY`, and `uv sync` will reproduce the venv from the lockfile. No external services needed for this plan.

## Next Phase Readiness

- **Plan 01-02 (core settings):** Ready. `pydantic-settings`, `python-dotenv`, `structlog` installed. `.env.example` documents every field 01-02 needs to type into `Settings(BaseSettings)`.
- **Plan 01-03 (db + alembic):** Ready. `sqlalchemy[asyncio]`, `aiosqlite`, `alembic` installed. `data/db/.gitkeep` ensures the SQLite directory exists on fresh clones.
- **Plans 01-04 onward (auth, API, Docker):** Ready. `pyjwt`, `pwdlib[bcrypt]`, `fastapi[standard]`, `uvicorn[standard]` all locked.
- **Phase 2 (ingest):** Ready ahead of schedule. `pandas`, `openpyxl`, `charset-normalizer` already locked — no `uv add` required at phase boundary.
- **Phase 3 (DuckDB query engine):** Ready ahead of schedule. `duckdb`, `sqlglot` locked.
- **Phase 4-5 (LLM):** Ready ahead of schedule. `openai`, `altair` locked.

No blockers. Plan 01-02 and 01-03 (same wave-1 sibling plans? — STATE.md confirms wave-based parallel) can proceed immediately.

## Self-Check

```
[x] pyproject.toml exists (FOUND)
[x] .python-version = "3.12" (FOUND)
[x] uv.lock exists (FOUND, 1314 lines, sha256 25487264515b)
[x] .gitignore exists with .env exact-match rule (FOUND)
[x] .env.example exists with all D-06 fields + LOG_LEVEL (FOUND)
[x] README.md exists with `uv sync` quick-start (FOUND)
[x] data/db/.gitkeep, data/uploads/.gitkeep exist (FOUND)
[x] Commit 341eb2a in git log (FOUND — Task 1)
[x] Commit 127b0a2 in git log (FOUND — Task 2)
[x] passlib absent from pyproject.toml AND uv.lock (PASS — non-negotiable held)
[x] uv sync --frozen succeeds (PASS — lockfile consistent)
[x] Smoke import of all 14 key packages exits 0 (PASS)
```

## Self-Check: PASSED

---
*Phase: 01-foundation*
*Completed: 2026-04-25*
