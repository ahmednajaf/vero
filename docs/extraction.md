# Local metric extraction

This document covers the extraction stage. The later [batch coordinator](batch-processing.md) adds its own four-table migration and resumable orchestration; the underlying extraction evidence schema remains unchanged.

The operator-initiated pipeline is lexical retrieval → one page-local passage per model call → strict Pydantic candidate validation → literal evidence gates → Decimal unit conversion → conflict/quality rules → observations and validation events. It uses the existing provider-neutral adapter and loopback-only Ollama transport. No paid API, embeddings, report acquisition, OCR, scheduler, scoring engine or frontend change is introduced.

## Commands

From `backend/`, with PostgreSQL configured and migrations applied:

```bash
source .venv/bin/activate
ollama list
# Set OLLAMA_MODEL to an approved installed model in .env; no automatic pull.
python -m app.cli retrieve-metrics --year 2024 --report REPORT_UUID --metric scope_1_emissions --top-k 3
LLM_MAX_OUTPUT_TOKENS=2048 python -m app.cli extract-metrics --year 2024 --report REPORT_UUID --metric scope_1_emissions --top-k 3 --output storage/extraction/run.json
python -m app.cli extraction-status --run EXTRACTION_RUN_UUID --output storage/extraction/provenance.json
python -m app.cli recheck-extractions --run EXTRACTION_RUN_UUID
```

`--year` is the **observation year**, not publication/discovery year. Reports published in 2025 often describe 2024 performance. Both `--report` and `--metric` are repeatable. Without metric filters, all 43 active v1 catalogue definitions are attempted; without report filters, up to `--limit` downloaded reports are selected (default 20). The API does not trigger inference. Output paths are exclusive-create, never overwrite; CLI failure returns nonzero. A successful run means calls completed, not that evidence is complete or validated.

The current approved installed model is `qwen3:14b`, selected through environment configuration, never in extraction code. The adapter verifies the local model identity/digest before a run and verifies it again on every response. No report data is sent to remote providers. A local server and available model are required for live extraction, not for tests. The existing connection/total timeout, sensible retry policy, structured JSON enforcement, output limits and rejection of remote models/redirects continue to apply.

## Retrieval and prompt limits

- Catalogue aliases/name, small lexical variants, token coverage, nearby keywords, section terms, year presence and numeric table structure contribute to a deterministic score. Navigation/index and target-oriented prose are penalised for achieved-performance requests. Tie-breaking uses physical page and chunk UUID.
- `--top-k` defaults to 3 and is bounded to 1–6. Each call receives exactly **one existing chunk**, maximum 4,200 characters. Oversized chunks are excluded and counted, not silently truncated. The parser's default chunks are 2,400 characters.
- Only the latest successful current-checksum parse is eligible; a failed/latest incompatible parse blocks use. Legacy cross-page chunks must be reparsed. All chunk hashes are verified before retrieval. No whole-PDF prompt, cross-page concatenation or automatic table-content reinterpretation occurs.
- Every ranked passage retains its chunk/hash/page, score, matched terms and complete versioned prompt. Model text is untrusted data, never instructions.
- Zero candidates means `no_candidates_needs_review`. Top-k retrieval is not an exhaustive report review. Neither missing retrieval nor model `not_reported` proves company-level absence.

## Candidate contract and evidence gates

The model returns `{ "candidates": [...] }` with 1–6 objects. Each object contains exactly metric_id, reported_value, reported_unit, reporting_period, boundary, page_number, supporting_excerpt, confidence, notes and status. Values/units/period/boundary are nullable **verbatim strings**; this preserves separators, precision, magnitude and uncertainty. Model status is extracted, not_reported, ambiguous or needs_review. Unexpected fields/types, invalid JSON, non-finite confidence and oversized output fail explicitly.

Multiple explicit values in one passage are retained separately. No arithmetic, missing-as-zero, guessed boundary, Scope 3 inference, partial-category sum or intensity-to-absolute conversion is requested. Target catalogue entries are extracted into the run audit for separate target-specific review; they are **never written as achieved-performance observations**. Qualitative definitions retain raw evidence as review candidates without an invented numeric scale. This is not yet an automatic target ingestion or qualitative semantic-validation engine.

Checks require the requested metric, physical page, a contiguous supporting excerpt found in the exact supplied chunk, literal value support, and an explicitly supported requested year. Whitespace-only quote differences are permitted; the database stores the original substring plus chunk/page offsets. Wrong IDs/pages, fabricated quotations/values, unsubstantiated years, target contexts, wrong Scope 2 methods and intensity-as-absolute claims remain in the run audit but cannot become observations.

Prompt 1.1 explicitly requests the overall reporting-entity row rather than gender, region or division subsets. Quality v3 checks the row label preceding each occurrence of a proposed Scope 1/2 value, so quoting an entire emissions table does not justify using its combined total as Scope 2. A narrow electricity exception permits a row labelled only “Electricity” when the supplied parent section explicitly concerns energy consumption; it adds `metric_context_parent_section` and requires review. Generation context is excluded. These are tested lexical safeguards, not a general table interpreter.

A year header outside the model quote is permitted only when present in the supplied chunk, with an explicit `year_context_outside_excerpt` review flag and its chunk offsets. All multi-year passages require column-alignment review. Boundary wording must occur in the chunk; unknown/unsupported boundaries are not guessed. Unknown/incompatible units, qualitative meaning and missing comparison context are review issues. The narrow checks are safeguards, **not proof that a table row, subsidiary boundary or reporting standard was interpreted correctly**.

## Deterministic normalisation

Raw strings are always retained. Finite Decimal arithmetic applies explicit catalogue factors and a versioned, small spelling map:

| Input | Canonical tCO2e factor |
| --- | ---: |
| kg CO2e | 0.001 |
| tCO2e | 1 |
| kt CO2e | 1,000 |
| Mt CO2e | 1,000,000 |

Explicit `1,000 tonnes CO₂e` is recognised as ktCO2e; magnitude case matters. CO2-only, ambiguous tons, unknown units, approximate/range values and ambiguous numeric separators are not guessed. Numeric(38,12) overflow or precision loss blocks conversion instead of rounding silently. Other unambiguous scale factors already declared in the catalogue (energy, volume, mass, headcount and injury-rate units) are supported.

Percentage shares must be 0–100; an **explicit** fraction unit scales by 100 and is then range-checked. `0.5%` stays 0.5%, never becomes 50%. Year-on-year signed change retains the catalogue's distinct bounds; no relative change is calculated from unrelated numbers.

Intensity without a concrete denominator is `not_comparable`, with no normalised value. With an explicit denominator, only the numerator's CO2e mass is rescaled; denominator meaning/scale/currency and reporting boundaries still require comparison review. No FX, revenue inference or absolute-emissions derivation occurs.

## Conflicts and confidence

Within each report/metric/year attempt, differing candidate values are all retained and marked `needs_review`; there is no arbitrary winner, average or benchmark selection. Equal Decimal values in equivalent units are not false conflicts. Corroboration adds weight only for a different physical page with matching boundary wording; duplicate responses on the same page do not increase it. Different boundaries may explain disagreements, but still require review before selection. Restatement/conflict resolution across separate reports/attempts remains a review task; no historical attempt is silently preferred.

Stored confidence is an explicit **heuristic, not a probability**: relevance up to .25; page/quote consistency .15; year support .20; unit clarity .15; literal value support .15; corroboration .10. Any quality flag caps it at .60; unpersistable evidence at .25. Model self-confidence is retained separately and does not approve evidence. Every new observation is extracted, needs_review or not_comparable—never automatically validated. Compatibility remains unchecked or not_comparable, and no comparison group/rank is assigned.

## Persistence and recovery

No schema migration is needed: existing `extraction_runs`, `metric_observations` and `validation_events` already provide the required storage. Each report/metric/year has a run linked to its parse run, source checksum, canonical definition version, local model/digest and prompt/schema/code versions.

Run JSONB retains all attempted prompts, candidate responses, raw valid JSON, adapter metadata/timings, rejection/error codes, assessment flags, source offsets and observation IDs. Malformed/schema-invalid model output is rejected by the adapter and retains a safe failure code rather than being repaired. Missing candidates and ungrounded model responses are audited without inventing a page-backed observation. Per-call checkpoints survive later failures. Observations and their initial validation events commit atomically after all calls; a failed call marks surviving observations needs_review.

Session advisory locks prevent simultaneous processing of the same report/metric/year. A fingerprint covers input chunks, definition, model digest and pipeline/options; identical successful runs are skipped. `--force` adds a new attempt, never overwrites previous evidence. Interrupted attempts are retained and marked interrupted when restarted; cancellation through the CLI records cancelled status. Unexpected persistence failures roll back observations; an abandoned running row is resolved on the next attempt. Existing privileged-database caveats still apply: these run records are append-preserved by the service, not protected against administrator DDL.

Audit output contains public report excerpts, not credentials, and should remain local. A run's model prompts must never be forwarded to an external provider as an automatic fallback.

`recheck-extractions` applies the current explicit-scope row rule to older unapproved local observations without inference. It never changes validated records. A failed association becomes rejected; the unsupported normalised value is withdrawn, while its previous conversion/confidence is preserved in a new immutable validation event and the original run audit. Raw values and excerpts remain intact. Rechecking the same version is idempotent. Run summaries describe the original attempt; current observation states and validation events describe subsequent rejection. This caught one combined-total-as-Scope-2 error during the live exercise.

## Verification and limitations

Tests use fictional fixtures and mocked adapters: clean table, missing Scope 3, targets/actuals, multi-year data, intensity-only, conflicts, equivalent/different units, citation/period/boundary errors, output-schema errors, failure/cancellation, PostgreSQL persistence, events and idempotence. No live model is needed for routine tests.

Extraction-stage regression on 2026-09-29, before batch orchestration: **263 backend tests passed, one optional live acquisition test skipped** (including 55 extraction tests). Python type checks, scoped lint/formatting, dependencies and Alembic no-drift checks passed. Unchanged frontend: **12 tests**, TypeScript and production build passed. Current combined verification is recorded in the batch guide.

Live verification is intentionally bounded: [ten examples and exact outcomes](extraction-live-2026-09-29.md), [full provenance for those ten](extraction-examples-2026-09-29.json), and [all 21 attempts, including failures and rejected evidence](extraction-audit-2026-09-29.json). It is not a precision/recall evaluation, complete extraction of three PDFs, or broad company coverage. There is no automatic benchmark admission, human-review UI, entity/subsidiary resolver, exhaustive disclosure review, target ingestion, OCR or external data transfer in this stage.

Changed implementation: `app/extraction/`, CLI integration, provider-neutral model identity inspection in `app/llm/`, extraction fixtures/tests and documentation. Frontend, catalogue seed, report PDFs and parsed evidence are unchanged.
