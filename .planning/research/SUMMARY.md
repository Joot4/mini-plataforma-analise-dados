# Project Research Summary

**Project:** Mini Plataforma de Análise de Dados
**Domain:** AI-assisted tabular data analysis API — CSV/XLSX ingestion, LLM text-to-SQL, PT-BR first
**Researched:** 2026-04-24
**Confidence:** HIGH

## Executive Summary

This is a backend-only AI data analysis API targeted exclusively at PT-BR users. The system receives CSV/XLSX/TSV uploads, runs an automated cleaning pipeline, generates a structured summary with Portuguese narration, and answers natural language questions by generating DuckDB SQL and narrating results in Portuguese. Research across all four dimensions confirms that the initial PROJECT.md decisions are sound, but surface several mandatory implementation constraints that must be wired in from phase one — not retrofitted later.

The recommended build approach is strict layer-by-layer construction: auth and file ingestion first, then DuckDB session management and summary, then NL Q&A, then hardening. This order is forced by hard dependency chains: NL Q&A cannot work without clean data in a DuckDB session, which cannot exist without the ingestion + cleaning pipeline, which cannot be trusted without PT-BR locale handling. Each layer is independently testable, which is critical given the many silent failure modes in this domain.

The top two cross-cutting risks are PT-BR localization (encoding + number format + date format + accented column names) and LLM-generated SQL security. Both are well-understood and have concrete mitigations — but they must be addressed at ingestion time and SQL validation time respectively. Deferring either to a later phase is not an option: PT-BR data loaded without locale handling produces wrong types that corrupt every downstream layer, and unvalidated LLM SQL is a real RCE-adjacent risk with known CVEs in comparable systems (CVE-2024-5827, CVE-2024-9264).

---

## What We Learned Beyond PROJECT.md's Initial Assumptions

These findings sharpen or correct decisions that were left open in the initial project definition:

| Topic | PROJECT.md Assumption | Research Finding |
|-------|----------------------|-----------------|
| Password hashing | "auth" mentioned; library not named | `passlib` (top FastAPI tutorial result) is abandoned since 2020, breaks Python 3.13+. FastAPI docs now use `pwdlib[bcrypt]`. Use `pwdlib` from day one. |
| OpenAI structured output | "LLM gera SQL" — method unspecified | Use `client.chat.completions.parse()` (not `.create()`) with a Pydantic response model. This is the SDK v2 structured output entrypoint and eliminates all code-fence stripping fragility. |
| DuckDB connection model | "dados viram tabela DuckDB" — pattern unspecified | Per-session isolated `duckdb.connect()` is mandatory. A shared global connection causes thread-safety crashes under concurrent requests (GitHub issue #3517). Named in-memory DBs also have sharing problems (#16717). One connection per session, stored in `SessionStore`. |
| DuckDB security | Not specified | Two-layer defense is required: (1) sqlglot AST parse + SELECT-only assertion before execution AND (2) `SET enable_external_access = false; SET lock_configuration = true` at every new connection. `lock_configuration = true` is critical — without it, a crafted query can re-enable external access at runtime, bypassing Layer 1. |
| pandas version | "pandas" — no version pinned | pandas 3.0 (released Jan 2026) has three breaking changes for the cleaning pipeline: Copy-on-Write is now default (chained assignment silently does nothing), string dtype changed from `object` to `StringDtype`, and datetime resolution changed to microseconds. The cleaning pipeline must be written CoW-aware from the start. |
| Chart heuristic data source | "heuristica deterministica" confirmed | The heuristic must inspect the *result* shape (column types of the query result), not the source schema. A question like "top 5 products" returns categorical+numeric regardless of source schema. |
| Altair usage | "spec Vega-Lite" | Use `altair.Chart.to_dict()` server-side. Altair validates the spec against the Vega-Lite JSON schema before returning — hand-built dicts produce silent malformed specs. |
| Prompt injection | Not mentioned | Real attack surface: cell values in the 3-5 row sample sent to LLM can contain injection attempts. Mitigations: truncate sample values to 50 chars, strip content after `--`, and explicitly instruct the model to ignore instructions found in column names or values. |

---

## Key Findings

### Recommended Stack

All versions verified against live PyPI data as of 2026-04-24. Key constraints: pandas 3.0 requires Python >=3.11 (satisfied by 3.12 pin), FastAPI 0.136 requires pydantic v2 (no v1 compat mode), `pwdlib` is 0.x (beta versioning) but is FastAPI's current documented recommendation.

**Core technologies:**
- `Python 3.12` — runtime; minimum 3.11 required by pandas 3.x
- `FastAPI 0.136` + `uvicorn[standard] 0.46` — async API framework; UploadFile + BackgroundTasks built-in
- `pydantic 2.13` — validation and serialization; Rust core ~50x faster than v1
- `python-multipart 0.0.26` — required for FastAPI UploadFile; missing it causes silent 422 errors
- `pandas 3.0.2` — CSV/XLSX/TSV ingest and cleaning pipeline (CoW-aware code required)
- `openpyxl 3.1.5` — XLSX backend; must pass `engine="openpyxl"` explicitly; `xlrd` must NOT be used for xlsx
- `duckdb 1.5.2` — per-session in-memory OLAP engine; 10-100x faster than pandas for aggregations
- `openai 2.32` (`AsyncOpenAI`) — SDK v2; `chat.completions.parse()` for structured output
- `sqlglot 30.6` — SQL AST parser for SELECT-only validation; DuckDB dialect support; zero external deps
- `charset-normalizer 3.4.7` — encoding detection; 97% accuracy vs chardet's 89%
- `altair 6.1.0` — Vega-Lite JSON spec generation via `to_dict()`; validates against Vega-Lite schema
- `PyJWT 2.12` — JWT encode/decode
- `pwdlib[bcrypt] 0.3` — password hashing; passlib replacement; current FastAPI recommendation
- `SQLAlchemy 2.0` + `aiosqlite` — async SQLite for users/sessions
- `structlog 24.x` — structured JSON logs per LLM call (tokens/cost/latency)
- `anyio 4.x` — `run_in_executor` for offloading blocking pandas/DuckDB calls from async handlers

**What NOT to use:**
- `passlib` — abandoned 2020, deprecation warnings on 3.12, breaks on 3.13+
- `xlrd` for xlsx — dropped xlsx support in v2.0; raises `XLRDError`
- `cchardet` — unmaintained C extension, dropped from most distros
- Celery or arq — Redis broker is overkill for 2-3 local users; use FastAPI BackgroundTasks
- Global DuckDB connection — causes non-deterministic thread-safety crashes

### Expected Features

All PROJECT.md features confirmed as table stakes based on competitive landscape analysis (Julius AI, ChatGPT ADA, PandasAI, Rows AI, Vizly). The PT-BR localization cluster is most likely to produce silent wrong-but-not-erroring behavior if skipped.

**Must have (table stakes) — all in v1:**
- Upload with immediate task_id + polling status
- Delimiter auto-detection (comma vs semicolon) — Brazilian CSVs use `;` by default from Excel
- Encoding auto-detection (UTF-8 / cp1252 / UTF-8-BOM) — government and SAP exports arrive as Windows-1252
- PT-BR number format parsing (`1.234,56`) — pandas and DuckDB do NOT auto-detect this
- DD/MM/YYYY date parsing — pandas default is MM/DD; `dayfirst=True` required
- Accented column name normalization (ASCII aliases + original mapping stored in session manifest)
- Auto cleanup with cleanup report (toggle flags: type inference, null fill, dedup, text norm)
- Structured summary stats + PT-BR LLM narration (2-3 paragraphs)
- NL Q&A returning text + table + Vega-Lite chart spec + `generated_sql` (transparency)
- SQL SELECT-only validation (sqlglot AST) before execution
- Out-of-scope question classifier (gate before SQL generation)
- Retry 1x on invalid SQL with schema re-injection in prompt
- Authentication (email+password, JWT, per-user session isolation)
- Session TTL (1h inactivity)

**Should have (differentiators):**
- PT-BR-first narration quality (system prompt forces PT-BR; competitors are English-first)
- Cleanup report surfaced in summary (Julius AI does not expose what was changed)
- Deterministic chart heuristic (competitors use non-deterministic LLM-chosen charts)
- SQL transparency (competitors don't expose generated SQL)
- XLSX merged cell handling (forward-fill before DataFrame creation)

**Defer to v2+:**
- Multi-turn conversation within session
- Follow-up question suggestions post-answer
- Multi-file join sessions, fuzzy deduplication, frontend UI, persistent history, SSE/WebSocket progress

### Architecture Approach

Standard monolith with clean layering: thin routers to service layer to LLM/DuckDB infrastructure. Session store is an in-process dict (not Redis) — correct for 2-3 local users. Critical structural decisions: one `duckdb.connect()` per session in `SessionStore`, one `AsyncOpenAI` singleton per app lifespan, `CleaningPipeline` as a pure callable with zero HTTP or LLM awareness. All pandas and DuckDB calls are synchronous and must be wrapped in `run_in_executor` inside async handlers.

**Major components:**
1. `IngestionService` — parse CSV/XLSX/TSV; enforce size/row limits; detect delimiter + encoding
2. `CleaningPipeline` — 4 togglable transforms (types, nulls, dedup, text norm); emits `CleanReport`; pure callable, no I/O
3. `SessionStore` — holds per-session `duckdb.connect()` + schema manifest + TTL timestamp; TTL sweeper every 5 min
4. `SummaryService` — per-column stats via DuckDB queries; LLM call for PT-BR narration
5. `QueryOrchestrator` — 7-step pipeline: classify -> build prompt -> LLM -> validate SQL -> execute -> narrate -> chart
6. `LLMClient` — `AsyncOpenAI` singleton; typed methods (sql/narrate/classify); logs tokens+cost per call
7. `SQLValidator` — sqlglot AST parse + SELECT-only + function allowlist; never touches DB
8. `TaskRegistry` — in-process `dict[task_id, TaskState]`; written by background tasks; polled by status endpoint
9. `app/llm/chart.py` — deterministic chart heuristic (result shape -> Vega-Lite spec via Altair `to_dict()`)

### Critical Pitfalls

**1. PT-BR locale cluster — the #1 risk (surfaces in STACK, FEATURES, and PITFALLS)**

Four interlocking silent failures that corrupt data before it reaches DuckDB:

- **Semicolon delimiter misdetected:** pandas defaults to `sep=','`; Brazilian Excel CSVs use `;`. Fix: `sep=None, engine='python'` + assert `len(df.columns) > 1` post-parse; fallback to `sep=';'`.
- **Number format `1.234,56` stays as string:** pandas produces `object` dtype; DuckDB sees `TEXT`; all aggregations return NULL. Fix: scan all `object` columns for PT-BR regex pattern; convert with `replace('.','').replace(',','.')` before DuckDB load. Must happen in cleaning pipeline.
- **Date `DD/MM/YYYY` swapped to `MM/DD`:** pandas defaults to US format; July data becomes January. Fix: `dayfirst=True` always; detect unambiguous cases (day > 12) as confirming signal.
- **Accented column names break LLM SQL:** LLMs produce ASCII identifiers; DuckDB raises `Binder Error` on `Regiao`. Fix: normalize all column names to ASCII snake_case at ingestion, store original->alias mapping, inject only aliases into LLM prompt.

**2. SQL security — mandatory two-layer defense (surfaces in STACK, ARCHITECTURE, and PITFALLS)**

Known CVEs (CVE-2024-5827 Vanna, CVE-2024-9264 Grafana) confirm unvalidated LLM SQL against DuckDB is exploitable. Both layers are required:
- Layer 1: sqlglot AST parse + `isinstance(stmt, exp.Select)` + function allowlist — before any DuckDB contact
- Layer 2: `SET enable_external_access = false; SET lock_configuration = true` at every new connection — `lock_configuration = true` prevents runtime re-enabling; omitting it makes Layer 1 alone insufficient

**3. Per-session DuckDB connection — non-negotiable (surfaces in ARCHITECTURE and PITFALLS)**

DuckDB connections are thread-local. Shared global connection causes non-deterministic `RuntimeError` under concurrent requests (GitHub #3517, #12817). Per-session `duckdb.connect()` in `SessionStore` is the only safe pattern. Also: `conn.register("dataset", df)` (view) fails with cursors — use `CREATE TABLE dataset AS SELECT * FROM df` instead.

**4. passlib -> pwdlib — must be addressed before first commit (surfaces in STACK and PITFALLS)**

passlib last released 2020; raises deprecation warnings on Python 3.12; breaks on 3.13+. FastAPI docs migrated to `pwdlib[bcrypt]` in 2025. Using passlib copied from tutorials is the most common auth mistake in FastAPI projects.

**5. pandas 3.0 Copy-on-Write — affects cleaning pipeline design throughout**

CoW is now default. Chained assignment (`df["col"][idx] = val`) silently does nothing. The entire cleaning pipeline must use `df.loc[idx, "col"] = val` or `df["col"] = df["col"].where(...)`. String dtype is now `StringDtype`, not `object` — checks like `dtype == object` break.

---

## Implications for Roadmap

Based on research, a 5-phase build order is confirmed by both architecture dependency analysis and pitfall prevention requirements.

### Phase 1: Foundation — Auth, Project Setup, and File Ingestion with PT-BR Locale

**Rationale:** Everything downstream depends on a working upload pipeline with correct PT-BR locale handling. Auth comes first because session isolation is wired into every other endpoint. The PT-BR ingestion fixes (encoding, delimiter, number format, date format, column name normalization) must live here — they cannot be added on top of DuckDB later. The security baseline (pwdlib, JWT secret from env, UUID4 session IDs, no user input in file paths) must also be in this phase.

**Delivers:** `POST /auth/register`, `POST /auth/login` (JWT). `POST /upload` that parses CSV/XLSX/TSV correctly for PT-BR data, runs `CleaningPipeline`, returns `task_id`. `GET /upload/{task_id}/status` polling. `CleaningPipeline` fully tested in isolation.

**Addresses:** Upload + task_id feedback, delimiter auto-detect, encoding auto-detect, PT-BR number format, DD/MM/YYYY date parsing, column name normalization, cleanup report, auth + session isolation, session TTL scaffolding.

**Avoids:** Pitfalls 1-5 (entire PT-BR locale cluster), Pitfall 11 (cross-user session leak), Pitfall 12 (weak passwords/hardcoded secret).

**Research flag:** Well-documented patterns throughout. No additional research phase needed.

---

### Phase 2: DuckDB Session + Security Baseline

**Rationale:** Once clean DataFrames come out of Phase 1, this phase materializes them into isolated DuckDB connections. The two-layer SQL security hardening must happen here, not in Phase 4 — DuckDB connections exist from this phase onward. XLSX merged-cell handling also belongs here.

**Delivers:** `SessionStore` with per-session `duckdb.connect()`. `CREATE TABLE dataset AS SELECT * FROM df` at end of upload pipeline. TTL sweeper coroutine. `SET enable_external_access = false; SET lock_configuration = true; SET autoload_known_extensions = false` on every connection at creation. XLSX merged-cell forward-fill in `IngestionService`.

**Addresses:** Session TTL, session isolation, file size/row limits with clear PT-BR error messages, XLSX edge cases.

**Avoids:** Pitfalls 7 (LLM DELETE/DROP/ATTACH), 8 (prompt injection via column names), 10 (DuckDB thread-safety), 6 (XLSX merged cells).

**Research flag:** `lock_configuration = true` is documented in DuckDB securing docs — verify at implementation time. Standard pattern otherwise.

---

### Phase 3: Structured Summary + PT-BR Narration

**Rationale:** With clean data in DuckDB, per-column stats are computed via DuckDB queries. This is the first LLM integration and validates the `AsyncOpenAI` singleton wiring and `chat.completions.parse()` pattern before the more complex 7-step Q&A pipeline.

**Delivers:** `SummaryService` with per-column stats (row/col count, types, nulls%, min/max/mean/median, top-5 categoricals). LLM narration in PT-BR via `client.chat.completions.parse()` with Pydantic response model. `GET /sessions/{session_id}` returning full summary. `structlog` LLM call logging (tokens/cost/latency) established as pattern for all future calls.

**Addresses:** Auto summary (stats + PT-BR narration), observability logging, SQL transparency pattern established.

**Avoids:** Pitfall 9 (full CSV in prompt — summary uses only computed stats, not raw data).

**Research flag:** `client.chat.completions.parse()` verified in Context7 OpenAI SDK docs. Standard pattern.

---

### Phase 4: NL Q&A — Full Text-to-SQL Pipeline

**Rationale:** The central product feature. Depends on Phase 2 (DuckDB session + security baseline) and Phase 3 (schema manifest established, LLM client pattern validated). Implements the full 7-step `QueryOrchestrator`.

**Delivers:** `POST /sessions/{session_id}/query` endpoint. `QueryOrchestrator` (classify -> build prompt -> LLM -> sqlglot validate -> DuckDB execute -> narrate -> chart). `SQLValidator` (sqlglot AST + function allowlist). Out-of-scope classifier prompt. Retry logic (1x with error feedback in prompt). Chart heuristic in `app/llm/chart.py` via Altair `to_dict()`. Full `QueryResponse` with `narration`, `rows`, `chart_spec`, `generated_sql`.

**Addresses:** NL Q&A endpoint, structured response (text + table + Vega-Lite), SQL transparency, out-of-scope rejection, retry-on-invalid-SQL, deterministic chart heuristic.

**Avoids:** Pitfall 7 (SQL security Layer 1), Pitfall 8 (prompt injection), Pitfall 9 (schema context only, no full CSV). Result rows capped at 500 before chart spec to avoid Vega-Lite browser freeze.

**Research flag:** Out-of-scope classifier prompt for PT-BR domain-agnostic data has MEDIUM confidence. Budget for 1-2 prompt refinement cycles with real PT-BR test questions.

---

### Phase 5: Hardening, Error Boundaries, and Integration Tests

**Rationale:** Error boundary cleanup (no raw LLM/DuckDB errors in HTTP responses), OpenAI client timeout + retry config, Docker image optimization, and full integration test suite. These affect production stability but do not block feature validation.

**Delivers:** All exceptions caught and mapped to `UserFacingError` with PT-BR messages; `HTTPException` raised at router level only. `OpenAI(max_retries=2, timeout=httpx.Timeout(connect=5.0, read=30.0))`. `python:3.12-slim` multi-stage Docker image (~300-400MB vs 1.2GB+ naive). Integration tests for: 2 concurrent users, PT-BR CSV fixture (cp1252, semicolon delimiter, `1.234,56` numbers, DD/MM/YYYY dates), adversarial SQL injection attempt, XLSX merged cells.

**Addresses:** PT-BR error messages (`error_type: invalid_question | sql_error | execution_error`), observability finalized, performance SLAs (80k rows <=30s, NL Q&A <=10s verified under load).

**Avoids:** Raw LLM error leak (Anti-Pattern 5 in ARCHITECTURE.md), Docker image size trap, thread-safety validated under concurrent load.

**Research flag:** Standard hardening patterns. No additional research phase needed.

---

### Phase Ordering Rationale

- **PT-BR handling is Phase 1** — if number formats are wrong at load time, every downstream stat and SQL result will be wrong. Not recoverable without re-ingestion.
- **Security baseline is Phase 2** — DuckDB connections exist from Phase 2 onward; `lock_configuration = true` must be set at connection creation, not added retroactively.
- **Summary before Q&A** — Phase 3 validates `AsyncOpenAI` singleton, prompt construction, and `chat.completions.parse()` pattern with a simpler LLM call before the full 7-step pipeline.
- **Hardening last** — error boundaries and Docker optimization don't block feature validation; they are a quality gate before real use.
- **No WebSocket/SSE** — polling is sufficient for 2-3 users; never introduce stateful connections.
- **No Celery/arq** — `FastAPI BackgroundTasks` + in-process `TaskRegistry` is correct for single-box 2-3 users.

### Research Flags

Needs attention during planning:
- **Phase 4 (out-of-scope classifier):** The classifier prompt for PT-BR domain-agnostic data has MEDIUM confidence. Plan for 1-2 prompt iterations with real PT-BR test questions (on-topic, off-topic, ambiguous mix).

Standard patterns (no research phase needed):
- **Phase 1:** PT-BR encoding/delimiter/number/date patterns fully documented and verified.
- **Phase 2:** Per-session DuckDB connection pattern documented in official DuckDB Python docs and confirmed in GitHub issues.
- **Phase 3:** `chat.completions.parse()` pattern verified in Context7 OpenAI SDK docs.
- **Phase 5:** Standard FastAPI error handling and Docker multi-stage build patterns.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All 17 package versions verified against live PyPI 2026-04-24; library patterns verified via Context7 official docs |
| Features | HIGH (table stakes) / MEDIUM (PT-BR specifics) | Table stakes verified across 5 competitors; PT-BR locale behavior verified via DuckDB and pandas official docs; chart heuristic confirmed by architecture cross-reference |
| Architecture | HIGH | FastAPI + DuckDB patterns verified via official docs and confirmed GitHub issues (#3517, #12817, #16717) |
| Pitfalls | HIGH | 3 pitfalls have associated CVEs; 4 others have confirmed GitHub issues with reproduction steps; passlib deprecation confirmed via FastAPI official discussion #11773 |

**Overall confidence:** HIGH

### Gaps to Address

- **Out-of-scope classifier prompt quality:** Logically designed but no PT-BR-specific prompt benchmarking was done. Validate with ~30 real test questions before committing to the prompt format.
- **XLSX merged cell edge cases:** The forward-fill fix handles the most common case. Edge cases (empty first rows, merged cells outside main data grid, password-protected sheets) were not researched. Handle reactively if they surface.
- **OpenAI token budget per session:** No hard per-session token ceiling was designed. Set an OpenAI dashboard hard budget limit before first use.
- **DuckDB extension autoloading:** `SET autoload_known_extensions = false` must be added to Phase 2 connection setup alongside `lock_configuration = true`.

---

## Sources

### Primary (HIGH confidence)
- PyPI live data (2026-04-24) — version pins for all 17 core packages
- Context7 `/fastapi/fastapi` — BackgroundTasks, UploadFile, lifespan
- Context7 `/openai/openai-python` — `AsyncOpenAI`, `chat.completions.parse()` structured output
- Context7 `/tobymao/sqlglot` — `exp.Select`, `find_all`, `parse()` with DuckDB dialect
- Context7 `/duckdb/duckdb-python` — extension management, ICU autoload, connection isolation
- DuckDB securing docs — https://duckdb.org/docs/stable/operations_manual/securing_duckdb/overview
- DuckDB concurrency docs — https://duckdb.org/docs/current/connect/concurrency
- pandas 3.0 whatsnew — https://pandas.pydata.org/docs/whatsnew/v3.0.0.html
- FastAPI pwdlib discussion #11773 — https://github.com/fastapi/fastapi/discussions/11773
- DuckDB threading issue #3517 — https://github.com/duckdb/duckdb/issues/3517
- DuckDB named in-memory connections issue #16717 — https://github.com/duckdb/duckdb/issues/16717
- DuckDB FastAPI concurrency discussion #13719 — https://github.com/duckdb/duckdb/discussions/13719
- OpenAI structured outputs — https://developers.openai.com/api/docs/guides/structured-outputs
- Altair internals — https://altair-viz.github.io/user_guide/internals.html

### Secondary (MEDIUM confidence)
- Julius AI reviews (letdataspeak.com, fritz.ai) — competitive feature landscape
- DuckDB CSV auto-detection docs — https://duckdb.org/docs/current/data/csv/auto_detection
- Text-to-SQL prompt engineering — Arize AI, Wren AI — schema grounding patterns
- FastAPI best practices (zhanymkanov) — project structure
- MotherDuck blog — CSV edge cases with DuckDB
- Rows AI, Vizly AI — feature set reference

### Tertiary (LOW confidence — precedent and validation context)
- CVE-2024-5827 (Vanna text-to-SQL DuckDB SQL injection)
- CVE-2024-9264 (Grafana DuckDB SQL injection file read)
- CVE-2024-11958 (llama-index DuckDB retriever SQL injection)
- arxiv:2308.01990 — prompt injection attack vectors in FastAPI+LLM+SQL
- arxiv:2503.05445 — LLM text-to-SQL backdoor attacks (2025)
- ICSE 2025 — P2SQL injections in LLM web applications

---
*Research completed: 2026-04-24*
*Ready for roadmap: yes*
