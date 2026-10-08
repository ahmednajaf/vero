# Vero delivery status — 8 October 2026

## Acceptance status

**Working local application; not a finished 500-company benchmark dataset or an
enterprise production deployment.** A passing software test suite does not close
the acquisition, interpretation, comparability or operating requirements below.

## What is available

The existing globe, purple background, dark-glass material, navigation wheel and
cyan Sustainobot remain. Companies, report search, saved peer analysis, metric
extraction, source drill-down and exports share that shell. The new pricing page
adapts the supplied card composition for proposed $5,000 company / $10,000 sector
annual editions. Checkout is not enabled.

The fixed pharma sample publication and Race are not customer routes. Their
retired code is recoverable in `archive/`, outside the active runtime. Actual
previously saved company analyses and original report evidence are preserved.
No new cloud service, vector database, queue service or billing integration was
introduced.

Start with `bash scripts/dev.sh`; open <http://127.0.0.1:5173/>. Do not expose the
unauthenticated local server publicly.

## Verified coverage

Read-only audit: `outputs/acquisition-audit-20261008-final.json`.

| Measure | Actual result |
|---|---:|
| Company registry / companies attempted | 500 / 500 |
| Retained source records in active library | 305 |
| Searchable PDF records | 272 |
| Companies with searchable text | 265 |
| Companies with indexed primary-report candidates | 262 |
| Indexed supporting documents, not primary reports | 10 |
| Indexed physical pages | 27,711 |
| Indexed PDF hashes and actual source endpoints verified | 272 / 272 |
| Companies still without an indexed primary candidate | 238 |

Primary-report labels: 233 are labelled 2025, 14 are labelled 2024, and 15 have no
unambiguous year. These are document labels, **not verified measurement years**.
A primary candidate is a document-type classification, not audited completeness
or a validated comparison. The roster spans 18 countries but is S&P-500-heavy,
not a census of the world's 500 largest companies.

The final 98-company recovery pass completed all attempts and retained 49 PDFs.
Its manifest is under
`backend/storage/collections/992a346a-e134-4d33-8655-794bcd6713fb/`.
Additional individually checked official links recovered Microsoft, Aramco,
Tesla's 2024 extended report and other documents. All acquisition runs made zero
AI calls and added no synthetic metrics.

The approved unavailable-robots rule is now applied only to exact public PDFs
with retained official source-link evidence. It does not grant wider crawling.
Published robots exclusions, PDF-level forbidden responses, login/CAPTCHA/bot
challenges, rate limits and network failures are not bypassed. Microsoft and
Aramco are indexed; Allianz and AbbVie still have explicit access-policy failures.

Remaining job outcomes among the 238 primary-report gaps: 140 need source review,
78 failed acquisition/content/parsing checks and 20 were not located within the
bounded search. These statuses do not mean that the reports do not exist. Some
require further source discovery; explicitly blocked publishers require permitted
access or legitimately supplied PDF files, not increasingly aggressive retries.

## AI and cost controls

Active provider: OpenAI. Pinned model: `gpt-5.4-mini-2026-03-17`.

The backend allows only the configured pinned model, uses no silent fallback or paid automatic
retry, and reserves against a 2M-token UTC-day limit and $5 monthly conservative
list-price estimate. These are app-level limits, **not proof that every call is
free**; the organisation allowance is shared with other applications.

Four small live provider calls were used for integration checks. Two tested source
extraction; one question used planning and synthesis calls. The comparison answer retained
three grounded claims and withheld three unsupported citation drafts. This is
evidence of a working integration and safeguards, not a general accuracy score.
No additional inference was used for collection, final audits or browser checks.

## Tests and real checks

- Backend: **631 passed, 2 optional live tests skipped**. All provider unit tests
  use mocked transport. Existing dependency deprecation warnings remain.
- Frontend: **74 passed across 9 test files**.
- Backend type checking and lint passed; frontend type check and production build
  passed. The lazy globe bundle still produces a size warning.
- Four real topic searches and their evidence endpoints returned HTTP 200.
- All 272 indexed PDF endpoints returned the exact recorded SHA-256 bytes.
- Browser checks covered the preserved landing/shell, companies, saved comparison,
  source selection/drawer, saved chat, pricing and mobile pricing. Reopening saved
  results did not invoke a model. Automated tests cover provider failures and
  missing-data behaviour; this does not imply every browser path is failure-free.

Visual proof:
`outputs/pricing-20261008.png`, `outputs/edison-source-20261008.png`,
`outputs/source-drawer-20261008.png`, `outputs/live-mini-answer-20261008.png`.

## Backup verification

Backup:
`backend/storage/backups/a7d620f8a1b241c488a1f89089ced33b/database.dump`.

A restore into a new, uniquely named disposable database matched all **32 table
row counts**. All **319 retained PDF records across the full database** passed
local file/hash checks, including historical records outside the active library.
Only the disposable restore database was removed; the original was not modified.

The dump **does not contain PDF bytes**. Its adjacent manifest records their
checksums. Preserve `data/reports/` separately; this is not off-device disaster
recovery.

## Requirements still open before a corporate release

1. Acquire and index the remaining 238 primary reports without access-control
   bypasses. Review candidate type, coverage and period; supporting documents do
   not count as full reports. Some available PDFs also retain image/text gaps.
2. Measure extraction and analytical accuracy on a wider held-out report set.
   Exact quotations and valid JSON do not prove the interpretation is correct.
3. Establish compatible measurement years, scopes and denominators before
   numerical peer rankings. Library breadth is not metric completeness.
4. Agree an actual deployment/security plan, customer access and data retention.
   Authentication and cloud deployment remain outside the current local setup;
   no enterprise certification or audited ESG-rating claim is made.
5. Validate the commercial scope and willingness to pay with prospective buyers.
   The pricing page is a proposal, not proven demand or an enabled purchase flow.

These are release gates, not hidden successes. No requirement above is represented
as complete merely because its UI is present.
