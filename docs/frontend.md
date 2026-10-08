# Active Vero interface

`frontend/src/app/ReportApp.tsx` is the single application entry. The globe landing,
purple shader, dark-glass navigation and cyan Sustainobot remain the visual
baseline. New functions use the same shell; there is no separate demo dashboard.

| Route | Working surface |
|---|---|
| `/` | Interactive region globe and Sustainobot launcher |
| `/overview`, `/insights` | Actual library coverage and saved company/peer briefings |
| `/companies` | Search/filter the real registry; report availability and pagination |
| `/companies/:id` | Company reports, source search, reported numerical figures, saved analysis |
| `/compare` | Select a company and peers; preview evidence and explicitly generate topic analysis |
| `/compare?view=reports` | Side-by-side source comparison |
| `/sources` | Search/download official reports and inspect page-level passages |
| `/methodology` | Short source, extraction and comparison limitations |
| `/pricing` | Proposed $5,000 company / $10,000 sector annual editions; no checkout |

`/edition` redirects to the workspace. Race and the fixed pharma sample product
are retired. Their implementation history is archived, not shipped as navigation.

## Data behaviour

The library loads paginated companies and retained reports from FastAPI. Counts
come from the database; a source file, searchable report and validated numerical
metric are separate states. Provider/network errors never substitute test data.
Original PDFs remain downloadable, including reports not yet eligible for a
numerical comparison.

AI actions are explicit and bounded. Opening pages, filters, saved analyses,
source search, evidence drawers and exports makes no inference call. Selected
numerical extraction uses a metric and year, at most one model call per selected
report, and preserves cached results. Narrative comparisons retain completed
topic results if a later topic fails. Reopening saved results does not rerun AI.

The source drawer shows company, report, physical page, quote, original URL,
local PDF and fingerprint. Metric evidence additionally shows original/normalised
values, period, boundary and validation state. Plain report passages do not show
invented metric fields. Multiple source excerpts remain individually inspectable.

Briefing exports are HTML, evidence CSV and JSON. Reported-figure CSV preserves
provenance and unresolved comparability; exports are not independent assurance.
Pricing is a proposal; its buttons lead to peer selection or sector coverage.

## Verification

Run `npm test -- --run` and `npm run build` from `frontend/`; the build includes
TypeScript checks. Test fixtures stay in tests, never production data. Browser
checks use the actual local API and report library, including mobile layouts,
navigation, saved results, source drilling, extraction state, errors and exports.

Current startup and release limitations are in the [README](../README.md).
The application is local and unauthenticated; it is not an enterprise-hosted
deployment. The lazy 3D globe bundle is still large and is a performance caveat.
