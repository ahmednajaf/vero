# Five-company official-site smoke check — 29 September 2026

Requested label year: **2025**. Actual final acquisition outcomes: **5 companies processed; 2 downloaded, 2 needs review, 1 failed; 0 discovered-only, 0 unavailable.** These are source-acquisition results, not metrics or disclosure-quality scores. No claim is made about any other company.

Used the existing seed companies' IR URLs and official-domain roots. Their sustainability URL fields were blank; no manual report URL was injected, no external domain alias added, and no seed/company metadata changed. Requests and BeautifulSoup only; JS fallback was disabled. All source access controls were respected.

| Company | Final status | Observed outcome | Discovery pages / requests | Retained candidates |
| --- | --- | --- | --- | --- |
| Apple Inc. | downloaded | [2025 Environmental Progress Report](https://www.apple.com/environment/pdf/Apple_Environmental_Progress_Report_2025.pdf), 22,928,608 bytes, application/pdf. | 6 / 13 | 100 |
| Samsung Electronics Co. Ltd. | downloaded | [2025 Sustainability Report, English](https://www.samsung.com/global/sustainability/media/pdf/Samsung_Electronics_Sustainability_Report_2025_ENG.pdf), 5,820,129 bytes, application/pdf. | 18 / 30 | 69 |
| Nestlé S.A. | needs_review | Both [IR seed](https://www.nestle.com/investors/faqs) and [official root](https://nestle.com/) returned HTTP 403. No bypass attempted. | 0 / 6 | 0 |
| Saudi Aramco | failed | [IR seed](https://www.aramco.com/en/investors/investor-faq) and [official root](https://aramco.com/) timed out with 15-second read timeouts after configured retries. No report was acquired. | 0 / 9 | 0 |
| Unilever PLC | needs_review | Both [IR seed](https://www.unilever.com/investors/investor-centre/) and [official root](https://unilever.com/) returned HTTP 403. No bypass attempted. | 0 / 6 | 0 |

Discovery request counts include robots, redirects and retries, not subsequent download requests. Samsung reached the 18-page crawl bound; its selected report was still acquired. Apple encountered an HTML/challenge response at a separate regulatory subdomain's robots file, which was not bypassed. Its candidate archive was capped at 100, with 193 lower-ranked encounters omitted and a diagnostic recorded.

Apple was checked twice during development: an initial `needs_review` run exposed candidate truncation by page order. After fixing retention to preserve the best candidates and adding a regression test, a second run found the actual 2025 corporate report. Both runs remain in the database; counts use only the latest. Exactly five distinct companies were contacted; there were six discovery attempts. No retries of the blocked Nestlé/Unilever jobs or alternate-identity/browser attempts were made.

## Download evidence

| Company | Retrieved at (UTC) | SHA-256 |
| --- | --- | --- |
| Apple | 2026-09-29 10:57:45.875400 | `597676e8b48ac45529303abc7ef47425ca62ff4efc3a375962a077a033525f74` |
| Samsung | 2026-09-29 10:57:44.547604 | `aee5b45480512c05b13b3bfceab1d170232aae847e6ba398b2ebdcab842f7155` |

Files are under the project `data/reports/<company UUID>/2025/<hash>.pdf` directory (ignored by git). They were MIME/signature checked and hashed, not parsed or reviewed for sustainability metrics. A 2025 label does not establish the underlying performance year; verified `reporting_year` is NULL.

The [exact machine-readable status export](discovery-live-2026-09-29.json) includes URLs, source pages, candidates, reasons, timestamps, byte counts, hashes and diagnostics. It is a captured result, not frontend mock data. PostgreSQL records were created only in the isolated local `sbi_test` cluster, not a production database.

Independent post-download checks matched both hashes and file sizes. The database contains six discovery attempts, 269 historical candidate manifests, two canonical artifacts, and zero metric observations, targets, chunks or extraction runs. A SQL backup is retained at ignored `backend/storage/verification/discovery-smoke-2026-09-29.sql`; restore only into a new empty database, never over an existing deployment. Desktop/mobile screenshots are in the same verification directory. Temporary services were stopped after verification; downloaded files and evidence remain on disk.

## Reproduction

With migrations and the metadata seed imported, from `backend/`:

```bash
python -m app.cli discover-reports --year 2025 --limit 5 \
  --company 01900000-0000-4000-8000-000000000005 \
  --company 01900000-0000-4000-8000-000000000008 \
  --company 01900000-0000-4000-8000-000000000012 \
  --company 01900000-0000-4000-8000-000000000015 \
  --company 01900000-0000-4000-8000-000000000016
python -m app.cli download-reports --year 2025 --limit 5 \
  --company 01900000-0000-4000-8000-000000000005 \
  --company 01900000-0000-4000-8000-000000000008 \
  --company 01900000-0000-4000-8000-000000000012 \
  --company 01900000-0000-4000-8000-000000000015 \
  --company 01900000-0000-4000-8000-000000000016
python -m app.cli report-status --year 2025
```

Results may change with site content, network conditions, robots policy, and access controls. These observed failures do not establish that the companies lack reports. The originally supplied Aramco example PDF was not substituted for the timed-out discovery run.
