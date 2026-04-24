# Roadmap: Mini Plataforma de Análise de Dados

## Overview

Six phases build the system layer by layer, each independently testable. Phase 1 establishes the project skeleton and auth so all subsequent endpoints have a security perimeter from day one. Phase 2 handles file ingestion with full PT-BR locale correctness — this is the highest-risk phase because wrong encoding, delimiter, or number format corrupts every downstream stat and query without raising an error. Phase 3 materializes clean DataFrames into isolated DuckDB sessions with two-layer SQL security hardened at connection creation time. Phase 4 validates the LLM client wiring by implementing the simpler summary narration before the full query pipeline. Phase 5 delivers the core value: natural-language questions answered with text + table + Vega-Lite chart spec. Phase 6 verifies performance SLAs, closes error boundaries, and validates the system under concurrent load.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Project skeleton, Docker infra, auth (register/login/JWT), SQLite migrations, task registry baseline
- [ ] **Phase 2: Ingestion & PT-BR Locale** - Upload endpoint + polling, CSV/XLSX/TSV parsing with full PT-BR locale handling, cleaning pipeline with report
- [ ] **Phase 3: DuckDB Session & Security** - Per-session isolated DuckDB connections, two-layer SQL security hardening, session TTL sweeper
- [ ] **Phase 4: Structured Summary** - Per-column stats via DuckDB, PT-BR LLM narration, structured logging for every LLM call
- [ ] **Phase 5: NL Query** - Full text-to-SQL pipeline: classify → generate SQL → validate → execute → narrate → chart spec
- [ ] **Phase 6: Hardening & Performance** - Error boundaries, performance SLA validation (80k rows ≤30s, NL Q&A ≤10s), integration tests

## Phase Details

### Phase 1: Foundation
**Goal**: The project skeleton, Docker environment, and authentication layer are fully operational so every subsequent endpoint has a security perimeter from the first commit.
**Depends on**: Nothing (first phase)
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, OPS-04, OPS-05, OPS-06
**Success Criteria** (what must be TRUE):
  1. `POST /auth/register` creates a user with bcrypt-hashed password and returns HTTP 201; a second call with the same email returns HTTP 409.
  2. `POST /auth/login` returns a JWT token; any protected endpoint called without that token returns HTTP 401; the same endpoint called with a valid token returns HTTP 200.
  3. User A's JWT cannot be used to access resources belonging to User B (cross-user isolation enforced at the dependency layer).
  4. `docker compose up` starts the API in under 10 seconds; SQLite migrations run automatically on startup with no manual step required.
  5. The final Docker image size is under 500MB (`docker image ls` shows ≤500MB for the app image).
**Plans**: TBD

### Phase 2: Ingestion & PT-BR Locale
**Goal**: A user can upload any supported file format and receive a task_id immediately, with the background pipeline correctly parsing PT-BR data and returning a complete cleaning report via polling.
**Depends on**: Phase 1
**Requirements**: INGEST-01, INGEST-02, INGEST-03, INGEST-04, INGEST-05, INGEST-06, INGEST-07, INGEST-08, INGEST-09, CLEAN-01, CLEAN-02, CLEAN-03, CLEAN-04, OPS-01, OPS-02
**Success Criteria** (what must be TRUE):
  1. `POST /upload` with a valid file returns HTTP 202 with a `task_id` in under 2 seconds, regardless of file size up to the limit.
  2. A file exceeding 50MB or 500k rows is rejected immediately with HTTP 413 and a Portuguese error message.
  3. A Brazilian CSV file encoded in CP1252, using `;` as delimiter and `1.234,56` as number format, is ingested with correct column types (float, not string) and no garbled characters in column names or values.
  4. A CSV with `DD/MM/YYYY` dates where day > 12 produces correct dates (e.g., `15/07/2024` parses as July 15, not unambiguous).
  5. `GET /upload/{task_id}/status` returns `done` with a cleaning report that includes non-zero counts for `nulos_preenchidos`, `duplicatas_removidas`, or `tipos_convertidos` on a fixture file known to have those issues.
**Plans**: TBD
**UI hint**: no

### Phase 3: DuckDB Session & Security
**Goal**: Every uploaded dataset lives in an isolated, hardened DuckDB connection with a 1-hour TTL, and no SQL variant — however crafted — can access files outside the session or execute non-SELECT operations.
**Depends on**: Phase 2
**Requirements**: AUTH-05, AUTH-06, SQL-01, SQL-02, SQL-03, SQL-04, SQL-05
**Success Criteria** (what must be TRUE):
  1. After a successful upload, `GET /sessions/{session_id}` returns a response (schema manifest with column aliases and sample rows).
  2. Sending `SELECT * FROM read_csv('/etc/passwd')` or any `DROP`/`DELETE`/`ATTACH` statement as a query returns a validation error before DuckDB executes it.
  3. A session that has had no activity for over 1 hour is absent from the session store within 5 minutes (verified by the sweeper logic with a shortened TTL in tests).
  4. Two concurrent requests from two different users to their respective sessions complete without a `RuntimeError` related to DuckDB thread safety.
  5. User B cannot retrieve or query the session created by User A even with a valid JWT (returns HTTP 403 or 404).
**Plans**: TBD

### Phase 4: Structured Summary
**Goal**: Every completed upload produces a full structured summary — per-column stats plus a 2-3 paragraph Portuguese narration — accessible via the polling endpoint, with every LLM call logged with tokens and cost.
**Depends on**: Phase 3
**Requirements**: SUM-01, SUM-02, SUM-03, OPS-03
**Success Criteria** (what must be TRUE):
  1. `GET /upload/{task_id}/status` when `done` includes a `summary` object with `rows`, `cols`, and a `columns` array containing `null_pct`, `min`/`max`/`mean`/`median` for numeric columns and `top5` for categorical columns.
  2. The `summary.narration` field contains 2–3 Portuguese paragraphs that correctly identify the dataset (correct column count, a notable numeric range, or a top categorical value that matches the actual data).
  3. Every LLM call produces a structured log entry on stdout with `provider`, `model`, `tokens_in`, `tokens_out`, `cost_estimated`, `latency_ms`, and `session_id` — verifiable by grepping JSON logs during a test run.
**Plans**: TBD

### Phase 5: NL Query
**Goal**: A user can ask a natural-language question in Portuguese about an uploaded dataset and receive a structured response with an explanatory text, a result table, and a Vega-Lite chart spec — all in under 10 seconds.
**Depends on**: Phase 4
**Requirements**: NLQ-01, NLQ-02, NLQ-03, NLQ-04, NLQ-05, NLQ-06, NLQ-07, NLQ-08, NLQ-09, NLQ-10
**Success Criteria** (what must be TRUE):
  1. `POST /sessions/{session_id}/query` with a valid on-topic question returns HTTP 200 with a response containing non-empty `text`, `table`, and `generated_sql` fields.
  2. An off-topic question (e.g., "qual a capital do Brasil?") returns an error response with `error_type: out_of_scope` and a friendly Portuguese message instead of SQL.
  3. A result containing 1 categorical column and 1 numeric column produces a `chart_spec` with `mark: bar`; a result with 2 numeric columns produces `mark: point`; a result with over 1000 rows has `truncated: true` in the response and the table contains exactly 1000 rows.
  4. The `chart_spec` is a valid Vega-Lite v6 JSON object (parseable by Altair with no schema errors) when a chart-eligible result is returned.
  5. When the LLM generates invalid SQL on the first attempt, the system retries once automatically; if the second attempt also fails, the response contains `error_type: invalid_question` with a Portuguese reformulation prompt.
**Plans**: TBD

### Phase 6: Hardening & Performance
**Goal**: The full pipeline meets its performance SLAs under realistic load, all error paths return user-facing Portuguese messages with no raw exceptions leaking, and integration tests confirm the system works end-to-end with real PT-BR fixture files.
**Depends on**: Phase 5
**Requirements**: PERF-01, PERF-02
**Success Criteria** (what must be TRUE):
  1. A PT-BR CSV fixture of 80,000 lines (CP1252 encoding, `;` delimiter, `1.234,56` numbers, `DD/MM/YYYY` dates) completes the full upload → clean → summary pipeline in 30 seconds or less (measured end-to-end from POST to status `done`).
  2. A NL query on a loaded dataset (including both LLM calls) returns a complete response in 10 seconds or less (measured from POST to HTTP 200).
  3. No endpoint returns a raw Python exception, traceback, OpenAI error message, or DuckDB error string in the HTTP response body — all error cases return structured JSON with a Portuguese `message` field.
  4. Running the integration test suite with 2 concurrent users, each uploading a different PT-BR fixture and asking 3 questions, produces zero 5xx responses and zero DuckDB thread-safety errors.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/TBD | Not started | - |
| 2. Ingestion & PT-BR Locale | 0/TBD | Not started | - |
| 3. DuckDB Session & Security | 0/TBD | Not started | - |
| 4. Structured Summary | 0/TBD | Not started | - |
| 5. NL Query | 0/TBD | Not started | - |
| 6. Hardening & Performance | 0/TBD | Not started | - |
