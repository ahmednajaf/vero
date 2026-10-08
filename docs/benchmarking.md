# Benchmark methodology v1

**Prototype benchmark score — not an external ESG rating.**

The engine uses existing reviewed evidence only. It makes no requests, invokes no AI, and never discovers, downloads, parses, validates or alters company observations. No real company metrics or scores are seeded. Fictional tests do not establish live data coverage.

## Source of truth and validation

The official report is the source of the *reported claim*, not independent proof of actual environmental performance. Source validation is distinct from external assurance.

Every eligible performance observation requires:

1. `validation_state=validated`, an exact value qualifier, and a finite normalised value in its canonical unit. Missing is not zero; percentage shares must be 0–100; negative absolute quantities are rejected.
2. A report recorded as an `official` source, document SHA-256, URL, physical page and supporting excerpt. Existing DB constraints enforce report/company/chunk identity and cited page membership.
3. A latest append-only validation event in the validated state, timestamped at least as recently as both the observation and report's last edit. Responses show its reviewer/rule identity and reason. Subsequent edits invalidate its eligibility until re-reviewed.
4. `compatibility_state=comparable` and every catalogue-required comparison dimension populated. High model confidence is not a substitute.

`metric_observations.comparison_context` stores explicitly reviewed dimensions absent from typed columns: inventory/GWP/gas definitions, gross/net treatment, energy definitions, denominator details, etc. Typed columns always take precedence, including nulls. The engine never fills missing context or accepts the old opaque `comparison_group_key` as sufficient proof. Exact reviewed context equality is deliberately conservative; reviewers must establish source-supported controlled terms rather than guess equivalence.

Context edits are covered by the existing observation last-edit trigger. Append an attributed validation event **after flushing reviewed changes**. This migration gives new events `clock_timestamp()` so they can correctly follow an update inside the same transaction. Historical events are unchanged. There is no automatic or bulk promotion to validated.

Inputs retain raw/normalised values and units, document/chunk IDs, report hash, URL/page/excerpt, extraction method, confidence, state, notes and audit event. Derived results carry input citations and formulas. Null outputs include reasons. Unvalidated/contextual evidence remains inspectable, but is not silently benchmarked.

## Cohorts and percentiles

Only active companies participate. Explicit `year` means observation year, not publication year. The prior observation year is loaded for trajectory calculations.

Peer groups: `sector` (default), `country`, `region`, `industry`, `revenue_band`. Sector/country list filters and pagination affect **display only**, not the peer universe. Sector summaries always use sector peers.

Revenue bands use base currency units: `<1bn`, `[1bn,10bn)`, `[10bn,100bn)`, `>=100bn`. They require finite positive revenue, matching year and known currency; currency/year are part of the key. GBP and USD are never pooled and no FX conversion occurs. Bands are financial metadata, not an intensity-denominator attestation.

Inside each group, comparable cohorts require identical metric definition/version, canonical unit and required dimensions. Boundaries, exact periods, methods, Scope 3 categories, denominator definitions and currency bases stay separate. Cohort keys and member IDs are returned. Absolute emissions percentiles describe magnitude, not efficiency or sustainability merit.

At least **five distinct comparable companies, including the subject**, are required. `min_peers` may increase to 500 but cannot fall below five. Repeat source observations do not increase sample size. Below the threshold, percentiles, medians and distances are null and extreme flags empty. Sample size is always exposed. This threshold is a prototype policy, not a statistical representativeness guarantee.

```text
Ascending midrank percentile:
100 × (number below + (number tied − 1) / 2) / (sample size − 1)
```

A unique minimum is 0, unique maximum 100, and all-equal cohort 50. Higher means larger, not better. Median is the middle value or average of the middle pair. Distance is `value − median` in the same unit. Sector median, sample size and distance are shown separately when another peer group is selected.

Conflicting validated values/definitions/units/context are withheld, with all citations retained. Only an explicitly validated successor of the same company/metric/year can retire a predecessor. Pending or unrelated successors cannot; there is no latest-file-wins rule.

## Derived metrics

| API metric | Formula and safeguards |
| --- | --- |
| `derived_scope_1_2_total` | Scope 1 + exactly one selected Scope 2 variant, in tCO2e. Default location-based; market-based requires explicit selection. Eligible inputs and matching shared dimensions required. No substitution/double counting. A conflicting comparable reported combined total blocks use. |
| `derived_yoy_emissions_change` | `100 × (current Scope 1+2 − prior Scope 1+2) / prior`. Requires positive prior total, consecutive matching annual periods and identical definitions/boundary/method. Negative means a decrease, not proof of decarbonisation causality. |
| `derived_renewable_energy_adoption` | Eligible renewable **total-energy** percent; renewable electricity is never substituted. |
| `derived_disclosure_completeness` | `100 × present validated flags / 7`. Checklist: Scope 1/2/3, methodology, boundary, assurance and base-year disclosure flags. Unknown slots lower only a **verified-coverage lower bound**, not a nondisclosure claim. No assessed slots => null. Only a fully assessed, consistent-entity checklist is comparable/score-eligible. |
| `derived_emissions_per_revenue` | Scope 1+2 tCO2e per million units of same-year consolidated revenue, with reviewed financial provenance and exact boundary/period alignment. Currency, currency basis and Scope 2 methods remain separate. |

Company CSV revenue alone is insufficient for intensity. Both Scope 1 and Scope 2 observations need the same reviewed `comparison_context.revenue_alignment` object. Example shape only—not actual evidence:

```json
{
  "validated": true,
  "value": "10000000",
  "currency": "GBP",
  "year": 2025,
  "period_start": "2025-01-01",
  "period_end": "2025-12-31",
  "organisational_boundary": "<source-supported boundary identical to emissions>",
  "currency_basis": "<reviewed nominal/constant-currency basis>",
  "unit_scale": "1",
  "report_id": "<recorded financial report UUID>",
  "report_sha256": "<downloaded financial document SHA-256>",
  "source_url": "<official financial source URL>",
  "source_page": 3,
  "supporting_excerpt": "<literal financial-report excerpt>"
}
```

Numeric revenue/currency/year must match the company record. The attestation is covered by the observation's validation audit. The adapter also checks its financial report belongs to the company, is official, has a matching document hash/URL, contains the cited page, and has not changed since review. It computes `source_verified` itself; JSON cannot override this check. Revenue magnitude/source URLs stay in provenance, not comparison identity. Unknown boundaries, zero/stale revenue and unclear base-unit amounts cannot yield intensity.

## Prototype components

These are fixed, inspectable design choices, not an external ESG methodology.

| Component | Weight | Formula |
| --- | ---: | --- |
| Emissions trajectory | 45% | `clamp(50 − 2.5 × YoY percent, 0, 100)`; flat = 50; 20% decrease = 100; 20% increase = 0. |
| Renewable energy | 35% | Validated total renewable-energy percent; catalogue conditional eligibility required. |
| Disclosure completeness | 20% | Fully assessed seven-flag checklist percentage. |
| Governance | 0% | Context only; catalogue excludes it from performance scoring. |
| Net-zero target | 0% | Context only; commitments are not achieved performance. |

Both performance components are mandatory and must have matching organisational/consolidation boundaries and reporting periods, giving minimum available weight 80%. Unknown disclosure is excluded, not zero; available weights are renormalised. Each component exposes score, nominal weight, formula, provenance and missing/exclusion reason. The result exposes coverage and available weight. Composite ranking is disabled (`ranking_eligible=false`): partial and full coverage are not interchangeable. Components are rounded to six decimal places before the weighted mean.

An individual score uses absolute formulas, not peer percentiles, and therefore does not require five peers. Peer statistics still do. No headline score is possible from disclosure alone.

## Extremes and disclosure gaps

Highest/lowest are numeric extrema within a sufficiently sized comparable cohort. All-equal cohorts get no extreme flags. Lowest negative/highest positive YoY also receive `biggest_yoy_decrease` / `biggest_yoy_increase` flags, corresponding to the requested improvement/deterioration views without implying cause or moral merit. Unknown disclosure is separate from verified absence.

Validated target years before the observation year or more than 50 years afterwards receive review flags. This explicit heuristic is **not a scientific target-quality standard**. Targets are never treated as achieved emissions. There are no “good/bad company” labels or claimed z-score/IQR anomaly detection.

## API, startup and storage

```bash
# From backend/, with the configured PostgreSQL environment:
.venv/bin/python -m alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

curl 'http://127.0.0.1:8000/api/benchmarks?year=2025&peer_group=sector&page_size=25'
curl 'http://127.0.0.1:8000/api/companies/COMPANY_UUID/benchmark?year=2025&peer_group=industry'
curl 'http://127.0.0.1:8000/api/sectors/Industrials/summary?year=2025'

# Save a benchmark snapshot from existing reviewed evidence; NOT run-pipeline:
.venv/bin/python -m app.cli build-benchmarks --year 2025 --peer-group sector --min-peers 5
```

GETs calculate a repeatable-read snapshot, never write or silently serve stale saved results. List pagination max is 100. Inactive company detail returns 409; unknown company/sector 404; invalid parameters 422. Decimal outputs are strings. Insufficient evidence is a 200 with null results and reasons, not a fabricated value or database error.

The explicit CLI atomically creates an immutable `benchmark_snapshots` row and five separate `benchmark_components` per active company, including missing/excluded rows. Same inputs/methodology/parameters reuse the snapshot; changed evidence, company data or parameters produce a new input hash/snapshot. Results preserve output provenance and version. DB triggers reject updates/deletes of history; downgrade refuses existing snapshots. No company observations are modified.

### Fictional response excerpt

The integration fixture's six Scope 1 values are 0,10,20,30,40,50 tCO2e. This shortened excerpt is test-only, not a real company benchmark:

```json
{
  "value": "0.000000",
  "unit": "tCO2e",
  "peer_sample_size": 6,
  "includes_subject": true,
  "minimum_sample_size": 5,
  "percentile": "0.000000",
  "median": "25.000000",
  "distance_from_median": "-25.000000",
  "sector_median": "25.000000",
  "sector_sample_size": 6,
  "flags": ["lowest_value"],
  "reason": null
}
```

## Verification and limitations

Verified on 2026-09-29: **360 backend tests passed**, two opt-in browser/live-site tests skipped; Python strict type checking passed across 60 files; **12 unchanged frontend tests** and TypeScript checking passed. Benchmark-scoped lint/format checks passed. PostgreSQL tests covered upgrade/downgrade, model drift, immutable history and source audits in isolated schemas. The new migration was not applied to saved user data, no real benchmark snapshots were created, and no company pipeline was run. The temporary test database was stopped afterwards.

Pure tests need no model or HTTP. PostgreSQL tests use isolated disposable schemas for migrations, audit freshness, APIs, read-only GETs, append-only component storage and idempotence. Existing real evidence still requires review; no new real-company benchmark coverage is claimed. Small/empty cohorts are shown honestly. Broad sector labels alone do not establish comparability; subsidiary/parent universes can overlap economically. No frontend or hosted deployment changes are included.
