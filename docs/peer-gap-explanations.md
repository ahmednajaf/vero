# Why this position?

Version `peer-gap-v1`: deterministic explanations of reviewed benchmark inputs. No free-form AI, new inference, report collection, automatic validation, database migration or real-company metric seeding. The feature appears on every available company profile, below benchmark position. The Race panel links to the full explanation and exports.

## What is explained

Three score components: emissions trajectory, renewable **energy** and disclosure completeness. Additional context: renewable **electricity**, Scope 3 reporting, board sustainability oversight and net-zero commitments. Governance and targets still have zero score weight. The existing live composite-ranking gate stays disabled; the UI explicitly says when no overall rank exists. These are peer comparisons and inspectable score contributions, not causal attribution of changes in rank.

Every factor retains company value, unit, sector median, ascending percentile, signed difference, direction-aware assessment, nominal score weight, component score, actual weighted score points where available, completeness, cohort/sample information and both company and peer provenance. Non-applicable quantities stay null, not zero: a binary governance disclosure has a prevalence rather than a fabricated median/percentile. The net-zero factor shows a single validated target year only when unambiguous; it is not ranked or treated as achieved performance.

## Numeric comparisons

- The source is a repeatable-read benchmark snapshot, calculated over the complete active universe before display filters or pagination.
- Peers share sector and the engine's metric cohort hash: definition/version, canonical unit, period, boundaries and required comparison dimensions. The company is included, matching existing benchmark percentile semantics.
- `difference = company_value − sector_median`. Percentage metrics use **percentage points**.
- Percentile remains ascending numeric midrank. It is not transformed into a merit score.
- Direction-aware effect uses the sign of `difference` for higher-preferred components and the opposite sign for lower-preferred emissions trajectory. Equality stays equality.
- Example from fictional tests: company YoY −4%, median −9%, difference +5 percentage points, numeric percentile 100. The effect is **below peer median performance** because the emissions reduction is smaller. Neither value is represented as a live company finding.
- At least five comparable companies are required by default. Missing, incomparable and insufficient-peer states retain reasons and sources; comparisons are withheld, never imputed.
- Company completeness is eligibility of the metric's reviewed inputs. The disclosure component additionally exposes assessed/required checklist slots. Sector completeness is comparable companies divided by active sector companies; it is not a claim about all reports published in the market.
- Actual weighted points use `component_score × nominal_weight / available_weight` only if the engine has a headline prototype score. This respects its existing 80%/100% coverage rules and does not invent a contribution when the score is unavailable.

The benchmark response adds `sector_percentile` so explanations cannot accidentally display a country percentile alongside a sector median. Existing numeric results and score weights do not change.

## Reporting coverage versus governance prevalence

Both exclude the subject company and require at least five assessed peers. One company contributes once, regardless of how many supporting observations it has.

**Verified reporting coverage:** reported peers / **all other active sector companies**. Unknown/unreviewed evidence is shown explicitly in the denominator and counts; the rate is a conservative verified-coverage lower bound, not proof that every remaining company failed to report. Rates spanning conflicting metric-definition versions are withheld. This statistic concerns disclosure availability, not comparability of the reported quantities; no water, waste or supplier values are pooled across incompatible boundaries.

**Board-oversight prevalence:** affirmative peers / **assessed comparable peers**. Unknown and incompatible peers are excluded from that denominator and displayed separately. The subject's reviewed governance context anchors the cohort; a missing subject context cannot pick an arbitrary peer cohort. Definition/version and substantive required context must match.

New engine `context_indicators` cover Scope 3 availability, board oversight and supplier engagement. They require validated, exact, comparison-reviewed boolean observations, current official source audits and all catalogue-required context. Conflicts, missing context and stale audits are not affirmative/negative evidence. The peer key excludes evidence-specific references and assessment timestamps (`supporting_evidence`, `reviewed_source_set`, `scope3_observation_reference`, `assessment_date`), but these remain required in retained provenance. All substantive required dimensions remain in the key; the reporting cycle is retained.

Scope 3's reviewed availability flag distinguishes true (reported), false (reviewed not reported) and unknown. By contrast, a reviewed supplier-programme **false** is still an explicit disclosure: it must not be mislabelled as failure to report. An actual numeric zero is also a reported value.

## Common disclosure gaps

The initial watchlist is supplier engagement (`scope3_supplier_engagement`), water consumption and recycled/diverted waste percentage. “Common” is explicitly defined as at least **50% verified peer reporting**, with at least five assessed peers. This is a transparent product threshold, not an external standard.

The requested “Peers commonly disclose metrics you do not” section reserves definitive gaps for source-reviewed absence. Unknown observations appear separately under **Not yet established for this company**, as review priorities. Missing rows do not establish nondisclosure. The current catalogue does not provide dedicated absence-review flags for each watchlist metric, so those missing observations normally remain review priorities; this feature does not manufacture negative attestations. All watchlist checks, exclusions and completeness counts remain inspectable even if no common gap qualifies.

## API and exports

```text
GET /api/companies/{id}/peer-explanation?year=2025
GET /api/companies/{id}/peer-explanation/export?year=2025&format=json
GET /api/companies/{id}/peer-explanation/export?year=2025&format=csv
```

These are read-only. Parameters include existing `min_peers` (5–500), `scope2_method`, `peer_group` and optional `expected_input_sha256` (64 lowercase hex characters). The explanation itself always uses sector comparison statistics, even if the underlying benchmark request uses another peer grouping. Company profile requests carry the same parameters and input fingerprint as their displayed benchmark snapshot.

Unknown/inactive companies return 404/409; invalid formats/thresholds return 422. Changed inputs return 409 when an expected fingerprint was supplied. The frontend clears year/company-superseded requests and offers retry on errors; no synthetic fallback is used.

The payload exposes:

```text
version / methodology_version / input_sha256 / explanation_sha256
company_id / company_name / sector / year / peer_group / minimum_peers
score (original engine output)
factors[]
disclosure_opportunities[]
common_threshold_percent / notice
```

`factors` and `disclosure_opportunities` retain structured values, reasons, completeness counts, peer members and complete provenance, including original/normalised values and units, report/page/excerpt, official URL, document checksum and validation/audit details supplied by the engine. The source drawer supports all contributing peers, not merely the selected company's evidence.

JSON exports retain the entire response. CSV has one factor/check per row, decimal strings, blank missing fields and structured provenance/completeness/peer lists in JSON cells. Unsafe formula-like text is apostrophe-escaped; strictly numeric negative values are preserved. Both exports carry the input and explanation fingerprints. Exports use attachment filenames based on UUID/year, `Cache-Control: no-store`, and `X-Explanation-SHA256`; allowed CORS origins may read the digest header. The browser verifies the export digest against the displayed result before downloading.

Adding `context-indicators-v1` to the input-hash parameters prevents old stored benchmark snapshots from being mistaken for the new structured context contract. Prior snapshots are untouched. Explanation rules have a separate version and content fingerprint, so a rule change can be distinguished from an input change.

## Verification and limits

Tests cover above/below/equal median, negative YoY direction, missing metric, not comparable, insufficient peers, sector versus country statistics, reviewed/unknown Scope 3, governance prevalence, stale/conflicting context, zero and false values, common disclosure thresholds, definition versions, repeated observations, reproducibility, complete CSV provenance, formula escaping, read-only endpoints, stale fingerprints and export formats. Frontend tests additionally cover evidence drawers, honest unavailable states and matching-fingerprint CSV/JSON downloads.

Current verification: **265 backend tests passed, 113 skipped; 70 frontend tests passed**. Python/TypeScript type checks, scoped Python lint, dependency checks and the frontend production build passed. Skips include PostgreSQL integration tests without `TEST_DATABASE_URL` and the opt-in live acquisition test; this run does not establish database integration or real-company explanation coverage. No model or live report request was made. No new browser screenshots/visual QA or deployment was performed for this feature.

The company profile requires the existing API and configured database. Start the API and frontend using the root README; no pipeline or data validation is launched by this feature. The existing local React/Vite + FastAPI/PostgreSQL architecture is preserved.
