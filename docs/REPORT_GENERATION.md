# Client report generation

## Active method: master analytical brief

New Company benchmark and Sector intelligence runs start from one master brief:
`backend/app/knowledge/prompts/peer_report_v1.txt`.
`analytical.py` supplies its analytical assignment to the existing OpenAI adapter,
with a strict, task-specific Pydantic contract from `analysis_contract.py`.
The existing PeerBriefing record, stage runner, source index, cost ledger and
dashboard are reused. No extra service or database is introduced. Saved older
analyses keep their original method; opening one never regenerates it.

The brief defines the job from the buyer's perspective: discover relationships,
test promises against delivery, connect financial/operational/people data,
propose multi-step calculations, analyse qualitative differences, design meaningful
awards and apply an explicit peer-disclosure deduction policy. It specifies the
two packages and what the report, workbook and dashboard should communicate.
Metric ideas are examples, not a closed catalogue or preassigned winners.

The runtime separates four responsibilities:

1. **Collect:** retrieve page-aware passages in climate/transition, people/social,
   and finance/innovation lenses for every selected company. Extract numerical and
   qualitative facts, commitments and checklist assessments. Keep exact source IDs,
   excerpts, units, periods and populations. No prior Vero summaries become evidence.
2. **Analyse:** apply the master brief across those grounded ledgers. The model
   proposes questions, multi-input formulas, findings, award criteria and an outline.
   There is no schema limit of ten findings; each call still has the configured
   output-token limit. With `master-analysis-v1.5`, a continuation is requested only
   when output capacity prevents concrete, distinct remaining analysis. Missing
   disclosures, research questions and alternative wording are not reasons to keep
   generating. There is no minimum quota of metrics or awards. Truncation
   is an error, not a silently shortened report. Collection also partitions its
   retrieved passages into saved batches. Model packets exclude bulky parser
   metadata, and use short fact references resolved back to permanent IDs.
3. **Calculate:** execute named arithmetic steps with Decimal, deterministic unit
   conversions and dimension checks. No model-supplied code is executed. Calculate
   winners and ties from the returned inputs; qualitative awards require a common
   cited rubric. Disclosure deductions use the frozen peer-common checklist.
4. **Publish:** assemble the AI-authored headline, takeaway, explanation and business
   implication already returned by analysis. Do not pay a second model call to
   rewrite the same findings. Calculations and award rubrics have their own schedules.
   The shared publication read model feeds the dashboard, PDF, HTML and formula-driven
   workbook. Historical written chapters are retained; later rewrites of the same
   record do not appear repeatedly in the publication. Raw variants remain in JSON.

The dashboard leads with calculated values, a selectable comparison chart, peer
distinctions and the disclosure scorecard. Findings, promises, source detail and
downloads are separate, readable views. It does not substitute a source-count or
findings-per-topic chart when no calculated metric exists.

The disclosure scorecard and promise register are aggregated from all collection
lenses, not from the first analytical response. Dashboard and exports share that
whole-report summary. Source evidence stays one click away; workbook cells contain
source links rather than page-length excerpts.

The score policy is `peer-common-equal-v1`: a checklist item is common when at least
two and at least half of the selected companies disclose it. Each common item has
equal weight. An identified omission after a completed search earns a deduction;
an incomplete search remains pending. This score measures disclosure, not overall
company sustainability. The deterministic tests cover deductions, ties, incomplete
searches, cross-currency ratios and multi-step conversions.

### Fixed experiment

`data/prompt-evaluation/energy-analysis-v1.json` selects raw pages from six retained
official reports for Aramco, Shell, TotalEnergies, Equinor and Eni. It also holds
twelve researcher-authored evaluation cases, kept separate from model input.
The test covers positive analytical value as well as mistakes: portfolio versus
operational change, cross-report social-spend ratios, representation, training
gaps, credit strategy, AI outcomes, promise delivery, safety and awards.

Prepare both package inputs without an API call, database writes, prior Vero
summaries or precomputed edition findings:

```sh
cd backend
.venv/bin/python -m app.knowledge.prompt_trial --package sector
.venv/bin/python -m app.knowledge.prompt_trial --package company \
  --primary-company-id 01900000-0000-4000-8000-000000000012
.venv/bin/pytest tests/test_prompt_trial.py
```

The preparer uses locally retained page-aware JSON in `tmp/energy-2025`, checks
the original PDF byte hashes, and writes `tmp/prompt-trials/peer-report-v1-*.json`.
Those ignored files include the exact developer/user messages, prompt fingerprint,
input fingerprint and per-page text hashes. It refuses to overwrite a baseline;
use `--output` for a new trial. The local corpus is not bundled with the repository:
a clean checkout needs the matching reports and parsed pages before preparation.

The `review_only` section, expected arithmetic, previous editorial claims and local
file paths do not enter model messages. Selected pages are explicitly partial
coverage, so this test cannot establish full-report recall or final missing-item
penalties. A later completed-search fixture tests the disclosure score mechanics.

### Refinement protocol

1. Review the master brief and proposed score policy, not another dashboard mockup.
2. With an explicitly approved API budget, run the configured model against the
   frozen input. Keep the raw response, model/settings, actual token usage, cost,
   latency, prompt/input fingerprints and any truncation or refusal.
3. Grade each of the twelve cases 0/1/2 using the separate rubric; record missed
   relationships, unsupported claims, formula errors and worthwhile discoveries
   not anticipated by the rubric. Review usefulness and specificity, not only JSON.
4. Classify failures as missing input/retrieval, extraction, analytical proposal,
   arithmetic, scoring or writing. Change the responsible part rather than
   masking failures with UI changes. Change one prompt hypothesis at a time.
5. Rerun against the same input and settings; preserve v1 and its failures. Use
   held-out reports/pages before claiming generalisation. Repeated runs measure
   consistency; a single attractive output is not reliability evidence.
6. Once the analysis is good, implement/verify its calculation and score contract,
   test PUBLISH mode using executed results, and connect the saved output to the
   existing client deliverables and dashboard.

No API budget is consumed by the preparation command. Runtime quality needs a live
test; passing the mocked tests alone is not an extraction-accuracy claim.
The method follows the task/input/review
iteration described in the official [prompt engineering](https://developers.openai.com/api/docs/guides/prompt-engineering)
and [evaluation](https://developers.openai.com/api/docs/guides/evals) guides; those
guides do not establish whether this Vero prompt performs well.

## Current delivered packages — 14 October 2026

Both packages have completed against six retained official reports for Saudi
Aramco, Shell, TotalEnergies, Equinor and Eni. No synthetic company figures were
added. The existing globe, dark/glass shell and chart-first dashboard are retained.

| Package | Saved analysis | Completed stages | Findings | Calculated metrics | Awards | PDF |
| --- | --- | --- | --- | --- | --- | --- |
| Sector intelligence | `470c6d1c-f9e5-4c6d-b62e-a275a4d530f2` | 86/86 | 18 | 9 | 5 | 28 pages |
| Company benchmark | `83d39866-a0c6-4b98-8a02-8ca27791b213` | 79/79 | 15 | 8 | 3 | 23 pages |

Open either using `/workspace/analysis?briefing=<id>`. Neither has a resumable
stage. All five disclosure checklists are complete: Aramco has seven of eight
peer-common items identified; the other four have eight of eight. The 71-item
promise register is included in each workbook. Database quality status `partial`
retains rejected analytical proposals in the audit; it does not mean a job is
still running. Rejected proposals do not appear as published findings or awards.

Deliverables:

- `output/pdf/Vero-sector-benchmark-2025.pdf`
- `output/pdf/Vero-company-benchmark-2025.pdf`
- `outputs/vero-energy-peer-intelligence/Vero-sector-benchmark-2025.xlsx`
- `outputs/vero-energy-peer-intelligence/Vero-company-benchmark-2025.xlsx`

Both workbooks have seven sheets: Findings, Comparisons, Inputs, Sources,
Scorecard, Reported data and Promises. Sector has 99 native formulas and 766
hyperlinks; Company has 129 formulas and 761 hyperlinks. No Excel error cells
were found. Formula-change/recalculation tests use Artifact Tool, not a claim
of manual verification in the Microsoft Excel desktop application. PDF pages
and workbook previews were visually checked. PDF/XLSX/HTML/CSV/JSON exports
return HTTP 200 for both packages.

### Live contextual assistant

`POST /api/knowledge/briefings/{identifier}/explain` accepts `question` and up to
three `previous_questions`. It uses the **published saved calculations, awards,
disclosure scores, findings and original reported inputs**. It does not restart
report discovery or substitute an unrelated library search. Strict output-schema
references point to actual records; source buttons open the original report pages.
Follow-ups retain the analysis context. Changing the selected peers leaves that
context and starts ordinary library research.

The explanation adapter reuses the existing model provider, usage ledger and
content cache. There is no new service or database. Internal generation calls are
excluded from chat history. Identical questions/context replay without inference;
source ordering is canonicalised so a server restart cannot invalidate the cache.
Chat answers are concise; extra citation pages expand on demand. The full report
does not inherit chat's five-paragraph answer limit.

Verified live: a broad peer-differences explanation and a numerical training-gap
follow-up. Eni's cited female/male averages are 27.5/35.9 hours; Equinor's are
22.6/28.7 hours. Vero's stored Eni gap is -8.4 hours. A repeated identical request
returned `cached=true`, `model_called=false`, and the same answer ID.

### Model and quality corrections

The model remains `gpt-5.4-mini-2026-03-17`, low reasoning. Completed extraction
batches were reused rather than paid for again. New analytical calls, focused
finding checks and award-criterion checks completed both packages. A small earlier
fixture scored mini 11/12 and nano 10/12; that is not report-wide accuracy.

Real-response corrections included Scope 3 category/total confusion, an annual
versus decade-long return calculation, company attribution in training data, and
an innovation award incorrectly attached to training growth. Duplicate conflicting
awards were excluded. PDF units, table years, arithmetic constants and ordinary
typographic variations no longer wrongly reject valid calculations/explanations.
Unknown references, changed numerical quotes and unsupported results still fail.

Final verification: **812 backend tests passed, two optional tests skipped**;
Python type checking passed for 98 source files. **94 frontend tests passed**,
along with TypeScript checking and the production build. Browser checks verified
PDF and Excel downloads, the saved contextual answer and its source-page drawer.
The Excel endpoint completed in 3.4 seconds; the final live explanation took
4.38 seconds and cost approximately $0.0201. Its immediate replay made no model
call and returned the same saved answer.

The follow-up functionality gate also verified all ten export endpoints across
both packages and checksum-matched all six original PDFs. The global assistant
button now loads the active saved analysis and its peer group before opening;
it cannot silently fall back to general library research when that load fails.
Two regression tests cover that context and failure path. No landing-page design
or workspace styling was changed for this repair.

The saved usage ledger totals **$6.41946835**, including earlier uncertain-call
reservations. The user-authorised local app spending ceiling is **$7**. Usage and previous
unknown-call reservations remain intact; no free allowance is assumed. Live chat
checks have taken roughly 3–13 seconds and about $0.02 per response on these
inputs. Iterative development spend is not a future per-report price estimate.

This verifies a local five-energy-company product workflow, not complete
500-company report coverage, external factual certification, authenticated
enterprise hosting or a working commercial checkout. The missing sales email
remains explicit: enquiries can be downloaded, but are not silently sent.

## Previous energy edition — 13 October 2026 (historical)

Open the saved edition:
<http://127.0.0.1:5173/workspace/analysis?briefing=ffe0189e-484c-4f2d-8387-717eab039241>.
The backend, PostgreSQL and frontend must be running using the README commands.
Opening this edition or downloading its files does not call a model.

| Item | Verified result |
| --- | --- |
| Cohort | Saudi Aramco, Shell, TotalEnergies, Equinor, Eni |
| Input documents | Six real, locally retained official annual/sustainability PDFs |
| Processing | All 109 saved stages completed; no resumable stages remain |
| Extracted material | 592 collected fact records from 57 source pages; not 592 independently distinct metrics |
| Publication | 47 written sections, 10 distinct calculated comparisons, 6 peer distinctions, 71 commitments |
| PDF | 40 pages, 47 official source links; all pages visually checked |
| Workbook | Seven sheets, 123 formulas, 794 native hyperlinks; no cached Excel error cells |
| Downloads | PDF, XLSX, HTML, CSV and JSON return HTTP 200 |
| Browser | Desktop/mobile reading, chart switching, source drawer, saved source PDF, PDF/XLSX downloads; no console errors observed |

Final regression checks: **778 backend tests passed, two opt-in live tests skipped;
91 frontend tests passed.** Python type checking (97 files), TypeScript checking,
production build and `git diff --check` passed. Existing dependency deprecation
warnings and the large globe-bundle warning remain.

The workbook keeps findings, comparisons, inputs, source index, scorecard, reported
data and promises separate. Calculations remain Excel formulas; source links replace
long excerpts. Tests change inputs and recalculate isolated workbooks using Artifact
Tool; this is not a claim that every formula was manually tested in Microsoft Excel.

Local deliverables:

- `output/pdf/Vero-energy-peer-intelligence-2025.pdf`
- `outputs/vero-energy-peer-intelligence/Vero-energy-peer-intelligence-2025.xlsx`
- Acceptance ledger: `tmp/completion-verification/final-acceptance.json` (ignored).

### Models, usage and availability

The configured model is `gpt-5.4-mini-2026-03-17` with low reasoning. This saved
edition also contains earlier/rescue analytical responses from `gpt-5.4-2026-03-05`;
it is not a single-model controlled experiment. The small extraction comparison
scored mini 11/12 and nano 10/12 on its fixed cases. That is **not** report-wide
factual accuracy or full-report recall.

The approved spending baseline was $1.81902925. Additional accounted usage is
$3.34237560 of the $4 approved extension, retaining unknown-call reservations.
Total accounted spend is $5.16140485, below the approved $5.819 ceiling.
The current run has $2.811012 of known model usage plus a retained $0.518605
unknown-call reservation. Earlier experiments retain their own reservations.
Known usage for this run is 1,649,488 input and 223,043 output tokens. These are
application estimates, not invoice reconciliation. This iterative run's cost
must not be presented as a reliable future per-report price.

The 2.5-million daily application token guard was reached during late editorial
rewrites. No further model calls or budget increases were made. Saved analysis and
exports work; fresh generation and live chat need available quota. The unnecessary
paid publication rewrite has now been removed. The final pipeline changes have
offline end-to-end coverage for both packages, but have not received a fresh
complete live run after that guard was reached.

### Remaining quality limits

- The saved database quality state is `partial`, not an unfinished job: rejected
  proposals and six pending checklist checks remain in the audit. The UI shows
  identified coverage rather than giving pending searches zero scores. Shell has
  a completed 8/8 checklist; Aramco, TotalEnergies, Equinor and Eni still have checks
  to resolve. Aramco has one explicit Scope 3 search-based deduction.
- Exact duplicate calculations and repeat writing are removed from the publication.
  A named award keeps its first supported rubric instead of changing winners on a
  continuation. Unsupported zero-point and qualitative timing awards are excluded.
  Related qualitative angles still overlap; 47 written sections does not mean 47
  independently novel discoveries.
- No comprehensive independent factual audit, extraction-recall study, 500-company
  coverage or enterprise deployment acceptance is claimed. Cited report text is
  supporting evidence, not proof of causal interpretation.
- Workbook rendering uses the configured bundled local runtime. A portable hosted
  deployment still needs an explicitly provisioned renderer. The existing globe
  bundle size warning remains.

## Earlier $0.30 experiment — 13 October 2026 (historical)

The implementation is active, but this was **not a complete five-company report
acceptance pass**. The user approved a total incremental API ceiling of $0.30.
No free-token allowance was assumed and the configured model was not changed:
`gpt-5.4-mini-2026-03-17`, low reasoning.

Six retained official PDFs for Aramco, Shell, TotalEnergies, Equinor and Eni were
hash-checked, parsed and indexed. No synthetic company metrics entered the app.
The first broad collection request exposed oversized parser metadata and hit the
output limit. The packet builder now excludes that metadata and splits passages
into resumable small batches. A subsequent focused climate/transition run reused
the same remaining budget, with a 4,500-character retrieval ceiling per company.
This narrowed run does not substitute for all ten research topics or the twelve
full evaluation cases above.

| Check | Observed result |
| --- | --- |
| Broad run | `cf8aa59f-3a83-4311-9a27-26b44caace04`; 1 of 23 stages saved |
| Focused run | `a8d26887-d7a4-4441-a25e-7dbc0cdad6f1`; 8 of 10 current stages saved, further analysis requested |
| Collection | All five companies called; 30 grounded fact records retained |
| Calculations | Two calculated comparisons, using Aramco, Shell and Eni; not five comparable entrants |
| Awards | One computed methane criterion winner; not an overall sustainability ranking |
| Writing | Two saved chapters, plus an unwritten analytical finding retained |
| Disclosure deductions | No common checklist established by the narrowed live input; mechanics tested offline |
| Latency | 11.67 seconds mean across ten responses with known usage; failed first call excluded |
| Known token usage | 59,012 input and 19,394 output tokens, including corrections |
| Known metered cost estimate | $0.131532 |
| Unknown-usage reservation | $0.14557875 retained for the first truncated request |
| Total trial budget accounting | **$0.27711075 of $0.30**; not an OpenAI invoice reconciliation |
| Exports | PDF, XLSX, HTML, CSV and JSON returned HTTP 200 without model calls |

The calculated methane ratios are 0.04 / 0.2 = 0.2 for Aramco and
0.08 / 0.2 = 0.4 for Eni. The shared contextual benchmark comes from the Eni report;
it is not claimed to have been independently disclosed by both companies. The
second calculation takes the magnitude of Shell's 9% and Eni's 10% reported
year-on-year reductions. Their different net-emissions boundaries remain with
the calculation. Neither comparison proves an overall leader.

Issues exposed by real responses:

- Several table quotations were reordered or compressed by the model. Grounding
  retained only one of Equinor's fourteen proposed facts. The revised collection
  prompt requires original table order and footnotes; that change has not yet
  received a new full-cohort live evaluation.
- Percentage labels such as `% lower` and numeric strings ending in `%` were
  unnecessarily blocking arithmetic. Deterministic conversion and workbook inputs
  now support them; the saved proposals were recalculated without AI calls.
- A draft finding named the wrong methane leader. Executed results and the writer
  corrected the direction. This demonstrates why proposed prose is not the
  calculation authority.
- Short quotations lost adjacent explanations of emissions changes. Model packets
  now include deduplicated surrounding report text. One chapter was rewritten
  inside the original budget. Full editorial factual accuracy is still unproven;
  for example, wording about which companies disclose a shared benchmark needs
  another review before client publication.
- Numeric awards sometimes included an unused model points rubric. Numeric
  winners use the calculated measure only; the unused rubric is no longer
  displayed or passed forward as scoring.

The live test does **not** establish extraction accuracy, full-report recall,
full-package latency or cost, or commercial report readiness. No percentage
accuracy score has been manufactured from this partial run. The saved trial
ceiling also applies when resuming through the UI. Further live verification needs
a separately approved budget; opening results and exporting remain free of calls.

The real working-draft exports and machine-readable verification ledger are in
`tmp/analytical-acceptance-check/` (local, ignored). PDF pages and all five workbook
sheets were rendered and visually checked. Formula-edit/recalculation tests use
isolated fixtures and never overwrite these actual company results. Browser
checks covered metric switching, source page 161, the report, promises, disclosure
empty states and desktop/mobile layouts; no console errors were observed.

Final offline verification: 724 backend tests passed, two opt-in live tests
skipped; 89 frontend tests passed. Python type checking (96 source files),
TypeScript checking and the production build passed. The build retains the
existing large globe-bundle warning. Native Excel integration tests were enabled.

## Retained method for older saved runs

The existing saved-analysis workflow now supports two package briefs. It does not
change the configured OpenAI model, create another service, or make model calls
when opening a result or downloading a file.

## Packages

| Package | Audience | Research scope |
| --- | --- | --- |
| Company benchmark | Primary company's sustainability and strategy teams | Primary company plus up to four selected peers; differences, opportunities and management questions |
| Sector intelligence | Banks, analysts and strategy teams | Up to twenty selected companies; recurring approaches, business-model contrasts and distinctive initiatives |

Pricing remains in the commercial page. The generation contract does not promise
complete industry coverage or a fixed number of findings. Research includes all
ten topic families by default; customers can choose fewer.

## Versioned method

The comprehensive instructions are maintained in
`backend/app/knowledge/report_prompts.py`, not a one-off chat prompt.

1. **Freeze the sources.** Store the selected companies, report IDs, source
   fingerprints, package and method version in the existing briefing record.
2. **Research each topic twice.** A results lens retrieves achieved performance,
   history and usable denominators. A strategy lens looks for distinctive
   initiatives, implementation, AI, innovation, credits and measured outcomes.
   Larger cohorts are researched in batches of five so none disappear behind a
   global retrieval limit. Annual and sustainability reports are both eligible.
3. **Assemble all cited findings.** Split them into bounded evidence packets. There
   is no ten-insight total limit or six-insight/four-award schema cap. A single
   oversized finding fails visibly instead of being silently discarded.
4. **AI proposes comparisons and awards.** It selects useful relationships and
   source operands, not just a fixed emissions checklist. Examples include
   leadership/workforce representation, training per employee, social investment
   relative to business scale, and gross progress versus credit use. Qualitative
   findings are first-class report content.
5. **Code calculates.** Common-unit conversion, ratios, differences and percentage
   changes run through the existing deterministic calculation functions. Winners,
   ties and assessed sample size are stored alongside original inputs and sources.
   The model cannot execute arbitrary Python or supply an unchecked result.
6. **AI writes chapters.** Package-specific instructions explain differences,
   calculations and implications. Each paragraph references structured record IDs.
   A separate short takeaway feeds Excel. The report can use calculated numbers,
   not only numbers that appear verbatim in source text.
7. **Publish the saved edition.** One publication model feeds the dashboard, PDF,
   HTML and workbook. Completed chapters replace the research notes only when all
   chapter batches for that topic exist. Unfinished work remains available.

AI reruns are not guaranteed to produce identical wording or proposals. Saved
editions replay without calls; arithmetic and unit conversion are reproducible.
The existing model ledger records usage, prompt/schema hashes, latency and model.
Research remains retrieval-based, not a claim that every PDF sentence was examined.

## Client deliverables

- **PDF:** readable chapters, vector comparison charts, award calculations and
  linked source endnotes. Long source excerpts are not pasted into the narrative.
- **Workbook:** concise filterable Findings; Comparisons and editable Inputs when
  calculations exist; source-page index with native hyperlinks. Comparison formulas
  refer to the input cells. Empty calculation tabs are omitted from older editions.
- **Supporting exports:** full evidence CSV and JSON, available behind a secondary
  disclosure. These retain detail without dominating the client deliverables.

Existing saved analyses are reformatted, not silently regenerated. An old analysis
with no calculated awards does not acquire made-up awards from the new renderer.

## Local workbook runtime

PDF generation uses ReportLab. XLSX authoring uses the installed Artifact Tool
Node runtime. Set these two server-side values in `backend/.env` on this machine:

```dotenv
WORKBOOK_NODE=/Users/ahmednajaf/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node
WORKBOOK_MODULES=/Users/ahmednajaf/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules
```

After changing environment values, restart the backend. Other hosts must supply
their own installed runtime paths; these are not portable production defaults.
Missing runtimes return an explicit export error, never a renamed CSV. Native Excel
hyperlinks are added in a narrow OOXML compatibility step because this renderer
does not evaluate HYPERLINK formulas. Formula creation and calculation stay in
Artifact Tool. Export subprocesses are local, bounded and shell-free.

## Verification

`test_publication.py` covers both package flows with mocked providers, source
grounding, packet coverage and resume/read-only behavior. `test_report_synthesis.py`
covers conversion, arithmetic, ties, missing inputs and awards. `test_workbook_export.py`
checks source hyperlinks and optional native XLSX integration. Enable the latter:

```sh
cd backend
WORKBOOK_TEST_NODE=/path/to/node WORKBOOK_TEST_MODULES=/path/to/node_modules \
  .venv/bin/pytest tests/test_workbook_export.py
```

The integration check imports the generated file and changes inputs to verify
converted results, leading-company changes, zero versus missing values and chart
presence. It does not claim Microsoft Excel UI testing. Live package quality must
be assessed separately on actual reports with an approved API budget.

## Research-studio presentation (14 October 2026)

The product target is a repeatable B2B research proof of concept: company and
sector reports, calculated comparisons, peer distinctions, disclosure analysis,
and Excel workbooks with source links. Accounts, checkout and enterprise hosting
are not acceptance requirements for this proof of concept. Buyer demand and the
proposed prices still need customer testing.

The non-landing screens use one charcoal/lavender material system. The globe
landing and its launcher are preserved. Workspace AI actions now open a contextual
“Explore the findings” panel; they use the same saved-analysis scope and endpoints.
No new model calls or infrastructure were needed for this presentation work.

User-supplied components are adapted in `glass-folder.tsx`, `press-depth.tsx` and
`package-art.tsx`. The dashboard composition references
[Efferd's Dashboard 4](https://21st.dev/@efferd/components/dashboard-4), inspected
in the signed-in account (MIT). The supplied folder's overlapping file hit targets
were replaced with a separate accessible download list while retaining its fan
animation. Its sample files and default add-file control are removed.

The workspace opens actual saved editions, the dashboard charts calculated values,
and the commitment register filters by company/text with six items per page.
Calculation detail is selected one metric at a time. Awards retain their existing
criteria, winners and evidence; artwork never determines an award.

Original transparent 3D badge assets are in `frontend/public/awards/`. Generated
with the built-in Image Generation tool, not Vero's paid report-generation API:

- `people.png`: silver titanium/lavender circular medallion, three ascending
  abstract people/pillars joined by an orbital ring; equal opportunity and growth.
- `innovation.png`: silver/icy-blue rounded hexagonal medallion, crystal four-point
  star and orbiting bead; learning and innovation.
- `clarity.png`: platinum/lilac concentric-ring medallion around a four-facet prism;
  evidence and transparency.

Shared generation direction: original Apple Health-quality dimensional achievement
object, isolated on transparent square canvas, slight 12-degree perspective,
78% canvas coverage, polished bevels, realistic refraction, studio rim light,
legible at 96px; no Apple logo, text, numbers, ribbon, confetti or green.

Verification: 99 frontend tests, TypeScript and production build pass. Browser
checks cover desktop and 390px layouts, real saved analysis navigation, library
search, commitment filters, source drill-down, award rendering and the folder's
actual XLSX download. No source data, prompts, calculation rules or backend
processing were changed in this UI pass. The existing large globe bundle still
produces Vite's chunk-size advisory.
