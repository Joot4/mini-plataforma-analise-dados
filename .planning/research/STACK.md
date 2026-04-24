# Stack Research

**Domain:** Python data analysis API — CSV/XLSX ingest, DuckDB query engine, OpenAI text-to-SQL
**Researched:** 2026-04-24
**Confidence:** HIGH (all versions verified against PyPI live data; library patterns verified via Context7 official docs)

---

## Recommended Stack

### Core Technologies

| Technology | Version to pin | Purpose | Why Recommended |
|------------|----------------|---------|-----------------|
| Python | `3.12` (constraint in `.python-version`) | Runtime | Minimum 3.11 required by pandas 3.x; 3.12 is stable, wheels available for all key deps including duckdb 1.5.x |
| FastAPI | `^0.136` | API framework | Latest stable 0.136.1 (2026-04-23). Async-native, pydantic v2 integrated, UploadFile built-in |
| uvicorn | `^0.46` (standard extra) | ASGI server | 0.46.0 (2026-04-23). `[standard]` extra bundles uvloop + httptools for perf; required for FastAPI |
| pydantic | `^2.13` | Data validation + serialization | v2.13.3 (2026-04-20). v2 is default; ~50x faster than v1 via Rust core. FastAPI uses it natively |
| python-multipart | `^0.0.26` | Multipart form/file parsing | 0.0.26 (2026-04-10). Required for FastAPI UploadFile — without this, file uploads return 422 silently |
| duckdb | `^1.5` | In-memory OLAP query engine | 1.5.2 (2026-04-13). Text-to-SQL target; SELECT over uploaded data; 100x faster than pandas for aggregations |
| pandas | `^3.0` | CSV/XLSX ingest + data cleaning | 3.0.2 (2026-03-31). **Requires Python >=3.11**. pandas 3 enables Copy-on-Write by default (breaking change from 2.x) |
| openpyxl | `^3.1` | XLSX reading backend for pandas | 3.1.5 (2024-06-28). Canonical xlsx engine since pandas 1.2 deprecated xlrd for xlsx. Pass `engine="openpyxl"` explicitly |
| openai | `^2.32` | OpenAI API client (GPT-4o-mini) | 2.32.0 (2026-04-15). SDK v2; provides `AsyncOpenAI` + `client.chat.completions.parse()` for structured output |
| sqlglot | `^30.6` | SQL parse + SELECT-only validation | 30.6.0 (2026-04-20). Zero-dependency AST parser; DuckDB dialect support; `exp.Select` type check blocks DDL/DML |
| charset-normalizer | `^3.4` | Encoding detection (UTF-8 / Latin-1 / Windows-1252) | 3.4.7 (2026-04-02). Drop-in `chardet` replacement; 97% accuracy vs 89%; ships with `requests` already; MIT licensed |
| altair | `^6.1` | Vega-Lite JSON spec generation | 6.1.0 (2026-04-21). `chart.to_dict()` emits validated Vega-Lite v6 JSON server-side — no rendering required |
| PyJWT | `^2.12` | JWT encode/decode for auth | 2.12.1 (2026-03-13). RFC 7519 compliant; production stable; simpler than python-jose (which is newer but less mature) |
| pwdlib | `^0.3` | Password hashing (bcrypt/argon2) | 0.3.0 (2025-10-25). Modern passlib replacement — passlib last released 2020, breaks on Python 3.13+. FastAPI docs now use pwdlib |
| SQLAlchemy | `^2.0` | SQLite ORM for users/sessions | 2.x async-native; used by FastAPI ecosystem; avoids raw sqlite3 cursor management |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | `^1.0` | `.env` file loading for local dev | Always in local-only v1; `OPENAI_API_KEY`, `SECRET_KEY`, etc. |
| httpx | `^0.28` | Async HTTP client (also test client) | Required for `httpx.AsyncClient` in pytest; already a dep of `fastapi[standard]` |
| pytest | `^8.0` | Test runner | Standard; use with `pytest-asyncio` for async test support |
| pytest-asyncio | `^1.3` | Async test support | 1.3.0 (2025-11-10). Required to run `async def test_*` functions with FastAPI AsyncClient |
| respx | `^0.23` | Mock httpx-based HTTP calls | 0.23.1 (2026-04-08). OpenAI SDK v2 uses httpx under the hood; respx intercepts at the transport layer — no OpenAI-specific mock lib needed |
| anyio | `^4.0` | Async test utilities | Used internally by FastAPI/Starlette; needed for `anyio.to_thread.run_sync()` to offload sync pandas/DuckDB work from async handlers |
| structlog | `^24.0` | Structured logging (LLM call logs) | Emit JSON-structured logs with tokens_in/tokens_out/latency/cost per LLM call; far less boilerplate than stdlib logging |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Package manager, virtualenv, run | Use `uv init`, `uv add <pkg>`, `uv sync`, `uv run <cmd>`. Lock file is `uv.lock`. Never use `pip` directly. |
| Docker + Docker Compose | Container runtime | OrbStack replaces Docker Desktop on macOS (already in use). Volume mount `/data/uploads` for session storage |
| Ruff | Linter + formatter | Fast, replaces flake8 + isort + black. Add as dev dep: `uv add --dev ruff` |
| mypy | Static type checking | `uv add --dev mypy`. Helps catch pydantic model misuse and DuckDB result typing |

---

## Installation

```bash
# Initialize project
uv init mini-plataforma-analise-dados
cd mini-plataforma-analise-dados
uv python pin 3.12

# Core runtime deps
uv add "fastapi[standard]>=0.136" \
       "uvicorn[standard]>=0.46" \
       "pydantic>=2.13" \
       "python-multipart>=0.0.26" \
       "duckdb>=1.5" \
       "pandas>=3.0" \
       "openpyxl>=3.1" \
       "openai>=2.32" \
       "sqlglot>=30.6" \
       "charset-normalizer>=3.4" \
       "altair>=6.1" \
       "PyJWT>=2.12" \
       "pwdlib[bcrypt]>=0.3" \
       "sqlalchemy>=2.0" \
       "python-dotenv>=1.0" \
       "anyio>=4.0" \
       "structlog>=24.0"

# Dev dependencies
uv add --dev \
       "pytest>=8.0" \
       "pytest-asyncio>=1.3" \
       "httpx>=0.28" \
       "respx>=0.23" \
       "ruff" \
       "mypy"

# Sync environment
uv sync
```

---

## Alternatives Considered

| Recommended | Alternative | Why NOT the Alternative |
|-------------|-------------|-------------------------|
| sqlglot (AST parse) | duckdb native parse (`conn.execute("SELECT parse(...)")`) | DuckDB's native parser parses but does NOT block execution — you'd need to wrap in a transaction and check statement type after the fact. sqlglot parses without connecting to a DB, gives you the AST to inspect statement type before any DB contact. Safer for v1 |
| sqlglot (AST parse) | Regex-based SELECT check | Regex fails on `/* SELECT */ DROP TABLE` and SQL comment injections. sqlglot is a real parser — it won't be fooled by trivial obfuscation |
| charset-normalizer | chardet | chardet 7.0 was rewritten with AI assistance and relicensed (LGPL→MIT) under disputed circumstances; also shows poor perf on large files (>1MB). charset-normalizer ships with `requests` already, MIT licensed, 97% accuracy |
| charset-normalizer | cchardet | cchardet is a C extension wrapping an unmaintained Mozilla library; dropped from most distros and not updated since 2021 |
| FastAPI BackgroundTasks + in-memory dict | arq + Redis | v1 is single-box with 2-3 users. arq needs Redis as external dep — adds Docker service, serialization, and retry config for zero actual benefit at this scale. BackgroundTasks + `asyncio.Queue`-backed worker + in-memory `dict[task_id, status]` covers the polling requirement with zero infra |
| FastAPI BackgroundTasks | Celery | Celery is synchronous-first, needs broker (RabbitMQ/Redis), adds worker process management. Complete overkill for a v1 local tool |
| pwdlib[bcrypt] | passlib | passlib last release was 2020; raises deprecation warnings in Python 3.12, breaks in Python 3.13+. FastAPI's own docs switched to pwdlib in 2025 |
| PyJWT | python-jose | python-jose is fine (3.5.0 released 2025-05) but PyJWT is simpler API, production/stable, and directly used in FastAPI official security tutorial |
| altair.chart.to_dict() | Hand-built Vega-Lite dict | Altair validates the spec against the Vega-Lite JSON schema before returning — hand-built dicts produce silent malformed specs. Altair is a schema-validated spec builder, not a chart renderer; backend only needs `to_dict()` |
| altair | vl-convert-python | vl-convert is for rendering Vega-Lite to PNG/SVG server-side. Not needed since the frontend renders via `vega-embed` |
| pandas 3.x | pandas 2.x | pandas 3.x requires Python >=3.11 which the project already uses. Copy-on-Write in 3.x eliminates a class of silent mutation bugs in cleaning pipelines. Staying on 2.x just delays the migration |
| openpyxl (xlsx) | xlrd | xlrd >= 2.0 explicitly dropped xlsx support; only reads legacy `.xls` format. Must not use xlrd for xlsx |
| SQLAlchemy 2.x async | Raw sqlite3 module | sqlite3 is synchronous; calling it from async FastAPI handlers blocks the event loop. SQLAlchemy 2.x with `AsyncSession` handles this correctly. Alternatively: `aiosqlite` + raw SQL |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `xlrd` for `.xlsx` | xlrd >= 2.0 dropped xlsx support intentionally; will raise `XLRDError` on xlsx files | `openpyxl` via `pd.read_excel(..., engine="openpyxl")` |
| `passlib` | Last release 2020; deprecated `crypt` module removal breaks it on Python 3.13+; maintenance uncertain | `pwdlib[bcrypt]` — FastAPI docs updated to use this |
| `cchardet` | Unmaintained C extension; dropped from Debian/Ubuntu packaging; not updated since 2021 | `charset-normalizer` |
| Celery or arq for v1 | Requires Redis broker, multi-process worker management, serialization overhead for 2-3 users on a single box | `FastAPI BackgroundTasks` + in-memory task state dict |
| LLM generates pandas code | Risk of RCE via `eval()` or `exec()` of LLM output; sandbox is complex and brittle | LLM generates SQL (SELECT only); validated by sqlglot AST check before DuckDB execution |
| WebSocket/SSE for progress | Stateful connections, more complex client code, harder to test | HTTP polling on `/tasks/{task_id}` — sufficient for the 2-3 user v1 use case |
| `python-jose` | Older project with less recent activity vs PyJWT; not needed when PyJWT covers all requirements | `PyJWT` |
| `pandas` for query execution | pandas aggregations on 100k+ rows are 10-100x slower than DuckDB; also cannot do SELECT-validated sandboxing | `duckdb` for all query execution; pandas only for ingest/cleaning pipeline |

---

## Key Patterns

### Pattern 1: File Upload Size Enforcement

FastAPI's `UploadFile` does NOT enforce a max size by default. You must check manually before reading into memory:

```python
from fastapi import UploadFile, HTTPException

MAX_BYTES = 50 * 1024 * 1024  # 50 MB

@app.post("/upload")
async def upload(file: UploadFile):
    if file.size and file.size > MAX_BYTES:
        raise HTTPException(413, "File exceeds 50MB limit")
    # Also enforce row count limit after parsing
```

Note: `file.size` is available only when client sends Content-Length. Validate post-read as well.

### Pattern 2: Encoding Detection for PT-BR Files

```python
from charset_normalizer import from_bytes

raw = await file.read()
result = from_bytes(raw)
encoding = result.best().encoding  # e.g. "windows-1252" or "utf-8"

import io
import pandas as pd
df = pd.read_csv(io.BytesIO(raw), encoding=encoding, sep=None, engine="python",
                 decimal=",", thousands=".")  # PT-BR numeric format
```

`sep=None` + `engine="python"` triggers pandas' Python-engine sniffer that auto-detects `,` vs `;` vs `\t`. The `decimal=","` + `thousands="."` handles `1.234,56` Brazilian number format.

### Pattern 3: SELECT-Only SQL Validation with sqlglot

```python
import sqlglot
from sqlglot import exp

def validate_select_only(sql: str, dialect: str = "duckdb") -> str:
    """Raises ValueError if sql is not a single SELECT statement."""
    try:
        statements = sqlglot.parse(sql, dialect=dialect)
    except sqlglot.ParseError as e:
        raise ValueError(f"SQL parse error: {e}")

    if len(statements) != 1:
        raise ValueError("Only single statements allowed")

    stmt = statements[0]
    if not isinstance(stmt, exp.Select):
        raise ValueError(f"Only SELECT allowed, got {type(stmt).__name__}")

    # Block subquery-based mutations and forbidden functions
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Drop,
                 exp.Create, exp.Alter, exp.Command)
    for node in stmt.walk():
        if isinstance(node, forbidden):
            raise ValueError(f"Forbidden node type: {type(node).__name__}")

    return sql
```

This is more robust than DuckDB's native parser for validation because it never opens a DB connection and cannot accidentally execute anything during validation.

### Pattern 4: Structured Output (text-to-SQL) with AsyncOpenAI

Use `response_format` with a Pydantic model instead of plain prompt parsing — the SDK validates and deserializes automatically:

```python
from pydantic import BaseModel
from openai import AsyncOpenAI

class SQLResponse(BaseModel):
    sql: str
    explanation: str  # narration in PT-BR

client = AsyncOpenAI()  # reads OPENAI_API_KEY from env

async def generate_sql(question: str, schema: str) -> SQLResponse:
    completion = await client.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(schema=schema)},
            {"role": "user", "content": question},
        ],
        response_format=SQLResponse,
    )
    return completion.choices[0].message.parsed
```

`client.chat.completions.parse()` (not `.create()`) is the structured output entrypoint in SDK v2. It handles JSON schema generation from the Pydantic model and deserialization back.

### Pattern 5: Background Task with Progress Polling

FastAPI's `BackgroundTasks` runs in the same process but after the response is sent. For progress polling, maintain a shared state dict (or a small in-memory store backed by a dataclass):

```python
import asyncio, uuid
from fastapi import BackgroundTasks
from enum import Enum

class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"

# In-memory store — acceptable for single-process v1
task_store: dict[str, dict] = {}

@app.post("/upload")
async def upload(file: UploadFile, bg: BackgroundTasks):
    task_id = str(uuid.uuid4())
    task_store[task_id] = {"status": TaskStatus.pending, "result": None}
    bg.add_task(process_file, task_id, file)
    return {"task_id": task_id}

@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    return task_store.get(task_id) or HTTPException(404)
```

Limitation: `task_store` is lost on restart. Acceptable for v1 with TTL sessions. If persistence is needed, swap with a lightweight SQLite row.

### Pattern 6: DuckDB ICU Extension (text normalization / collation)

ICU is **autoloaded** on first use from DuckDB's extension repo (no explicit install needed in v1.5.x). It provides locale-aware collations and `NOCASE`/`NFC` normalization for Portuguese text:

```python
import duckdb

conn = duckdb.connect()
# ICU autoloads when first ICU collation is used
# For PT-BR case-insensitive text comparison:
conn.execute("""
    SELECT * FROM data
    WHERE LOWER(nome) = LOWER('São Paulo')
    COLLATE pt
""")
```

For the cleaning pipeline, use pandas `str.strip().str.lower()` for normalization before loading into DuckDB; ICU collation is most useful at query time.

### Pattern 7: Vega-Lite Spec Generation with Altair

Altair's `to_dict()` validates the spec against the Vega-Lite schema before returning — use this server-side to emit JSON the frontend's `vega-embed` can render directly:

```python
import altair as alt
import pandas as pd

def make_bar_chart_spec(df: pd.DataFrame, x_col: str, y_col: str) -> dict:
    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(x=x_col, y=alt.Y(y_col, aggregate="sum"))
        .properties(width="container")
    )
    return chart.to_dict()  # validated Vega-Lite v6 JSON dict
```

The heuristic that picks chart type (bar/line/scatter/table) lives in Python, not the LLM — call the appropriate Altair chart builder based on column shape.

---

## Security Notes

| Concern | Mitigation |
|---------|------------|
| SQL injection via LLM-generated query | sqlglot AST validates SELECT-only before DuckDB execution; DuckDB connection is read-only at session level (`duckdb.connect(read_only=True)`) |
| Prompt injection in user question | System prompt instructs model to only produce valid SQL; classification step rejects off-topic questions; sqlglot catches any DDL/DML regardless |
| File upload abuse | Reject >50MB at upload handler; reject >500k rows post-parse; filename sanitization before writing to volume |
| JWT secret | Read from env var (`SECRET_KEY`); never hardcode; minimum 32 bytes random |
| Password storage | pwdlib uses bcrypt with configurable cost factor (default 12); never store plaintext |
| LLM API key exposure | Load via python-dotenv from `.env`; `.env` in `.gitignore`; never log the key |

---

## pandas 3.0 Breaking Changes to Know

pandas 3.0.0 (released January 2026) has three changes that directly affect this project's cleaning pipeline:

1. **String dtype is now `str` not `object`** — any code checking `df[col].dtype == object` must be updated to `isinstance(df[col].dtype, pd.StringDtype)` or just check `.dtype.kind == 'O'`
2. **Copy-on-Write is default** — chained assignment `df["col"][idx] = val` silently does nothing; use `df.loc[idx, "col"] = val` or `df["col"] = df["col"].where(...)` everywhere in the cleaning pipeline
3. **Datetime resolution changes** — `read_csv` infers microseconds (not nanoseconds) for datetimes; affects downstream integer conversions from timestamps

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| pandas 3.0.x | Python >=3.11, NumPy >=1.26 | Pinning Python 3.12 satisfies this |
| duckdb 1.5.x | Python >=3.10 | No conflicts with pandas 3.x |
| fastapi 0.136.x | pydantic >=2.0 | pydantic v1 compat mode is removed in recent fastapi versions |
| altair 6.x | Vega-Lite v6 schema | Frontend must use `vega-embed` >=6.x or Vega-Lite >=6.x |
| pwdlib 0.3.x | Python >=3.10 | Still beta (0.x) but FastAPI docs use it; stable enough for v1 |
| openai 2.x | httpx >=0.27 | respx mocks at httpx transport layer — works transparently |
| sqlglot 30.x | No external deps | Pure Python; DuckDB dialect up to date with DuckDB 1.5.x |

---

## uv Workflow Reference

```bash
# Add a new runtime dependency
uv add <package>

# Add a dev-only dependency
uv add --dev <package>

# Install all deps from lock file (CI / fresh clone)
uv sync

# Run a command in the project venv
uv run pytest
uv run uvicorn app.main:app --reload

# Update a specific package
uv add "fastapi>=0.137"
# then: uv sync

# Export requirements.txt (for Docker image)
uv export --no-dev --format requirements-txt > requirements.txt
```

In `pyproject.toml`, the `[tool.uv]` section controls Python version and constraint behavior. The lock file `uv.lock` must be committed to git.

---

## Sources

- PyPI live data (2026-04-24): fastapi 0.136.1, uvicorn 0.46.0, pydantic 2.13.3, python-multipart 0.0.26, duckdb 1.5.2, pandas 3.0.2, openai 2.32.0, sqlglot 30.6.0, charset-normalizer 3.4.7, altair 6.1.0, PyJWT 2.12.1, pwdlib 0.3.0, openpyxl 3.1.5, respx 0.23.1, pytest-asyncio 1.3.0, python-jose 3.5.0, bcrypt 5.0.0
- Context7 `/fastapi/fastapi` — BackgroundTasks pattern, UploadFile
- Context7 `/openai/openai-python` — AsyncOpenAI, `chat.completions.parse()` structured output
- Context7 `/tobymao/sqlglot` — `exp.Select`, `find_all`, `parse()` with dialect
- Context7 `/duckdb/duckdb-python` — extension management, ICU autoload
- DuckDB ICU extension docs — `https://duckdb.org/docs/current/core_extensions/icu.html`
- Altair internals — `https://altair-viz.github.io/user_guide/internals.html` — confirms `to_dict()` server-side use, Vega-Lite v6
- pandas 3.0 whatsnew — `https://pandas.pydata.org/docs/whatsnew/v3.0.0.html` — CoW, string dtype, datetime resolution
- FastAPI pwdlib discussion — `https://github.com/fastapi/fastapi/discussions/11773` — confirms passlib abandonment
- charset-normalizer vs chardet — PyPI pages + benchmark data (97% vs 89% accuracy)

---
*Stack research for: mini-plataforma-analise-dados*
*Researched: 2026-04-24*
