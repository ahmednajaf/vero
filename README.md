# Vero

Company sustainability reports, source-backed peer analysis and exportable evidence in one workspace.

The existing globe, dark glass, navigation wheel and Sustainobot design are retained. The customer-facing pharma sample publication, race and fictional checkout are retired. Historical source files and database records are preserved, not replaced with sample data.

## Start

```sh
bash scripts/dev.sh
```

Open **http://127.0.0.1:5173/**. Existing local services: PostgreSQL **55433**, API **8000**, Vite **5173**. Startup applies migrations, never imports companies or runs AI automatically. See [local database setup and recovery](docs/local-workspace.md). Do not expose this unauthenticated local server publicly.

If running separately:

```sh
cd backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
# In another terminal, from the repository root:
cd frontend
npm run dev
```

### Fresh clone

Requires Python 3.12+, Node 22.18+ and Docker Compose (or PostgreSQL 17).
The repository includes code, tests, brand assets and the sourced company roster.
Local API keys, downloaded PDFs, PostgreSQL data/backups, generated results and
retired workspace snapshots are deliberately excluded. A clone is not a backup
of the live report library; preserve the database and `data/reports/` separately.

For a **new checkout only**, from the repository root:

```sh
docker compose up -d postgres
python3 -m venv backend/.venv
cd backend
.venv/bin/python -m pip install -r requirements-dev.lock
cp .env.example .env
export DATABASE_URL=postgresql+psycopg://sbi:sbi_local_dev@127.0.0.1:5432/sbi
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.cli import-company-snapshot data/company_universe_500.json
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
# In another terminal, from the repository root:
cd frontend
npm ci
npm run dev
```

Keep that database URL in your backend environment, or set it in `backend/.env`,
for later commands. Add your own OpenAI key only to `backend/.env` if enabling AI.
Importing the roster does not download reports or run inference; use the explicit
[collection commands](docs/BULK_COLLECTION.md) when ready. The existing-machine
`scripts/dev.sh` launcher above expects the already-provisioned local database.

## Use the product

The completed five-company energy packages are available locally:

- [Company benchmark](http://127.0.0.1:5173/workspace/analysis?briefing=83d39866-a0c6-4b98-8a02-8ca27791b213): 23-page PDF, formula-driven Excel workbook and contextual explanations.
- [Sector intelligence](http://127.0.0.1:5173/workspace/analysis?briefing=470c6d1c-f9e5-4c6d-b62e-a275a4d530f2): 28-page PDF, formula-driven Excel workbook and peer distinctions.

See [verified package delivery and source limitations](docs/REPORT_GENERATION.md).
Saved results and exports use no new AI calls. The dashboard's assistant action
explains the selected saved analysis, including its calculations and source inputs.

1. **Companies:** search/filter the real company registry; report availability is explicit.
2. **Company page:** open retained PDFs, inspect reported figures and their source pages, search report text, reopen saved analysis.
3. **Compare:** select a primary company and peers, choose topics, then explicitly generate analysis. Completed sections persist; failures do not erase them. Reported numerical figures remain separate from narrative findings.
4. **Sources:** search the report library by topic and inspect the supporting page. This requires no model call.
5. **Sustainobot:** ask source-backed questions with an explicit company scope. Citations open the same source drawer. Saved results reopen without inference.
6. **Export:** download the client PDF and Excel workbook, with HTML, evidence CSV and JSON as supporting formats. Formulas, original/normalised inputs and source-page links remain inspectable.
7. **Pricing:** proposed $5,000 company / $10,000 sector annual packages. Coverage must be agreed; there is no enabled checkout or claim that every company has complete data.

Opening a company page never starts AI. **Extract figures from selected reports** requires a metric and measurement year; it makes at most one model call per selected report for that metric and reuses cached results. This bounded extraction can miss evidence elsewhere in a report. Unreviewed figures are labelled, not silently admitted into rankings.

## OpenAI and cost controls

The backend explicitly loads **`backend/.env`**. Keep the API key there, never in browser code or chat. It is git-ignored. Do not overwrite the existing file with an example.

```dotenv
AI_PROVIDER=openai
KNOWLEDGE_AI_ENABLED=true
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-mini-2026-03-17
OPENAI_ALLOWED_MODELS=["gpt-5.4-mini-2026-03-17"]
OPENAI_DAILY_TOKEN_LIMIT=2000000
OPENAI_REASONING_EFFORT=low
OPENAI_MAX_OUTPUT_TOKENS=4000
OPENAI_TIMEOUT_SECONDS=90
OPENAI_INPUT_PRICE=0.75
OPENAI_OUTPUT_PRICE=4.5
KNOWLEDGE_MONTHLY_BUDGET_USD=5
```

Restart the backend after changing configuration. `GET /api/system/ai` checks model/key access with a metadata GET, **not inference**. Changing models requires changing both the selected model and allowlist. There is no silent fallback, automatic paid retry or inference at startup.

Vero reserves requests against the configured UTC-day token ceiling and monthly list-price estimate before calling; the example above uses **2M tokens / $5**. Unknown-usage failures retain reservations. These are **app-level guards, not a guarantee of free calls**: eligibility and any shared-data allowance must be checked in your own account, other applications share the organisation allowance, and quota-crossing requests can be billed. OpenAI billing is authoritative. Account data-sharing settings apply even with `store=false`. See [OpenAI eligibility terms](https://help.openai.com/en/articles/10306912-sharing-feedback-evaluation-and-fine-tuning-data-and-api-inputs-and-outputs-with-openai).

An allowance stop pauses the saved analysis; it does not delete completed steps.
`GET /api/knowledge/status` exposes the current app cap, accounted usage, unresolved
reservations and remaining allowance, without credentials or report text. The new
analysis form shows remaining allowance before generation. After an authorised
change to `KNOWLEDGE_MONTHLY_BUDGET_USD` in `backend/.env`, restart the backend and
choose **Continue unfinished topics** on the same saved analysis. Do not erase the
ledger or create a duplicate analysis to work around a limit. The local cap was
explicitly raised to **$10** on 14 October; the daily limit remains **2.5M tokens**.

## One application

```text
Official report links → bounded download → immutable PDF + SHA-256
    → physical pages / tables / chunks → PostgreSQL text search
    → selected passages → OpenAI structured output → evidence checks
    → saved figures / peer findings → Vero UI → source drill-down / exports
```

| Responsibility | Existing module |
|---|---|
| UI and shared visual shell | `frontend/src/app/ReportApp.tsx`, `components/` |
| API and validated contracts | `backend/app/api/` |
| Discovery, robots, redirects, domain pacing | `backend/app/discovery/` |
| Page-aware PDF text and tables | `backend/app/parsing/` |
| Search, chat, saved peer analysis, acquisition jobs | `backend/app/knowledge/` |
| Numerical evidence checks and unit normalisation | `backend/app/extraction/` |
| Shared hosted transport and token/cost guard | `knowledge/provider.py`, `knowledge/budget.py` |
| Structured-extraction adapter using the same provider | `backend/app/llm/openai.py` |
| Records, audit history and search index | PostgreSQL; existing Alembic migrations |
| Original documents | `data/reports/`; content-addressed, checksum-checked |

No additional database, queue service, vector service, cloud infrastructure, authentication system or billing integration was introduced. Legacy local extraction remains only for explicit CLI use and regression coverage; it is not the active product's fallback.

## Real coverage and collection

The registry has **500 companies**, not 500 completed report analyses. For current, database-derived counts:

```sh
curl -s http://127.0.0.1:8000/api/knowledge/status
cd backend
.venv/bin/python -m app.cli knowledge-status
```

See [collection/resume instructions](docs/BULK_COLLECTION.md). Collection checkpoints persist; restarting does not erase acquired reports. Official reporting hubs, relevant links and English sitemap branches are prioritised. Non-report archives/assets are skipped. Failed downloads, robots exclusions, anti-bot restrictions, unknown company CDN ownership and missing year evidence remain explicit. No bypass, invented PDF URL or synthetic metric fills a gap.

## Tests

```sh
cd backend
TEST_DATABASE_URL=postgresql+psycopg://vero@127.0.0.1:55433/vero_test .venv/bin/python -m pytest -o addopts='' -q
.venv/bin/python -m mypy app
cd ../frontend
npm test -- --run
npm run build
```

PostgreSQL tests use disposable schemas in `vero_test`, not production tables. Provider tests mock HTTP; optional live discovery tests are disabled by default. Live model calls are separate, explicit tests, never hidden in the test suite.

## Removed from the active product

Obsolete frontend routes/components and their feature tests are recoverable under `archive/legacy-frontend-20261008/`. The fixed pharma publication backend, publication scripts and corresponding tests are under `archive/legacy-research-20261008/`. Earlier source and design snapshots remain in `archive/`. PDFs, company records, evidence and migration history were not deleted. These archived files are not runtime dependencies.

## Release boundary

### Customer navigation and enquiry flow

The globe landing is preserved. Public navigation is Home, Workspace, Pricing and
How it works. `/workspace` holds saved analyses; `/workspace/new` selects a peer
group; `/workspace/analysis?briefing=<id>` shows actual progress, then results.
Company profiles and source reports sit under `/workspace/library`. Old company,
comparison and source URLs remain usable so saved links are not broken.

Analysis results separate Summary, Report, Findings, Figures, Disclosure gaps and
Sources. The chart-first summary adapts Efferd's Dashboard 4 composition to Vero.
Downloads prioritise a multipage PDF and a native Excel workbook; full evidence
CSV, JSON and HTML remain secondary. Browsing and exporting do not invoke AI.
The package-specific research, AI comparison proposals, deterministic arithmetic,
chapter-writing method and local workbook runtime are documented in
[REPORT_GENERATION.md](docs/REPORT_GENERATION.md). Existing saved analyses are
reformatted, not silently regenerated.

Pricing offers proposed $5,000 company and $10,000 sector annual editions. Package
requests go to `/contact?package=company` or `sector`, where visitors prepare an
enquiry for a consultation. With no sales address configured, the form downloads
a text brief and explicitly says it has **not been sent**. To enable an email
draft, set the public `VITE_SALES_EMAIL` in `frontend/.env.local` and restart Vite
(rebuild for production). It opens the visitor's email app; it does not send mail
from the server. No contact details are stored or sent automatically.

Consultation and client-account provisioning remain an operational step, not an
implemented registration or checkout service. The local workspace is not an
authenticated customer portal.

This is a local application with source search, company/peer research, saved results, numerical extraction, evidence drill-down and exports. It is **not yet an enterprise-hosted service or a complete 500-company metric dataset**. Complete report acquisition, broader measured extraction accuracy, agreed comparable periods/boundaries, access control and operational deployment remain release requirements. Pricing is proposed, not evidence of willingness to pay. Model schema/quotation checks are useful safeguards, not an audit or proof that every interpretation is correct.
