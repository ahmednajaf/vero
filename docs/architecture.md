# Vero architecture

One React website, one FastAPI application, one PostgreSQL database and retained
PDF files. Collection is a command in the same backend, not a separate service.
OpenAI is an explicitly invoked analysis provider, never the source of truth.

```text
Official company links → robots-aware download → original PDF + SHA-256
    → page-aware parsing → PostgreSQL full-text index
    → company/source browser, scoped search
    → selected passages + structured OpenAI response
    → evidence checks → saved findings / figures → comparison and exports
```

## Where each responsibility lives

| Layer | Existing code | Responsibility |
|---|---|---|
| Customer interface | `frontend/src/app/ReportApp.tsx` | Globe, company library, peer analysis, source drawer, Sustainobot and pricing |
| HTTP contracts | `backend/app/api/` | Pydantic-validated requests/responses; no browser secrets |
| Acquisition | `backend/app/discovery/` | Official source policy, exact publishing links, redirects, robots, pacing, retries and hashes |
| Parsing | `backend/app/parsing/` | Immutable physical-page text, table candidates and explicit OCR gaps |
| Knowledge | `backend/app/knowledge/` | PostgreSQL retrieval, persistent collection jobs, cited answers, saved briefings and call budgets |
| Numerical extraction | `backend/app/extraction/` | Original values/units, metric/year evidence checks and deterministic conversions |
| Provider adapter | `backend/app/llm/openai.py` | Reuses the hosted transport/budget guard for structured numerical extraction |
| Quantitative rules | `backend/app/benchmarking/` | Compatibility gates and deterministic statistics; unreviewed text is not a ranking |
| Storage | PostgreSQL + `data/reports/` | Identity, provenance, pages, observations, runs and original document bytes |

The active model and safe configuration are exposed through `/api/system/ai`.
The current pinned model and conservative app-level limits are documented in the
[README](../README.md). No automatic inference, model fallback, extraction or
collection starts when someone opens a page. There is no queue broker, vector
database, extra microservice, cloud deployment or billing service.

## Evidence boundaries

- A downloaded PDF is a retained company disclosure, not verified performance.
- A parsed/indexed report can still have missing image-only text. No bulk OCR is
  run silently. Report-label year is distinct from the period of each fact.
- A cited AI answer is an interpretation of retrieved passages. Schema and quote
  checks reject unsupported output, but cannot prove every interpretation correct.
- Reported figures can be inspected before review. Original units, year, boundary
  and conflicting values remain visible. Missing values are never zero.
- Peer statistics require compatible definitions, periods, units and boundaries.
  Renewable electricity and renewable energy, targets and results, and different
  Scope 2 methods remain separate. Vero is not an independent ESG rating.

## Operations and current limits

Run `bash scripts/dev.sh`; services bind to loopback only. The backend explicitly
loads `backend/.env`, with keys kept out of frontend bundles and logs. Back up the
database **and** `data/reports/`; neither alone restores the evidence library.

Collection uses persistent company/year jobs and frozen cohorts. It attempts all
selected companies, preserves successful work and reports failures. A completed
pass is not synonymous with complete coverage. See [collection policy](BULK_COLLECTION.md).

The registry contains 500 real identities, not 500 verified report analyses.
`/api/knowledge/status` provides live coverage; dated audits belong in `outputs/`.
The S&P-heavy roster is not a worldwide largest-company census. Complete source
acquisition, measured extraction accuracy, deployment and enterprise access
controls remain release requirements. Do not expose the local server publicly.

Retired product implementations and their tests are recoverable in `archive/`.
Historical design documents are under `docs/archive/`. Database migrations,
retained company evidence and original reports have not been deleted.
