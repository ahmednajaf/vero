# Page-aware PDF parsing

Implemented with PyMuPDF 1.28.2 and pdfplumber 0.11.10; current pipeline `page-provenance-v2`. No AI layout package, model, OCR process or metric extractor is called. Parsing consumes already-downloaded artifacts and does not access company websites.

## Evidence contract

```text
reports → report_artifacts (canonical PDF SHA-256 + size + storage key)
   └── extraction_runs (stage=parsing, input hash, versions, options, quality)
           └── document_pages (one row per physical page, including empty pages)
                   ├── document_chunks (exact single-page text slices)
                   └── document_tables (unvalidated string/null cell grids)
```

- The source URL remains on the report and is copied into the run parameters. The parser checks report/artifact metadata, resolves the file inside `REPORTS_ROOT`, and copies it into a private temporary directory while verifying its SHA-256 and byte count. It parses that verified snapshot, never edits the original, and checks integrity even on an otherwise-idempotent rerun.
- Physical page numbers are **one-based PDF positions**. `printed_page_label` is the PDF's embedded label, if present, not a guessed number extracted from a footer. These can differ from the numbers printed on the page.
- `raw_text` is native PyMuPDF content-stream text (`sort=False`). It is preserved separately from `ordered_text`, a left-to-right geometric reading-order heuristic. Both have SHA-256 hashes. No dehyphenation, summarisation, unit conversion or whitespace cleaning is performed. If native text contains NUL (unsupported by PostgreSQL text), the original UTF-8 is retained losslessly in `layout.original_raw_utf8_base64`; searchable text replaces NUL with U+FFFD and emits a warning.
- Page layout retains crop/media boxes, rotation, native line text, block/line IDs, font size, bold flag, direction, bounding boxes and ordered-text offsets. PyMuPDF coordinates are unrotated page points with a top-left origin; the crop box is retained for overlay consumers.
- Headings are candidates from the PDF outline or typography, marked unvalidated with their method. A known outline section may span pages; inferred typography headings do not silently carry across pages. Unknown chunk sections are null.
- Chunks preserve report, run and page IDs; `physical_page_start = physical_page_end`; section title; exact text/hash; zero-based Unicode character offsets `[source_char_start, source_char_end)` in **ordered_text**, not raw_text; and overlapping native line references/bounding boxes. Newline separators need no fabricated glyph box. Concatenating the chunks of a nonempty successfully extracted page reconstructs its ordered text, with no overlap. Even an oversized paragraph is split inside its page.
- `document_tables` stores each candidate separately: page/run/report, table index, dimensions, cells, table/cell bounding boxes, header metadata, extraction settings/method/version and a hash of canonical JSON cells (UTF-8, sorted keys, compact separators). Empty strings/nulls stay empty/null; values remain strings. `validation_state` is constrained to `needs_review`. These are **not sustainability metric observations**.

## Layout and tables

Native line boxes are arranged by recursive whitespace cuts, with spanning headings retained. Geometric table regions are kept together and read row-wise rather than treating numeric columns as prose columns. This handles the synthetic multi-column fixture and reviewed real pages; it is not a guarantee of semantic reading order on all layouts, scripts, footnotes or rotated text.

Table detection tries PyMuPDF `lines_strict` with `use_layout=False`. If no table is found, a deterministic horizontal-rule strategy joins touching cell strokes, keeps side-by-side regions separate, and infers separators from whitespace. Its inferred boundaries are retained. If neither finds a table and numeric alignment suggests one (or primary detection failed), pdfplumber text alignment is attempted. Pure text alignment can include prose/charts, merge adjacent regions or fragment cells: every candidate remains unvalidated and fallback use raises a page-specific warning. Detection is best-effort, not a table-completeness score. The current fallback is page-level; a page with one detected ruled table can still contain undetected borderless tables.

Raw table text remains in page text/chunks for provenance; the structured table is an additional representation, not another independently observed metric. Headers, merged cells, year/unit alignment and totals require later review. A visual check of Samsung 2025 physical page 62 exposed a merged side-by-side table in pipeline v1; v2 separates its four table regions. Both runs are retained.

References: [PyMuPDF extraction representations](https://pymupdf.readthedocs.io/en/latest/app1.html), [page/table APIs and coordinates](https://pymupdf.readthedocs.io/en/latest/page.html), [pdfplumber table extraction](https://github.com/jsvine/pdfplumber#extracting-tables).

## Status and quality

Acquisition status remains `downloaded`; `reports.parse_status` is separate:

| Parse status | Meaning |
| --- | --- |
| pending / running | Not yet parsed / committed run is in progress. |
| parsed | Native extraction completed without review-level warnings; not metric validation. |
| needs_review | Review warnings or individual failed pages; other available evidence is preserved. |
| needs_ocr | At least one page has no native text, or sparse text with images; OCR was **not** run. This can include blank back covers and is a triage flag, not a mandate to OCR. |
| failed | Invalid/encrypted PDF, source-integrity failure, resource limit, worker failure or all page extractions failed. No OCR fallback or password bypass. |

OCR-related flags take precedence over `needs_review`; inspect the full warnings and `pages_failed` rather than only the headline. Individual pages have `parsed`, `needs_ocr` or `failed`. A completed run may be `succeeded` while report quality is `needs_review`/`needs_ocr`.

Successful parse summaries contain `pages_total`, `pages_with_text` (non-whitespace native text), `text_characters` (raw Unicode characters including whitespace), `table_count` (candidates, not verified tables), `chunk_count`, `pages_needing_ocr`, `pages_failed`, `parse_warnings` and `ocr_performed=false`. Warnings preserve code, message, physical page and severity. Native absence does not imply non-disclosure. For whole-file failures, counts may be unknown or represent no accepted output; do not use failed runs to calculate disclosure coverage.

## Invocation and configuration

```bash
cd backend
source .venv/bin/activate
python -m alembic upgrade head
python -m app.cli parse-reports
python -m app.cli parse-status
python -m app.cli parse-reports --year 2025 --limit 20
python -m app.cli parse-reports --report REPORT_UUID --force
python -m app.cli parse-status --report REPORT_UUID --examples 2 --output /tmp/new-parse-status.json
```

`--report` is repeatable; `--year` means requested acquisition year, not verified metric year. Status `--examples` accepts 0–5 first chunks per report. JSON output is exclusive-create. No frontend changes or parsing API are included.

| Setting | Default | Purpose |
| --- | ---: | --- |
| PARSE_CHUNK_CHARS | 2400 | Maximum page-local chunk size. |
| PARSE_MAX_PAGES | 1500 | Reject over-limit documents without silent truncation. |
| PARSE_MAX_PAGE_CHARS | 300000 | Reject excessively large page extraction. |
| PARSE_MAX_DOCUMENT_CHARS | 25000000 | Reject excessive document text. |
| PARSE_TIMEOUT_SECONDS | 300 | Per-report worker wall-clock timeout. |
| PARSE_MAX_TABLES_PER_PAGE | 50 | Cap candidate tables; emit an explicit warning if truncated. |
| PARSE_PDFPLUMBER_FALLBACK | true | Enable gated text-alignment fallback. |
| DISCOVERY_MAX_DOWNLOAD_MB | 100 | Existing artifact size limit also checked on parsing input. |

The macOS/Linux worker runs in a separate subprocess, is killed on timeout and caps each output/log file at 256 MiB. It is crash/timeout isolation, **not a security sandbox or a hard memory limit**. Native-library allocation can occur before text-size checks. Keep dependencies patched; do not expose this unauthenticated local workflow as a public upload service.

Exit codes for `parse-reports`: 0 batch completed (possibly needs review/OCR, unchanged or busy), 1 at least one returned failure, 2 setup/database/path error. Inspect per-report JSON. `parse-status` has no network acquisition side effects.

## Persistence and reruns

An advisory lock serialises runs for each report. A matching successful latest attempt (same input hash and version/options profile) is reused only after source verification. New code/library versions, changed options, retry after failure, or `--force` create a new run and new evidence. There is no destructive replacement. A crashed `running` attempt is marked interrupted on the next invocation after its lock has been released. Unexpected database failures can leave an auditable `running` attempt for that recovery.

Pages, tables and chunks commit atomically with final quality metrics. Whole-file resource/integrity failures accept no new evidence. Individual page failures retain explicit page records and any available raw text; warning/status gates remain visible. Older successful output is retained if a later attempt fails, but `parse-status` deliberately shows the latest failure, not stale success.

Composite foreign keys enforce matching report/run/page identity. Database triggers reject mismatched page hashes, chunks that are not exact page-text slices, and UPDATE/DELETE of new parsed pages, tables or linked chunks. Legacy chunks remain nullable on the new fields and are not retroactively verified. Revision `53487b8db383` refuses downgrade when parsed pages exist. These DML guarantees do not protect against privileged trigger removal/TRUNCATE; back up the database **and** PDF artifacts.

## Scope and verification

No metric extraction, numeric normalisation, target classification, disclosure-completeness claims, OCR, local AI or scoring is implemented. Tests exercise six generated fixture files and real PostgreSQL provenance constraints. See [the three-report smoke record](parsing-live-2026-09-29.md) for actual counts, hashes and page/chunk examples. Visual sampling is not an accuracy audit of every table/page.
