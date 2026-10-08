# Real-company corpus: collection results, 7 October 2026

> Historical acquisition checkpoint. For the 8 October application, coverage,
> test and restore results, see [delivery status](DELIVERY_STATUS.md). The original
> figures below are preserved as a dated audit, not current live coverage.

## Delivered

The PostgreSQL registry contains **500 real companies across 18 countries**.
All 500 received an acquisition attempt. A 33-company recovery pass corrected
supporting-document selection and unknown-year exclusions; later download-only
retries recovered sources without repeating discovery.

No synthetic companies, sustainability metrics, benchmark scores or AI-generated
facts were added by these collection runs. The existing 53 metric observations
were left unchanged. This release is the document/database layer, not a completed
500-company benchmark study. The frontend remains unchanged for guided design.

## Independently audited acquisition corpus

| Measure | Result |
|---|---:|
| Company registry / full-cohort attempts | 500 / 500 |
| Companies with retained downloads | 227 |
| Downloaded source records | 242 |
| Unique PDF SHA-256 hashes | 240 |
| Stored PDF hashes independently verified | 242 / 242 |
| Searchable source records | 220 |
| Companies with searchable source text | 214 |
| Companies with searchable primary-report candidates | 211 |
| Searchable supporting documents | 9 |
| Retained PDF pages | 24,291 |
| Pages in the audited indexes, including retained empty pages | 22,558 |
| Page-local text/table passages | 424,158 |
| Raw text characters in the audited indexes | 72,453,409 |
| Collection AI calls / new metric writes | 0 / 0 |

The definitive source inventory is
[`output/company-corpus-audit-2026-10-07.json`](../output/company-corpus-audit-2026-10-07.json).
It includes company IDs, exact original/final URLs, discovery pages, timestamps,
SHA-256, physical pages, file paths, document roles, parsing gaps and real search
examples. Two repeated PDF hashes are not counted as unique documents.

The live library also retains two older source records outside these acquisition
manifests: its API currently reports 244 downloaded records and 221 searchable
records. Both views report **211 companies with searchable primary candidates**.
These differences are scope, not fabricated coverage.

## Remaining work is explicit

- **273 companies have no download in this audited corpus.**
- **289 companies do not yet have a searchable primary-report candidate.**
- A primary *candidate* is a document-type classification, not a human-verified
  full report, validated metric or claim of peer comparability.
- Report-record year labels: 216 labelled 2025, 10 labelled 2024, 16 unknown.
  Filename/title years are not verified observation years. Unknown years stay
  null and cannot enter a 2025-filtered search via the requested year.
- Robots exclusions, HTTP 403/challenges, unresolved external publishers, broken
  links, network failures, crawl limits and parsing/content-check gaps remain in
  the manifests. Not located does not mean not published. Supporting-only sources
  remain searchable without being counted as primary reports.
- The universe is S&P-500-heavy, not the world's 500 largest companies. New country
  metadata uses headquarters rather than uniformly verified legal domicile.
- No OCR, AI extraction or research validation was silently run. Search is lexical
  over retained report text, not an exhaustive semantic understanding of every PDF.

## Reuse the system

See [commands and source policy](BULK_COLLECTION.md). From `backend/`:

```sh
.venv/bin/python -m app.cli import-company-snapshot data/company_universe_500.json
.venv/bin/python -m app.cli knowledge-search 'supplier water scarcity'
.venv/bin/python -m app.cli collection-status 5b0a5660-0eab-4786-8ad5-b4998da217ac
```

For a new collection, use `collect-reports`; resume a frozen cohort with
`--resume RUN_UUID`. Existing PDFs and pages are checksum-verified/reused. Explicit
retries keep earlier source evidence, retry incomplete work and retain failures.

Completed run IDs:

- Initial 210-company pass: `962e227c-5ba4-4f7a-a6f6-47b3a2bead26`
- Full 500-company pass: `5b0a5660-0eab-4786-8ad5-b4998da217ac`
- Targeted recovery: `6874f62b-65d7-4e68-90fa-5b6f22ed2be8`
- Request-budget download retries: `313788bb-12f2-4311-991e-f6fd7d712abd`
- PDF MIME-alias retry: `60a1260a-f2e5-49f7-8ef9-97a5719d85ff`

PostgreSQL is authoritative; exported progress manifests can reflect later file
acquisition state. The audit JSON above is an immutable point-in-time export.

## Verification and backup

- **527 backend tests passed; two optional live tests skipped.**
- **105 frontend tests passed.** Frontend type check and production build passed;
  the existing large globe-bundle warning remains. No frontend components changed.
- Backend type check passed for 88 source files; lint passed for changed modules.
- Real search/evidence/PDF requests through port 5173 returned HTTP 200, including
  HSBC physical page 177, Mizuho page 44 and TD page 49 for climate-risk retrieval.
- A PostgreSQL dump was restored into a disposable database. **All 31 table row
  counts matched**, and **258/258 retained PDF records across the entire database**
  passed file-hash verification, including older sources outside this corpus.
- Verified database backup:
  `backend/storage/backups/af337718349b449ca6f26d3ae31a404b/database.dump`.
  Its manifest lists table counts and PDF checks. The temporary restore database
  was removed; the original database was not overwritten.

**The database dump does not contain PDF bytes.** Preserve `data/reports/` alongside
it. This is a tested local backup, not an off-device disaster-recovery service.

Hosted AI remains disabled. No paid search/model calls, model downloads, messages,
outreach or cloud publishing were performed by this collection workflow.
