# Resumable local batch processing

`run-pipeline` coordinates existing discovery, download, page-aware parsing, retrieval and local extraction services. No queue server, microservice, scheduler, external AI provider or frontend change is required. PostgreSQL persists a frozen cohort, stage states, attempt history, downstream evidence links and checkpoint results. The report and observation tables remain the source of truth for evidence.

## Strict progression

The checkpoints are **5 → 20 → 50 → 100 → 200**. Requesting twenty first creates/runs five. Twenty is created only after the matching five-company checkpoint passes; the same rule applies to later sizes. This implementation exercise stops at twenty at the latest. It does not treat terminal errors as success.

A checkpoint passes only when its full company count is present and **every** company has:

1. A selected official report, downloaded and checksum-verified.
2. A completed parse with extracted text. Parser review warnings remain visible. `needs_ocr` blocks completion unless every affected page has an explicit decorative/no-metric visual review bound to that exact PDF checksum and parse run. Absent text, failed pages and unresolved scan pages still block completion. No automatic OCR occurs.
3. All requested metric jobs completed, including their validation/normalisation/storage receipts.
4. At least one source-backed, non-rejected metric observation for the requested metric year.

Missing individual metrics remain visible in coverage; this gate does not claim 100% disclosure coverage. Review observations satisfy the extraction requirement but are **not validated or benchmark-ready**. Targets alone cannot pass the performance-observation gate. `validated` means the observation's approved validation state, not passing Pydantic. No automatic human approval was added.

Fail-fast is on by default: once a stage fails, no new queued network/model work starts; calls already in flight drain safely. Remaining jobs are explicitly blocked. Setting `PIPELINE_FAIL_FAST=false` permits finishing the current checkpoint's diagnostics only; it **never** changes the data-complete expansion gate. A failed five-company checkpoint cannot be reclassified as a successful twenty-company run.

Companies are sorted by stable UUID, not selected by site accessibility. Sector/country/company filters apply before the cohort is frozen. Company IDs, names, domains and seed URLs are snapshotted. An explicit filtered selection smaller than five may run for diagnosis but cannot pass the five-company scale checkpoint. Other undersized selections fail before work starts. Inactive or unmatched explicit company IDs are rejected.

## Commands

From `backend/`, configure PostgreSQL and the approved installed local Ollama model, then:

```bash
source .venv/bin/activate
python -m alembic upgrade head
ollama list

# The requested command: starts at five, then conditionally expands to twenty.
python -m app.cli run-pipeline --year 2025 --limit 20

# Explicitly distinguish 2025 publication from 2024 performance data.
LLM_TIMEOUT_SECONDS=300 LLM_MAX_OUTPUT_TOKENS=2048 \
  python -m app.cli run-pipeline --year 2025 --observation-year 2024 --limit 20

# Use the SAME settings and filters when resuming the preceding example.
LLM_TIMEOUT_SECONDS=300 LLM_MAX_OUTPUT_TOKENS=2048 \
  python -m app.cli run-pipeline --year 2025 --observation-year 2024 --limit 20 --resume

python -m app.cli run-pipeline --year 2025 --limit 5 --sector Technology --country US
python -m app.cli run-pipeline --year 2025 --company COMPANY_UUID
python -m app.cli pipeline-status --run PIPELINE_RUN_UUID
```

`--company` and `--metric` are repeatable. `--resume --run UUID` additionally requires that exact run to match the selected cohort/configuration. A repeated matching command resumes automatically, never creates duplicate work; `--resume` requires an existing matching batch. Changing years, filters, source URLs, metric set, model/digest, component versions or processing settings starts a different profile at five. No implicit model substitution occurs.

`--year` selects the report/publication cycle. `--observation-year` defaults to that same year; it is **not** automatically shifted back a year or inferred from a filename. If this produces no supported values, the checkpoint fails honestly. Fiscal/calendar boundaries still require review.

Exit codes: 0 for a passed requested checkpoint (or read-only status export); 1 for data-incomplete checkpoint; 2 for configuration/preflight/coordinator errors; 130 for interruption. No twenty-company success is claimed merely because the command requested `--limit 20`.

## Metric coverage

The default batch profile requests seven definitions, covering the six requested groups:

| Group | Canonical definitions |
| --- | --- |
| Scope 1 | `scope_1_emissions` |
| Scope 2 | `scope_2_location_based`, `scope_2_market_based` — separately counted, never combined |
| Scope 3 | `scope_3_emissions` |
| Renewable energy | `renewable_energy_percent` — not renewable electricity |
| Net-zero target | `net_zero_target_year` — separate target-candidate evidence, never achieved performance |
| Assurance | `assurance_status` — raw qualitative review evidence, not a numeric performance score |

`--metric` can define a different explicit profile; a narrow five-company metric profile cannot authorise expansion for a broader one. `--top-k` defaults to **1** for this bounded first batch, permits 1–6 existing page-local chunks, and is fingerprinted. This is lexical retrieval, not an exhaustive report review. No whole PDF is sent to the model.

Coverage uses **all companies in the checkpoint** as its denominator, including failures and unprocessed companies. Each definition reports companies with candidate passages, source-backed observations, approved observations, review observations, and separately grounded review-only target candidates. Failed retrieval is not a factual `not_reported` finding; missing sustainability values stay null, never zero.

## Persistence and resume

Migration `6ccc1d6cca42` adds four tables:

| Table | Purpose |
| --- | --- |
| `pipeline_runs` | UUID, checkpoint, requested/observation years, profile hash, frozen cohort/configuration, parent checkpoint, state, timestamps and summary. |
| `pipeline_jobs` | Unique run/company/stage/metric, status, lifetime attempt count, retryability, failure code, result/evidence references and timestamps. |
| `pipeline_events` | Append-only attempt/state history, reason and structured details. PostgreSQL rejects ordinary UPDATE/DELETE. |
| `pipeline_domains` | Approved parent domain and next permissible request time, shared across workers/restarts. |

Stages are `discover`, `download`, `parse`, `retrieve`, `extract`, `validate`, `normalise`, `store`. States are pending, running, succeeded, needs_review, unavailable, failed and blocked. Extraction already validates, normalises and writes evidence atomically; the final three stage records are explicit **receipts for that atomic group**, not separate model calls or human-validation claims. If a process stops after the atomic commit, resume retrieves the original extraction result and completes the missing receipts.

A dedicated PostgreSQL session-level coordinator lock prevents two batch processes running concurrently. This keeps configured company/parser/model limits meaningful across commands. The existing parser/report and extraction/report/metric locks continue to protect those services. Abrupt process loss releases the coordinator lock; the next owner records formerly running jobs as interrupted and resumes incomplete work. Successful jobs are reused. Completed five-company jobs are inherited into twenty with explicit source-job links.

Model responses from earlier attempts are reusable only when the exact chunk hash, prompt, model name/digest, instruction version and closed output schema match, and the output fits the current limit. Current deterministic quality and normalisation rules are reapplied, including when those rules change. Their JSON is validated again; the new attempt records `reused_from_run_id`. Failed/cancelled calls are retried, completed matching calls are not repeated. Earlier observations/attempts remain as history, not arbitrarily chosen canonical winners. Artifact bytes are rehashed before a completed batch can authorise expansion.

The original development cohort has a fixed-ID wrapper: `bash scripts/run-report-checkpoint.sh` from the project root. It requests twenty but cannot pass the five-company gate without complete data. It does not select a different first five after the 200-company directory is imported. See `docs/report-backed-checkpoint-2026-09-30.md` for the official-source registration and source-fact review workflow.

Unknown/unexpected exceptions retain a safe type/code and stop the batch; no credential-bearing exception text is printed. The frozen model is selected from local configuration and must be available. A missing model or unreachable Ollama preflight stops before company work.

## Bounded retries and throttling

- Company workers: default 2, maximum 4. Parser subprocesses: default 1, maximum 2. Local model requests: default 1, maximum 2. These limits are distinct; no unbounded task fan-out reaches a provider.
- Each invocation makes at most one new attempt per incomplete stage. Existing HTTP/adapter transport retries remain bounded and selective. Transient failed stages may be attempted on resume, with 1/2/4-second backoff and a lifetime default cap of 3 attempts (configurable 1–5).
- Malformed schema, unknown model, bad MIME, checksum failures, login/CAPTCHA/403/429 and robots policy controls are not automatically retried or bypassed. A permanent source failure requires operator correction/review, not an infinite resume loop.
- A database-reserved time slot paces every batch HTTP request, including robots, redirects and browser-fallback resources. Approved parent domains and their subdomains share the slot. The configured minimum and site crawl-delay rules are preserved. Robots delays above the existing 60-second bound are deferred.
- No JS fallback is newly enabled. Existing explicit `DISCOVERY_ALLOW_JS` policy still applies, and every browser request uses the same safe transport. No site metadata or official-domain allowlist is silently broadened.

Version `resumable-batch-v1.1` also refuses to automatically use sustainable/green/social bond allocation or impact reports as the primary company-wide source. These receive `specialised_financing_disclosure` and require source review. The historical live run that exposed this issue remains unchanged; profile versions are not retroactively rewritten.

## Logs, summaries and exports

Operational stdout uses JSON events with UTC timestamps, run/job/company IDs, stage/metric, attempt, status and reason codes. Prompts, report excerpts and credentials are not operational log fields. The database event table and full exports preserve detailed diagnostics independently of terminal output.

Every completed or interrupted run exports versioned **JSON and CSV** under `backend/storage/pipeline/RUN_UUID/` (or `PIPELINE_ROOT`). Both formats are written to temporary files, flushed and published without overwriting prior snapshots. `pipeline-status` exports saved state without running discovery or inference.

The summary reports companies total, reports discovered, downloaded, parsed, extracted, validated, needs review and failed. These are company counts (one selected report per company); observation-state and stage-state counts are separately named. “Failed” includes all companies not satisfying the strict gate, not just transport exceptions. Existing historical downloads outside this run are not counted until linked through its jobs.

JSON includes the frozen selection, all jobs/events, complete extraction-run audits, source-backed observations and withheld/target candidates. CSV includes observation/candidate rows **plus a coverage row for every requested company/metric**, so missing companies and failures cannot disappear. Provenance includes company/year, raw and normalised values/units, source URL/document/hash/page/chunk, exact supporting excerpt, extraction/run/model identity, validation state, confidence and notes. Records with no report have no fabricated page or excerpt. A rejected model quote is separately labelled rather than presented as verified evidence. CSV formula prefixes are escaped for spreadsheet safety; JSON preserves exact source strings.

## Verification and limits

Mocked tests cover 5 → 20 success with no repeated five-company work, failed-five blocking twenty, no 50-company start after twenty, restart recovery, partial-model-call reuse, strict no-values failure, permanent versus transient retries, lifetime retry limits, worker bounds, global locks, shared-domain pacing, CSV safety, missing-company export, artifact tampering and migration history protection. Routine tests need PostgreSQL but no live company sites or installed model.

Final regression: **290 backend tests passed, one optional live acquisition test skipped**, including 27 batch tests. Python typing passed for 55 application files; scoped lint, formatting and migration consistency passed. The unchanged frontend passed 12 tests, TypeScript checking and its production build. Upstream Starlette/httpx and PyMuPDF deprecation warnings remain non-failing.

The [live five-company attempt](batch-live-2026-09-29.md) failed the strict checkpoint; twenty was not run. Passing fixture tests is **not** proof of twenty live companies. Review/target ingestion semantics are unchanged from the extraction stage; no scoring, benchmark admission, dashboard update or deployment is included.
