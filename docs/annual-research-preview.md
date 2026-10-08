# Annual research preview

## What is being sold

Vero is the interactive companion to an annual sustainability research edition.
The proposed deliverable is the research report, evidence-linked analysis
workbook, company/sector briefing and a results discussion. It is not a software
implementation project or an external ESG rating. New reports feed a new annual
edition after extraction and review; archived editions remain versioned.

The Corporate package shows indicative USD 5,000 per annual edition. The
Institutional package shows USD 10,000. These are pricing hypotheses from the
commercial concept, not validated demand, revenue or margin forecasts. Scope,
delivery, terms and price require agreement. No checkout, authentication,
billing, CRM, automatic renewal or email delivery is implemented.

## Presentation path

1. Open `http://127.0.0.1:5173/?year=2025`. The existing globe and Vero brand remain.
2. Select **Preview the annual research**. Show the two banks, two official
   sources and five checked facts before describing future coverage.
3. Open **Explore the Race**. Switch market- and location-based Scope 2. Select
   either car, then **View source**. The numbers and source pages change together.
4. Open the saved PDF at page 38 (Bank of America) or 20 (JPMorgan Chase).
5. Return to **Open the briefing**. Download the PDF and workbook.
6. Show the annual packages. **Request a proposal** opens a local draft form.
   Downloading the request sends no email and places no order.
7. Explain the yearly cycle: official reports, local extraction, review,
   comparison, client briefing. Do not claim the 500-company study is complete.

The collection edition is 2025. These source observations concern 2024. The
preview was prepared on 30 September 2026; it is not labelled the latest global
reporting cycle. Price refers to the proposed annual product, not this small
sample alone.

## Truth and limits

The publication freezes five existing PostgreSQL observations: Bank of America
Scope 1, location-based Scope 2 and market-based Scope 2; JPMorgan location- and
market-based Scope 2. Duplicate BofA Scope 1 extractions count once. No new
sustainability values have been invented or manually inserted into the database.

Source facts were extracted by the approved local Ollama model in earlier work,
checked by Codex against rendered pages and deterministic rules, and retained
with raw values, units, exact excerpts, report hashes and review decisions. This
is **not human sign-off or independent assurance**. No new inference is needed
to browse the publication. No source passages are sent to an external AI.

Peer compatibility is still `unchecked`. Accordingly:

- The Race is a labelled absolute-value chart. Position is linear in reported
  tCO2e with a visible zero-based scale. Cars are not assigned scores or ranks.
- No sector percentile, sector median or net-zero progress is computed.
- Road movement is decorative. No exhaust, trend or acceleration is invented.
- The two banks are not a statistically sufficient or approved comparable cohort.
- The two BofA Scope 1+2 sums are within-company, same-year, same-source-page
  additions. Scope 2 accounting methods remain separate. No offsets or financed
  emissions are included.
- Metrics unassessed in this preview are not labelled unreported or given zero.

## Publication controls

`data/editions/2025-preview.json` is the versioned snapshot. API
`GET /api/editions/2025-preview` compares every selected observation with the live
source record and review, and checksum-verifies both retained PDFs. A change
withdraws the edition with HTTP 409 instead of substituting current values into
an old publication.

The same endpoint feeds the UI and export builders. `edition_payload` owns the
derived sums. The workbook independently reproduces those sums using cell
formulas; missing and zero inputs have been tested separately.

Downloads are served only through:

- `GET /api/editions/2025-preview/download/briefing`
- `GET /api/editions/2025-preview/download/workbook`

`data/editions/2025-preview-artifacts.json` binds the exported files to the exact
snapshot SHA-256 and each artifact's hash. Stale, missing, changed or unsafe-path
exports are withheld. The files are not exposed as unchecked public assets.

Builders and QA:

- `scripts/build-edition-pdf.py`: reads the checked local endpoint and builds the
  three-page briefing plus its intermediate payload.
- `tmp/edition/build-workbook.mjs`: bundled Artifact Tool builder; formulas,
  source register, input-change tests, error scan and rendered sheet previews.
- `tmp/edition/browser-check.mjs`: installed Chrome end-to-end journey; desktop
  and mobile screenshots, sources, exports, proposal draft and Race controls.

Use bundled runtime dependencies for exports. Rebuilding requires the local
API, database and retained PDFs. Re-render and review all affected pages/sheets
before deliberately updating the export manifest. Do not auto-approve a changed
source or patch hashes merely to make a failing integrity check pass.

## Not done by this preview

The five-company data-complete checkpoint remains unsuccessful; bulk processing
has not resumed. The 200-company directory is metadata, not completed research.
The hosted historical prototype is unchanged. Human review, an approved peer
cohort, broader metric coverage and commercial validation remain next steps.

## Verification on 30 September 2026

- Backend: 423 passed, 2 optional live tests skipped. Isolated test database only.
- Frontend: 90 tests passed. TypeScript check and production build passed.
- Python: mypy passed across 67 source files; scoped Ruff checks passed.
- Installed Chrome: source drawer and saved-PDF page, both artifact downloads,
  local proposal text, method switching, car selection, table view and mobile
  width checks passed, with no browser runtime errors.
- All three PDF pages and both workbook sheets were rendered and inspected.
- Workbook totals 683,176 and 82,350 reconciled. Changing Scope 1 to zero kept
  zero meaningful; clearing it withheld the dependent total. Inputs restored.
