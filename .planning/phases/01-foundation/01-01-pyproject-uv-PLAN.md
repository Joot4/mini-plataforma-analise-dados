---
name: pyproject-uv
phase: 01-foundation
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - .python-version
  - uv.lock
  - .gitignore
  - .env.example
  - README.md
autonomous: true
requirements: [OPS-04, OPS-05, OPS-06]
must_haves:
  truths:
    - "uv sync installs all runtime + dev deps from locked versions with no resolution errors"
    - "Python version is pinned to 3.12 via .python-version"
    - ".env.example documents every required env var; .env is gitignored"
  artifacts:
    - path: "pyproject.toml"
      provides: "Locked dependency manifest per research/STACK.md"
      contains: "fastapi>=0.136"
    - path: ".python-version"
      provides: "Python 3.12 pin"
      contains: "3.12"
    - path: ".env.example"
      provides: "Required env var documentation"
      contains: "JWT_SECRET_KEY"
    - path: ".gitignore"
      provides: "Protects .env, .venv, SQLite files, caches"
      contains: ".env"
  key_links:
    - from: "pyproject.toml [project.dependencies]"
      to: "research/STACK.md pinned versions"
      via: "exact version floors from STACK.md"
      pattern: "pwdlib\\[bcrypt\\]>=0.3"
---

<objective>
Bootstrap the Python project: `pyproject.toml` with `uv`, Python 3.12 pin, runtime + dev dependencies pinned per `research/STACK.md`, `.gitignore`, `.env.example`, minimal `README.md`. This plan is the foundation every other Phase 1 plan depends on — nothing else can `import` anything until `uv sync` succeeds here.

Purpose: Enables all downstream plans (core settings, db, auth, API, tests, Docker) by giving them an importable virtualenv and a locked dep manifest that Docker can reproduce.
Output: `pyproject.toml`, `.python-version`, `uv.lock`, `.gitignore`, `.env.example`, `README.md` (stub).
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
</context>

<tasks>

<task type="auto">
  <name>Task 1: Initialize uv project + Python 3.12 pin + full dependency set</name>
  <read_first>
    - CLAUDE.md (stack table, pwdlib NOT passlib, uv only, no pip/poetry)
    - .planning/research/STACK.md (exact pinned floors: FastAPI 0.136, uvicorn[standard] 0.46, pydantic 2.13, PyJWT 2.12, pwdlib[bcrypt] 0.3, SQLAlchemy 2.0, alembic, structlog 24.0, python-dotenv 1.0, python-multipart 0.0.26, openai 2.32, duckdb 1.5, pandas 3.0, openpyxl 3.1, sqlglot 30.6, charset-normalizer 3.4, altair 6.1, anyio 4.0)
    - .planning/research/STACK.md §Installation (canonical uv commands)
  </read_first>
  <files>pyproject.toml, .python-version, uv.lock</files>
  <action>
Project is greenfield — no existing pyproject.toml. Run `uv init --no-readme --bare` at the repo root to scaffold the project file, then edit.

Write `pyproject.toml` with this exact shape:

```toml
[project]
name = "mini-plataforma-analise-dados"
version = "0.1.0"
description = "API-only PT-BR data analysis platform (CSV/XLSX → summary + NL Q&A)"
requires-python = ">=3.12,<3.13"
dependencies = [
    "fastapi[standard]>=0.136",
    "uvicorn[standard]>=0.46",
    "pydantic>=2.13",
    "pydantic-settings>=2.6",
    "python-multipart>=0.0.26",
    "pyjwt>=2.12",
    "pwdlib[bcrypt]>=0.3",
    "sqlalchemy[asyncio]>=2.0",
    "aiosqlite>=0.20",
    "alembic>=1.13",
    "structlog>=24.0",
    "python-dotenv>=1.0",
    "anyio>=4.0",
    # Phase 2-5 deps pre-declared so Docker image is complete from Phase 1:
    "pandas>=3.0",
    "openpyxl>=3.1",
    "duckdb>=1.5",
    "sqlglot>=30.6",
    "charset-normalizer>=3.4",
    "altair>=6.1",
    "openai>=2.32",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=1.3",
    "httpx>=0.28",
    "respx>=0.23",
    "ruff",
    "mypy",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "UP"]
ignore = []

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["B"]

[tool.mypy]
python_version = "3.12"
strict = false
plugins = ["pydantic.mypy"]
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

Then pin Python: `uv python pin 3.12` (creates `.python-version` containing `3.12`).

Then resolve + lock: `uv sync` — this populates `uv.lock` and creates `.venv/`.

Rationale notes:
- `requires-python = ">=3.12,<3.13"` — pandas 3.x requires 3.11+; pinning 3.12 floor + 3.13 ceiling matches CLAUDE.md and avoids pwdlib-on-3.13 edge case mentioned in PITFALLS.md.
- Dev deps in `[dependency-groups.dev]` (PEP 735 format supported by uv) — not `[project.optional-dependencies]`.
- All Phase 2-5 deps declared NOW so Docker image build in plan 08 produces the final image, not an incremental one. Cost is trivial; avoids rebuilding per phase.
- `pydantic-settings>=2.6` added because D-06 requires `Settings(BaseSettings)` from `pydantic-settings` (split out from pydantic v2 core).
- `aiosqlite>=0.20` added because async SQLAlchemy engine talking to SQLite needs an async driver.
- `alembic>=1.13` — latest stable supporting SQLAlchemy 2.0 async templates.
  </action>
  <verify>
    <automated>uv sync --frozen 2>&amp;1 | tee /tmp/uv_sync.log &amp;&amp; grep -q "Resolved" /tmp/uv_sync.log &amp;&amp; uv run python -c "import fastapi, pydantic, pwdlib, jwt, sqlalchemy, alembic, structlog, aiosqlite, pandas, duckdb, sqlglot, altair, openpyxl, openai; print('ok')" | grep -q "^ok$"</automated>
  </verify>
  <acceptance_criteria>
    - `pyproject.toml` exists and `grep -q 'pwdlib\[bcrypt\]>=0.3' pyproject.toml` succeeds
    - `grep -q 'passlib' pyproject.toml` MUST return exit code 1 (passlib absent — CLAUDE.md non-negotiable)
    - `.python-version` exists and contains exactly `3.12`
    - `uv.lock` exists (generated by `uv sync`)
    - `uv run python -c "import pwdlib; import jwt; import sqlalchemy"` exits 0
    - `test "$(cat .python-version)" = "3.12"` succeeds
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: .gitignore, .env.example, README stub</name>
  <read_first>
    - .planning/phases/01-foundation/01-CONTEXT.md §D-06 (Settings fields list)
    - .planning/research/PITFALLS.md §Pitfall 12 (JWT secret from env, never hardcoded)
    - CLAUDE.md (data volume paths: /data/uploads, /db)
  </read_first>
  <files>.gitignore, .env.example, README.md</files>
  <action>
Write `.gitignore` at repo root:

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.ruff_cache/
.mypy_cache/

# uv / venv
.venv/
venv/

# Env
.env
.env.local

# SQLite + uploaded data
data/db/*.sqlite
data/db/*.sqlite-journal
data/db/*.sqlite-shm
data/db/*.sqlite-wal
data/uploads/*
!data/uploads/.gitkeep
!data/db/.gitkeep

# Editor
.vscode/
.idea/
*.swp
.DS_Store
```

Create empty placeholder files so the data dirs exist in git:
- `mkdir -p data/db data/uploads`
- `touch data/db/.gitkeep data/uploads/.gitkeep`

Write `.env.example` at repo root (documents every env var per D-06):

```
# --- Database ---
# async SQLAlchemy URL. For local/Docker use SQLite on a mounted volume.
DATABASE_URL=sqlite+aiosqlite:///./data/db/app.sqlite

# --- JWT / Auth ---
# 32+ byte hex string. Generate via: python -c "import secrets; print(secrets.token_hex(32))"
# Leaving blank causes startup to generate an ephemeral key and log a warning (per PITFALLS.md#12).
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30

# --- Upload limits (used starting Phase 2) ---
UPLOADS_DIR=/data/uploads
MAX_UPLOAD_BYTES=52428800
MAX_UPLOAD_ROWS=500000
SESSION_TTL_SECONDS=3600

# --- OpenAI (used starting Phase 4) ---
OPENAI_API_KEY=

# --- App ---
DEBUG=false
LOG_LEVEL=INFO
```

Write `README.md` stub (minimal — project README will be expanded later):

```markdown
# Mini Plataforma de Análise de Dados

API-only PT-BR data analysis backend: upload CSV/XLSX/TSV → automatic summary + natural-language Q&A with text + table + Vega-Lite chart spec.

## Quick start

    cp .env.example .env
    # edit .env — set JWT_SECRET_KEY (see comment in file)
    uv sync
    uv run alembic upgrade head
    uv run uvicorn app.main:app --reload

## Docker

    docker compose up --build

See `.planning/` for full project spec (ROADMAP, REQUIREMENTS, PROJECT, research).
```
  </action>
  <verify>
    <automated>test -f .gitignore &amp;&amp; test -f .env.example &amp;&amp; test -f README.md &amp;&amp; test -f data/db/.gitkeep &amp;&amp; test -f data/uploads/.gitkeep &amp;&amp; grep -q '^\.env$' .gitignore &amp;&amp; grep -q 'JWT_SECRET_KEY' .env.example &amp;&amp; grep -q 'DATABASE_URL' .env.example</automated>
  </verify>
  <acceptance_criteria>
    - `grep -qE '^\.env$' .gitignore` (blocks real `.env` from being committed)
    - `grep -q 'data/uploads/\*' .gitignore` (user data not tracked)
    - `.env.example` contains ALL of: `DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `UPLOADS_DIR`, `MAX_UPLOAD_BYTES`, `MAX_UPLOAD_ROWS`, `SESSION_TTL_SECONDS`, `OPENAI_API_KEY`, `DEBUG`
    - `data/db/.gitkeep` and `data/uploads/.gitkeep` exist (directories committed empty)
    - README exists and contains `uv sync` command
  </acceptance_criteria>
</task>

</tasks>

<verification>
After both tasks:
1. `uv sync --frozen` succeeds (lock file is consistent).
2. `uv run python -c "import fastapi, pydantic, pwdlib, jwt, sqlalchemy, alembic, structlog"` prints nothing and exits 0.
3. `git status` shows `.env.example`, `.gitignore`, `pyproject.toml`, `.python-version`, `uv.lock`, `README.md`, `data/db/.gitkeep`, `data/uploads/.gitkeep` as new files.
4. `grep -r passlib pyproject.toml` returns empty (exit 1) — passlib must be absent per CLAUDE.md.
</verification>

<success_criteria>
- `uv sync` reproducible from `uv.lock` in any clean checkout
- Every env var consumed by the app (D-06) is documented in `.env.example`
- No secrets, `.env` file, or SQLite DB files can be accidentally committed (gitignore correct)
- OPS-05 and OPS-06 foundations laid: Python 3.12-slim image can reuse this pyproject verbatim
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundation/01-01-SUMMARY.md` with: pinned versions, `uv.lock` hash (first 12 chars), any deviations from STACK.md and why.
</output>
