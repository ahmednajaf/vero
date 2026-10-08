# Vero: real-company bulk report collection

One backend and PostgreSQL database. This implements acquisition and a searchable
document library, not a fabricated benchmark dataset. No UI changes or paid calls.

## Run and resume

From the repository root, start the local database/API with `bash scripts/dev.sh`.
The API explicitly loads `backend/.env`. Then:

```sh
cd backend
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.cli import-company-snapshot data/company_universe_500.json
.venv/bin/python -m app.cli collect-reports \
  --year 2025 --limit 500 --workers 8 --parse-workers 2 \
  --max-pages 8 --allow-js --allow-prior-year --no-search

# Use the UUID printed in collection_started. Resume uses its frozen cohort/config.
.venv/bin/python -m app.cli collect-reports --resume RUN_UUID
.venv/bin/python -m app.cli collection-status RUN_UUID
.venv/bin/python -m app.cli knowledge-search 'supplier water scarcity'
```

Optional cohort filters: `--company UUID` (repeatable), `--sector`, `--country`.
The snapshot importer requires no network and preserves existing user-managed
company rows. It validates the entire snapshot before a single atomic import;
duplicate identities, listing collisions and missing provenance abort the import.
These affect new runs only. A new year creates independent company/year jobs.
Successful prior work is checksum-verified and reused. Each explicit retry makes
one new attempt at an incomplete company; HTTP transient retries remain bounded.
Do not run overlapping cohorts concurrently on this laptop.

Exit 0 means the cohort finished without source/text gaps. Exit 2 means the pass
finished with gaps; it does **not** discard successful sources. An interrupted run
can be resumed using the same UUID. All companies are attempted; no 20-company
early-stop rule applies to this acquisition-only command.

## What it actually does

1. Freeze up to 500 real company IDs in `report_collections`.
2. Queue independent company/year records in `knowledge_jobs`.
3. Crawl known sustainability/IR pages and relevant official-domain links.
4. If needed, inspect company-published sitemap locations. Retain candidate URLs,
   source pages, selection reasons and rejected alternatives.
5. Try up to five eligible official candidates, continuing if a download fails.
6. Check MIME/signature, retain the downloaded PDF under `data/reports/`, hash and
   deduplicate bytes. Retained source files are never overwritten.
7. Parse pages with PyMuPDF, retaining table/reading-order warnings. An annual PDF
   with no ESG-labelled link must contain sustainability text before indexing.
8. Index **all extracted page text**, not only selected sustainability metrics.
   Missing image-only text remains a recorded OCR gap. No automatic bulk OCR.
9. Commit progress and write the source manifest. No AI or metric writes.

With `--allow-prior-year`, a discovered 2024 report may be retained if the bounded
2025 search fails. Its detected year stays 2024, the requested-year gap stays
explicit, and knowledge searches filter it as 2024. It must not be represented as
2025 performance. Filename/report-label years are not verified observation years.

`--allow-unlabelled-year` additionally retains otherwise eligible official PDFs
whose title/URL does not establish a single year, after exact/prior-year options
are exhausted. Their detected/reporting year remains null and the job is partial.
They are searchable without a year filter, but never appear as 2025 coverage just
because 2025 was requested. Excluded document types and access controls still apply.

Eight company workers, two parser subprocesses and one browser at most are used
on this laptop. Database-reserved per-domain request slots coordinate throttling;
timeouts, byte limits and request/page budgets bound each attempt. Playwright is
only used for identifiable client-rendered shells, through the same HTTP policy.

## Source policy and real limitations

Approved company-owned domains and exact PDF links observed on their HTTPS pages
are accepted for primary downloads. Publishing-CDN support is restricted to Q4,
Contentful, Webflow, CloudFront, Sanity, Prismic, Contentstack, Azure CDN/Front Door,
Adobe AEM delivery and S3 virtual-hosted publishing. An observed link grants only that exact file
and its robots.txt lookup, not permission to crawl or trust the whole CDN.
The source page, anchor text and `exact-publisher-pdf-v1` decision are retained in
the discovery audit. Resumed downloads restore only the recorded exact link.
The optional `DISCOVERY_ALLOW_UNAVAILABLE_ROBOTS_FOR_LINKED_DOCUMENTS=true`
setting applies RFC 9309 §2.3.1.3 only to these exact company-published PDFs:
an unavailable 4xx robots file can permit a normal PDF request. It defaults off
and was enabled locally with explicit operator approval. Authentication, rate
limits, legal restrictions and challenge responses still stop the request;
5xx/network failures and published exclusions remain blocking. A PDF-level 403
is never bypassed. Each such robots decision is recorded in the discovery audit.
The exception also covers an exact owned-domain PDF with its retained official
source page, including owned download endpoints explicitly labelled `file_ext=.pdf`.
It is never cached as permission for other paths or HTML crawling on that host.
Ordinary redirects between exact PDFs on company-owned subdomains retain that
file-specific scope. Other destinations still require their own source approval.
Robots lookups can follow bounded HTTPS redirects on the same publishing host,
including a genuine 404 handler; this grants no general page or asset access.
Refused redirect destinations are retained in the acquisition audit.
Literal JSON hydration/Next download records are also read without executing
scripts: a file's own URL, filename and adjacent download label stay together.
Bare extension, filename and storage-key parameters are not invented PDF paths.
Explicit FY25 labels resolve to 2025 independently of a /2026/ publication path;
FY24/25 ranges remain ambiguous. Neither establishes individual metric periods.
Robots exclusions, logins, CAPTCHA/challenges, rate limits and forbidden responses
are not bypassed. External links without an observed, approved publishing chain
remain review items. A missing report is not replaced with a mirror or
invented value. Discovery is bounded, so “not located” does not mean “does not exist.”

An optional free public-search adapter is included and tested. It uses robots,
shared pacing and a circuit breaker; snippets are never evidence. During this live
run the search service challenged requests, so the expanded pass uses `--no-search`
and official-site/sitemap discovery. No paid search or model is required to run.

Inclusion in the library verifies retrieval/provenance, not the correctness of a
company's disclosures or the comparability of its figures. Supporting assurance
statements/frameworks, CEO letters, conflict-minerals statements and other partial
disclosures are labelled separately in the library and search results, not counted
as primary reports. Content/type heuristics
can still require review; new metrics and AI interpretations need their own tests.

## The company roster

`data/company_universe_500.json` contains 500 source-backed identities, not 500
guaranteed reports: 210 retained company IDs plus 290 sourced additions. It has
18 countries and six broad sector buckets (120 industrials, 101 technology,
97 consumer/retail, 94 financial services, 71 energy, 17 pharmaceuticals).

The expansion is S&P-500-heavy and not a worldwide largest-company census. Company
website metadata is from revision-addressed company infoboxes; downloaded report
facts come from the actual official PDFs. New country metadata uses headquarters,
not verified legal domicile. Raw metadata responses and retrieval hashes are in
`backend/storage/universe-metadata/`. The builder excludes unresolved websites,
ambiguous identities, duplicate share classes and unsupported sector mappings.

```sh
# For a NEW snapshot only; existing output is deliberately not overwritten.
backend/.venv/bin/python scripts/build-company-universe.py --size 500 --import-db
```

## Inspect the result

- `GET /api/companies?page_size=100`: paginated real registry.
- `GET /api/knowledge/collections`: current/recent run IDs and processed counts.
- `GET /api/knowledge/collections/{run_id}`: per-company report provenance and failures.
- `GET /api/knowledge/status`: library/parse/index coverage, not benchmark accuracy.
- `GET /api/knowledge/reports`: downloaded source library and parse quality.
- `POST /api/knowledge/search`: arbitrary-topic page-grounded retrieval.

Each run exports `backend/storage/collections/RUN_UUID/manifest.json` and an
append-only `events.jsonl`. PostgreSQL remains authoritative. The manifest is
refreshed every ten completed companies and at completion; `collection-status`
refreshes it on demand. It includes company, requested/detected year, original and
final URL, discovery source, report ID, SHA-256, retrieval time, file path, pages,
parse status, outcomes and exact acquisition diagnostics.

Back up PostgreSQL **and** `data/reports/`; a database dump alone cannot restore
PDF bytes. `scripts/check-database-backup.py` performs a local dump/restore smoke
check when collection is idle. It retains the dump but does not copy the PDFs.

Independently verify retained PDF hashes and export page/search examples after a
run finishes:

```sh
backend/.venv/bin/python scripts/audit-collection.py RUN_UUID \
  --output output/collection-audit.json
# Combine source inventories without double-counting report IDs:
backend/.venv/bin/python scripts/audit-collection.py RUN_UUID \
  --include-run RECOVERY_RUN_UUID --output output/combined-audit.json
```

Audit outputs are immutable: use a new filename for a later snapshot. Physical
PDF hashes and report-record counts are shown separately. An indexed empty PDF
does not count as searchable; a supporting document does not count as a primary
report candidate. Remaining text/image gaps are retained in each source's quality
metadata. No synthetic document or metric fills a failed acquisition.
