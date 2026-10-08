# Real PDF parsing verification — 2026-09-29

Scope: **three official downloaded reports, two companies, two requested cycles**. Apple 2025 and Samsung 2025 were already downloaded. Samsung's 2024 PDF was additionally discovered and downloaded through the existing official-domain/robots-aware acquisition CLI, without third-party mirrors or company metadata changes. This is not a three-company test, an accuracy evaluation of every page/table, or evidence of 200–500-company coverage.

Current parser: `page-provenance-v2`, PyMuPDF `1.28.2`, pdfplumber `0.11.10`; default limits and 2,400-character page-local chunks. PostgreSQL 17 isolated local smoke database, migration `53487b8db383`. Exact full statuses, source hashes, completion times and every page warning: [captured JSON](parsing-live-2026-09-29.json).

## Outcomes

| Official report | Pages | With native text | Raw characters | Chunks | Table candidates | Warnings | Quality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| [Apple Environmental Progress Report 2025](https://www.apple.com/environment/pdf/Apple_Environmental_Progress_Report_2025.pdf) | 126 | 126 | 417,584 | 248 | 93 | 46 | needs_review |
| [Samsung Sustainability Report 2025](https://www.samsung.com/global/sustainability/media/pdf/Samsung_Electronics_Sustainability_Report_2025_ENG.pdf) | 87 | 86 | 386,445 | 211 | 99 | 34 | needs_ocr |
| [Samsung Sustainability Report 2024](https://www.samsung.com/global/sustainability/media/pdf/Samsung_Electronics_Sustainability_Report_2024_ENG.pdf) | 83 | 82 | 333,787 | 188 | 101 | 31 | needs_ocr |

All three execution runs succeeded, with **zero failed pages** and **no OCR performed**. `needs_ocr` is exclusively physical page 87 (Samsung 2025) and 83 (Samsung 2024): rendered review shows otherwise blank back covers containing a Samsung logo without a native text layer. The flag is retained honestly; it is not a claim that report content is missing or permission to OCR. Other warnings include text-aligned table fallback and rotated text. Table counts are unvalidated candidates, never an accuracy/completeness score.

The three source PDFs independently matched stored SHA-256 and byte sizes (Apple 22,928,608; Samsung 2025 5,820,129; Samsung 2024 4,237,033). Canonical storage remains `data/reports/{company_id}/{year}/{sha256}.pdf`. Company IDs: Apple `01900000-0000-4000-8000-000000000005`; Samsung `01900000-0000-4000-8000-000000000008`. The JSON records each complete checksum.

## Page and chunk examples

Offsets below are zero-based Unicode character positions in that page's `ordered_text`, end-exclusive. Hashes cover the **complete chunk**, not the short quoted excerpts. Original native `raw_text` and line boxes are retained separately. All examples have `page_start = page_end`; none merge page boundaries.

### Apple 2025 — physical page 10

- Report: `6aeb395b-b23a-4340-9886-72e4277190ba`; run: `1bfcce1c-3818-458c-8f0d-fac191cf3a66`.
- Page: `3e58dc28-dcff-45ed-a906-909a0cc606e0`; 3,197 raw characters; raw SHA-256 `e88fd24cb2c31294096341a1793b4b60eb57d96d8624c3841556d169b3814019`.
- Native page starts `Approach\nApple 2030\n`. These are retained as heading candidates, not validated section semantics. Bold body lines can also be over-detected by typography; the metadata exposes that limitation.
- Chunk: `3c8dd0d4-0555-4677-b393-f0b84110dc0c`, index 12, page 10–10, offsets **0–2390**, section null (chunk starts before a known heading).
- Chunk SHA-256: `e998b73401f9dcd04c6474082ffe15f7ec9b452a3a4147d46b8e585d87c1998f`.
- Ordered chunk starts `Contents\nIntroduction \nEnvironmental Initiatives\n`; page navigation is retained, not silently stripped.
- First source line: block 18, line 2, page-text offsets 0–8; bbox `[32.0, 23.2230, 63.3568, 33.1980]` in unrotated page points.

Visual review shows two prose columns plus a roadmap graphic. pdfplumber proposes a **50×13** text-alignment candidate across this layout; it is not a clean data table. The candidate and explicit fallback warning remain available for later review and must not be consumed as validated metric data.

### Samsung 2025 — physical page 62

- Report: `ad85cf22-8639-43af-889b-15a120c2ac96`; run: `82c439e3-afe6-4ce0-9759-b85f72179f0f`.
- Page: `082d0130-c727-431b-8f10-7d9f3a86d75e`; 2,647 raw characters; raw SHA-256 `6d64dcade2afcf93268d9d505cd7704dec23f648be3d7e8f1243e4d67da12bf6`.
- Chunk: `52c809a6-ae32-4933-af23-91bdbbbace21`, index 163, page 62–62, offsets **0–2305**, section `Economic Performance`.
- Text starts `Economic Performance\n1)\nKey Financial Performance\n2022\n2023\n2024\n`.
- Chunk SHA-256: `5504701c301178ebc89f9b470f2099fa2f10c4650055723713507c734559d41e`.
- First source line: block 1, line 0, page-text offsets 0–20; bbox `[42.4447, 40.4141, 162.5088, 56.9016]`.
- Four separate horizontal-rule table regions: **4×5, 11×5, 11×5, 25×4**. All use `pymupdf.horizontal_rules_whitespace`, retain inferred boundaries, and remain `needs_review`.

Visual review identified a v1 merged table combining two page columns. V2 separates the four visible regions and keeps native table lines row-wise. Header/units/merged-cell semantics still need review; no financial or sustainability observations were created.

### Samsung 2024 — physical page 60

- Report: `4c454a7e-542d-4fdd-a770-832cf02f0790`; run: `52f295eb-6675-44aa-9edd-2447d86ad2e1`.
- Page: `1b1d6c3d-427e-4ffd-ad50-8c05e4b84a78`; 4,245 raw characters; raw SHA-256 `edc27961a97dcf20955bc05fcf4aebfcaceae51a05e6b49302fbc41ca10e95ad`.
- Chunk: `74c09dec-ed2c-41f1-b297-9a71b4422c38`, index 143, page 60–60, offsets **0–2393**, section null (no reliable heading candidate).
- Text starts `Career Development\n2021\n2022\n2023\nNumber of training sessions\n`.
- Chunk SHA-256: `b22a3f6f606d52c78320f98281a66d29aec194fb007bd38c807a74f40f51845e`.
- First source line: block 1, line 0, page-text offsets 0–18; bbox `[43.9370, 72.2309, 105.4340, 82.1234]`.

Visual review confirms left/right table regions. Two structured candidates are stored (**24×4, 24×5**); some labels and units share cells, and the short one-row table near the bottom is not separately detected. Its text remains in the page/chunks. This illustrates why structured table counts must not be mistaken for complete/validated disclosure extraction.

## Verification and retained history

- `parse-reports --limit 3` processed the three PDFs. Repeating it returned **unchanged: 3**, with identical run IDs and no duplicated evidence.
- An independent final database read verified all **296 pages, 647 chunks and 293 table candidates** in v2: page/table/chunk hashes match; chunks reproduce each nonempty page's ordered text exactly; all chunk report/run/page references align; no chunk crosses a page boundary. Warning codes total 102 table fallbacks, 7 rotated-text flags and 2 native-text-absent pages.
- Pipeline v1 runs remain immutable history; current status refers to v2. Query by parse run, not all historical chunks combined.
- Backend: **132 passed, 1 skipped** (optional live acquisition test disabled); real PostgreSQL and installed Chromium with mocked company HTTP. Python typing, dependency consistency and Alembic no-drift checks passed.
- Frontend unchanged: **12 passed**, TypeScript and production build passed.
- Synthetic fixtures cover native text, alternating-stream columns, ruled/borderless/side-by-side tables, blank, scanned and malformed inputs. The PDF skill's rendered-review workflow caught the real side-by-side table error before final verification.
- No AI/model download, OCR, sustainability metric observation, target, normalisation or scoring was performed. Real `metric_observations` and `targets` counts remain **0**.
- Rendered source/fixture review images are under ignored `tmp/pdfs/parsing-review/`; SQL backup is under ignored `backend/storage/verification/parsing-smoke-2026-09-29.sql`. The isolated test PostgreSQL instance was stopped after verification and backup. No hosted site was changed.

## Changed files in this stage

Backend: `app/parsing/{__init__,contracts,engine,worker,service}.py`; `app/cli.py`; `app/core/config.py`; `app/db/models.py`; `alembic/versions/53487b8db383_page_aware_pdf_parsing.py`; `pyproject.toml`; `requirements-dev.lock`; `.env.example`; `tests/pdf_fixtures.py`; `tests/test_parsing.py`; expected table set in `tests/test_database.py`.

Documentation/configuration: repository `.gitignore`, `README.md`, `docs/architecture.md`, `docs/database-schema.md`, regenerated `docs/schema.sql`, `docs/parsing.md`, and this smoke record plus its JSON. No frontend source or company CSV was changed. The project was already untracked in git; this inventory identifies this stage rather than claiming all untracked files were newly authored here.
