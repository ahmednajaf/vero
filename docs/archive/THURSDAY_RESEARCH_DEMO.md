# Vero — Thursday research-product demonstration

Prepared 30 September 2026 for Thursday, 1 October. **FOR EVALUATION.** Technical source checks are not expert approval. Not independently assured, investment advice, or a finished commercial research product.

## What we are demonstrating

Jalal's idea in one sentence: sell an annually refreshed, source-backed sustainability research report that helps companies and banks understand meaningful peer differences without re-reading every corporate report.

The website makes that research inspectable; it is not the justification for the business. This release tests five pharmaceutical groups before attempting broader sector coverage. The larger company universe, PostgreSQL, migrations, discovery, parsing, local extraction, audit history and existing reports are preserved. No bulk run was started, no original evidence deleted, no cloud deployment performed, and no new model downloaded.

## Five-minute walkthrough

| Time | Show | Say / check |
|---|---|---|
| 0:00–0:25 | Overview | “Annual peer research, with every figure traceable to the report.” Five companies is a reviewed sample, not the full universe. |
| 0:25–0:45 | Companies | One sector first exposes real period, boundary and unit problems before scaling. |
| 0:45–1:10 | Evidence CSV and six-page briefing | These are exports from the reviewed database, not a second dataset. Show raw value, unit, page, excerpt and assessment status. |
| 1:10–1:45 | Select Sanofi and Johnson & Johnson → Compare | Renewable electricity: 86% and 100%. Same reviewed annual-total-electricity definition, but not identical procurement quality or business mix. Median 93%; n=2 includes Sanofi. No percentile. |
| 1:45–2:10 | Insights | Other nominally similar electricity figures are excluded: GSK's table period and Merck's purchased-electricity denominator differ. This is why “100%” alone is not enough for a defensible ranking. |
| 2:10–2:40 | Sanofi company page | “Why this position?” applies to one selected metric. Sanofi is 7 percentage points below this two-value median, not “worse at sustainability.” |
| 2:40–3:15 | View source → Open saved PDF | Show Sustainability Statement 2025, physical page 29 (printed page 25), its 86% excerpt and denominator footnote. The raw and normalised values agree. |
| 3:15–3:45 | Race | Two electricity cars on a fixed 0–100% scale. Click a car for the same comparison/source. Target-year mode shows announced dates only; higher means a later year, not better performance. Road movement is decorative. No invented emissions exhaust. |
| 3:45–4:20 | Methodology | Six statuses, small sample, incomplete reporting sets, no composite score. Selected corporate assurance does not assure Vero's analysis. |
| 4:20–5:00 | Ask Jalal / experts | “Which of these comparisons is genuinely useful, what is missing, and would this save enough research time to pay for?” Ask for one useful buyer decision and one methodological correction. |

## Exact coverage

Study: `pharma-2025-v1`; methodology: `pharma-review-v1`. Reporting-set year 2025; individual observation years are retained, including GSK's 2024 Scope 3 total.

| Company | Country | Official primary PDF | Source-checked checklist |
|---|---|---|---|
| GSK plc | UK | Responsible Business Report 2025 | 7 / 8 |
| Johnson & Johnson | US | Health for Humanity Report 2025 | 2 / 8 |
| Merck & Co., Inc. | US | Purpose for Progress Impact Report 2025/2026 | 7 / 8 |
| Novartis AG | Switzerland | ESG Data Summary 2025, updated September 2026 | 6 / 8 |
| Sanofi | France | Sustainability Statement 2025 | 8 / 8 |

Five primary PDFs plus Merck's 2025 GHG assurance letter: **six retained official PDFs**. Review was bounded to selected value pages and supporting context, not a line-by-line audit of all six documents. AstraZeneca and Roche attempts encountered robots.txt access failures; those controls were not bypassed. Other candidates were selected instead.

| Assessment state | Count | Meaning in this release |
|---|---:|---|
| VALIDATED | 10 | Suitable for the stated comparison: 2 electricity shares, 3 announced target dates, 5 qualitative assurance-disclosure records. |
| NOT_COMPARABLE | 20 | Source-checked values retained, excluded from the applicable peer calculation. |
| NEEDS_REVIEW | 3 | J&J emissions raw values retained; unit expansion unresolved in this reviewed set. No normalised magnitude inferred. |
| NOT_FOUND_IN_REVIEWED_SOURCES | 7 | Bounded review did not establish the requested value. Not proof of corporate nondisclosure. |
| NOT_REPORTED | 0 | No sufficiently exhaustive absence claim made. |
| NOT_ASSESSED | 0 | Each of the 40 company–metric slots received an explicit assessment. |

There are **30 source-checked value/target records**, not 40 confirmed values: 10 comparison-eligible plus 20 not comparable. Three further raw candidates need review; seven slots have no value. The stored value records comprise 30 metric observations and three targets. Source-checked checklist coverage is not a disclosure-quality rating.

Technology and Financial Services were **not attempted** in this release. Five companies across one sector are completed as bounded assessments—not five companies with every number comparable, and not a passed bulk-pipeline checkpoint.

## Strongest supported findings

1. **Reported electricity shares require denominator checks.** Sanofi 86% and J&J 100% form a two-value calendar-2025 total-electricity cohort; descriptive median 93%. GSK's 99% table uses December 2024–November 2025; Merck's 100% relates to purchased electricity. Neither joins this cohort. This says nothing about hourly carbon-free power or equivalent climate impact.
2. **Target dates describe intent.** Three reviewed all-scopes net-zero commitments specify 2045: GSK, Merck and Sanofi. The other two years were not established in the bounded reporting set, not declared absent. No target credibility or delivery ranking is inferred.
3. **Assurance is metric- and version-specific.** All five companies have a selected assurance disclosure. Novartis explicitly states that its updated full-year actuals did not receive additional limited assurance. None of this independently assures Vero's research.

The database-calculated findings include contributing assessment IDs; the UI and HTML link to their official source pages. No free-form model reasoning establishes these findings.

## Architecture, without the jargon

Official PDF → saved/checksummed document → page-aware text → bounded extraction → source review → PostgreSQL → explicit comparison → UI and exports.

- Existing discovery and download code handles HTTP/robots policy; this study uses a small, explicit official-source manifest rather than restarting the company-universe crawler.
- Existing parsing stores immutable pages, chunks and tables. Reviewed raw-text slices are separately identified and still checked for exact offsets and SHA-256; existing ordered-text provenance is not overwritten.
- Existing local Ollama `qwen3:14b` ran nine bounded extraction jobs across the five primary reports. No whole PDF or data went to a paid/cloud model. Several candidates failed quality gates; two wrong GSK row assignments were explicitly rejected and retained. Final records use `visual-source-review+literal-page-check`, not a false claim that the model extracted everything correctly.
- `research_assessments` links each study/company/metric to an observation, a target or a bounded absence decision. Generic benchmark compatibility is not automatically approved by this study.
- `app.research.service` reads the stored review and audit trail, verifies source files, page slices, values, years and review identity, then calculates the small explicit cohorts.
- `/api/research/pharma` supplies the active React workspace. The same payload produces the HTML and CSV files. Downloads check the publication fingerprint and each artifact's hash; stale or changed evidence withdraws publication.
- The CSV files are outputs only. Editing them does not alter PostgreSQL or the website. A later reporting cycle requires new sources and versioned review decisions, not overwriting this release.

## Proven source-to-finding acceptance chain

Sanofi renewable electricity:

| Step | Verified identifier / outcome |
|---|---|
| Official source | https://www.sanofi.com/assets/dotcom/content-app/publications/esg-reports/sanofi-sustainability-statement-2025.pdf |
| Report | `cf24bdf1-1f2d-41bd-8366-9e2ee2447672` |
| PDF SHA-256 | `82547ddb72b6b05dca88f93ed4cfe13010cb5690a5693b96721e9be3ff9c8fcc` |
| Parse run | `a669961b-1e96-4d39-b563-eb38fc9e4af4` |
| Page / reviewed chunk | Physical page 29; `ba142649-4f1b-47d5-b3ec-cf730b708218` |
| Extracted and source-reviewed observation | `f62e9f69-4cf4-4446-8413-819f08200302`; raw 86%, normalised 86% |
| Validation event | `c6de160f-0760-4b18-b6fd-45d9a1c0adf4` |
| Research assessment | `5e629ba0-da78-4c41-ba76-d7b830e642a2`; VALIDATED for annual reported share only |
| Comparison | J&J 100%, Sanofi 86%; median 93%; difference −7 pp; n=2; percentile null |
| UI / source drill-down | Companies → Sanofi → Renewable electricity → View source; saved PDF served HTTP 200 with `%PDF-` signature and `#page=29` |
| Finding / briefing | First Insights finding; briefing pages 4 and 5; same contributing IDs in evidence export |

Acceptance was run against the real local API/database, not a browser mock. In-memory tamper probes for value, reporting year, source URL and comparison group all caused publication checks to reject the changed record. Probes were rolled back; no altered study values were committed.

## Startup

On this prepared machine:

```bash
cd "/Users/ahmednajaf/Documents/ChatGPT/sustainability dashboard"
bash scripts/dev.sh
```

Open `http://127.0.0.1:5173/?year=2025`. The script uses the existing local PostgreSQL cluster on 55433, applies migrations, and starts/reuses API port 8000 and Vite port 5173. It does not download reports, run AI or start the bulk pipeline. Ollama is not required to browse the already-published study. Do not restore a database or rerun a 200-company import for the demo.

To regenerate HTML/CSV from unchanged reviewed database records:

```bash
cd "/Users/ahmednajaf/Documents/ChatGPT/sustainability dashboard/backend"
.venv/bin/python -m app.research.export
```

This intentionally invalidates the old PDF download until the HTML has been printed and its hash registered again. The provided final PDF is already registered. The reproducible local browser/print check is `node tmp/edition/pharma-check.mjs` from the repository root on this prepared machine (bundled Playwright dependency and Chrome).

## Outputs

- `output/Vero_Pharma_Benchmark_Prototype.html` — six-page self-contained briefing.
- `output/Vero_Pharma_Benchmark_Prototype.pdf` — matching locally printed six-page PDF.
- `output/vero_research_observations.csv` — 40 assessments with raw/normalised fields, source URL/page/excerpt, units, hashes, IDs, status, comparison and review notes.
- `output/vero_company_summary.csv` — five company summaries and bounded checklist coverage.
- `output/vero_research_manifest.json` — publication fingerprint and file checksums.

Publication fingerprint: `285d80d5d5659036ad0d09043f2c827bec64236e2e3226ee2ca4fa764c9199e1`.

## Verification

Verification passed: **444 backend tests**, **98 frontend tests**, Python type checks across 74 source files, TypeScript checks and the production build. Two optional live-discovery tests were skipped. Non-failing upstream Starlette/PyMuPDF deprecation warnings remain. Reproduce backend integration tests using the isolated test database:

```bash
cd "/Users/ahmednajaf/Documents/ChatGPT/sustainability dashboard/backend"
TEST_DATABASE_URL=postgresql+psycopg://vero@127.0.0.1:55433/vero_test .venv/bin/python -m pytest -o addopts='' -q
.venv/bin/mypy app
cd ../frontend
npm test
npm run build
```

Tests use private schemas inside `vero_test`, not the live study tables. Optional live-discovery smoke tests remain disabled. Browser checks covered all six navigation routes, search, country filters, company selection, explicit medians, both Race metrics, source drawer/PDF retrieval, exports, mobile layouts and navigation. No browser runtime errors were observed. All six PDF pages and desktop/mobile screenshots were visually inspected.

## Changed files and preserved foundations

New research layer: `backend/app/research/{__init__,acquire,protocol,review,service,export}.py`; `backend/app/api/research.py`; `data/pharma_sources.json`.

Schema/integration: `backend/app/db/models.py`, `backend/app/schemas/company.py`, `backend/app/main.py`, `backend/app/extraction/service.py`; migrations `e251001a_pharma_sector.py`, `e251001b_research_assessments.py`, `e251001c_raw_evidence.py`.

Frontend: `frontend/src/app/PharmaResearch.tsx`, `frontend/src/lib/research.ts`, `frontend/src/research.css`, `frontend/src/main.tsx`, `frontend/src/components/{GlassSidebar,LandingHero,SourceDrawer}.tsx`. Existing brand assets, globe and backend features remain intact. Old `App.tsx` and commercial prototype code are retained but not the customer-facing entry point.

Tests: `backend/tests/{test_research,test_parsing,test_database,test_health}.py`, `frontend/src/tests/{research.test,App.test}.tsx`; real-browser acceptance/print script and screenshots under `tmp/edition/`.

Documentation/outputs: this file, `README.md`, the five output files above, retained report PDFs and acquisition/parse/extraction/review records in PostgreSQL. The repository was already untracked; no unrelated files were reset or removed.

## What still needs a person

- **Jalal:** sustainability-expert feedback, potential-buyer conversations and commercial validation. The $5,000–$10,000 price remains an untested hypothesis. No purchases, outreach or orders were sent.
- **Domain expert:** review definitions, boundary choices, comparable cohorts and interpretation; approve methodology before commercial publication.
- **Technical prototype:** automate collection/extraction assistance, organise evidence, calculate explicit comparisons, preserve audit history and present repeatable outputs.

Next research work, after feedback: resolve J&J's unit evidence, review broader Novartis/J&J reporting sets for unlocated targets/metrics, and select a buyer-relevant pharma question. Add water or supplier measures only when definitions support comparison. Do not expand sectors or company counts merely to populate the interface.

