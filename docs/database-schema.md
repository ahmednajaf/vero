# PostgreSQL schema — revision d40e179a21c6

Benchmark revision `d40e179a21c6` adds reviewed `metric_observations.comparison_context` JSONB (default `{}`, no guessed backfill), `benchmark_snapshots`, and `benchmark_components`. Snapshots have unique input SHA-256, reporting year, methodology version, parameters and result/provenance JSONB; indexed by year/creation time. Components have UUID foreign keys to snapshot/company, a unique `(snapshot_id, company_id, component)` key, score `[0,100]` or null, weight `[0,1]`, reason, formula and evidence JSONB, with a company/snapshot index. Both tables have UUID identities and timezone-aware timestamps and are append-only via database triggers. New validation events use `clock_timestamp()` to follow in-transaction last-edit triggers. Downgrade refuses existing benchmark history. See [methodology](benchmarking.md). There are now twenty tables; the earlier schema export described below predates this migration.

Implemented in `backend/app/db/models.py` and six Alembic revisions: `0001`, acquisition `f0b2edabe086`, parsing `53487b8db383`, catalogue `840b86a2302e`, batch processing `6ccc1d6cca42`, and benchmarking `d40e179a21c6`. [schema.sql](schema.sql) remains the historical PostgreSQL DDL/catalogue export through the first five migrations (eighteen tables); the sixth migration defines the current additions. Migrations define explicit tables/constraints, never import live models or invoke create_all. Empty-schema upgrade/downgrade and model consistency are tested on PostgreSQL 17. Evidence-bearing or otherwise lossy downgrades are refused; use backups instead.

Company metadata and 43 canonical metric definitions are seeded, never company sustainability values. Explicit acquisition and parsing commands populate reports/pages/chunks. The later `extract-metrics` command now writes real source-backed observations and validation events after local-model/evidence checks; none is automatically validated. Candidate prompts/responses/rejections remain in extraction-run JSONB. Targets/themes remain unpopulated by this pipeline. Routine tests use only fictional company data. See [metric catalogue](metric-catalogue.md) and [extraction contracts](extraction.md).

## Relationships

The batch layer adds `pipeline_runs` (frozen cohort/configuration, profile hash, checkpoint, predecessor, status/summary/timestamps), `pipeline_jobs` (unique run/company/stage/metric, state, lifetime attempts, retryability, reasons and downstream evidence links), append-only `pipeline_events` (job FK, attempt, status, reason/details/time), and `pipeline_domains` (domain PK, next permissible request time). Jobs reference company/run via restrictive FKs; parent runs link checkpoints. Run/profile/checkpoint/time, job/run/state and event/job/time indexes support resume and audit. States/stages/attempt bounds have checks; run/job updated_at uses the shared database trigger. An immutable-event trigger rejects UPDATE/DELETE. Downgrade refuses any existing batch run. Full [resume and checkpoint contracts](batch-processing.md).

```text
companies ──< report_discovery_runs ──< reports >── report_artifacts (unique SHA-256)
companies ───────────────────────────< reports ──< extraction_runs
                  └────< document_pages >── extraction_runs (parse run)
                              ├──< document_chunks
                              └──< document_tables

companies + reports + document_chunks + extraction_runs
    ├──< metric_observations >── metric_definitions
    ├──< targets             >── metric_definitions
    └──< company_themes      >── themes

metric_observations / targets / company_themes ──< validation_events
```

Composite foreign keys require each evidence record's company to match its report and each chunk/run to belong to that report. A database trigger also requires its cited source page to lie within the linked chunk's physical page range.

## Conventions

- UUID primary keys. The importer requires explicit stable company IDs; seeded metric definitions use deterministic UUID5 identifiers derived from canonical code/version. Other ORM records default to UUID4.
- All tables have timezone-aware created_at. Mutable tables have updated_at, maintained by PostgreSQL triggers for ORM/direct SQL updates. Validation events only have created_at.
- Restrictive/no-action foreign keys prevent cascade deletion of evidence. Self-references preserve report/observation supersession, theme parents and run lineage.
- Financial metadata: numeric(30,6). Normalised observations/targets: numeric(38,12). Confidence: numeric(5,4). Raw values/units remain separate text fields.
- Physical PDF pages are one-based; printed labels are separate. Reporting year/period is distinct from publication date.
- JSONB retains category sets, definition dimensions and run parameters; query keys, values, states and lineage are named columns.
- Company financial metadata describes the selected universe/cycle, not a time series. Report observations retain their own reporting year independently of company updates.

## companies

| Columns | Types / rules |
| --- | --- |
| id | UUID PK, stable import/update key. |
| company_name, ticker, exchange | varchar(240/32/32), required/non-blank. Ticker preserves leading zeros. |
| country, region | varchar(2/80), required; country uppercase ISO alpha-2, assigned codes checked by importer. |
| index | varchar(160), nullable, administrative label rather than historical membership. |
| sector, industry | varchar(80/160), required; five allowed sectors enforced by DB. |
| official_domain | varchar(253), required; hostname syntax checked by importer. |
| investor_relations_url, sustainability_url | nullable text; HTTP(S) syntax checked by importer. |
| reporting_currency | nullable varchar(3); required with monetary values, assigned ISO code checked by importer. |
| revenue, market_cap | nullable numeric(30,6), non-negative/finite, never missing-as-zero. |
| revenue_year | nullable integer 1900–2100; required with revenue. |
| reporting_year | required integer 2000–2100. |
| active | boolean; CSV must explicitly supply true/false. |
| source_file, source_row, source_sha256, imported_at | Latest changed-row CSV lineage: text/integer/varchar(64)/timestamptz. |
| created_at, updated_at | Database-maintained timestamptz. |

Unique index: lower(exchange), lower(ticker). Other indexes: lower(company_name) plus UUID; sector/country; reporting_year/active. Substring scans are appropriate for 200–500 rows; no search service/extension is needed. Names/domains are not unique because distinct entities may share them. Multi-listing entities are deferred.

## Evidence and taxonomy tables

| Table | Main fields | Keys, indexes and checks |
| --- | --- | --- |
| reports | Company, title/type, nullable verified reporting year/period, requested/detected year, source/final/discovery URLs, discovery run, retrieval time, artifact/storage/hash, MIME, size/pages, selection confidence/reason/status, is_selected, source_policy, version/predecessor, download/parse status, notes. | Company and artifact FKs; composite run/company/year FK; unique run/URL-hash and id/company; partial unique index allows one selection per run. Company/year/type, company/checksum, requested-year/status/selection and artifact indexes. Five acquisition statuses, confidence 0–1, year ranges, checksum, size/page, period and self-supersession checks. Company/checksum is no longer unique: multiple source manifests may share a blob. |
| report_discovery_runs | Company, requested year, status/reason, policy version, seed URLs and diagnostics JSONB, HTML page/request counters, completion time and identity timestamps. | Company FK, unique id/company/year for provenance FK, company/year/time index, year and acquisition-status checks. A no-report outcome has a real run with zero candidates, not a fabricated URL. |
| report_artifacts | SHA-256, relative canonical storage key, actual byte count, MIME and identity timestamps. | Globally unique checksum and storage key; valid hex checksum, positive byte count. One physical file may serve several company/year/source manifests. |
| extraction_runs | Report, stage/status, parent run, idempotency key/input hash, optional model metadata, prompt/schema/code versions, parameters, timestamps/errors/output summary. | Report/parent FKs; unique idempotency key and id/report; report/stage/status index; allowed stage/status checks. Parsing runs now retain source URL/artifact, library versions/options, quality counts and page warnings. No model metadata is fabricated. |
| document_pages | Report/parse run, physical page number, embedded page label, dimensions/rotation, raw text/hash, ordered text/hash, character count, status, headings/layout/warnings JSONB, parser/version, identity timestamps. | Composite run/report FK; unique report/run/page and id/report/run/page; report/page and run/status indexes. Positive pages/dimensions, text-count/hash/status checks. INSERT trigger verifies hashes and parsing-stage run. UPDATE/DELETE rejected. |
| document_chunks | Report/parse run/page, chunk index, physical pages, printed label, section, exact ordered-text slice/hash, parser/version, character offsets and source line spans. | Existing run/report FK plus composite page/report/run/physical-page FK; unique report/run/chunk; report/page, run and page-ID indexes. New page-linked chunks must have equal start/end pages and valid offsets; trigger verifies exact substring/hash and rejects UPDATE/DELETE. Legacy nullable page fields remain supported. |
| document_tables | Report/run/page/physical number, page-local table index, row/column counts, string/null cells, table/cell boxes, header/extraction metadata, canonical cell-JSON hash, method/version, validation state, identity timestamps. | Composite page/report/run/number FK; unique page/index; report/page and run indexes. Shape/index/hash checks; validation state constrained to needs_review. UPDATE/DELETE rejected. No numeric interpretation or metric conversion. |
| metric_definitions | Code/definition/catalogue versions, name/description, category/evidence kind, sector applicability, quantity kind, nullable canonical unit, allowed units/aliases JSONB, value type, directionality, scope, comparison dimensions, normalisation rule/validation constraints JSONB and their versions, comparability warning, score eligibility, active. | Unique code/definition version; catalogue/category/code index. Complete metadata required for canonical records; conditional scoring requires numeric achieved-performance semantics and comparison dimensions. Seeded definitions are immutable except activation/timestamps. Legacy definitions retain null catalogue metadata and are excluded from the canonical API. |
| metric_observations | Shared evidence below; metric/idempotency key; period; raw and normalised values/units; qualifier/conversion version; boundary/consolidation/scope; Scope 2 basis/Scope 3 categories; denominator/unit/currency/basis; coverage/methodology; historical/restatement flags/predecessor; compatibility state/rule/key. | Metric/predecessor FKs; unique idempotency key; company/year/metric/state and metric/year/group indexes. Normalised values require raw value/unit, normalised unit and conversion version. not_reported cannot contain raw/normalised values. |
| targets | Shared evidence; metric, target type/year, baseline year/raw/normalised values/units, target raw/normalised values/units, conversion version, reduction percentage, boundary/scope/coverage. | Separate from achieved performance. Company/year/metric and metric indexes. Baseline <= target year; reduction 0–100; normalised values require raw value/unit and conversion provenance. |
| themes | Code/taxonomy version, name/description, parent theme, active. | Unique code/version; indexed parent FK. Disclosure topics are not performance metrics. |
| company_themes | Shared evidence; theme FK. | Unique company/theme/year/chunk; theme/year index. Multiple chunks can support one theme. |
| validation_events | Exactly one observation/target/company-theme FK; prior/new state; rule/version; actor type/reference; reason/details; created_at. | Subject/time indexes; exactly-one-subject, state and actor constraints. Trigger rejects UPDATE/DELETE, preserving history through normal DML. |

### Shared evidence

Columns: company_id, report_id, document_chunk_id, optional extraction_run_id (manual evidence may have no model run), reporting_year, source_url, source_physical_page, optional source_printed_page_label, supporting_excerpt, extraction_method, confidence, confidence_notes, validation_state, notes.

Company/report/chunk, URL, page, excerpt and method are required. URL/excerpt/method must be non-blank. Confidence must be 0–1 or explicitly unknown with non-blank notes. Composite FKs and page-range triggers apply to observations, targets and company themes.

### States

Allowed: extracted, validated, needs_review, not_reported, not_comparable, rejected. Default is extracted, never validated. Missing is NULL, not zero. Raw value/unit and normalised value/unit are independent fields. Targets remain separate from observations.

not_reported must eventually reflect documented source review, not a missing report or failed parser. The DB enforces null values and required evidence but cannot judge review quality. Confidence does not mean approval; validated transcription does not imply cohort comparability.

## Guarantees versus deferred work

Enforced now: table relationships, source alignment, page-range checks on evidence writes, status vocabulary, null/normalisation-provenance checks, CSV validation, uniqueness, timestamps, transactional imports, immutable validation history and immutable new parsed evidence. New chunk identity, exact page-text slicing and hashes are checked in PostgreSQL as well as application code. Page/chunk/table output and final run quality commit atomically. Catalogue contracts validate types, units, exact conversion-factor declarations, comparison metadata and conservative eligibility; PostgreSQL protects definition identity and versions. Full contracts and limitations are in [parsing.md](parsing.md) and [metric-catalogue.md](metric-catalogue.md).

Extraction now applies bounded lexical retrieval, strict model output validation, literal excerpt/value/page/year gates, exact Decimal unit factors, confidence heuristics and conflict flags. Missing retrieval is not report-level absence. Original reporting-period strings and excerpt offsets are retained in observation notes; full candidate audit/model metadata remains in extraction runs. No new table or schema migration was required.

Deterministic `recheck-extractions` may reject an unapproved older Scope 1/2 observation when a broad quote attached the value to the wrong row. Original raw evidence remains; the withdrawn conversion and prior confidence are recorded in an immutable validation event. Current observation states can therefore differ from the original extraction-run summary, which is retained as historical evidence.

Deferred: full semantic validation; target ingestion; peer compatibility; canonical restatement selection; human approval transitions; multipage evidence joins; benchmark/export lineage. Literal source matches do not prove table-column alignment or correct reporting boundaries. Legacy evidence remains unchanged. Parsing downgrade refuses when parsed pages exist; catalogue downgrade refuses referenced definitions, new/custom definitions or changed activation state. Privileged administrators can alter tables/triggers or truncate data; append-preserving services do not replace later database-role controls and backups.

Inference and observation writes are operator CLI actions, not a public evidence-writing API. No scoring pipeline exists. See the recorded live extraction results for actual coverage; a populated schema does not imply validated sustainability data.
