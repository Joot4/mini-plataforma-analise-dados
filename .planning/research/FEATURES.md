# Feature Research

**Domain:** AI Data Analysis Assistant over Uploaded Tabular Files (CSV/XLSX)
**Researched:** 2026-04-24
**Confidence:** HIGH (table stakes verified across Julius AI, ChatGPT ADA, PandasAI, Rows AI, Vizly); MEDIUM (PT-BR specifics, chart heuristics)

---

## Feature Landscape

### Table Stakes (Users Expect These)

After two years of AI data analysis products (Julius AI, ChatGPT Advanced Data Analysis, Rows AI, Vizly, PandasAI), users arrive with specific expectations. Missing any of these makes the product feel broken, not just incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Upload + immediate processing feedback** | Every competitor returns a task ID or progress indicator; silent processing feels like a crash | LOW | Polling endpoint is sufficient; WebSocket not needed at v1 |
| **Auto column type inference** | Users expect the tool to "understand" the data without manual schema definition | MED | Must handle: integer, float, date (DD/MM/YYYY PT-BR), boolean, categorical text, free text; distinguish numeric-looking strings (CPF, CEP) from actual numbers |
| **Null/missing value report** | Any serious data tool surfaces missing data before analysis | LOW | Count + % per column; users must know their data quality before trusting answers |
| **Duplicate row detection and removal** | Duplicates silently inflate aggregates; any cleanup tool handles this | LOW | Exact-match dedup is sufficient for v1; fuzzy dedup (near-duplicates) is differentiator territory |
| **Auto data summary on upload** | Julius AI, Rows AI, ChatGPT ADA all return a structured summary immediately after upload; users expect this | MED | Minimum: row count, column count, types, nulls%, min/max/mean for numerics, top-5 values for categoricals |
| **Natural language narration of the summary** | The narration is the product's voice; stats alone feel like a raw JSON dump | MED | 2-3 paragraphs in Portuguese explaining what the dataset is, what stands out, and data quality flags; must be in PT-BR |
| **NL question endpoint (text-in, answer-out)** | Core value proposition; missing it = no product | HIGH | Accept PT-BR question, return text + table + chart spec; this is the central feature |
| **Structured response: text + table + chart spec** | Julius AI, ChatGPT ADA, Vizly all return multi-modal answers; text-only feels incomplete | MED | Text narration in PT-BR, result table (rows), Vega-Lite JSON spec; caller renders chart |
| **SQL transparency (show the generated SQL)** | Explainability is table stakes in 2026; users want to verify how the answer was reached | LOW | Return `generated_sql` field alongside the answer; no UI needed, just expose it in the JSON response |
| **Rejection of out-of-scope questions** | Users trust the product more when it clearly says "this question is not about your data" rather than hallucinating an answer | MED | Classifier prompt that checks question relevance against dataset context before generating SQL |
| **Error message when query fails** | Silent failures destroy trust; users need to know when to rephrase | LOW | Expose `error_type: invalid_question | sql_error | execution_error` with a human-readable PT-BR message |
| **PT-BR number format parsing** | Brazilian CSVs use `1.234,56` (period thousands, comma decimal); pandas and DuckDB do NOT auto-detect this | MED | Must pre-process during ingest: detect decimal separator heuristically (most cells with comma-decimal → pt-BR mode), then convert before loading into DuckDB (see PT-BR section below) |
| **DD/MM/YYYY date parsing** | Default pandas/DuckDB date parsing assumes MM/DD/YYYY or ISO; Brazilian dates are DD/MM/YYYY | MED | Use `dayfirst=True` in pandas, `dateformat='%d/%m/%Y'` in DuckDB; must be auto-detected or default to PT-BR ordering |
| **Delimiter auto-detection (comma vs semicolon)** | Brazilian CSV exports from Excel use `;` as delimiter (because `,` is the decimal separator) | LOW | pandas `sep=None, engine='python'` sniffs; or scan first line explicitly |
| **Encoding auto-detection (UTF-8 / Latin-1 / Windows-1252)** | Files from old Excel or government systems arrive as Windows-1252 | LOW | Try UTF-8 first, fall back to cp1252; chardet library as backup |
| **File size / row count enforcement with clear error** | Users expect a meaningful message when file exceeds limits | LOW | 500k rows / 50MB ceiling; return `413` with PT-BR explanation |
| **Authentication (email + password, per-user session isolation)** | Users expect their uploaded data not to be visible to others | MED | JWT or session token; SQLite for users table; sessions isolated by user_id |

### Differentiators (Competitive Advantage)

These are not expected from a v1 tool but would set this product apart, especially at the informal 2-3 person team scale.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **PT-BR first narration quality** | Julius AI and ChatGPT ADA generate English narration regardless of data locale; a tool that thinks and explains in Portuguese natively is distinctly valuable for BR teams | MED | System prompt explicitly in PT-BR; few-shot examples with Brazilian data vocabulary (e.g., "CNPJ", "parcelas", "inadimplência"); test with real BR datasets |
| **Cleanup flags (toggle per operation)** | Exposing 4 cleanup toggles (type inference, null fill, dedup, text normalization) lets callers control what the tool does vs their own pipeline | LOW | Already in PROJECT.md; differentiates from black-box tools where you don't know what was changed |
| **Cleanup report in response** | Precise count of changes made (X nulos preenchidos, Y duplicatas removidas, Z colunas com tipo corrigido) builds trust and auditability | LOW | Trivially generated during cleanup pass; Julius AI does not surface this |
| **Acento-safe column name normalization** | Brazilian files routinely have `Receita Bruta (R$)`, `% Inadimplência`, `Mês/Ano` as column names; tools that fail on these silently lose queries | LOW | Normalize to DuckDB-safe snake_case but keep original name in the schema manifest; return both `column_original` and `column_id` in summary |
| **Deterministic chart type heuristic** | LLM-chosen charts are non-deterministic and untestable; a rule-based heuristic is reproducible and auditable | LOW | Already in PROJECT.md; this is a correct architectural choice that competitors don't always make |
| **Vega-Lite spec as contract** | Any future UI (React, Streamlit, Jupyter) can render without re-querying; the API is future-proof | LOW | Already decided; vega-embed ready |
| **Retry-on-invalid-SQL with reformulation hint** | Products that silently fail or return raw SQL errors frustrate non-technical users; one auto-retry before asking for rephrasing is a graceful UX | LOW | Already in PROJECT.md; max 1 retry with schema re-injection in the prompt |
| **Explicit `session_id` in all responses** | Allows a future UI or script to manage multi-file sessions; the caller always knows their context | LOW | Include in every response envelope |

### Anti-Features (Commonly Requested, Often Problematic)

These are features users sometimes request after seeing AI data tools, but that create more problems than value for this product's scope.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **LLM picks chart type** | Feels smart; users assume AI "knows best" | Non-deterministic: same query returns different charts across calls; untestable; LLMs pick pie charts inappropriately for >5 categories; breaks if model updates | Deterministic heuristic: 1 categorical + 1 numeric → bar; date + numeric → line; 2 numeric → scatter; else → table only. Testable, reproducible. |
| **LLM executes arbitrary Python/pandas code** | ChatGPT ADA does it; users expect it | RCE surface: even sandboxed execution has escape vectors; containerizing Python per-request adds infrastructure complexity; security auditing burden for a v1 local tool | LLM generates SELECT SQL only; DuckDB whitelist validation; zero code execution risk |
| **Persistent upload history** | "Why can't I see my old files?" | LGPD/data retention obligation; backup complexity; UI needed to browse history; one-shot model is intentional scope decision | Explicit session TTL (1h); clear documentation that data is ephemeral by design |
| **Dashboard / scheduled refresh** | Julius AI users ask for this; looks impressive in demos | Requires a scheduler, a persistent data store, a render service, and a sharing/permissions model; out of scope for a v1 API | Return Vega-Lite spec to the caller; the caller can persist and re-render on their own schedule |
| **Multi-file joins** | "Can I upload my sales file AND my customer file and join them?" | Schema disambiguation becomes hard (same column name in both files); LLM prompt bloat; session model breaks; requires a query planner | Explicitly out of scope v1; document as v2 feature if demand materializes |
| **LLM-generated confidence scores** | Users want to know "how sure is the AI?" | LLMs produce poorly-calibrated confidence estimates; a stated 90% confidence may be 40% accurate; creates false trust | Show the SQL (transparency over false confidence); show row count of result ("answer based on 1,423 rows"); let the user judge |
| **Fuzzy/semantic deduplication** | "These two rows are clearly the same company spelled differently" | Requires embedding model + similarity threshold; slow; subjective threshold; false positive risk on legitimate variants | Exact-match dedup in v1; flag columns with >80% unique values as "possible ID column" in the summary |
| **Multi-sheet XLSX support** | "My file has 5 sheets" | Sheet selection requires UI or parameter negotiation; sheets may have incompatible schemas; ingest pipeline complexity multiplies | Always take first sheet; document clearly; add sheet selector as a named parameter in v2 |
| **Rate limiting and abuse protection** | "What if someone uploads 10GB files?" | For 2-3 informal users, formal rate limiting is engineering overhead without payoff | File size/row hard cap (already defined); auth isolates users; TTL cleans up storage |
| **WebSocket / SSE progress streaming** | "I want a real-time progress bar" | SSE adds infrastructure state; polling is simpler, well-understood, and sufficient for a 30s processing window | task_id polling with status endpoint; document expected wait times |

---

## PT-BR Localization Expectations

This deserves a dedicated section because it is the single most common source of silent failures in data analysis tools used in Brazil.

### Number Format (HIGH RISK — NOT auto-detected by DuckDB or pandas)

Brazilian CSVs use the European convention:
- Decimal separator: `,` (comma)
- Thousands separator: `.` (period)
- Example: `1.234.567,89` means one million two hundred thirty-four thousand five hundred sixty-seven point eighty-nine

**What fails silently:**
- pandas reads `1.234,56` as a string (not a number) unless `decimal=','` and `thousands='.'` are explicitly set
- DuckDB's CSV sniffer does NOT auto-detect decimal separator; the `decimal_separator` parameter must be set manually
- If not handled, every numeric column in a PT-BR file stays as VARCHAR, aggregations return zero or error, and the LLM gets a useless schema

**Mitigation strategy:**
1. During type inference pass, sample each column: if >60% of cells match regex `^\d{1,3}(\.\d{3})*(,\d+)?$` → flag as PT-BR numeric
2. Convert: `cell.replace('.', '').replace(',', '.')` before loading into DuckDB
3. Report in cleanup summary: "X colunas numéricas no formato PT-BR foram normalizadas"

### Date Format (HIGH RISK — ambiguous with default parsers)

Brazilian dates are `DD/MM/YYYY` or `DD/MM/YY`. Pandas defaults to MM/DD (US), so `01/05/2024` is parsed as January 5 instead of May 1.

**Mitigation:** Default to `dayfirst=True` for all date parsing; expose as `locale: pt-BR | iso` parameter in upload endpoint for callers who know their format.

DuckDB needs `dateformat='%d/%m/%Y'` explicitly — it does not sniff DD/MM.

### Accented Column Names (MEDIUM RISK)

Brazilian spreadsheets routinely use column names like:
- `Receita Bruta (R$)`, `% Desconto`, `Mês de Referência`, `Nº Pedido`, `CPF/CNPJ`

**What fails:**
- Column names with spaces, parentheses, `%`, `/`, `ñ`, `ç`, `ã` break SQL generation (LLM wraps in quotes inconsistently)
- DuckDB handles quoted identifiers but the LLM may forget to quote them
- Accent handling in Python varies by normalization form (NFD vs NFC)

**Mitigation:**
1. On ingest, create a normalized alias: `receita_bruta_r` (snake_case, ASCII, no special chars)
2. Store a mapping: `{alias: original_name}` in the session schema manifest
3. Inject alias names into the LLM prompt (never the original names with special chars)
4. Return both `column_id` (alias) and `column_label` (original) in summary output
5. Use `unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()` for alias generation

### Encoding (MEDIUM RISK)

Files from government portals, SAP exports, and old Excel typically arrive as Windows-1252 (cp1252) or ISO-8859-1 (Latin-1). Attempting to read them as UTF-8 raises `UnicodeDecodeError` or, worse, silently corrupts accented characters.

**Mitigation:** Try `utf-8`, then `cp1252` (covers Windows-1252 and Latin-1 superset). Use `chardet` only as last resort (it's slow on large files).

### LLM Narration Language

When narrating summaries and answers, the LLM must:
- Generate in PT-BR (system prompt forces this, not instruction-dependent)
- Use Brazilian vocabulary: "dataset", "linha", "coluna", "valor nulo", "média", "mediana" — not English terms
- Handle Brazilian-specific domain labels: "CNPJ", "CPF", "CEP", "R$", "parcelas" without confusion
- Format numbers in output as PT-BR: `1.234,56` not `1,234.56` — even if DuckDB returns `1234.56` internally

---

## Feature Dependencies

```
File Upload
    └──requires──> Encoding Detection
    └──requires──> Delimiter Detection

Encoding Detection
    └──requires──> (chardet or heuristic fallback)

Auto Cleanup
    └──requires──> Column Type Inference
                       └──requires──> PT-BR Number Detection
                       └──requires──> Date Format Detection (dayfirst heuristic)
                       └──requires──> Encoding-safe column name read

Cleanup Report
    └──requires──> Auto Cleanup (tracks delta: nulls filled, dupes removed, types cast)

Auto Summary (structured stats)
    └──requires──> Auto Cleanup (clean types needed for min/max/mean/top-5)
    └──requires──> Column Name Normalization (accented → alias)

Auto Summary (LLM narration)
    └──requires──> Auto Summary (structured stats) [stats injected into LLM prompt]
    └──requires──> Schema Manifest (types + aliases)

NL Q&A
    └──requires──> DuckDB Table Load
                       └──requires──> Auto Cleanup (clean types required for valid SQL)
                       └──requires──> Column Name Normalization (aliases used in SQL)
    └──requires──> Schema Manifest (injected into LLM prompt as context)
    └──requires──> SQL Validator (whitelist + SELECT-only enforcement)
    └──requires──> Out-of-scope Classifier (question relevance check)

SQL Transparency
    └──requires──> NL Q&A (the SQL is a byproduct of the generation step)

Chart Spec Generation
    └──requires──> NL Q&A result shape (column types of result determine chart heuristic)

Session (multi-turn)
    └──requires──> DuckDB Table Load (table persists in-memory for session lifetime)
    └──requires──> Schema Manifest (referenced on every follow-up question)

Out-of-scope Classifier ──enhances──> NL Q&A (gate before SQL generation)
Cleanup Report ──enhances──> Auto Summary (can be included in summary narration)
SQL Transparency ──enhances──> User Trust (show the SQL in response envelope)

Column Name Normalization ──conflicts──> Raw column names in SQL
    (never pass original accented names to LLM; always use aliases)
```

### Dependency Notes

- **Auto Summary requires Auto Cleanup:** Running summary stats on raw data with un-cast types gives meaningless results. A column of `"1.234,56"` strings produces no mean/max.
- **NL Q&A requires Column Name Normalization:** If column aliases aren't injected into the LLM prompt, the model will hallucinate or quote original names inconsistently, producing invalid SQL.
- **Chart Spec requires result shape inspection:** The heuristic must examine the column types in the query result (not the source schema), because a question like "what are the top 5 products?" returns a categorical + numeric result regardless of source schema.
- **PT-BR Number Detection must run before DuckDB load:** Once data enters DuckDB as VARCHAR, fixing it requires re-loading. Do it in the pandas cleanup pass before writing to DuckDB.

---

## MVP Definition

### Launch With (v1)

Minimum to validate the core pipeline and deliver the stated product value.

- [x] **Upload endpoint** — CSV/XLSX/TSV with delimiter + encoding auto-detect; returns task_id
- [x] **Auto cleanup** — type inference (PT-BR number + date aware), null fill, dedup, text normalization; produces cleanup report
- [x] **Column name normalization** — accented/special-char columns mapped to ASCII aliases; manifest stored in session
- [x] **Structured summary** — row/col count, types, nulls%, min/max/mean/median/top-5 per column
- [x] **LLM narration in PT-BR** — 2-3 paragraphs describing dataset + anomalies + data quality flags
- [x] **NL Q&A endpoint** — accept PT-BR question + session_id; return text + table + Vega-Lite spec + generated_sql
- [x] **Out-of-scope classifier** — reject questions about things not in the data
- [x] **SQL validation + SELECT-only whitelist** — before execution; retry 1x on invalid SQL
- [x] **Chart heuristic** — deterministic rule-based (categorical+numeric → bar; date+numeric → line; 2 numeric → scatter; else → table-only)
- [x] **Authentication** — email/password, per-user session isolation, JWT
- [x] **Session TTL** — 1h inactivity, files wiped from volume

### Add After Validation (v1.x)

Add once core pipeline is live and used by 2-3 people.

- [ ] **Multi-turn conversation within session** — accumulate question history in session context; pass last 3 Q&A pairs to LLM for pronoun resolution ("show me the same for last year")
- [ ] **Explicit PT-BR locale parameter** — `?locale=pt-BR` to force number/date format; currently defaulted
- [ ] **Follow-up question suggestions** — LLM proposes 2-3 follow-up questions after each answer; low token cost, high UX value
- [ ] **XLSX sheet selector parameter** — `sheet_index=0` currently hardcoded; expose as optional parameter

### Future Consideration (v2+)

Defer until product-market fit or until a real user asks for it.

- [ ] **Multi-file join sessions** — upload two files, ask questions across them; requires query planner + schema disambiguation
- [ ] **Fuzzy deduplication** — near-duplicate detection via edit distance or embedding similarity
- [ ] **Frontend UI** — already out of scope for v1; only after API is validated
- [ ] **Export to PDF/Excel report** — Julius AI has this; irrelevant until UI exists
- [ ] **Persistent upload history** — requires LGPD policy decision; explicitly deferred
- [ ] **Real-time progress (SSE/WebSocket)** — only if 30s processing window proves painful in practice
- [ ] **Database connectors (Postgres, BigQuery)** — out of scope; this is file-based analysis

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| PT-BR number format parsing | HIGH | MED | P1 |
| PT-BR date format (DD/MM/YYYY) | HIGH | LOW | P1 |
| Auto cleanup with cleanup report | HIGH | MED | P1 |
| Column name normalization (accents → alias) | HIGH | LOW | P1 |
| Auto summary (structured stats + PT-BR narration) | HIGH | MED | P1 |
| NL Q&A with text + table + Vega-Lite | HIGH | HIGH | P1 |
| SQL transparency (return generated SQL) | HIGH | LOW | P1 |
| Out-of-scope question classifier | HIGH | MED | P1 |
| SQL validation + SELECT whitelist | HIGH | LOW | P1 |
| Chart heuristic (deterministic) | MED | LOW | P1 |
| Auth + session isolation | HIGH | MED | P1 |
| Session TTL + storage cleanup | MED | LOW | P1 |
| Encoding auto-detect (UTF-8 / cp1252) | MED | LOW | P1 |
| Delimiter auto-detect (; vs ,) | MED | LOW | P1 |
| Multi-turn follow-up within session | MED | MED | P2 |
| Follow-up question suggestions | MED | LOW | P2 |
| Locale parameter (explicit) | LOW | LOW | P2 |
| XLSX sheet selector | LOW | LOW | P2 |

---

## Competitor Feature Analysis

| Feature | Julius AI | ChatGPT ADA | PandasAI | Our Approach |
|---------|-----------|-------------|----------|--------------|
| **Auto cleanup** | Yes (opaque, no report) | Yes (Python sandbox) | Yes (via LLM-driven code) | Deterministic pandas pipeline; cleanup report surfaced in response |
| **Auto summary** | Column names + types on upload | Immediate stats | Optional | Stats + PT-BR LLM narration in response to upload |
| **NL Q&A** | Multi-turn, conversational | Multi-turn, code exec | NL → pandas code | NL → SQL → DuckDB; SELECT-only, no code exec |
| **Chart generation** | LLM-chosen; non-deterministic | LLM-chosen | LLM-chosen | Deterministic heuristic; Vega-Lite spec as contract |
| **SQL transparency** | Not exposed | Not exposed (shows Python) | Not exposed | Always returned in response envelope |
| **Session / conversation** | Multi-turn with context retention | Multi-turn | Single or multi | Single-turn v1; multi-turn in v1.x via message history |
| **PT-BR / localization** | English-first; no PT-BR locale | English-first | No locale support | PT-BR first: number/date parsing, narration in Portuguese |
| **Out-of-scope rejection** | Partial (hallucinates sometimes) | Partial | No | Explicit classifier step before SQL generation |
| **File size limits** | Varies by plan | 512MB file, ~50MB CSV effective | Memory-limited | 500k rows / 50MB hard cap |
| **Code execution risk** | High (Python sandbox) | High (sandboxed Docker) | High (arbitrary Python) | None (SQL only, whitelist validated) |
| **Confidentiality** | Cloud (OpenAI-backed) | Cloud (OpenAI) | Configurable | Local Docker; files in isolated volume with TTL |

---

## Sources

- [Julius AI Review 2026 - Let Data Speak](https://letdataspeak.com/julius-ai-review/) — feature list, hallucination risk, session behavior
- [Julius AI Review 2025 - Fritz AI](https://fritz.ai/julius-ai-review/) — limitations, chart handling, conversation model
- [DuckDB CSV Auto Detection](https://duckdb.org/docs/current/data/csv/auto_detection) — type detection capabilities and `decimal_separator` limitation
- [DuckDB CSV Date Format Discussion](https://github.com/duckdb/duckdb/discussions/10951) — DD/MM/YYYY requires explicit `dateformat` parameter
- [Reading CSV with DD/MM/YYYY in Pandas - w3reference](https://www.w3reference.com/blog/read-csv-with-dd-mm-yyyy-in-python-and-pandas/) — `dayfirst=True` pattern
- [Reading CSV with Special Characters - Saturn Cloud](https://saturncloud.io/blog/reading-csv-files-with-pandas-and-special-characters-in-column-names/) — column name unicode handling
- [Reducing Hallucinations in Text-to-SQL - Wren AI](https://medium.com/wrenai/reducing-hallucinations-in-text-to-sql-building-trust-and-accuracy-in-data-access-176ac636e208) — SQL validation, schema grounding
- [Actionable Explainability for AI Data Agents - ConnectYAI](https://www.connectyai.com/blogs/actionable-explainability) — SQL transparency pattern
- [PandasAI GitHub](https://github.com/sinaptik-ai/pandas-ai) — NL → code architecture reference
- [Advancing Conversational Text-to-SQL - MDPI](https://www.mdpi.com/1999-5903/17/11/527) — multi-turn context strategies
- [Rows AI](https://rows.com/ai) — feature set reference
- [Vizly AI](https://vizly.ai/) — NL data analysis feature reference
- [Taming Wild CSVs with DuckDB - MotherDuck](https://motherduck.com/blog/taming-wild-csvs-with-duckdb-data-engineering/) — CSV edge cases and DuckDB handling

---

*Feature research for: AI Data Analysis Assistant (text-to-SQL, CSV/XLSX, PT-BR)*
*Researched: 2026-04-24*
