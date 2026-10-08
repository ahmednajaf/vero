# Canonical metric catalogue 1.0.0

**43 definitions; no company sustainability values.** Frozen source: [`backend/app/catalogue/data/v1.json`](../backend/app/catalogue/data/v1.json). Seed migration: `840b86a2302e`. These are platform-owned definitions, not a certification of reporting-standard compliance or a universal ESG score.

| Category | Count |
| --- | ---: |
| Climate | 9 |
| Energy | 4 |
| Targets | 4 |
| Water | 3 |
| Waste | 3 |
| Governance | 6 |
| Social | 4 |
| Supply chain | 3 |
| Disclosure quality | 7 |
| **Total** | **43** |

## Score eligibility

**37 are not eligible; six are conditional. None is automatically rankable.** Conditional means potential eligibility only after validated evidence, like-for-like periods/boundaries/definitions and an explicit peer/comparison policy. No scoring engine is implemented.

| Conditional metric | Direction | Necessary distinctions |
| --- | --- | --- |
| emissions_intensity | lower | Same numerator scope and denominator identity/unit/scale/currency basis. |
| yoy_emissions_change | lower | Signed change in comparable gross inventories; positive prior value and aligned restatements. |
| renewable_electricity_percent | higher | Same electricity denominator and renewable procurement/claim basis. |
| renewable_energy_percent | higher | Same total-energy denominator, carrier coverage and renewable definition. |
| recycled_or_diverted_percent | higher | Same recovery routes and denominator; recycling and landfill diversion remain distinct. |
| injury_rate | lower | Same injury definition/population/jurisdiction; TRIR and LTIFR remain distinct. |

Absolute totals are size/activity-dependent. Target years, governance, policies, headcount, workforce composition, assurance and disclosure flags have no automatic performance direction. No target or disclosure indicator is score-eligible. Publishing more information is not automatically better sustainability performance.

## Stored and exposed fields

Each definition has canonical_id, name, description, category, data_type, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, preferred_direction and validation_constraints. Additional fields identify catalogue/definition versions, evidence_kind, quantity_kind, required comparison dimensions, sector applicability, scope and activation state.

`canonical_id` maps to existing `metric_code`; `data_type` to `value_type`; preferred_direction is lower/higher/null (stored as lower/higher/none). The database UUID identifies a specific definition version and is deterministically seeded with UUID5 from code/version. Canonical IDs persist across future definition revisions; observations remain linked to their original definition UUID.

Data types are decimal, integer, boolean, enum, text and object. A null canonical unit means non-physical or context-dependent, not zero: qualitative/compound definitions have no invented physical unit; intensity exposes `tCO2e/{denominator_unit}` as a template and requires the actual denominator. Aliases are retrieval clues, not permission to merge distinct concepts.

Rules contain explicit versions, exact decimal-string conversion factors where meaningful, contextual requirements, unknown-unit action (`needs_review`) and raw-value preservation. Constraints declare null/missing policy, finite/integer/bounds checks, enum vocabularies, optional structured-value schemas and semantic review requirements. Required context is conditional where named, e.g. currency_code_if_monetary. A false disclosure finding can retain a null observation reference but must document its completed source review.

**Catalogue rules are declarative.** The later [extraction stage](extraction.md) executes supported exact unit conversions and conservative evidence gates while retaining raw values/units and review candidates. It does not implement complete semantic validation, automatic target ingestion, typed/compound-value normalisation or scoring. Missing values remain null, not zero/false. The catalogue-stage verification below records its original zero-observation state, not the subsequent extraction run.

## Comparison safeguards

- Climate uses explicit CO2-equivalent mass, not CO2-only/carbon mass, offsets, removals or avoided emissions. Scope 2 location/market methods remain separate; a combined Scope 1+2 uses exactly one identified method. This separation follows [GHG Protocol guidance](https://ghgprotocol.org/scope-2-guidance). Inventory standards/GWP/method versions remain comparison dimensions, not silently updated assumptions.
- Generic total GHG is not automatically a complete Scope 1+2+3 inventory. Scope 3 categories and financed-emissions coverage must be explicit. Base-year values are historical context, not current results.
- Intensity retains numerator scope, denominator meaning/unit/scale and monetary currency/basis. Revenue, production and employee denominators cannot be pooled.
- Percentage shares are 0–100 and require explicit percent/fraction notation. Percentage points are not relative changes. Year-on-year change is `(current - prior) / prior * 100`; prior gross emissions must be positive. Its floor is -100, with no arbitrary +100 ceiling. Reduction wording needs explicit sign handling, not guessing.
- Energy uses GJ and explicit joule/kWh conversion factors; power is not energy. Renewable electricity differs from renewable total energy. Water uses m3, retaining withdrawal/consumption/discharge and basin/stress/source distinctions; see the [GRI water standard overview](https://www.globalreporting.org/standards/standards-development/topic-standard-for-water-and-effluents-gri-303/). Ambiguous gallons or tons require review.
- Net-zero/carbon-neutral years are different commitments, not achievements. Interim targets are structured objects retaining target/baseline years, amount/unit, scope, absolute/intensity basis and status.
- SBTi uses a non-ordinal internal vocabulary, with original wording, target type, source and as-of date retained. Commitment is not validation, and validation is not achieved reduction. [Official dashboard labels](https://sciencebasedtargets.org/target-dashboard) evolve; unmatched labels remain other_reported_status, never guessed as validated.
- TCFD/ISSB references, partial disclosures and alignment/compliance claims are distinct. A keyword mention is not a verified compliance finding; retain standards/versions and extent. See [IFRS S2](https://www.ifrs.org/issued-standards/ifrs-sustainability-standards-navigator/ifrs-s2-climate-related-disclosures/). Assurance requires scope, level, provider, standard and opinion; limited is not reasonable assurance.
- Headcount is not FTE. Injury rates per 200,000 hours rescale by factor 5 to per-million hours only with the injury definition and workforce coverage retained. Supplier programmes/policies are existence indicators, not achieved emissions reductions.
- Disclosure booleans require a defined reviewed source set. Failed parsing or a missing keyword never establishes false; an explicit zero still counts as disclosed. Scope 2 availability does not imply both methods, nor Scope 3 availability all categories. Disclosure quality is not performance.

Four reference sources and their 2026-09-29 review date are retained in the seed. These sources inform definitions; they do not endorse the platform's conservative score-eligibility policy.

## Persistence and migration

`metric_definitions` is extended; there is no new table. An index covers catalogue/category/code, the existing code/definition-version uniqueness remains, and database checks require complete catalogue metadata and numeric achieved-performance semantics for conditional scoring. A trigger rejects definition edits/deletion except is_active/timestamps. Deactivation preserves all evidence links.

Seed data is checksum-pinned by the migration and packaged with the backend. Do not edit a released seed: create a new file/version/migration. Repeated `alembic upgrade head` does not duplicate data. Legacy definitions retain their original fields with null new metadata and are excluded from the canonical API. Conflicting existing code/version records fail the migration atomically, never overwrite or silently skip them; reconcile explicitly before retrying.

Downgrade removes only unused, unchanged seeds. Referenced definitions, custom/new catalogue data or changed activation state block downgrade. Restrictive foreign keys and backups remain necessary; privileged DDL/TRUNCATE can bypass ordinary DML protections. Catalogue metadata is not yet an observation-level validator or target-versus-performance routing engine.

## API

```bash
cd backend
source .venv/bin/activate
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
curl http://127.0.0.1:8000/api/metrics
curl 'http://127.0.0.1:8000/api/metrics?category=climate'
curl 'http://127.0.0.1:8000/api/metrics?score_eligibility=conditional'
```

GET returns all active definitions for catalogue 1.0.0, deterministically ordered by category/code/version. Category and eligibility filters are AND-combined; keys use lowercase snake_case. An unknown catalogue_version (e.g. 9.0.0) returns an empty set, never a fallback. Invalid parameter syntax/vocabulary returns 422; database errors use the existing sanitised 503. With 43 definitions the full catalogue is returned without pagination. No write endpoint or frontend change is included.

Envelope: catalogue_version, filtered total/category_counts/score_eligibility_counts, complete items and ranking_notice. A real test returned HTTP 200, 43 definitions, 37 not_eligible and 6 conditional; the database still held **zero company observations and zero targets**.

## Verification

On 2026-09-29: **208 backend tests passed, 1 optional live acquisition test skipped**, using isolated PostgreSQL schemas; Python typing, dependency checks, scoped lint and Alembic no-drift check passed. Unchanged frontend: **12 tests**, TypeScript and build passed. Tests cover exact IDs/category counts, full API/seed equality, exact factors/bounds, scoring restrictions, filters, deterministic UUIDs/idempotence, immutability, legacy preservation, collision rollback and evidence-safe downgrade. No AI or scraping ran in this stage.

Changed files: catalogue contracts/loader/frozen JSON, metric API, main router registration, metric ORM definition, package-data configuration, migration `840b86a2302e`, catalogue/schema/health tests, README, architecture/schema documentation and regenerated schema.sql. Frontend source, company CSV and prior evidence are unchanged. Existing project files were already untracked in git. A new local SQL backup preserves the verified database; the isolated test server is stopped afterward.
