# Vero local workspace

## Start the working app

From the project root:

```sh
bash scripts/dev.sh
```

Open http://127.0.0.1:5173. Leave the terminal running. The command starts the existing local PostgreSQL instance if needed, applies migrations, and starts the API and Vite when they are not already responding. It never imports companies, downloads reports, invokes Ollama or approves observations. Ctrl-C stops only processes started by this invocation; PostgreSQL remains available.

The dedicated database uses loopback port **55433**, database/user **vero**, with PostgreSQL 17 under `/opt/homebrew/opt/postgresql@17/bin`. Override `VERO_PG_BIN` for another compatible installation. Its private data directory is `backend/storage/runtime/postgres`; runtime data and `.env` are git-ignored. This is a local trusted development database, not a public deployment. Do not expose its port or use this configuration in production.

The ignored `backend/.env` points ordinary backend CLI commands at this same database. The active product uses the server-side OpenAI configuration in the root README. Legacy local-model settings are not an automatic fallback. The original saved backup was not modified.

Current architecture and routes are documented in [architecture](architecture.md)
and [frontend](frontend.md). The dated recovery record below is historical, not
today's company/report count. Use `/api/knowledge/status` for live coverage.

## Recovery performed, 29 September 2026

- Restored `backend/storage/verification/batch-checkpoint-2026-09-29.dump` into a new, dedicated database, then migrated to `d40e179a21c6`.
- Imported `data/company_universe_200.csv`: 183 inserts, 17 updates, zero rejected rows. No sustainability observations were added or approved.
- 200 pilot companies, 40 per sector, plus 3 retained research companies (Samsung, Saudi Aramco and Santander): **203 searchable companies**, 16 markets overall.
- 4 downloaded reports, for Apple, Samsung (two years) and JPMorgan Chase. Downloaded is not the same as complete company-wide reporting; the JPMorgan document is a sustainable-bond report.
- 13 retained metric observations: 12 `needs_review`, 1 `rejected`, 0 `validated`. The source library shows every state, not just benchmark-eligible observations. Duplicate or conflicting candidates are retained independently.
- The failed five-company checkpoint remains failed. No 20- or 200-company pipeline was started, and no collection, OCR, model inference or automatic approval was performed during this repair.

## Historical research flow — 29 September

Search a company from the globe or Companies. Filter Companies by “Reports available” to find saved evidence. Company profiles show all performance years, original reported values, validation states and report links. “View source” shows the excerpt, physical PDF page, raw and normalised values, review rationale and document checksum. The saved-PDF route verifies the bytes before serving them inline.

Compare supports two separate views: reported claims grouped by metric/year/raw unit, and peer benchmarks. Reported claims are never ranked or silently pooled. Benchmark outages do not prevent searching companies or opening their evidence. A missing library response is shown as unavailable, not zero coverage.

The globe uses country anchors for company domicile only. It does not depict ozone, emissions or progress towards net zero. The Race displays only eligible engine-provided rankings; the production fictional-demo entry point was removed. Ranked cars, calculations and synthetic fixtures remain tested independently.

## API additions (read-only)

```text
GET /api/library
GET /api/companies/{company_id}/evidence
GET /api/reports/{report_id}/file
```

The file endpoint takes a report UUID, not an arbitrary filename; it enforces root containment, a file-size limit, PDF signature and SHA-256 equality. It returns 404 for missing/unsafe paths and 409 for mismatched bytes. No mutation/review endpoint was added. Existing validation and comparability gates are unchanged.

## Verification

```sh
cd frontend
npm run build
npm test
cd ../backend
.venv/bin/mypy app
TEST_DATABASE_URL=postgresql+psycopg://vero@127.0.0.1:55433/vero_test .venv/bin/pytest
```

The test database is separate; each PostgreSQL test creates and removes its own temporary schema. Optional live-site tests remain disabled. Do not point `TEST_DATABASE_URL` at the research database.

## Fresh-machine setup

The startup command intentionally fails if its local cluster is missing. Follow the main README for a fresh PostgreSQL installation and environment setup. Restore a saved dump only into a new empty database, never over an existing research database. Set `DATABASE_URL` explicitly before migration/import commands. The brand assets and all frontend/API code are in the project; PostgreSQL runtime files and source PDFs are not committed.
