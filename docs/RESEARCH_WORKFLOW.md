# Vero research and company intelligence

The active application is one React workspace and one FastAPI/PostgreSQL backend.
The globe, silk background, wheel navigation and charcoal/indigo chat remain in
place. Company, source, comparison, saved-analysis and chatbot views share the
same retained report evidence.

## Customer surfaces

- Landing (`/`): unchanged region explorer and Sustainobot launcher.
- Company library (`/companies`): searchable, paginated, sector/country/report
  availability filters. A registry entry is not a completed analysis.
- Company profile: report coverage, last collection reason where unavailable,
  source documents, report search, contextual chat and saved company/peer analyses.
- Compare (`/compare`): company analysis with zero to four peers, six selectable
  research topics and optional additional focus. Source-comparison and reviewed
  pharmaceutical metrics are retained as explicit alternative views.
- Insights (`/overview` or `/insights`): real library coverage and saved analyses.
- Sources (`/sources`): official PDFs and page-aware search. Evidence buttons use
  the existing source drawer; no source URL is invented by the model.
- Historical reviewed publication (`/edition`): existing pharma charts and PDF/
  workbook remain accessible, clearly separate from the wider report library.

## Research engine

1. Validate the selected scope and previous user questions.
2. Ask the configured OpenAI model for a bounded plan: intent, up to three queries,
   named companies, explicit filters and comparison basis.
3. Resolve companies within the selected scope. Unknown names do not expand the
   search to unrelated companies.
4. Search PostgreSQL's lexical index, fuse complementary query results and balance
   passages across companies; preserve nearby page context. No whole-PDF upload.
5. Supply the bounded evidence packet to strict structured-output synthesis.
6. Validate the response again with Pydantic, exact excerpt/source checks and
   numerical checks. Equivalent numeric formatting is accepted without arithmetic
   or unit conversion; page references are checked against source metadata and
   Scope 1/2/3 identifiers against cited passage context, rather than confusing
   them with measured quantities. Reject unsupported statements independently and retain useful
   partial findings with a visible warning.
7. Persist the answer, source metadata, model, prompt version, coverage, actual
   token usage and estimated cost. Never write AI answers into validated metrics.

This is not semantic verification. A verbatim citation may still be misinterpreted;
table rows, units and reporting boundaries can still require checking.

Broad questions return supported examples, not an invented population ranking.
Reported comparisons can be useful when different periods or scopes prevent a
like-for-like calculation. Targets remain separate from achieved performance.
Exact library counts come from SQL, not model estimation. Quantitative peer
percentiles still require the existing benchmark engine's eligibility rules.

## Saved analysis

`peer_briefings` stores a primary company, optional peers, frozen report IDs and
index fingerprints, topic states and answers. Migration `k261008` is additive;
no existing company, report, metric, history or source file is removed.

Creating an analysis is free. An explicit Generate/Continue action advances one
topic at a time through the same research engine. The browser requests the next
topic after the previous one completes. A navigation away stops scheduling new
topics, not the already submitted request. Reopening requires only GET requests.
Continue runs unfinished topics, preserving successful work. A per-analysis
lease prevents concurrent advancement; expired leases expose a paused state.

The research engine reserves a conservative two-call budget before inference.
The configured monthly application cap is unchanged. Failed requests can retain
their cost reservation because the remote outcome may be unknown. A process
crash leaving a `knowledge_answers` row running still needs the existing explicit
operator recovery command; the UI does not silently retry an uncertain paid call.

## Evidence coverage, not a score

The company/topic matrix is computed from saved citations and retrieval metadata:

| State | Meaning |
|---|---|
| Evidence cited | An accepted finding cites this company's report |
| Needs a closer look | Passages were supplied, but no accepted finding cites this company |
| Not identified | No cited finding or supplied passage for this company/topic |
| No searchable report | No current searchable report within the frozen selection |
| Not analysed | Topic has not completed |

Gaps to investigate identify topics with cited peer evidence but no cited primary-
company finding. Counts describe selected peers in this analysis, not an exhaustive
disclosure census. Neither missing retrieval nor missing synthesis proves absence.

## API and exports

- `POST /api/knowledge/briefings` — save primary company, peer IDs, topics, focus.
- `GET /api/knowledge/briefings?company_id=UUID` — latest 50 matching analyses.
- `GET /api/knowledge/briefings/UUID` — saved progress, findings, matrix and gaps.
- `POST /api/knowledge/briefings/UUID/advance` — explicitly process next unfinished topic.
- `GET /api/knowledge/briefings/UUID/export?format=html|csv|json` — no model call.

HTML is a standalone printable briefing (Print → Save as PDF). CSV includes
topic status, statement, company, report year, physical page, quotation, URL,
hash, model, answer ID, source freshness and limitations. Spreadsheet formula
prefixes are escaped. HTML escapes untrusted text and restricts URL schemes.
JSON retains the complete analysis and provenance. Incomplete/stale results are
labelled, not silently represented as a completed current report.

## Evaluation

`data/research_workflow_cases.json` and `scripts/evaluate-research-workflow.py`
contain the twelve-question research test set. By default the script only lists
cases. `--live --case CASE_ID` explicitly enables a budgeted model call.

Earlier live tests on 8 October included a broad net-zero question, named-company
comparison, report-period lookup, biodiversity discovery, assurance discovery,
database counts, an unknown company and a grounded follow-up. Some answers were
partial; a draft follow-up statement failed a numerical check and was withheld.
These examples establish exercised behaviour, not a measured semantic accuracy
rate. See `outputs/research-workflow-live-20261008*.json` for saved runs.

### Connected product verification — 8 October 2026

Live saved analysis `321d3ebe-3490-435a-90b8-3ee6fe3fdf2d` used the retained
Apple, Samsung and NVIDIA reports, the configured `gpt-6.1-sol` model and prompt
`report-research-v4.4-citation-metadata`. All four requested topics completed:
emissions, energy, targets and assurance. There are 18 accepted cited findings;
one energy draft was withheld because its claimed year was not in the quotation.
The result is explicitly **partial**, not a verified complete benchmark.

Total measured topic processing was 131.52 seconds, with $0.163954 estimated usage
at the configured rates (before any account promotions). Three bounded live runs
were used to diagnose and verify the numeric check; the earlier saved attempts
are retained, not overwritten. This is a functional smoke test, not an extraction-
accuracy benchmark. Source drawer and CSV download were exercised in the browser.

Reopen this analysis at `/compare?briefing=321d3ebe-3490-435a-90b8-3ee6fe3fdf2d`.
Reopening/exporting makes no model call. An additional report arrival is shown
separately; it does not silently change the frozen source set.

Verification: 598 backend tests passed, with two optional live tests skipped;
131 frontend tests passed. Python and TypeScript type checks, focused Ruff checks
and the production build passed. Browser checks covered saved overview, company
profile integration, a concrete missing-report reason, four-topic live analysis,
source drawer, evidence matrix, no-gap state, scoped chat opening and CSV download.
The existing large globe bundle still produces a build-size warning. Protected
globe/background/sidebar/bootstrap/glass-style files match the UI baseline.

Known live retrieval limitation: the Apple target section found assurance
evidence rather than the main target statement. It correctly limits what it
claims, but relevant facts can still be missed. Accepted findings are not proof
that every disclosure in a report has been covered or semantically verified.

## What is not claimed

This is a local single-operator application, not an authenticated hosted service.
It is not a complete 500-company extracted metric database, a verified industry
ranking, an audited ESG research service, or a finished commercial annual report.
New acquisitions do not automatically produce reviewed metrics or annual trend
series. The same useful application can serve partial coverage without disguising
those outstanding data-production tasks.
