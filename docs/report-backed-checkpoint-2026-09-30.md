# Official-report checkpoint — 30 September 2026

## Scope and status

This is the original development cohort, with a strict five-company gate before
twenty. It is **not** the 200-company pilot run. A directory entry is not a
downloaded report, and a downloaded report is not an approved benchmark.

Paused run: `773fd27c-254e-4e4b-9e71-bb39516db345`.
Started at 03:30 UTC and interrupted at 03:51:56 UTC. The five-company
data-complete gate did not pass. Twenty-company and 200-company processing
have not started. The database ledger and exported run summary remain
authoritative. The commercial preview is a separate, bounded publication,
not evidence that a batch checkpoint passed.

The collection cycle is 2025; the requested observation year is 2024. The two
are deliberately distinct. Fiscal-period boundaries still require review.

## Acquisition repairs

- Exclude specialised bond allocation/impact reports from primary corporate
  report selection. Preserve old downloads and discovery alternatives.
- Add explicit official-source registration with company/domain checks, source
  selection rationale, curator identity and an idempotent evidence digest.
- Normal download safeguards still apply: robots, redirects, official hosts,
  MIME/signature/size checks, throttling and SHA-256.
- Review decorative pages explicitly against the exact PDF and parse-run hash.
  These reviews do not remove parser warnings, overwrite parsed text or run OCR.

Four new company-wide official documents were downloaded and parsed:

| Company | Official document | Physical pages | SHA-256 |
| --- | --- | ---: | --- |
| JPMorgan Chase | [2024 Sustainability Report](https://www.jpmorganchase.com/content/dam/jpmorganchase/documents/about/jpmc-sustainability-report-2024.pdf) | 66 | `925fb257f1b3df67afdb8a6532e93922581f58926f56c05b92811a5cb0164d98` |
| Bank of America | [2025 Sustainability Report](https://about.bankofamerica.com/content/dam/about/report-center/esg/2025/SustainabilityatBofA2025_WCAG2.2_121625.pdf) | 62 | `f92b68f3cbbd87ac6aa55c7705a865de34ff300a5bc9e25d3d47f71edd8c117f` |
| HSBC | [Annual Report and Accounts 2024](https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/2024/annual/pdfs/hsbc-holdings-plc/250219-annual-report-and-accounts-2024.pdf) | 460 | `c998d20da18afa770034b9c3506f25b68205bcbcd5e8444ea0f50157ee6689fb` |
| Santander | [Consolidated Annual Financial Report 2024](https://www.santander.com/content/dam/santander-com/en/documentos/informe-financiero-anual/2024/ifa-2024-consolidated-annual-financial-report-en.pdf) | 870 | `cfb8bceab16b948f94a07307db7060056297e48a7b5f942fe3eac4bc508f4f0c` |

Apple's previously downloaded 2025 Environmental Progress Report completes the
first five-company source set. Samsung's two existing reports and JPMorgan's
old bond report remain in the archive. Thus eight retained PDFs do not mean
eight newly covered companies.

## Extraction and factual review

All inference uses the installed, previously approved local `qwen3:14b` model,
digest `bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`.
No new model was installed. No report passages were sent to an external model.
Only retrieved, bounded page-aware chunks are supplied to Ollama.

Repairs include capitalised worded emissions units and attached Roman footnotes
in row labels. Original text, values and units remain unchanged. New rule
versions create new audited assessments; exact model responses can be reused
only if prompt, source chunk, model digest, instruction version and schema match.
Old assessments are not silently rewritten.

`review-source-facts` is an explicit review operation, **not** an automatic
pipeline promotion. Codex inspects the rendered source table, then the command
verifies the downloaded PDF checksum, page/chunk hashes, exact value/quote,
year/unit evidence and deterministic conversion. Each approval is recorded in
`validation_events` with its reviewer method and reason.

`validated` here means a checked source fact. It does **not** mean human sign-off,
an external audit opinion, or approval to compare companies. These reviews leave
peer compatibility `unchecked`. Boundary, period and method review is separate.
Model confidence cannot approve a figure. Failed and conflicting candidates
remain available in the extraction audit.

Important source distinctions found during visual checks:

- JPMorgan p.20 separates location- and market-based Scope 2 and combined totals.
- Bank of America p.38 separates gross emissions, offsets and net emissions.
- HSBC physical p.61 reports a twelve-month period ending 30 September, and its
  disclosed operational Scope 3 total covers specified categories, not all
  financed emissions.
- Santander p.136 separates operational emissions from financed emissions on
  p.137; target-year columns must not be read as achieved 2024 values.
- Apple p.104 covers fiscal 2024, despite the report's 2025 title; its facilities
  figures must not be substituted for the entire value-chain footprint.

Review manifests are in `data/reviews/`. The source manifest is
`data/report_sources_checkpoint_2025.json`. Repeated extractions of the same
fact are retained as audit records, not independent measurements.

## Running and resuming

From the project root, `bash scripts/run-report-checkpoint.sh` requests the
original twenty-company cohort and enforces the five-company gate first.
It uses the configured installed model; no model name is hard-coded in the
script. `--resume` requires an existing identical configuration and cohort.
It cannot launch a 200-company run.

Code-version changes intentionally create a new run profile. They must not be
misrepresented as resuming an old ruleset. Existing checksummed documents,
parses and eligible exact model responses can still be reused under new rules.

From `backend`, export current stage states, failures and source provenance:

```sh
.venv/bin/python -m app.cli pipeline-status --run 773fd27c-254e-4e4b-9e71-bb39516db345
```

CSV and JSON exports live under the configured pipeline output directory.
An extraction/validation stage receipt is not a human validation event.
