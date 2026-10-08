# Vero knowledge backend

One Vero application, database and evidence model. Current setup is in the [README](../README.md). Historical checkpoints below are dated, not current coverage claims. The registry has 500 companies; live acquisition counts come from `/api/knowledge/status`.

## What is implemented

- Complete retained raw-page text is indexed in lossless page-local windows, independent of the metric catalogue. All retained table cells are indexed with row positions, null cells and source table IDs. Original documents, pages, tables, parse runs and reviewed metrics remain unchanged.
- PostgreSQL English full-text search with a GIN index, relevance ranking, pagination, company/report/sector/country/report-year filters and limited explicit synonym expansion. This is lexical retrieval, not semantic embeddings or exhaustive language understanding.
- Every result includes the company, official source URL, PDF hash, physical page, printed label where available, passage hash, parse/index fingerprint and locator. The evidence endpoint returns its full page and structured tables.
- Search/knowledge status distinguishes library membership, downloaded reports, indexed reports and incomplete text extraction. Legacy company records are not automatically included in this knowledge library.
- Independent resumable acquisition jobs reuse existing robots-aware download, parser and domain-throttling services. One failed company does not stop the rest. The new `collect-reports` command supports bounded parallel collection with a durable cohort/run ledger; see [bulk collection](BULK_COLLECTION.md).
- OpenAI Responses API synthesis, strict JSON schema plus Python validation, passage-bound citations, safe provider errors, caching and cost tracking. Narrative synthesis cannot write metric observations; explicit metric extraction uses the same transport and budget guard through the numerical validation pipeline. Neither has web tools, arbitrary URL fetching or silent fallback.
- The original benchmark engine still governs quantitative performance comparisons. Searchable report statements do not become validated metrics or peer rankings merely because a model cites them.

## Fresh source policy

The prior five-company study and old registry are development/reference material, not the new product's coverage claim. No historical report is automatically promoted.

`knowledge-ingest` performs fresh discovery by default. Resuming a job reuses reports already acquired by that job. `--reuse-retained` is an explicit historical-data opt-in; `--refresh` performs discovery again. Existing documents are never overwritten. Identical downloaded bytes remain content-addressed/deduplicated.

Choose a freshly checked company universe before a broad run. The existing import CLI accepts a reviewed CSV with stable company UUIDs. It does not establish that a company is among the largest 500; universe membership and source dates must be researched separately. The new acquisition CLI supports up to 500 selected records, but does not fabricate missing companies or reports.

The discovery year is a report label. A report published in 2026 can contain 2025 observations. Search returns requested, detected and reporting years separately and does not fill unknown observation years. The existing crawler remains bounded and official-domain only; it is not a web-wide search engine. JS/access restrictions and unknown external CDN ownership can still require source curation. No controls are bypassed.

## Startup

From the repository root:

```bash
bash scripts/dev.sh
```

This applies migrations and starts the existing local API/frontend. No acquisition or inference runs on startup. PostgreSQL is on loopback port 55433, API on 8000. Do not expose this unauthenticated development server publicly.

From `backend/`, using the existing local `DATABASE_URL` in `backend/.env`:

```bash
.venv/bin/python -m app.cli knowledge-status
# Choose explicit freshly checked company UUIDs; repeat --company as needed.
.venv/bin/python -m app.cli knowledge-ingest --year 2025 --company COMPANY_UUID --limit 20
.venv/bin/python -m app.cli knowledge-ingest --year 2025 --company COMPANY_UUID --limit 20 --resume
# Only after replacing/checking the universe; this command is not run automatically:
.venv/bin/python -m app.cli knowledge-ingest --year 2025 --all-active --limit 500 --resume
# Optional explicit indexing of a selected already-parsed official source:
.venv/bin/python -m app.cli knowledge-index --report REPORT_UUID
.venv/bin/python -m app.cli knowledge-search 'supplier water scarcity'
```

CLI output is structured JSON. Nonzero ingestion exit means some jobs are incomplete; successful work remains saved. HTTP transient retries are bounded; explicit resume retries incomplete jobs up to `PIPELINE_JOB_MAX_ATTEMPTS`. Interrupted jobs can be resumed because a database advisory lock distinguishes a live worker from a crashed attempt. No OCR or AI is implicitly triggered by acquisition/indexing.

## API contract

| Endpoint | Purpose |
|---|---|
| `GET /api/knowledge/status` | Actual knowledge coverage, ingestion outcomes and safe AI configuration metadata |
| `GET /api/system/ai` | Direct OpenAI key/model access check; no inference, secrets or report text |
| `GET /api/knowledge/collections` | Recent bulk collection runs and processed counts |
| `GET /api/knowledge/collections/{run_id}` | Per-company sources, report-year gaps and acquisition diagnostics |
| `GET /api/knowledge/reports` | Paginated selected-library sources and parse/index quality |
| `GET /api/knowledge/reports/{report_id}/inspection` | Read-only file checksum, opening pages, period/boundary excerpts and source warnings |
| `POST /api/knowledge/preview` | Non-AI lexical preview; the planned live workflow may retrieve different evidence |
| `POST /api/knowledge/search` | Read-only arbitrary-topic document retrieval |
| `POST /api/knowledge/coverage` | Read-only company-by-company lexical search coverage |
| `GET /api/knowledge/evidence/{id}` | Full source page and tables for a current passage |
| `POST /api/knowledge/ask` | Opt-in paid, cached, source-bound research synthesis |
| `GET /api/knowledge/answers/{id}` | Retained answer and source freshness status |

Search example:

```bash
curl -s http://127.0.0.1:8000/api/knowledge/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"supplier engagement and water scarcity","limit":10}'
```

Optional scope fields: `company_ids`, `report_ids`, `sector`, `country` (ISO alpha-2), `report_year`. `report_year` filters known report-year metadata, not every observation in the report. Search also supports `offset` and `limit` (maximum 100).

The coverage endpoint examines every selected company in the knowledge library and distinguishes `matches_found`, `not_found_in_index`, and `not_indexed`. These are search outcomes, not disclosure/no-disclosure findings. An index may be partial because pages require OCR or failed parsing.

## Direct OpenAI setup

1. Use your project key from the [OpenAI API key page](https://platform.openai.com/api-keys), not an OpenRouter key or ChatGPT login. Do not share it in chat or put it in frontend code.
2. Local settings are already prepared in **`/Users/ahmednajaf/Documents/ChatGPT/sustainability dashboard/backend/.env`**. Enter the key after `OPENAI_API_KEY=` and save. Do not overwrite this file with an example once your key is saved. Settings explicitly load this file; a root `.env` is not implicitly loaded.

```dotenv
AI_PROVIDER=openai
KNOWLEDGE_AI_ENABLED=true
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-mini-2026-03-17
OPENAI_ALLOWED_MODELS=["gpt-5.4-mini-2026-03-17"]
OPENAI_DAILY_TOKEN_LIMIT=2000000
OPENAI_REASONING_EFFORT=low
OPENAI_TIMEOUT_SECONDS=90
OPENAI_MAX_OUTPUT_TOKENS=4000
OPENAI_INPUT_PRICE=0.75
OPENAI_OUTPUT_PRICE=4.5
KNOWLEDGE_MONTHLY_BUDGET_USD=5
KNOWLEDGE_MAX_EVIDENCE_CHARS=30000
```

3. Restart the backend after environment changes (stop its existing terminal process with Ctrl-C first), then:

```bash
cd '/Users/ahmednajaf/Documents/ChatGPT/sustainability dashboard/backend'
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
# From another terminal:
curl -s http://127.0.0.1:8000/api/system/ai
```

`ready: true` confirms authenticated access to the selected model's metadata. The check never runs inference; `inference_verified` stays false. Missing/invalid credentials, inaccessible models, rate limits and timeouts return safe error codes and HTTP 503. `/api/knowledge/status` remains a configuration-only read and does not contact OpenAI.

4. After fresh reports are indexed, call `/api/knowledge/ask` with `{"question":"How do the selected companies describe supplier engagement?","company_ids":["..."]}`. This is a real paid call when enabled. Do not send private uploads without appropriate approval.
5. To change model, edit `OPENAI_MODEL` and `OPENAI_ALLOWED_MODELS`, update token rates from official pricing, and choose a supported reasoning effort (remove that setting for models without it). Restart and recheck. Set `KNOWLEDGE_AI_ENABLED=false` to disable hosted calls. There is **no automatic fallback** and no OpenRouter configuration to supply.
6. Evaluate the exact model and prompts on held-out report cases before treating research as dependable. The starting model is a configuration choice, not a benchmark winner; mocked tests cannot establish live accuracy.

On **8 October 2026** the active model changed to pinned `gpt-5.4-mini-2026-03-17`. Standard token prices are **$0.75 input / $4.50 output per million**, per the [model documentation](https://developers.openai.com/api/docs/models/gpt-5.4-mini). Check any complimentary usage eligibility in your own account. The app uses a conservative 2M-token daily ceiling and a $5 monthly list-price guard. Neither is an account-wide billing guarantee. Other apps, eligibility changes and quota-crossing requests can cause charges. The old private environment remains git-ignored and is not loaded.

Endpoint is fixed to `https://api.openai.com/v1/responses`; ambient proxies and redirects are disabled. Requests set `store=false`. This is not a claim of zero data retention; the account's provider data controls still apply. Only the bounded selected passages and question are sent, not entire PDFs. No report text, response bodies or keys are logged.

## Grounding and limitations

The answer contains cited claims, not uncited factual narrative. Evidence IDs must belong to supplied passages; quotations and numerical literals must match. Statements failing a check are withheld individually and counted explicitly; supported independent findings remain visible as a partial answer. Scope/eligibility notes and exact database counts are server-generated, distinguished from report facts. These checks do **not** establish semantic entailment or correct table interpretation. Answers are labelled `ai_generated_citations_checked`, never `validated`. See [the shared research workflow](RESEARCH_WORKFLOW.md).

A schema-validated model plan selects 1–3 complementary searches and names the requested entities. The server resolves entities against the real registry and intersects all explicit scope filters. Query results are fused by reciprocal rank, then balanced across up to six relevant companies, with same-page context. Selection is by evidence relevance, never alphabetical order or sustainability merit. Phrases stay intact and generic question words are ignored. Up to eight page/kind-diverse candidates per company/query are considered; the model context stays bounded to 16 passages and 30,000 evidence characters by default. Provenance and layout metadata remain stored but unnecessary fields are omitted from model input.

The preview and answer coverage explicitly list `supplied`, `omitted_context_limit`, `no_lexical_match`, `not_indexed_in_scope`, and requested IDs outside the active library/scope. These are not reported/not-reported metric states. Large peer groups may exceed the context budget; this is not a 500-company analysis in one call. Retrieval may still miss paraphrases, distant footnotes, relevant companies, images or table context. Full report pages remain accessible. Multilingual semantic retrieval, page-image analysis and deeper table-aware extraction are not implemented here.

`POST /api/knowledge/preview` works without hosted AI and is explicitly labelled `lexical_only_not_final_ai_research_plan`. It is not a prediction of the paid planner's searches. The chat no longer describes preliminary preview counts as final analysis progress. Source inspection checks the first eight physical pages, period/boundary phrases and unknown metadata. Only the dedicated inspection endpoint rechecks on-disk PDF checksums. Neither endpoint validates metrics or changes report metadata.

See [the real-report retrieval evaluation](KNOWLEDGE_RETRIEVAL_EVALUATION.md) for regression cases, remaining limitations and the live-AI configuration blocker.

“How many” is no longer blanket-blocked. A numerical company fact is researched normally; library counts are computed from PostgreSQL; a disclosure-population question returns supported examples with an explicit census limitation. Exact semantic disclosure counts across hundreds of companies still require a persisted company-by-company assessment. Lexical matches are never presented as disclosure counts.

The original metric comparison safeguards have not been loosened. The new library enables qualitative research independently of benchmark eligibility; broader comparison policies still need separate implementation and tests.

## Budgets, caching and crash recovery

Costs use operator-configured rates. A conservative reservation covers both planning and synthesis before either call. A normal request uses at most two model calls; metadata-only or empty-retrieval outcomes skip synthesis. One research workflow runs at a time. Each call records its task, model, tokens and latency; retrieval and total wall time are also recorded. Prices must be kept current; provider billing remains authoritative.

Timeouts and malformed responses retain their entire reservation when usage is unknown, since a failed local request can still cost money. There is no automatic POST retry. Budget accounting includes unknown outcomes; exceeding the monthly local budget blocks subsequent calls. This controls this application's calls only, not other uses of the account key.

Cache identity includes question/conversation, scope, current corpus/index fingerprints, company membership, library counts, metric/validation update versions, model, reasoning effort, context/output limits and prompt version. Changed sources, records or validation invalidate replay. Historical answers remain inspectable. If a process is killed during a call, the operator can release its running state **after ten minutes**:

```bash
.venv/bin/python -m app.cli knowledge-recover-ai ANSWER_UUID
```

Its cost reservation remains charged conservatively; this command cannot recover a still-recent live request.

## Capacity and operations

PostgreSQL stores company/report metadata, page text, structured tables, search indexes, jobs and audit trails. PDFs stay in immutable content-addressed file storage. A cloud object store can replace that storage at deployment; no new database or microservice is needed just for 500 companies.

`scripts/benchmark-knowledge.py` creates a private schema only in a database ending `_test`, loads synthetic companies/pages/passages, runs the real search service and removes that schema. It never adds synthetic records to the Vero library. This checks single-process local search capacity, not internet acquisition throughput, production concurrency, hosted extraction accuracy or actual company coverage.

Before deployment: provision managed PostgreSQL with automated backups/PITR and TLS, private network access, a least-privilege app role, durable PDF storage, application access controls, monitoring and a restore rehearsal. Those production services are not provisioned by this local backend change.

Backup both the database and `data/reports/`; database-only backup cannot reconstruct PDFs. Keep credentials out of backup filenames, logs and repository commits. Use `pg_dump --format=custom` for PostgreSQL and preserve source-file hashes; restore into a new database first, never over the current one. See the local backup/restore smoke script for a non-destructive test of the database snapshot.

## Verification

Mocked-provider tests cover strict output, refusal, bad credentials, rate limits, redirects, timeout, citation and numerical checks, budget limits and replay. PostgreSQL integration tests cover full-page retention, table null cells, arbitrary topics, source freshness, filters, pagination, current evidence, immutable source protection, API error states and resumable independent jobs. UI code is unchanged.

## Real collection checkpoint — 6 October 2026

Fresh acquisition attempted **15 real companies**. Seven primary reports are now downloaded and indexed, totalling **1,573 physical PDF pages**. This is not 500-company coverage or a validated metric dataset.

| Company | Official primary source | PDF pages | Native-text pages |
|---|---|---:|---:|
| Apple | Environmental Progress Report 2025 | 126 | 126 |
| Hitachi | Sustainability Report 2025 | 149 | 149 |
| Siemens | Sustainability Statement 2025 | 117 | 116 |
| Schneider Electric | Sustainable Development Report 2025 | 290 | 290 |
| Danone | Annual Integrated Report 2025 (English PDF) | 57 | 57 |
| Shell | Annual Report and Accounts 2025 | 462 | 462 |
| HSBC Holdings | Annual Report and Accounts 2025, including ESG review | 372 | 370 |

Five of these primary reports were selected by the crawler. Shell and HSBC required explicit official-link checks, recorded in `data/official_sources_2026-10-06.json` and `data/hsbc_official_source_2026-10-06.json`. Shell's browser-rendered page failed during navigation; the PDF linked by its official reporting centre downloaded through the same robots-aware client. HSBC's group annual report replaced a narrow insurance disclosure as the selected primary source. Existing source evidence was not overwritten.

Three additional real supporting documents were retained separately: Hitachi assurance, HSBC insurance principles and Barclays reporting framework. These do **not** count as complete primary-report coverage. The image-only Hitachi assurance document has no searchable native text. The three textless pages in the primary reports are flagged, not silently OCR'd. Other table/layout warnings remain visible; indexed text is not validated metrics.

Eight companies still lack a collected primary report in this checkpoint: AstraZeneca and BP (robots endpoint 403), Nestlé and Unilever (403), SAP (robots denial), Roche (download access failure), L'Oréal (bounded discovery/official-domain resolution incomplete), Barclays (supporting framework only). No controls were bypassed and no figures were substituted. These are acquisition failures/limitations, **not** claims that the companies do not publish reports.

Report labels and measurement years remain distinct: for example, the 2025 Apple and Hitachi publications include fiscal-2024 results. No cross-year comparisons were inferred.

`output/real-report-acquisition-2026-10-06.json` contains exact URLs, report IDs, retrieval timestamps, SHA-256 hashes, local files, page counts, job diagnostics and real search examples. All ten downloaded PDF hashes and source-file API responses were checked. Four topic searches and their source-page endpoints passed. No AI calls or synthetic inserts were made by collection.

Reproduce the read-only audit with a **new output filename**:

```bash
backend/.venv/bin/python scripts/export-real-acquisition.py output/real-report-audit-next.json
```

For an explicitly registered source, use the exact report ID returned by `register-reports`:

```bash
# From backend/. Requires one company; does not substitute historical reports.
.venv/bin/python -m app.cli knowledge-ingest --year 2025 --company COMPANY_UUID --report REPORT_UUID
```

Verification: **484 backend tests passed, 2 optional live tests skipped; 105 frontend tests passed; backend/frontend type checks and frontend production build passed.** The unchanged globe bundle still produces a size warning. Actual API status was also checked on localhost:8000. Hosted AI remains disabled/unconfigured; this checkpoint verifies collection, provenance and retrieval, not model accuracy. UI integration remains for the user-guided design phase.

Official API references: [Responses](https://developers.openai.com/api/reference/responses/overview), [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Pricing](https://developers.openai.com/api/docs/pricing).
