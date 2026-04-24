# Architecture Research

**Domain:** Data analysis API — file ingestion, NL query, LLM-assisted SQL
**Researched:** 2026-04-24
**Confidence:** HIGH (FastAPI/DuckDB official docs + verified patterns)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         HTTP Layer (FastAPI)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────┐  │
│  │  /auth       │  │  /upload     │  │  /sessions │  │  /query  │  │
│  │  router      │  │  router      │  │  router    │  │  router  │  │
│  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘  └────┬─────┘  │
├─────────┼─────────────────┼────────────────┼───────────────┼────────┤
│                     Service Layer                                     │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌─────┴──────┐  ┌────┴─────┐  │
│  │ AuthService  │  │IngestionSvc  │  │SessionSvc  │  │QuerySvc  │  │
│  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘  └────┬─────┘  │
│         │                 │                 │               │        │
│         │         ┌───────┴────────┐        │        ┌──────┴──────┐ │
│         │         │ CleaningPipeline│       │        │  LLMClient  │ │
│         │         └───────┬────────┘        │        └──────┬──────┘ │
│         │                 │                 │               │        │
│         │         ┌───────┴────────┐        │        ┌──────┴──────┐ │
│         │         │  TaskRegistry  │        │        │ SQLValidator│ │
│         │         └───────┬────────┘        │        └─────────────┘ │
├─────────┼─────────────────┼────────────────┼────────────────────────┤
│                     Session Store (in-process dict + TTL sweeper)     │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ session_id → { duckdb.Connection, table_name, meta, last_at } │    │
│  └──────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────┤
│                     Persistence Layer                                 │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────┐ │
│  │  SQLite (users  │  │  /data/uploads   │  │  TaskRegistry dict  │ │
│  │  + sessions     │  │  volume (Parquet/ │  │  (in-process, RAM)  │ │
│  │  metadata)      │  │  raw CSV, TTL 1h) │  │                     │ │
│  └─────────────────┘  └──────────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Module |
|-----------|---------------|--------|
| Auth router | Login, token issue/validation | `app/routers/auth.py` |
| Upload router | Receive file, enqueue background task, return task_id | `app/routers/upload.py` |
| Sessions router | GET session summary, DELETE session | `app/routers/sessions.py` |
| Query router | Receive NL question, orchestrate LLM→SQL→exec→narrate | `app/routers/query.py` |
| IngestionService | Parse CSV/XLSX/TSV, enforce limits, hand off to pipeline | `app/services/ingestion.py` |
| CleaningPipeline | Apply 4 transforms (types, nulls, dedup, text); emit report | `app/services/cleaning.py` |
| SessionService | Create/get/delete sessions; own session store dict; run TTL sweeper | `app/services/session.py` |
| QueryService | Orchestrate: classify → build prompt → call LLM → validate → exec → narrate → chart | `app/services/query.py` |
| LLMClient | Singleton OpenAI async client; one method per call type (sql, narrate, classify) | `app/llm/client.py` |
| SQLValidator | Parse with sqlglot; assert top-level is SELECT; walk AST for disallowed nodes | `app/llm/validator.py` |
| TaskRegistry | In-process dict `task_id → TaskState`; written by background tasks; read by polling endpoint | `app/core/tasks.py` |
| SQLite DB | Users, hashed passwords, session metadata rows (not data) | `app/db/sqlite.py` |

---

## Recommended Project Structure

```
app/
├── main.py                  # FastAPI app, lifespan, router registration
├── dependencies.py          # get_current_user, get_session — shared Depends
├── routers/
│   ├── auth.py              # POST /auth/login, POST /auth/register
│   ├── upload.py            # POST /upload, GET /upload/{task_id}/status
│   ├── sessions.py          # GET /sessions/{session_id}, DELETE /sessions/{session_id}
│   └── query.py             # POST /sessions/{session_id}/query
├── services/
│   ├── ingestion.py         # parse_file() → DataFrame; enforce row/size limits
│   ├── cleaning.py          # CleaningPipeline.run(df, flags) → (df_clean, CleanReport)
│   ├── summary.py           # compute_stats(df) → StructuredStats; uses LLMClient for narration
│   ├── session.py           # SessionStore class, TTL sweeper coroutine
│   └── query.py             # QueryOrchestrator: classify→sql→validate→exec→narrate→chart
├── llm/
│   ├── client.py            # _openai_client singleton (created in lifespan); typed methods
│   ├── prompts.py           # prompt builders: build_sql_prompt(), build_narration_prompt()
│   ├── validator.py         # validate_sql(sql: str) → str (raises SQLValidationError)
│   └── chart.py             # heuristic_chart(sql_ast, result_df) → VegaLiteSpec | None
├── schemas/
│   ├── upload.py            # UploadResponse, TaskStatusResponse
│   ├── session.py           # SessionSummary, SessionMeta
│   └── query.py             # QueryRequest, QueryResponse (text + rows + chart_spec)
├── core/
│   ├── config.py            # Settings via pydantic-settings (env vars)
│   ├── tasks.py             # TaskRegistry; TaskState dataclass (PENDING/RUNNING/DONE/FAILED)
│   ├── errors.py            # custom exception classes; error response builder
│   └── logging.py           # structlog config; LLM call logger
├── db/
│   └── sqlite.py            # SQLite connection via aiosqlite; user/session CRUD
└── tests/
    ├── test_ingestion.py
    ├── test_cleaning.py
    ├── test_validator.py
    ├── test_query.py
    └── conftest.py
```

### Structure Rationale

- **`routers/`** — thin: validate request shape, call one service method, return response. No business logic.
- **`services/`** — domain logic lives here. Each file owns exactly one domain concern. `cleaning.py` has zero HTTP or LLM awareness; `query.py` has zero file I/O awareness.
- **`llm/`** — isolated from business logic. Swapping OpenAI for another provider touches only this package. Prompt strings, the validator, and the chart heuristic all live here to keep `services/query.py` readable.
- **`schemas/`** — Pydantic v2 models only. No database models here; SQLite uses plain dicts/dataclasses to avoid ORM overhead for simple user/session tables.
- **`core/`** — cross-cutting infrastructure: config, task registry, error types, logging. Nothing in `core/` imports from `services/` or `routers/`.
- **`db/`** — minimal aiosqlite wrapper. SQLite stores only authentication state and session metadata rows (not actual data).

---

## Architectural Patterns

### Pattern 1: Per-Session DuckDB Connection (Isolated In-Memory DB)

**What:** Each session gets its own `duckdb.connect()` — a completely separate in-memory database instance. The connection is stored in the `SessionStore` dict keyed by `session_id`. The uploaded DataFrame is materialized as a DuckDB table via `CREATE TABLE dataset AS SELECT * FROM df` (not `register()` — see pitfall below).

**Decision rationale:** Using a separate `duckdb.connect()` per session (not named `:memory:session_id` and not a shared connection with per-session tables) is the safest choice because:
1. `duckdb.connect()` with no args creates a fully isolated database — table names cannot collide between sessions.
2. Named in-memory DBs (`:memory:name`) share catalog across all connections to that name, which is not what we want for user isolation.
3. A single shared connection for all sessions requires table-name namespacing (`user_{id}_dataset`) and makes TTL cleanup fragile.
4. DuckDB's documented pattern for parallel Python programs is one connection per thread/context.

**Concurrency consideration:** DuckDB is not async-native. Each query on a connection serializes. Since queries run in background tasks or in `run_in_executor`, this is acceptable — per-user connections never contend with each other.

```python
# app/services/session.py
import duckdb
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Session:
    session_id: str
    user_id: int
    conn: duckdb.DuckDBPyConnection
    table_name: str = "dataset"
    meta: dict = field(default_factory=dict)
    last_accessed: datetime = field(default_factory=datetime.utcnow)

class SessionStore:
    def __init__(self):
        self._store: dict[str, Session] = {}

    def create(self, session_id: str, user_id: int, df) -> Session:
        conn = duckdb.connect()  # isolated in-memory DB
        conn.execute("CREATE TABLE dataset AS SELECT * FROM df")
        session = Session(session_id=session_id, user_id=user_id, conn=conn)
        self._store[session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        s = self._store.get(session_id)
        if s:
            s.last_accessed = datetime.utcnow()
        return s

    def delete(self, session_id: str) -> None:
        s = self._store.pop(session_id, None)
        if s:
            s.conn.close()
```

### Pattern 2: LLM Client as App-Scoped Singleton

**What:** One `AsyncOpenAI` instance, created once in the FastAPI lifespan and stored in `app.state`. Injected into services via FastAPI `Depends`. OpenAI's `AsyncOpenAI` client manages its own connection pool internally and is safe for concurrent use.

**Decision rationale:** Creating a new HTTP client per request wastes TCP connections and TLS handshakes. The official OpenAI Python SDK (`openai>=1.0`) is explicitly designed for singleton use. Per-request instantiation is the most common mistake in LLM service wiring.

```python
# app/main.py
from contextlib import asynccontextmanager
from openai import AsyncOpenAI
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.openai = AsyncOpenAI()       # reads OPENAI_API_KEY from env
    app.state.session_store = SessionStore()
    app.state.task_registry = TaskRegistry()
    # start TTL sweeper
    sweeper = asyncio.create_task(ttl_sweeper(app.state.session_store))
    yield
    sweeper.cancel()
    app.state.openai.close()

app = FastAPI(lifespan=lifespan)
```

### Pattern 3: CleaningPipeline as a Pure Callable Object

**What:** `CleaningPipeline` is a class with a single `run(df, flags) -> (DataFrame, CleanReport)` method. It holds no state between calls. It is instantiated fresh per upload task (or as a singleton — it doesn't matter since it's stateless). It takes the raw DataFrame in and returns the clean DataFrame and a structured report.

**Decision rationale:** Keeping cleaning as a pure function-like object makes it trivially testable in isolation without HTTP context, easy to call from the background task, and replaceable by a Polars or DuckDB-native version later without touching the service layer.

**Boundary:** CleaningPipeline imports only `pandas` and `typing`. It knows nothing about DuckDB, OpenAI, or HTTP.

### Pattern 4: Background Task with SQLite-Backed Task Registry

**What:** `POST /upload` immediately returns `{"task_id": "uuid4"}`. The actual parsing + cleaning + DuckDB loading runs in a FastAPI `BackgroundTask`. Progress is written to a dict (`TaskRegistry`) keyed by `task_id`. The polling endpoint `GET /upload/{task_id}/status` reads from this dict.

**Decision rationale:**
- `BackgroundTasks` is sufficient here because: (a) the pipeline is CPU-bound and completes in ≤30s, (b) there is no requirement for task survival across restarts (one-shot sessions), (c) no external queue infrastructure is needed for 2-3 users.
- The `TaskRegistry` dict is in-process only. If the server restarts, in-flight tasks are lost — acceptable given the single-user-local scope.
- For the task executor itself, pandas + DuckDB operations are synchronous. They must be wrapped with `asyncio.get_event_loop().run_in_executor(None, ...)` inside the background coroutine so they don't block the event loop.

```python
# Pattern for offloading blocking pipeline work
async def _run_pipeline(task_id: str, file_path: Path, flags: CleanFlags, ...):
    registry.set_status(task_id, TaskStatus.RUNNING)
    loop = asyncio.get_event_loop()
    try:
        df, report = await loop.run_in_executor(
            None, lambda: cleaning_pipeline.run(parse_file(file_path), flags)
        )
        session = await loop.run_in_executor(
            None, lambda: session_store.create(session_id, user_id, df)
        )
        registry.set_done(task_id, session_id=session.session_id, report=report)
    except Exception as e:
        registry.set_failed(task_id, error=str(e))
```

### Pattern 5: SQL Validation via sqlglot AST Walk

**What:** After LLM produces a SQL string, before execution:
1. `sqlglot.parse_one(sql, read="duckdb")` — parse or raise `ParseError`.
2. Assert the root node is `sqlglot.exp.Select` — reject anything else (INSERT, UPDATE, DELETE, DROP, CREATE, CALL, etc.).
3. Walk the AST with `.find_all(exp.Anonymous)` to catch unknown function calls; optionally walk `.find_all(exp.Func)` and check against an allowlist.
4. Optionally run `duckdb_conn.execute(f"EXPLAIN {sql}")` as a dry-run to catch schema mismatches before returning a user-visible error.

**Decision rationale — sqlglot over plain regex/string matching:** SQL is not a regular language; regex is trivially bypassed by whitespace, comments, or subqueries. sqlglot parses to a typed AST, making structural assertions reliable. It supports the DuckDB dialect natively (`read="duckdb"`).

**Decision rationale — sqlglot over `duckdb.sql()` dry-run only:** DuckDB's own parser can execute DDL if the SQL is malformed and doesn't parse as pure SELECT. sqlglot's structural check happens before DuckDB sees the SQL, providing a defense-in-depth layer.

```python
# app/llm/validator.py
import sqlglot
from sqlglot import exp

DISALLOWED_STATEMENT_TYPES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
    exp.AlterTable, exp.Command, exp.Use,
)

ALLOWED_FUNCTIONS = {
    "count", "sum", "avg", "min", "max", "round", "coalesce",
    "strftime", "date_trunc", "date_diff", "cast", "try_cast",
    "length", "lower", "upper", "trim", "replace", "substr",
    "row_number", "rank", "dense_rank", "lag", "lead",
    "percentile_cont", "percentile_disc", "stddev", "variance",
    "list_agg", "string_agg", "concat", "concat_ws",
}

def validate_sql(sql: str) -> str:
    """Parse, assert SELECT-only, check functions. Returns clean SQL or raises."""
    try:
        tree = sqlglot.parse_one(sql.strip(), read="duckdb")
    except sqlglot.errors.ParseError as e:
        raise SQLValidationError(f"SQL parse failed: {e}")

    if isinstance(tree, DISALLOWED_STATEMENT_TYPES):
        raise SQLValidationError(f"Statement type {type(tree).__name__} not allowed")

    if not isinstance(tree, exp.Select):
        raise SQLValidationError("Only SELECT statements are allowed")

    for func in tree.find_all(exp.Func):
        name = func.sql_name().lower()
        if name not in ALLOWED_FUNCTIONS:
            raise SQLValidationError(f"Function '{name}' is not whitelisted")

    return sql
```

---

## Data Flows

### Flow 1: Upload → Summary

```
POST /upload  (multipart/form-data)
    │
    ▼
upload router
    │  validate Content-Type, size pre-check
    │  generate task_id (uuid4), session_id (uuid4)
    │  write task_id → PENDING in TaskRegistry
    │  add BackgroundTask(_run_pipeline, ...)
    │  return 202 { task_id, session_id }
    │
    ▼ (background, off event loop via run_in_executor)
IngestionService.parse_file(file_path)
    │  detect delimiter, encoding
    │  read with pandas (csv / xlsx / tsv)
    │  enforce 500k rows / 50MB limit → raise if exceeded
    │  return raw DataFrame
    │
    ▼
CleaningPipeline.run(df, flags)
    │  [if flags.normalize_types]  → infer dtypes, convert PT-BR numbers/dates
    │  [if flags.fill_nulls]       → numeric: mean; categorical: "UNKNOWN"
    │  [if flags.remove_dupes]     → df.drop_duplicates()
    │  [if flags.normalize_text]   → str.strip().lower() on object cols
    │  build CleanReport (counts per transform)
    │  return (clean_df, report)
    │
    ▼
SessionStore.create(session_id, user_id, clean_df)
    │  conn = duckdb.connect()
    │  conn.execute("CREATE TABLE dataset AS SELECT * FROM clean_df")
    │  store Session in _store dict
    │
    ▼
SummaryService.compute_stats(session.conn)
    │  DuckDB queries for per-column stats (min/max/mean/median/nulls/top-5)
    │  return StructuredStats
    │
    ▼
LLMClient.narrate_summary(stats)  [async — back on event loop]
    │  build prompt from stats
    │  call OpenAI chat completion
    │  return 2-3 paragraph PT-BR narration
    │
    ▼
TaskRegistry.set_done(task_id, { session_id, stats, narration, clean_report })

    [Meanwhile: client polls]
GET /upload/{task_id}/status
    │
    ▼
TaskRegistry.get(task_id) → { status, result | error }
```

### Flow 2: NL Question → Answer

```
POST /sessions/{session_id}/query  { "question": "..." }
    │
    ▼
query router
    │  get session from SessionStore (validates ownership via current_user)
    │  call QueryOrchestrator.answer(session, question)
    │
    ▼
QueryOrchestrator.answer()
    │
    ├─ Step 1: Classify (fast LLM call)
    │      LLMClient.classify(question, schema_hint)
    │      → ON_TOPIC | OFF_TOPIC
    │      if OFF_TOPIC: raise UserFacingError("Pergunta fora do contexto dos dados")
    │
    ├─ Step 2: Build SQL prompt
    │      schema = conn.execute("PRAGMA table_info('dataset')").fetchdf()
    │      sample = conn.execute("SELECT * FROM dataset LIMIT 5").fetchdf()
    │      prompt = build_sql_prompt(schema, sample, question)
    │      [System: "You produce only valid DuckDB SELECT SQL. No explanation."]
    │      [structured output: {"sql": "<SELECT ...>"}]
    │
    ├─ Step 3: LLM → SQL
    │      sql_raw = LLMClient.text_to_sql(prompt)
    │      → structured output (response_format with json_schema) guarantees JSON
    │      sql = sql_raw["sql"]
    │
    ├─ Step 4: Validate SQL
    │      sql_clean = validate_sql(sql)   [sqlglot parse + type + function check]
    │      if invalid AND attempts < 2:
    │          retry Step 3 with error feedback in prompt
    │      if still invalid: raise UserFacingError("Não consegui gerar SQL válido")
    │
    ├─ Step 5: Execute
    │      result_df = conn.execute(f"{sql_clean} LIMIT 1000").fetchdf()
    │      [run in executor — DuckDB is sync]
    │
    ├─ Step 6: Narrate
    │      narration = LLMClient.narrate_result(question, sql_clean, result_df.head(20))
    │      [2-3 sentences PT-BR explaining what the data shows]
    │
    ├─ Step 7: Chart spec
    │      spec = heuristic_chart(sql_ast=sqlglot.parse_one(sql_clean), result_df)
    │      [deterministic Python — no LLM involved]
    │
    └─ Return QueryResponse { narration, rows: result_df.to_dict("records"), chart_spec }
```

---

## Session Lifecycle

**Storage:** A plain Python `dict[str, Session]` inside `SessionStore`, which lives in `app.state`. No external process needed.

**Creation:** Created during upload background task after DuckDB table is loaded. Session ID returned to client as part of upload response.

**Access:** Every `GET /sessions/{id}` and `POST /sessions/{id}/query` calls `session_store.get(session_id)` which bumps `last_accessed = datetime.utcnow()`.

**TTL cleanup strategy — lazy sweep (not lazy-on-access):**

A background coroutine started in `lifespan` wakes every 5 minutes and evicts sessions where `now - last_accessed > 1 hour`. This is the preferred pattern over lazy-on-access because:
- Lazy-on-access only evicts when the user next calls an endpoint; a session that's been idle for 4 hours would remain in memory with no natural eviction trigger.
- A sweeper is simple to implement and costs essentially nothing at 2-3 users.
- Closing the DuckDB connection in the sweeper frees the memory immediately.

```python
async def ttl_sweeper(store: SessionStore, interval_s: int = 300, ttl_s: int = 3600):
    while True:
        await asyncio.sleep(interval_s)
        now = datetime.utcnow()
        expired = [
            sid for sid, s in store._store.items()
            if (now - s.last_accessed).total_seconds() > ttl_s
        ]
        for sid in expired:
            store.delete(sid)   # closes DuckDB connection
```

**File cleanup:** The raw uploaded file in `/data/uploads/{user_id}/{filename}` is deleted after DuckDB loading succeeds (in the pipeline). If loading fails, it is deleted in the `finally` block. Files do not accumulate.

---

## Security Boundary: LLM → SQL → Execute

This is the most critical path. The defense-in-depth layers are:

```
LLM output (untrusted string)
    │
    ├─ Layer 1: Structured output (response_format json_schema)
    │     OpenAI guaranteed to return {"sql": "..."} — no prompt injection
    │     in the wrapper JSON; the SQL string inside may still be malicious.
    │
    ├─ Layer 2: sqlglot parse (structural check)
    │     Raises ParseError if not valid SQL.
    │     Asserts root node is exp.Select.
    │     Blocks: INSERT, UPDATE, DELETE, DROP, CREATE, CALL, PRAGMA.
    │
    ├─ Layer 3: Function allowlist (sqlglot AST walk)
    │     Blocks unknown functions that could be DuckDB extensions
    │     (e.g., read_csv, httpfs, copy, export_database).
    │
    ├─ Layer 4: DuckDB connection isolation
    │     Each user's DuckDB connection has no file system access
    │     (no ATTACH, no read_parquet('/etc/passwd') etc.) because
    │     the function allowlist blocks those function names.
    │
    └─ Layer 5: Row limit
          conn.execute(f"{sql} LIMIT 1000")
          Prevents accidental full-table dumps on very large datasets.
```

**Error surface rule:** LLM errors and SQL validation errors are caught at the service layer and converted to `UserFacingError` with a human-readable Portuguese message. Raw exception text never reaches the HTTP response body. Structured logging captures the raw error internally.

---

## Prompt Construction Decision

**Choice: OpenAI structured output (response_format with json_schema) over tool-call JSON or plain text.**

Rationale:
- `strict: true` with a JSON schema guarantees the model returns `{"sql": "<...>"}` — eliminates the need to strip markdown code fences, handle "Here is the SQL:" prefixes, or parse mixed prose.
- Tool calls are semantically for invoking external functions; SQL generation is a transformation, not a function call. Using structured outputs is the correct semantic.
- Plain text requires fragile post-processing (strip ` ```sql ` blocks, etc.) and has a real failure mode where the model adds an explanation sentence.
- GPT-4o-mini supports `response_format` with JSON schema as of gpt-4o-mini-2024-07-18 and later — the constraint is met.

**Prompt structure:**

```
System:
  You are a SQL expert. Given a DuckDB table schema and sample data,
  produce exactly one valid DuckDB SELECT statement that answers the user's question.
  Output only valid SQL. The table is named 'dataset'.

User:
  Schema:
  {column_name | dtype | nullable ...}

  Sample (5 rows):
  {json of first 5 rows}

  Question: {user_question}
```

**3-5 sample rows** (not full dataset, not zero-shot schema-only) — research shows sample rows significantly improve accuracy for data type and value format recognition.

---

## Build Order (Phase Dependencies)

```
Phase 1 — Foundation
  ├── app skeleton (FastAPI app, lifespan, config, logging)
  ├── Auth (SQLite users, JWT)
  └── TaskRegistry + background task infrastructure

Phase 2 — Ingestion + Cleaning   [depends on Phase 1]
  ├── IngestionService (parse CSV/XLSX/TSV)
  ├── CleaningPipeline (4 transforms + CleanReport)
  └── Upload endpoint + polling endpoint

Phase 3 — DuckDB Session + Summary   [depends on Phase 2]
  ├── SessionStore + TTL sweeper
  ├── DuckDB table loading (part of upload pipeline)
  └── SummaryService (stats + narration via LLM)

Phase 4 — NL Query   [depends on Phase 3]
  ├── LLMClient (text_to_sql, narrate, classify methods)
  ├── SQLValidator (sqlglot)
  ├── QueryOrchestrator (all 7 steps)
  └── Chart heuristic (Vega-Lite spec)

Phase 5 — Hardening + Observability   [depends on Phase 4]
  ├── Structured LLM call logging (tokens/cost/latency)
  ├── Error boundary cleanup (no raw errors to client)
  └── Integration tests (pytest end-to-end)
```

**Critical dependency:** The DuckDB table load is the output of Phase 2 (ingestion+cleaning pipeline) and the prerequisite for everything in Phase 3+. It is not a separate step — it is the last step of the upload background task. The boundary between Phase 2 and Phase 3 is: Phase 2 ends when `session_store.create()` is called; Phase 3 starts when `session.conn` is readable.

---

## Anti-Patterns

### Anti-Pattern 1: Shared Global DuckDB Connection

**What people do:** `conn = duckdb.connect()` at module level, all requests share it.
**Why it's wrong:** Single connection serializes all queries. In the discussion thread for DuckDB+FastAPI, users report the process freezing under concurrent load because multiple async requests fight over the same locked connection.
**Do this instead:** One `duckdb.connect()` per session, stored in `SessionStore`.

### Anti-Pattern 2: Register DataFrame as View Instead of Table

**What people do:** `conn.register("dataset", df)` to expose a pandas DataFrame as a DuckDB view.
**Why it's wrong:** Registered views are connection-scoped. If you create cursors from the same connection for parallel queries, those cursors cannot see the registered view. The DuckDB GitHub discussion (#13719) specifically identifies this as the cause of "view not found" errors in FastAPI apps.
**Do this instead:** `conn.execute("CREATE TABLE dataset AS SELECT * FROM df")` — persistent in the connection's in-memory catalog, visible to all cursors.

### Anti-Pattern 3: LLM Plain Text SQL Parsing

**What people do:** Ask LLM to return SQL as plain text, then `response.split("```sql")[1].split("```")[0]`.
**Why it's wrong:** Model output format varies; the split breaks on multi-fence responses, responses with no fence, or responses with explanations. One prompt injection can bypass all of it.
**Do this instead:** Use `response_format` with `json_schema: {"sql": {"type": "string"}}` and `strict: true`.

### Anti-Pattern 4: Running pandas in async def Directly

**What people do:** `async def upload_handler(): df = pd.read_csv(file)` — pandas inside an async route or background coroutine without executor.
**Why it's wrong:** pandas is synchronous and CPU-bound. Running it inside `async def` blocks the event loop for the duration, freezing all other requests.
**Do this instead:** `await loop.run_in_executor(None, lambda: pd.read_csv(file))` wraps the blocking call in a thread and yields the event loop while pandas runs.

### Anti-Pattern 5: Leaking Raw LLM Errors to HTTP Responses

**What people do:** `except OpenAIError as e: raise HTTPException(detail=str(e))`.
**Why it's wrong:** Raw OpenAI error messages may contain partial prompt content, API key hints, or internal model details. Bad UX and security risk.
**Do this instead:** Catch all LLM/validation exceptions in `QueryOrchestrator`, log the full error internally with `structlog`, raise a `UserFacingError` with a clean PT-BR message, and map `UserFacingError` to `HTTPException(422)` in the router.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| OpenAI API | `AsyncOpenAI` singleton in `app.state`; methods in `LLMClient` | One client, connection-pooled. Timeout 30s. Log tokens+cost per call. |
| Docker volume `/data/uploads` | Plain `pathlib.Path` writes during ingestion | Delete file after DuckDB load. No cleanup needed at session TTL — file already gone. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Router ↔ Service | Direct Python call via `Depends` | No message bus needed at this scale |
| Service ↔ LLMClient | Direct method call (async) | LLMClient raises typed exceptions; service handles retry |
| CleaningPipeline ↔ SessionStore | Returns `(DataFrame, CleanReport)`; caller passes df to `SessionStore.create()` | Pipeline has no reference to session system |
| QueryOrchestrator ↔ SQLValidator | `validate_sql(sql) → str` — raises `SQLValidationError` | Validator is pure function; no I/O |
| QueryOrchestrator ↔ DuckDB conn | Passes `session.conn` into executor calls | Conn stays in SessionStore; service borrows it per request |

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 2-3 local users (v1) | Everything in this document — monolith, in-process session store, SQLite, single Docker container |
| 10-50 users | Replace in-process TaskRegistry + SessionStore with Redis; keep DuckDB per-session pattern; add rate limiting middleware |
| 100+ users | Per-session DuckDB becomes per-request DuckDB against Parquet files on object storage; replace SQLite with Postgres; add Celery/ARQ worker pool |

---

## Sources

- [FastAPI Bigger Applications — Official docs](https://fastapi.tiangolo.com/tutorial/bigger-applications)
- [FastAPI Lifespan Events — Official docs](https://fastapi.tiangolo.com/advanced/events)
- [DuckDB Python DB API — Official docs](https://duckdb.org/docs/current/clients/python/dbapi)
- [DuckDB Concurrency — Official docs](https://duckdb.org/docs/current/connect/concurrency)
- [DuckDB Python Overview — Official docs](https://duckdb.org/docs/current/clients/python/overview)
- [DuckDB + FastAPI concurrency discussion (#13719)](https://github.com/duckdb/duckdb/discussions/13719)
- [DuckDB named in-memory connections issue (#16717)](https://github.com/duckdb/duckdb/issues/16717)
- [sqlglot — Official docs](https://sqlglot.com/sqlglot.html)
- [FastAPI best practices — zhanymkanov](https://github.com/zhanymkanov/fastapi-best-practices)
- [OpenAI Structured Outputs — Official docs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Text-to-SQL prompt engineering — Arize AI](https://arize.com/blog/how-to-prompt-llms-for-text-to-sql/)
- [FastAPI BackgroundTasks vs ARQ — davidmuraya.com](https://davidmuraya.com/blog/fastapi-background-tasks-arq-vs-built-in/)

---
*Architecture research for: Mini Plataforma de Análise de Dados (FastAPI + pandas + DuckDB + OpenAI)*
*Researched: 2026-04-24*
