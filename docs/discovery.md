# Official report acquisition

This is deterministic, operator-initiated acquisition, not extraction or an ESG score. A candidate's confidence is a ranking heuristic, not calibrated correctness or sustainability performance. A year in a filename/title is stored as `detected_year`; `reporting_year` remains NULL until content/period validation is implemented. A 2025-labelled report may describe 2024 performance.

## Flow

```text
Known sustainability URL → known IR URL → official-domain root
  → bounded relevant-link crawl → explainable ranking → one selected PDF + alternatives
  → PostgreSQL manifest → explicit download command → SHA-256 artifact
  → read-only /admin/reports
```

Each company/year attempt has a `report_discovery_runs` record, including zero-candidate outcomes. The next attempt preserves earlier runs. Only the latest completed job per company/year contributes to counts; alternatives do not inflate them. Incomplete/interrupted jobs have no `finished_at` and do not replace the last completed result. Retry discovery explicitly; there is no background scheduler.

## Source and comparison policy

- Trust the curator-provided official domain and its subdomains. IR/sustainability seed URLs on other domains are logged, not automatically trusted. Operator-confirmed company-owned aliases can be configured in `DISCOVERY_OFFICIAL_DOMAINS` by stable company UUID. Third-party mirrors/CDNs are not auto-approved. Domain suffix checks enforce a dot boundary.
- Sustainability and ESG reports rank at 0.95; climate, environmental, integrated, responsibility and impact reports at 0.90; annual reports at 0.80. Locally inferred context year subtracts 0.10. Annual reports require nearby sustainability-disclosure context. Scores do not assert content review.
- Exact requested-year label, owned host, PDF link/type and recognised report/disclosure label are required for automatic selection. Unknown/conflicting/wrong years, HTML-only disclosures and unverified hosts remain `needs_review`. Ties between eligible candidates use shortest URL, then lexical URL. Languages are not inferred/translated; language preference and actual reporting boundaries need later review.
- Press releases, brochures, supplier codes, policies, investor decks/presentations, highlights, factsheets and summaries are excluded from automatic primary selection. Product-level environmental reports are not treated as company-wide disclosures. An approval workflow is intentionally not implemented; no automatic override exists.
- The retained candidate set is bounded (100 by default), preserving the highest-ranked candidates even when a strong link occurs late in a long archive. Truncation is explicitly logged. This is not an exhaustive search and never establishes that a company publishes no report.
- The crawler follows relevant static links and extracts PDF URLs from viewer query parameters. It does not guess filenames, use search engines, crawl unrelated pages, parse report contents, or infer achieved sustainability performance.

## HTTP controls

Requests uses TLS verification, no ambient proxy/auth credentials, no persistent cookies, and an honest configured User-Agent. Every redirect is manually checked against the owned-domain policy; HTTPS downgrade, embedded credentials, non-HTTP schemes, nonstandard ports, redirect loops and excessive redirects are refused. DNS preflight rejects non-public addresses. This CLI is for curated URLs; DNS checks are not a hardened defense against hostile DNS rebinding. Do not expose an anonymous URL-fetch endpoint.

Robots files are fetched and cached per origin before page/PDF acquisition. Protego handles wildcard/Allow precedence. Crawl-delay/request-rate increase the delay; delays above 60 seconds defer the job. Missing robots (404/410) allow crawling; unavailable/blocked/challenge robots fail closed. Default delay is one second per host, minimum 0.5 seconds. HTTP 401/403/407, 429 and detected login/CAPTCHA/anti-bot pages do not trigger browser bypasses.

Defaults: 15-second connect/read timeout, two transient retries, 18 HTML pages, depth 3, 80 total requests per company job (including robots/redirects/retries), 2 MB HTML cap, 512 KB robots cap, 100 MB PDF cap, 120-second streaming body deadline, at most five redirects. Retry-After delays above 10 seconds defer the job; rate limiting (429) stops it. Transfer failures require an explicit retry; partial bytes are not resumed.

Optional Playwright runs only for an obvious JS application shell with no useful static links. It uses a new unauthenticated context, blocks service workers and WebSockets, rejects non-GET requests, and routes document/script/style/fetch/XHR loads through the same robots/host/rate controls. External scripts/CDNs are not exempt: some sites will remain unsupported. No fingerprint spoofing, login, CAPTCHA solving or anti-bot evasion. Browser fallback is best effort and off by default.

## Downloads and provenance

The download CLI handles selected reports only, from latest completed runs, skipping those already downloaded. It verifies MIME (`application/pdf` or binary/octet-stream variants) plus `%PDF-` signature, streams bounded bytes to a temporary file, computes SHA-256, and atomically moves the file to its content-addressed path. This checks transport/type, not PDF structural integrity, reporting scope or document truth. No parser or AI is invoked.

`report_artifacts` enforces global unique SHA-256 and storage path; a PostgreSQL advisory lock serializes identical blob writes. An existing artifact is checksum-verified before reuse, not blindly trusted. Each source remains a separate `reports` record with its own company, requested/detected year, URL, title, discovered-from URL, MIME, actual byte count/hash, confidence/reason, retrieval timestamp and outcome. MIME/size/time/hash stay NULL until observed; discovery time is separately available. Identical files may reference the first acquisition's canonical company/year path rather than create another copy. A crash between file rename and database commit may leave an unreferenced hash file, which a later identical download safely verifies/reuses. No automatic garbage collection deletes evidence.

## Status semantics

| Status | Meaning |
| --- | --- |
| discovered | Eligible primary PDF link selected; bytes/content not yet verified. |
| downloaded | Selected PDF retrieved and MIME/signature/checksum verified. Not metric validation. |
| needs_review | Ambiguous year/type/host, robots/access restriction, JS dependency, search bound, or unsafe/unexpected content. |
| unavailable | No eligible candidate within a completed bounded search, or selected URL returned 404/410. Not a global non-disclosure finding. |
| failed | Network/timeout/server/storage failure prevented completion. |

When candidates exist but none is eligible, the overall job is `needs_review`, even if some URLs failed; diagnostics preserve each cause. Successful selection can coexist with other blocked pages; the successful status does not imply complete crawling. The admin page exposes all retained alternatives and diagnostics. It is read-only, unauthenticated, and must remain on loopback.

## Reproducible commands

```bash
cd backend
source .venv/bin/activate
python -m alembic upgrade head
python -m app.cli discover-reports --year 2025 --limit 20
python -m app.cli download-reports --year 2025 --limit 20
python -m app.cli report-status --year 2025
```

Add `--company <stable-UUID>` repeatedly to bound the company set. Downloads never follow excluded alternatives automatically. CLI completion is not report-discovery success; inspect individual states and reasons.

Primary implementation references: [Requests streaming/timeouts](https://requests.readthedocs.io/en/latest/user/quickstart/), [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/), [Protego robots parser](https://github.com/scrapy/protego), [Playwright routing](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-route).
