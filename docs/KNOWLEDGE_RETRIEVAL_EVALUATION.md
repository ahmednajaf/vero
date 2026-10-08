# Evidence quality and retrieval — 7 October 2026

## Outcome

The fixed exploratory regression set now passes **12/12 cases** across three retained official reports: Apple Environmental Progress Report 2025, Amazon Sustainability Report 2025, and Unilever Sustainability Statement 2025. Nine cases check that an exact report/page/quote anchor is supplied to the model packet; three check that every selected company contributes evidence. All three PDF hashes match the case manifest.

This is **retrieval regression coverage, not model accuracy**, not a held-out benchmark, not all-company validation, and not proof that these companies are suitable quantitative peers. The cases were used to diagnose and improve retrieval. Independent unseen cases and live answer evaluations are still needed.

No model was called. Provider cost: **$0**. Production database was queried in a repeatable-read, read-only transaction. No company, report, observation or answer records were inserted or updated. Existing source pages/metrics were preserved. No UI changes.

## Reproducible artifacts

- Case definitions: `data/knowledge_evaluation_cases.json` (report UUIDs, expected PDF hashes, physical pages, literal anchors).
- Runner: `scripts/evaluate-knowledge.py` (local database/PDF reads only; exits nonzero on failures).
- Initial result: `output/knowledge-evaluation-2026-10-07-v1.json` — 10/12, median retrieval 41.04 ms.
- Query breadth revision: `output/knowledge-evaluation-2026-10-07-v2.json` — 10/12, median 50.14 ms.
- Same-page context revision: `output/knowledge-evaluation-2026-10-07-v3.json` — 11/12, median 47.155 ms.
- Final result: `output/knowledge-evaluation-2026-10-07-v4.json` — 12/12, median **46.745 ms**.

These are sequential local retrieval timings on this small scope, not hosted inference latency or a load test. The initial failures and all intermediate outputs remain retained; expected answers were not changed to make tests pass.

From the repository root, with the existing `backend/.env` database settings:

```bash
backend/.venv/bin/python scripts/evaluate-knowledge.py \
  --output output/knowledge-evaluation-new-run.json
```

Use a fresh output path. The runner refuses to overwrite previous results. It does not load credentials into its output or make provider requests.

## Defects addressed

1. **Peer starvation:** global top-100 retrieval could exclude a company's entire report before company balancing. Window ranking now happens within each company first.
2. **Layout metadata consumed the prompt:** Unilever pages carried 11–38 KB of heading/font/bounding-box metadata. The metadata remains available in source records but is excluded from model packets.
3. **Word frequency beat relevance:** long passages repeating a generic term outranked shorter passages covering more query concepts. Term coverage now leads, with bounded frequency scoring as a tie-breaker.
4. **Window boundaries cut off evidence:** the top Unilever window began just after its reporting-boundary statement. One contiguous same-page text window can now accompany a company's lead passage; each retains its own ID and hash.
5. **Reporting calendar questions surfaced data tables:** generic “use” wording and repeated year labels displaced Apple's reporting-year definition. Question verbs are excluded, and fiscal/calendar questions get a generic reporting-definition section hint. No company-specific retrieval rules were added.

The evidence budget still applies. Companies omitted by that budget are explicitly listed, not silently represented as analysed or missing disclosures.

## Source-quality spot checks

Opening/source pages were checked from the retained PDFs; Apple cover, Amazon physical p. 2 and Unilever physical p. 3 were also rendered and visually inspected. Temporary images are in `tmp/pdfs/source-review-20261007/`.

| Source | Evidence | Meaning for analysis |
|---|---|---|
| Apple 2025 report | Physical p. 1 says it covers fiscal 2024; p. 124 explains fiscal/calendar usage | A 2025 filename is not evidence that the figures measure 2025. |
| Amazon 2025 report | Physical p. 2 specifies January–December 2025 unless otherwise indicated | Preserve exceptions and each metric's own year/boundary. Discovery title is just a generic download label. |
| Unilever statement | Physical p. 1 identifies the 2025 statement; p. 3 specifies the 2025 period and Ice Cream demerger scope | The downloaded file is useful despite unknown discovery-year metadata; excluding Ice Cream affects year-on-year comparison. The year metadata was not silently rewritten. Physical p. 3 is printed p. 214. |

These are source observations, not sustainability performance ratings. Discovery titles, report roles and company-name matches remain explicitly heuristic. The new read-only inspection endpoint returns warnings and relevant excerpts rather than rejecting all useful text pending expert review.

## Try the actual backend

```bash
curl -s http://127.0.0.1:8000/api/knowledge/preview \
  -H 'Content-Type: application/json' \
  -d '{"question":"How do suppliers reduce emissions?","company_ids":["01900000-0000-4000-8000-000000000005","08d230e9-7989-5fe8-8548-92ef31dd3069","01900000-0000-4000-8000-000000000015"]}'

curl -s http://127.0.0.1:8000/api/knowledge/reports/6e186818-f8a7-451d-94b7-40841dd782fd/inspection
```

`preview` uses the exact same evidence-selection function as `/ask`, without invoking a model. Returned citations include report URL, PDF hash, physical page, text hash and an evidence ID. Fetch full context through `/api/knowledge/evidence/{id}` or open the PDF page URL. Source inspection rechecks file bytes; preview's source checks explicitly do not.

## What still prevents a live AI evaluation

Current configuration: hosted research disabled, OpenAI API key absent, model unspecified, approved monthly budget zero. Nothing was enabled or substituted. The installed local model is Gemma 3 4B (~3.3 GB); its existing extraction evaluation is too weak to silently treat it as a dependable replacement.

Enter any approved API key **locally in `backend/.env`, never in chat**, choose an explicit model and current token rates, set an approved application budget, then restart the API. Exact variables and commands are in [the backend setup](KNOWLEDGE_BACKEND.md#openai-setup-not-yet-live-validated). A ChatGPT subscription is not used as an API credential by this backend.

Once configured, run a separate held-out answer evaluation: correct company/period/boundary, accurate interpretation, complete citations, unsupported inference, latency and actual usage. Existing mocked-provider tests validate transport/schema/citation/budget/cache behavior, not real model reasoning. No inference latency, live-model accuracy or five-report AI cost is claimed here.

The adapter follows the official [Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs); the distinction between regression development cases and independent evaluation follows [evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

## Verification completed

- Backend: **537 passed**, two optional live tests skipped; six existing dependency deprecation warnings.
- Frontend: **105 passed**; TypeScript checking and production build passed. Existing large globe-bundle warning remains; no frontend source was changed.
- Python typing: passed across 89 application files. Ruff passed on changed Python files.
- Through the live frontend proxy on port 5173: readiness, corpus status, three-company evidence preview, three evidence endpoints, Apple file inspection and the retained PDF all returned HTTP 200. The PDF signature and recorded checksum were checked.
- Three-company HTTP preview: 148 ms in one smoke call, no model call. Library-wide preview: 3.482 seconds in one smoke call, 500-company roster, six companies supplied and 202 matching companies explicitly omitted by the context budget. This confirms bounded behavior, **not** complete all-company analysis or production load capacity.
- Live coverage remains **214 companies with searchable sources**, including **211 with primary-report candidates**, out of the 500-company roster. No acquisition ran in this step. Source inspection warnings do not remove the underlying searchable text.

Changed implementation files: `backend/app/knowledge/search.py`, `research.py`, `provider.py`, new `inspection.py`, and `backend/app/api/knowledge.py`. Regression tests: `backend/tests/test_knowledge.py` and `test_health.py`. New evaluation runner/cases/results and updated README/backend documentation provide reproduction and handoff. No migrations, credential changes or model downloads were needed.
