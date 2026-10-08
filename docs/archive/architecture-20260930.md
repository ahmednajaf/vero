# Historical architecture — 30 September 2026

Archived on 8 October. This records an earlier product direction, not the active application. See `../architecture.md` and the root README for the current system.

## Product boundary

Sustainability Benchmarking Intelligence is a research and benchmarking platform, not a chatbot. Its eventual users are corporate sustainability teams, banks, investors, strategy teams and consultants. Complex evidence processing stays underneath a small, professional interface.

Initial design envelope: 200–300 listed companies, Financial Services / Technology / Energy / Consumer-Retail / Industrials, multiple countries, and one selected reporting cycle at a time. Support 500+ by indexing and resumable processing before adding infrastructure. These are design targets, not current coverage.

## Current system in plain English

There is one local Python application, one PostgreSQL database and one React
website. The Python application has two entry points: commands for the researcher
to collect/process reports, and a FastAPI server for the website to read records.
These are not separate microservices. Ollama is a local extraction helper, not
the database, benchmark calculator or source of truth.

```text
Official company PDFs
        ↓ researcher starts collection/processing commands
Page-aware text → relevant passages → local Ollama candidate extraction
        ↓ deterministic unit conversions and quality checks
PostgreSQL: candidate facts + page references + review history
        ↓ explicit source review, then separate comparability assessment
Deterministic calculations and a versioned publication snapshot
        ↓ FastAPI
React website + evidence-linked PDF and workbook
```

PDF files stay on disk under `data/reports`; PostgreSQL stores their metadata,
checksums, parsed pages and observations. Both must be backed up together.
Browsing the website does not run extraction. Collection and review remain
operator-driven; no automatic yearly refresh or usable human review queue is
implemented. There is no report-upload endpoint or OCR service.

### Verified local coverage — 30 September 2026

- 203 active directory entries: 200 pilot companies and three retained entries.
- Eight downloaded reports across six companies. A retained PDF is not proof
  that it is the right primary report or that its metrics have been reviewed.
- 19 observation records: seven `validated`, eleven `needs_review`, one rejected.
  The seven validated records contain six distinct facts; one is a duplicate.
- All seven source-validated records still have `unchecked` peer compatibility.
  Reviews are attributed to Codex visual source review plus deterministic checks,
  not human sign-off or independent assurance.
- No peer percentiles or composite scores for either 2024 or 2025. The engine
  also deliberately disables composite ranking independently of data coverage.
- The annual preview selects five distinct 2024 facts from two banks and two
  official PDFs. Its collection edition is 2025; it was prepared in September
  2026. These dates must not be conflated.
- Ollama is reachable with the configured installed `qwen3:14b`. Model choice
  remains configuration, not a hard-coded application dependency.

These are a dated audit, not live counters. The five-company data-complete batch
checkpoint has not passed; 20/200-company processing must not be described as
complete or automatically resumed.

## Implementation map

```text
Browser: React + TypeScript + Tailwind
              |
              | company directory, source evidence, benchmarks, research edition
              v
Vite development proxy → FastAPI modular monolith
                         ├── Pydantic settings and API contracts
                         └── SQLAlchemy / psycopg → PostgreSQL
                                                  (metadata, evidence, audit and run tables)

Operator CLI → requests + BeautifulSoup → ranked source manifests
                         └── optional restricted browser for clear JS shells
Operator CLI → verified PDF download → SHA-256 local artifact + PostgreSQL
Operator CLI → verified snapshot → bounded PyMuPDF/pdfplumber worker
                                   └── immutable pages, chunks, table candidates
Operator CLI → persisted batch coordinator → bounded company/parser/model workers
                         └── 5 → 20 → 50 → 100 → 200 data-complete gates
                         └── stage attempts, evidence receipts and CSV/JSON exports
```

The API owns database access; the browser receives no database/model credentials.
Liveness is independent of external services. Readiness checks database
connectivity; neither proves that useful research is available. Company list/detail
endpoints support pagination, sector/country filters and text search. The website
contains a company browser, source drawer, comparison/trend views, globe, Race,
methodology and annual research preview. Several analytical views have no eligible
data yet. Synthetic fixtures belong in tests, not in the published research.

Deterministic acquisition/parsing and a local-only structured model adapter support
the [metric extraction pipeline](extraction.md). Calls use versioned prompts,
closed schemas, verified local-model identities and time/size limits.
`GET /api/system/ollama` reads metadata only. Extraction produces candidates,
not approved comparisons. Explicit source-review commands exist; comprehensive
human review and an end-to-end approved peer cohort are not complete. Benchmark
and prototype scoring code exists, with restrictive evidence gates. The read-only
admin quality page is not a review/approval interface. No SQLite fallback exists.
See [acquisition policy](discovery.md), [parsing contracts](parsing.md) and
[local AI boundary](local-ai.md).

The versioned [canonical metric catalogue](metric-catalogue.md) seeds 43 definitions across nine categories and exposes them through `GET /api/metrics`. Units, aliases, rule declarations and comparison warnings are explicit. Six numeric performance measures are only conditionally score-eligible; the remaining 37 are not eligible. Extraction executes supported unit factors and evidence gates; comprehensive semantic validation, peer compatibility and scoring remain separate. Migration-pinned seeds and immutable definition versions preserve evidence links.

## Batch architecture

A single backend codebase owns API routes, domain rules, persistence and the separately invoked local batch command. The implemented [batch coordinator](batch-processing.md) reuses those modules; it is not a microservice. A database lock permits one coordinator, with bounded company/parser/model workers. Persisted stage attempts, shared domain request slots and extraction-call checkpoints provide retries/resume without a message broker. Larger cohorts require the previous data-complete checkpoint; errors are not treated as success. CSV/JSON exports include failures and evidence, not only successful companies.

Store downloaded documents as immutable, content-addressed local files initially; PostgreSQL stores their metadata and storage keys. Do not keep arbitrary PDF binaries in observation rows. Back up both the database and source documents together. Object storage is a later option only if actual operating requirements justify it.

## Evidence and publication boundaries

1. **The official PDF supports a reported claim.** Its exact page, excerpt,
   original value/unit and file checksum are retained. It does not independently
   prove environmental performance.
2. **PostgreSQL is the research ledger.** It preserves extracted candidates,
   source checks, review attribution and failures. Missing is not zero.
3. **Source validation and comparison approval are different.** A correctly
   copied figure still needs matching definitions, periods, boundaries and units
   before a peer statistic can be calculated. Neither is external assurance.
4. **The annual edition is a publication snapshot.** The current implementation
   serves one explicitly selected preview from `data/editions`. It checks its
   observations against current records and verifies retained PDFs. Changed
   evidence withdraws the preview instead of silently changing published values.
   Artifact hashes bind the PDF/workbook to that snapshot. Publication building
   and sign-off are still manual, not a general annual publishing system.

The current Race has two distinct paths: an absolute Scope 2 chart from the
two-bank preview, and a dormant engine-ranked view. The preview supplies no
rank, percentile, net-zero progress or fair-performance verdict. The engine-ranked
view cannot run while composite ranking is disabled. The globe displays company
domiciles, not operational footprints or measured atmospheric conditions.

See [annual research preview](annual-research-preview.md) for the exact publication
scope. Indicative packages are commercial hypotheses. The proposal form downloads
a local text draft; it sends no email and places no order.

## End-to-end data flow and required controls

1. **Company universe:** curate entity identifiers, sector classification, country and verified official domains. Keep legal-entity identity separate from brand names and ticker changes.
2. **Official website discovery:** validate first-party domains. Use requests and BeautifulSoup; use Playwright only for sources that require JavaScript. Record discovery evidence and respect access rules and rate limits.
3. **Report discovery and download:** identify sustainability / ESG / climate reports, their reporting periods and language. Persist original and final URLs, timestamps, PDF checksum and version. Reject unexpected content, unsafe destinations and oversized files. Deduplicate by content, retain restatements.
4. **PDF parsing:** PyMuPDF native text and geometric tables; gated pdfplumber text-alignment fallback. Preserve one-based physical page positions, embedded labels, raw and ordered text, line boxes and page-local chunk hashes/offsets. Store table candidates separately. No native text means `needs_ocr`, without automatic OCR. Versioned immutable runs retain quality warnings and historical output; parsing success is not data validation.
5. **Candidate retrieval:** retrieve relevant chunks per metric definition with page provenance. A retrieval failure is not evidence that a metric is unreported.
6. **Local AI extraction:** inspect `ollama list` at implementation time and prefer an already-installed Gemma model. Use configurable `OLLAMA_BASE_URL` / `OLLAMA_MODEL`; never silently download a model. Require structured output and citations to supplied chunks. Treat report text as untrusted data, never instructions.
7. **Schema validation:** Pydantic checks types, allowed statuses, required evidence, reporting year and metric identity. Preserve invalid candidates and run errors for diagnosis, without admitting them to benchmarks.
8. **Deterministic normalisation:** explicit, versioned decimal conversion rules produce a separate normalised value/unit. Preserve the raw string and raw unit exactly. Never use an LLM for arithmetic or infer an unknown unit.
9. **Quality rules and review:** check evidence support, target-versus-performance, boundaries, Scope 2 basis, Scope 3 categories, denominators, duplicates and plausibility. Confidence is not approval. Contradictions require review, not automatic averaging.
10. **PostgreSQL:** commit observations and their lineage atomically with validation events. Idempotent processing does not overwrite earlier evidence. Select a reviewed canonical observation from competing versions explicitly.
11. **Benchmarking:** include only validated, compatible achieved-performance observations. Show peer definitions, inclusion/exclusion rules, sample size, missingness and formula versions. Insufficient evidence yields no rank, not a low rank.
12. **Interface and export:** company-to-peer comparison, trends, sector views, disclosure gaps, rank explanations and source drill-through. Exports retain source references, cohort, cycle, filters and calculation versions.

## Sustainability comparison risks and controls

| Risk | Required control |
| --- | --- |
| Absolute emissions versus intensity | Separate metric definitions. Never convert one into the other without a separately validated denominator and explicit derived-metric lineage. |
| Different organisational boundaries | Record operational/financial control versus equity-share basis, included entities and coverage. Unknown or mismatched boundaries are excluded from that comparison. |
| Scope 2 market/location basis | Distinct metric variants and comparison groups; do not pool them. |
| Scope 3 and financed emissions | Preserve categories, coverage and methods. Financial Services needs sector-specific definitions; a financed-emissions inventory is not an operational-emissions inventory. |
| Fiscal periods and publication dates | Compare reporting periods, not publication years. Record period length and deviations from the selected cycle. |
| Targets presented as results | Store targets separately, with baseline year/value, target year and scope. Targets never populate achieved-performance observations. |
| Units, magnitude and currencies | Preserve raw unit text; use decimal arithmetic and versioned conversions. Unknown units or denominators block comparison. Currency-adjusted intensity requires explicit currency/date/basis, not just a currency symbol. |
| Restatements, acquisitions and divestments | Keep document and observation versions. Prefer reviewed comparable historical restatements without deleting previous evidence. Flag structural breaks. |
| Missing or weak disclosures | Never fill with zero. Show not-reported, not-comparable and needs-review separately. Non-disclosure requires a documented review of relevant sources. |
| Extraction hallucination / table misalignment | Require source page and exact excerpt; review year/column/header alignment. Low confidence or conflicting evidence blocks admission. |
| Coverage mistaken for performance | Separate disclosure completeness, data quality and operational performance. Publishing more metrics does not automatically imply better sustainability. |
| Sector and size effects | Sector-specific metric sets and peer definitions. Document whether directionality is meaningful; avoid universal composite ESG scores. |
| Small samples, outliers and ranking volatility | Minimum cohort sizes, explicit exclusions, robust statistics and uncertainty. A detected outlier is a review flag, not proof of error. |
| One cycle versus improvement claims | Trends require at least two compatible periods. Historical comparatives inside a report are separate year-specific observations. No deterioration/improvement claim from one time point. |

## Implementation stages and exit criteria

1. **Foundation — completed.** Frontend/backend scaffolds, environment and PostgreSQL configuration, health endpoints, tests, type checks, README and architecture.
2. **Company universe and database — implemented.** Initial ten SQLAlchemy tables and Alembic migration, metadata-only 20-company CSV, atomic UUID-keyed importer and company query API. Real PostgreSQL tests cover migration reversal, source alignment, idempotency, 500-company imports and API queries. Later stages add four acquisition/parsing tables and the canonical catalogue. No real-company sustainability observations are seeded.
3. **Official-source acquisition — implemented.** Curated domain policy, robots-aware bounded requests/BeautifulSoup crawler, explainable candidate ranking, retained alternatives, acquisition history, immutable checksum-deduplicated downloads and read-only quality UI. Mocked HTTP and real PostgreSQL tests cover acquisition. Five official sites received a recorded live smoke run; no broader coverage is inferred.
4. **Page-aware parsing — implemented.** Verified PDF snapshots, versioned subprocess parsing, immutable page/chunk/table evidence, exact offsets/hashes, no cross-page chunks, explicit quality flags and CLI status. Synthetic layout/scan/malformed fixtures and real PostgreSQL tests pass. Three official downloaded reports from two companies were parsed and sampled visually; candidate table counts are not accuracy scores.
5. **Extraction and review — bounded extraction implemented; human review deferred.** The local adapter and 43-definition catalogue now support lexical retrieval, one-chunk prompts, strict candidate schemas, exact Decimal conversions, evidence/quality gates, conflict retention and heuristic confidence. Candidate prompts/responses and rejected/absent cases remain in run audits; accepted source-backed candidates become unvalidated observations with validation events. Three-report local verification is a smoke run, not an accuracy evaluation. Automatic target ingestion, exhaustive semantic validation, a labelled evaluation set and review queue remain deferred. No approval solely from model confidence.
6. **Benchmarking and exports — implemented in code, not research-complete.** Deterministic cohort rules, minimum sample sizes, statistics, explanations and prototype components exist. Composite ranks are disabled. The annual preview and source-linked PDF/workbook exist, but there is no approved peer cohort or decision-ready sector study. Scale only after measured source coverage, extraction accuracy and review throughput.

Human review/comprehensive evaluation and a useful completed peer study remain
the bottlenecks. Passing software tests does not establish research validity or
customer value. No auth, billing, CRM, Kubernetes, microservices, chatbot UI,
paid AI API or unnecessary cloud infrastructure is planned here.

## Simplification proposed by the review (not yet a navigation change)

Keep two clear responsibilities: the internal research workbench creates reviewed
evidence; the customer-facing annual report explains what that evidence means.
Prioritise a report, a focused company/peer comparison and their sources. Keep
the Race as an optional chart treatment, not a second scoring system. Hide
unready rankings/trends and put diagnostic controls outside the customer journey.
Retain provenance, review gates and audit history even when their UI is simplified.

## Operational boundaries

- Development services bind to loopback. Do not expose this unauthenticated research foundation to a public network.
- Version the metric dictionary, extraction schema, prompts, normalisation rules and benchmark formulas.
- Logs should identify runs and document hashes, not disclose credentials or dump entire reports.
- Connection pool limits apply per process. Choose worker counts from measured database and local model capacity; the number of companies is not a reason to multiply services.
- PostgreSQL migrations, constraints, company imports, evidence controls and calculation behavior are tested. Smoke runs and synthetic tests do not establish large-universe extraction accuracy or real-world peer-comparison validity; those still need a reviewed evaluation set.
