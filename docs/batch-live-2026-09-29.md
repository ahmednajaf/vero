# Live batch checkpoint — 2026-09-29

**Result: five-company checkpoint failed. Twenty was not created or run.** This follows the requested data-complete gate and fail-fast policy; it is not a successful twenty-company data run.

Run ID: `0aaa6d00-bc87-4da3-8149-e1a5a741786e`. Actual live coordinator version: `resumable-batch-v1`. Started 2026-09-29 13:31:07 UTC; finished 13:31:49 UTC; exit code 1. Company cohort was the first five active company UUIDs in stable order, not selected for accessible websites.

```bash
DATABASE_URL=postgresql+psycopg://sbi@127.0.0.1:55432/sbi_test \
LLM_TIMEOUT_SECONDS=300 LLM_MAX_OUTPUT_TOKENS=2048 \
  .venv/bin/python -m app.cli run-pipeline \
  --year 2025 --observation-year 2024 --limit 20
```

The URL above identifies the isolated local verification database, not a deployment. `ollama list` confirmed the already-installed, user-approved `qwen3:14b` (9.3 GB). Its model identity preflight succeeded. **Zero inference calls ran**, because the report-quality checkpoint stopped before metric retrieval. No model was downloaded. No OCR, CAPTCHA/login bypass, source-policy expansion or third-party mirror was used.

## Exact outcomes

| Company | Discovery | Download | Parsing / continuation |
| --- | --- | --- | --- |
| JPMorgan Chase & Co. | Selected a 2025 sustainable-bond report | Downloaded; SHA-256 verified | Parser produced text/chunks but flagged one page `needs_ocr`; batch parse stage `needs_review`; extraction blocked. |
| Bank of America Corporation | In-flight discovery completed with a 2025 sustainable-bond report | Blocked after the earlier failure | No download or parse attempted. |
| HSBC Holdings plc | Not started | Not started | Queued work blocked by fail-fast. |
| Banco Santander S.A. | Not started | Not started | Queued work blocked by fail-fast. |
| Apple Inc. | Not started | Not started | Queued work blocked by fail-fast; earlier independent Apple evidence was not counted in this batch. |

Two companies were contacted. Discovery already in flight was allowed to finish safely; no new queued network/model work began after the failure. Five companies fail the strict completeness gate, but this does **not** mean five sites returned errors: there was one direct stage-quality failure, one in-flight company's downstream work was halted, and three companies were not started.

| Summary field | Count |
| --- | ---: |
| Companies total | 5 |
| Companies started | 2 |
| Companies not started | 3 |
| Companies with a direct failed/review/unavailable stage | 1 |
| Reports discovered (selected) | 2 |
| Downloaded | 1 |
| Parsed and eligible to continue | 0 |
| Extracted | 0 |
| Validated | 0 |
| Needs review | 1 |
| Failed strict data-complete gate | 5 |

Stage totals: **3 succeeded, 1 needs_review, 186 blocked**. All requested definitions have **0/5 companies with metric observations**: Scope 1, Scope 2 location-based, Scope 2 market-based, Scope 3, renewable energy percentage, net-zero target candidates and assurance. These zeros are coverage counts, **not sustainability values or proof of non-disclosure**.

## Retained source evidence

JPMorgan selected source: [2025 Annual Sustainable Bond Report](https://www.jpmorganchase.com/content/dam/jpmorganchase/documents/about/annual-sustainable-bond-report-2025.pdf), discovered from its official sustainability page.

- Discovery run: `c2b907f5-d79b-4f88-8d57-4669ce801d04`.
- Report: `19faa9fc-e4fa-46ac-8fda-4142cf9a1bd3`.
- Download size: **1,003,939 bytes**; SHA-256: `53e88ee4d82a684fcc8325130696b9b67718a41aed8a23e48192650742b9e163`.
- Parse run: `f46a6280-d0d4-4f05-80a4-58f6b6c9e8e1`.
- **7 pages, 7 pages with native text, 23,384 characters, 13 chunks, 7 candidate tables, 3 warnings, 0 failed pages.**
- Page 1 received `sparse_image_page`: sparse native text with images, possibly an image page with footer text. `pages_needing_ocr=1` caused the report-level `needs_ocr` status. This is a conservative parser flag, **not a claim that all seven pages are scanned or unreadable**. No manual layout judgment or OCR was used to override it.

Bank of America selected source: [2025 Sustainable Bond Report](https://about.bankofamerica.com/content/dam/about/pdfs/2025-sustainable-bond-report.pdf), discovered from its official sustainable-issuances page.

- Discovery run: `787d80b0-4e31-444b-bf56-05ff8f8b05b6`.
- Report: `82e68afc-d357-4947-a581-4e83cc339b2e`.
- No downloaded bytes/hash/page evidence exists for this report in this batch. Its download job was explicitly blocked, not successful.

## Additional source-quality finding and final code

Inspection of the saved URLs/titles showed both choices concern **sustainable bonds**, not clearly company-wide sustainability performance. The batch must not silently equate financed-project impact with company metrics. Final coordinator version **`resumable-batch-v1.1`** therefore adds a tested `specialised_financing_disclosure` review guard before reusing/downloading such a primary report.

This guard was added **after** the recorded live attempt. The original run, selected reports, parser output and failure reason were preserved; they were not retroactively relabelled or rerun to improve the outcome. Current code would require source review earlier. Because profile versions are immutable, this older run remains inspectable through `pipeline-status`; a changed source/processing profile must start its own checkpoint sequence. No extra live requests were made after the failed checkpoint.

Progress to twenty requires appropriate company-wide source reports and resolution of relevant parse-quality blocks. The gate was not relaxed, and OCR or an alternative cohort was not used to force a pass.

## Exports and verification

- [Complete saved-state JSON](../backend/storage/pipeline/0aaa6d00-bc87-4da3-8149-e1a5a741786e/20260929T133456-2b0564d8.json).
- [CSV with 35 company/metric coverage rows and provenance columns](../backend/storage/pipeline/0aaa6d00-bc87-4da3-8149-e1a5a741786e/20260929T133456-2b0564d8.csv).

These exports were generated by read-only `pipeline-status` after the run. They include all five selected companies, reasons, stage attempts/events, original cohort/profile, available report provenance, and explicit blanks for unavailable metric values/pages. Earlier export snapshots remain intact. The run's original persisted summary remains historical; the status export additionally distinguishes started/not-started companies without rerunning work.

Fixture-based tests separately prove successful 5 → 20 progression, completed-prefix reuse, resume, retry ceilings and failure gates. Those fixtures are fictional and do **not** establish twenty-company live coverage. See [batch processing contracts](batch-processing.md).

Final checks: **290 backend tests passed, one optional live acquisition test skipped**; Python typing (55 files), scoped lint/formatting and migration drift checks passed. Unchanged frontend: **12 tests**, TypeScript and production build passed. The JSON contains all five companies and 190 stage jobs; the CSV contains 35 company/metric rows, 14 available source-URL cells and no invented raw metric values.

Changed implementation: new `backend/app/pipeline/` modules; migration `6ccc1d6cca42`; batch ORM tables/settings/CLI integration; optional shared pacing in `discovery/http.py`; resumable successful-call reuse in `extraction/service.py`; batch tests and database metadata assertions; environment example and documentation/schema SQL. No frontend source or hosted deployment changed. Existing extraction observations and validation states were not altered by this batch.

Final database check confirmed exactly **one batch run (checkpoint 5, failed)**, no twenty-company run, **zero new extraction runs**, and the same 13 historical observations (none validated). A new approximately 10 MB PostgreSQL custom-format backup is retained at `backend/storage/verification/batch-checkpoint-2026-09-29.dump`, alongside all earlier backups and downloaded source files. The temporary PostgreSQL instance was stopped after verification; Ollama was left unchanged. The JSON/CSV exports remain readable without a running database.
