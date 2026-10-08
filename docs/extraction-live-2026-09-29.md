# Local extraction verification — 2026-09-29

## Scope and outcome

Local Ollama processed selected passages from **three real downloaded reports, from two companies**: Samsung 2025 (performance year 2024), Samsung 2024 (2023), and Apple 2025 (FY2024). This exercise is **not** complete extraction of those PDFs, a ten-definition sample, a benchmark, or an accuracy/coverage estimate.

Ten selected report/metric/year observations span seven canonical definitions. All ten remain **needs_review**, none validated; eight have deterministic conversions and two preserve raw values with normalisation withheld. No value or boundary was manually substituted to make the examples pass.

- [Full provenance for the ten examples](extraction-examples-2026-09-29.json): raw/normalised values, source links/hash/page/chunk/excerpt offsets, model response/digest, run parameters, confidence components, notes and validation history.
- [Complete audit of all attempts](extraction-audit-2026-09-29.json): prompts, candidate responses, unsuccessful attempts and current observations, including the rejected Scope 2 candidate.
- [Implementation and operating instructions](extraction.md).

Across development and final live runs: **21 report/metric attempts**, 18 completed and three failed (two timeouts, one interrupted attempt). Completed means processing finished, not evidence approval. The database retains 12 review observations (including two duplicate-valued historical attempts) and one rejected observation. The ten examples below are an explicitly selected presentation subset, **not canonical winner selection**.

## Local model and bounds

`ollama list` confirmed the already-installed, user-approved **qwen3:14b**. No model was downloaded or substituted. Provider: Ollama; configured URL: `http://localhost:11434`. Model digest: `bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`.

Final calls used prompt **1.1.0**, schema **metric-candidate-v1**, pipeline **metric-extraction-v2**, lexical retrieval **lexical-v1**, Decimal conversions **decimal-units-v1**, a 300-second timeout and a 2,048-token output limit. Each final job retrieved only its top one existing page-local chunk; no whole PDF or external service received source content. Earlier diagnostics used prompt 1.0.0 and a 120-second timeout.

Most examples were initially assessed by quality v2; Scope 1/2 observations were subsequently checked with the versioned v3 row-association rule. The last Samsung electricity run used quality v3 directly. The full export retains these actual versions rather than relabelling previous executions.

## Ten observations

Pages are one-based physical PDF pages; years below are performance years.

| Report | Year | Metric | Original value and unit | Normalised | Page | Call latency |
| --- | ---: | --- | --- | --- | ---: | ---: |
| Samsung Sustainability Report 2025 | 2024 | `scope_1_emissions` | 4,725 1,000 tonnes CO₂e | 4,725,000 tCO2e | 68 | 45.96 s |
| Samsung Sustainability Report 2025 | 2024 | `women_percent` | 33.1 % | 33.1 % | 65 | 62.87 s |
| Samsung Sustainability Report 2025 | 2024 | `employees` | 262,647 Individuals | 262,647 persons | 64 | 69.22 s |
| Samsung Sustainability Report 2025 | 2024 | `total_energy_consumption` | 38,772 GWh | 139,579,200 GJ | 69 | 80.07 s |
| Samsung Sustainability Report 2024 | 2023 | `scope_1_emissions` | 3,733 1,000 tonnes CO₂e | 3,733,000 tCO2e | 62 | 63.95 s |
| Samsung Sustainability Report 2024 | 2023 | `employees` | 267,860 Individuals | 267,860 persons | 58 | 80.67 s |
| Samsung Sustainability Report 2024 | 2023 | `electricity_consumption` | 29,956 GWh | 107,841,600 GJ | 62 | 59.88 s |
| Apple Environmental Progress Report 2025 | 2024 | `scope_2_location_based` | 1,224,500 tCO2e | 1,224,500 tCO2e | 104 | 113.35 s |
| Apple Environmental Progress Report 2025 | 2024 | `electricity_consumption` | 3,800 Million kilowatt hours (mkWh) | withheld | 104 | 68.32 s |
| Apple Environmental Progress Report 2025 | 2024 | `water_withdrawal` | 1,800 Million gallons | withheld | 104 | 68.48 s |

Latencies are measured adapter-call durations (not throughput predictions). Across these ten examples they range from 45.96 to 113.35 seconds. The JSON separately retains inference-request latency and attempts.

## Failures, withheld evidence and corrections

- Samsung 2025 Scope 2 market-based: the model selected **14,889**, the combined emissions total. Scope/metric evidence gates withheld it. No Scope 2 observation was created.
- Samsung 2024 Scope 2 market-based: the model selected combined total **13,291** within a broad table quote. Quality v2 initially stored a review observation; source-page inspection exposed the wrong row. The tested v3 rule and explicit `recheck-extractions` transition now mark observation `e887986f-8d88-4117-b53f-91bd168df570` **rejected**, withdraw its normalised value and preserve the raw response, original conversion and confidence in the validation audit. The correct row was not manually substituted. Repeating the recheck produced zero additional changes.
- Samsung 2024 women percentage: the target-year value looked plausible, but the model altered an earlier value within its purported verbatim quote. Literal-quote validation withheld the entire candidate.
- Samsung 2024 electricity: an earlier literal row quote labelled only “Electricity” was withheld for insufficient metric context. A tested, narrow parent energy-consumption context rule was added, then a new live call produced the tenth example. The earlier attempt remains intact.
- Apple electricity: the parsed unit wording is separated by interleaved table text and is not a recognised unit alias. Raw **3,800 Million kilowatt hours (mkWh)** is retained as review evidence; conversion is withheld.
- Apple water withdrawal: raw **1,800 Million gallons** is retained; the gallon basis is not established, so conversion is withheld.
- Initial Samsung workforce attempts timed out at 120 seconds. A separate early Scope 2 attempt was interrupted. All three failed runs remain in the audit. A stricter earlier year-in-quote rule also withheld two Scope 1 candidates; later year-header handling retained explicit context offsets and mandatory review rather than guessing alignment.
- Apple Scope 2 returned an additional candidate lacking an explicit location/market method; it was withheld. Its response remains in the same call audit.

No `not_reported` result from top-k retrieval is asserted as company-wide absence. No automatically approved benchmark data was produced.

## Source and visual verification

Using the PDF skill's render-and-inspect workflow, source tables were checked visually: Samsung 2025 physical pages 64, 65, 68 and 69; Samsung 2024 pages 58, 59 and 62; Apple 2025 page 104. Column labels, scale units, footnotes and combined-versus-scope rows were reviewed. This revealed the Scope 2 row error above. Rendered review PNGs remain in ignored `tmp/pdfs/extraction-review/`.

All ten exported excerpts were additionally verified as exact slices of both stored chunks and ordered page text. Chunk/PDF SHA-256, page/report/parse/run links, year-context offsets and local model identities were checked against the database and files. All checks passed. Source PDFs were not modified. Visual inspection does **not** automatically update boundaries or confer validated status.

Samsung footnotes distinguish reporting populations and restatements; Apple FY2024 is not a generic calendar-year boundary. These remain review issues. Unknown or unsupported model boundaries are not filled from nearby company names. A confidence of .60 is a rule-capped heuristic, not 60% statistical certainty.

## Full provenance, readable excerpts

The sections below show each original quote and its source lineage. The linked JSON includes all validation-event fields and the complete returned candidate objects; the complete audit additionally preserves the exact prompts.

### 1. Samsung Sustainability Report 2025 — scope_1_emissions

- Company: Samsung Electronics Co. Ltd. (`01900000-0000-4000-8000-000000000008`); reporting year: **2024**; raw reporting period: `2024`.
- Original: **4,725 1,000 tonnes CO₂e**; normalised: **4,725,000 tCO2e**; rule: `decimal-units-v1`.
- Boundary: unknown / unsupported (null); intensity denominator: not applicable.
- [Official source PDF](https://www.samsung.com/global/sustainability/media/pdf/Samsung_Electronics_Sustainability_Report_2025_ENG.pdf); physical page **68**. Stored document title: "Download" (discovery label, not a semantic report title).
- Report: `ad85cf22-8639-43af-889b-15a120c2ac96`; PDF SHA-256: `aee5b45480512c05b13b3bfceab1d170232aae847e6ba398b2ebdcab842f7155`.
- Storage key under `data/reports/`: `01900000-0000-4000-8000-000000000008/2025/aee5b45480512c05b13b3bfceab1d170232aae847e6ba398b2ebdcab842f7155.pdf`.
- Parse run: `82c439e3-afe6-4ce0-9759-b85f72179f0f`; chunk: `8922967b-cdbc-42fa-b45e-497a491d863b`; chunk SHA-256: `bbaf6e33fe0876aec5751448614e238bd92a3bf34e583f6dabd50033ab973f7b`.
- Exact excerpt offsets (start-inclusive, end-exclusive): chunk **160–226**, ordered page text **160–226**. Year-context chunk spans: `[[83,87],[1009,1013],[1252,1256],[1392,1396]]`.
- Metric definition: `8bef2924-5553-5f69-985c-8be8e5a06c0f`, version 1; observation: `0c64a305-c5fd-4ef8-b50b-c81b7454cd80`; extraction run: `95a4e382-323f-4269-99a7-ee93077cdbc1`.
- Method: `local_structured_llm`; model: `qwen3:14b`; prompt: `1.1.0`; schema: `metric-candidate-v1`; extracted at: `2026-09-29T12:57:00.391684+00:00`.
- Prompt SHA-256: `6f3f9cde2f3a3d40ed1ccbab74f305d5571a1b41c3d3d86ff8c09f3b98e62c7a`; schema SHA-256: `57386cf84670f5b50de33111d89a2ec28a0d78abbaf2709c61f71a90f77b8d86`; source characters: 2348; call latency: 45963.94 ms; inference latency: 45953.57 ms.
- Validation state: **needs_review**; compatibility: `unchecked`; confidence: **0.6000**, heuristic only. Components: `{"candidate_relevance":0.21875,"literal_value_support":0.15,"page_consistency":0.15,"repeated_corroboration":0,"unit_clarity":0.15,"year_match":0.2}`; model self-confidence separately retained: 0.95.
- Quality flags: `year_context_outside_excerpt`, `boundary_unknown`, `multi_year_alignment_requires_review`.
- Model status: `extracted`; model notes: "The year header is explicitly listed as 2022, 2023, 2024 in the passage.".
- Validation history: `extraction_quality/metric-quality-v2`: new → needs_review (event `9ac2f516-7e31-40f2-9f20-23614a70d1a1`); `scope_row_recheck/metric-quality-v3`: needs_review → needs_review (event `776cca4a-637f-4090-8e24-fd2dc1bedf56`).

Exact supporting excerpt:

```text
Direct emissions (Scope 1)
1,000 tonnes CO₂e
 5,972 
 3,733 
4,725
```

### 2. Samsung Sustainability Report 2025 — women_percent

- Company: Samsung Electronics Co. Ltd. (`01900000-0000-4000-8000-000000000008`); reporting year: **2024**; raw reporting period: `2024`.
- Original: **33.1 %**; normalised: **33.1 %**; rule: `decimal-units-v1`.
- Boundary: unknown / unsupported (null); intensity denominator: not applicable.
- [Official source PDF](https://www.samsung.com/global/sustainability/media/pdf/Samsung_Electronics_Sustainability_Report_2025_ENG.pdf); physical page **65**. Stored document title: "Download" (discovery label, not a semantic report title).
- Report: `ad85cf22-8639-43af-889b-15a120c2ac96`; PDF SHA-256: `aee5b45480512c05b13b3bfceab1d170232aae847e6ba398b2ebdcab842f7155`.
- Storage key under `data/reports/`: `01900000-0000-4000-8000-000000000008/2025/aee5b45480512c05b13b3bfceab1d170232aae847e6ba398b2ebdcab842f7155.pdf`.
- Parse run: `82c439e3-afe6-4ce0-9759-b85f72179f0f`; chunk: `961a4d84-397d-4eb5-98f1-065bc51d44f6`; chunk SHA-256: `9ca43dd0fc6a08c656b3cc4a3d1da8e4add6aa408946d7136b828d2802382aa2`.
- Exact excerpt offsets (start-inclusive, end-exclusive): chunk **33–131**, ordered page text **33–131**. Year-context chunk spans: `[[43,47],[1065,1069],[1954,1958]]`.
- Metric definition: `14039724-13a2-521c-80dd-7f6c867ff823`, version 1; observation: `3c30473f-1f2f-4c0e-aa6e-d92c45bbfebf`; extraction run: `50cc7af7-2583-4cd1-9426-a79ddc642e01`.
- Method: `local_structured_llm`; model: `qwen3:14b`; prompt: `1.1.0`; schema: `metric-candidate-v1`; extracted at: `2026-09-29T12:58:58.229136+00:00`.
- Prompt SHA-256: `6f30eb45b85437215fa4df987ab5facd4513ecf2f369d967ffdc60e32fadcf8c`; schema SHA-256: `57386cf84670f5b50de33111d89a2ec28a0d78abbaf2709c61f71a90f77b8d86`; source characters: 2264; call latency: 62866.07 ms; inference latency: 62834.31 ms.
- Validation state: **needs_review**; compatibility: `unchecked`; confidence: **0.6000**, heuristic only. Components: `{"candidate_relevance":0.20625,"literal_value_support":0.15,"page_consistency":0.15,"repeated_corroboration":0,"unit_clarity":0.15,"year_match":0.2}`; model self-confidence separately retained: 0.9.
- Quality flags: `boundary_unknown`, `multi_year_alignment_requires_review`.
- Model status: `extracted`; model notes: "The year header is elsewhere in this passage.".
- Validation history: `extraction_quality/metric-quality-v2`: new → needs_review (event `1896f11c-663b-44ff-bf2b-397b805e70cb`).

Exact supporting excerpt:

```text
2022
2023
2024
[Percentage of female employees]
1)
Percentage of female employees
%
35.1
33.7
33.1
```

### 3. Samsung Sustainability Report 2025 — employees

- Company: Samsung Electronics Co. Ltd. (`01900000-0000-4000-8000-000000000008`); reporting year: **2024**; raw reporting period: `2024`.
- Original: **262,647 Individuals**; normalised: **262,647 persons**; rule: `decimal-units-v1`.
- Boundary: unknown / unsupported (null); intensity denominator: not applicable.
- [Official source PDF](https://www.samsung.com/global/sustainability/media/pdf/Samsung_Electronics_Sustainability_Report_2025_ENG.pdf); physical page **64**. Stored document title: "Download" (discovery label, not a semantic report title).
- Report: `ad85cf22-8639-43af-889b-15a120c2ac96`; PDF SHA-256: `aee5b45480512c05b13b3bfceab1d170232aae847e6ba398b2ebdcab842f7155`.
- Storage key under `data/reports/`: `01900000-0000-4000-8000-000000000008/2025/aee5b45480512c05b13b3bfceab1d170232aae847e6ba398b2ebdcab842f7155.pdf`.
- Parse run: `82c439e3-afe6-4ce0-9759-b85f72179f0f`; chunk: `5997538a-2d43-4904-a256-865d0073e9ea`; chunk SHA-256: `d2a3ed8b8a3ba37f0f966f728077a04fd994d62cbcd9fba0e26d5a5e7f39d768`.
- Exact excerpt offsets (start-inclusive, end-exclusive): chunk **0–96**, ordered page text **0–96**. Year-context chunk spans: `[[26,30],[1687,1691]]`.
- Metric definition: `e80db8f2-a3c1-5c64-b7ab-98a1e9e3a232`, version 1; observation: `02655e47-2ea7-472a-a082-475b8613bd2a`; extraction run: `faecc947-e493-43c8-9499-af887ebe36d9`.
- Method: `local_structured_llm`; model: `qwen3:14b`; prompt: `1.1.0`; schema: `metric-candidate-v1`; extracted at: `2026-09-29T13:00:07.548831+00:00`.
- Prompt SHA-256: `7903f40fb20f476b88009b9be805a93f3f8669a70185ab18d1750de5d8cdbdd3`; schema SHA-256: `57386cf84670f5b50de33111d89a2ec28a0d78abbaf2709c61f71a90f77b8d86`; source characters: 2340; call latency: 69225 ms; inference latency: 69182.47 ms.
- Validation state: **needs_review**; compatibility: `unchecked`; confidence: **0.6000**, heuristic only. Components: `{"candidate_relevance":0.20625,"literal_value_support":0.15,"page_consistency":0.15,"repeated_corroboration":0,"unit_clarity":0.15,"year_match":0.2}`; model self-confidence separately retained: 0.95.
- Quality flags: `boundary_unknown`, `multi_year_alignment_requires_review`.
- Model status: `extracted`; model notes: "The year header is explicitly stated in the passage.".
- Validation history: `extraction_quality/metric-quality-v2`: new → needs_review (event `ec2cb973-aa4f-4bf2-9fa7-acf40ad8a4a8`).

Exact supporting excerpt:

```text
Employee Status
2022
2023
2024
1)
Number of employees
Individuals
270,278 
 267,860 
 262,647 
*
```

### 4. Samsung Sustainability Report 2025 — total_energy_consumption

- Company: Samsung Electronics Co. Ltd. (`01900000-0000-4000-8000-000000000008`); reporting year: **2024**; raw reporting period: `2024`.
- Original: **38,772 GWh**; normalised: **139,579,200 GJ**; rule: `decimal-units-v1`.
- Boundary: unknown / unsupported (null); intensity denominator: not applicable.
- [Official source PDF](https://www.samsung.com/global/sustainability/media/pdf/Samsung_Electronics_Sustainability_Report_2025_ENG.pdf); physical page **69**. Stored document title: "Download" (discovery label, not a semantic report title).
- Report: `ad85cf22-8639-43af-889b-15a120c2ac96`; PDF SHA-256: `aee5b45480512c05b13b3bfceab1d170232aae847e6ba398b2ebdcab842f7155`.
- Storage key under `data/reports/`: `01900000-0000-4000-8000-000000000008/2025/aee5b45480512c05b13b3bfceab1d170232aae847e6ba398b2ebdcab842f7155.pdf`.
- Parse run: `82c439e3-afe6-4ce0-9759-b85f72179f0f`; chunk: `0287b88e-1501-4035-836d-2b7250aa1c25`; chunk SHA-256: `cbce697a9f41ff0f970a69b6544cdc5bd0209b808053bbbb1290901aa3e1879e`.
- Exact excerpt offsets (start-inclusive, end-exclusive): chunk **33–98**, ordered page text **33–98**. Year-context chunk spans: `[[28,32],[946,950],[1150,1154],[1664,1668]]`.
- Metric definition: `b04fe958-176f-5749-840f-802788b325a8`, version 1; observation: `19c8623e-8e89-474c-99a2-1e83ba4194c1`; extraction run: `13da197b-ccf8-4849-8073-388fc7d90e4a`.
- Method: `local_structured_llm`; model: `qwen3:14b`; prompt: `1.1.0`; schema: `metric-candidate-v1`; extracted at: `2026-09-29T13:01:27.752869+00:00`.
- Prompt SHA-256: `7079ec8cc14ff6cfbba5ad1101904386b26586497cf882e19f86a4fb342f899a`; schema SHA-256: `57386cf84670f5b50de33111d89a2ec28a0d78abbaf2709c61f71a90f77b8d86`; source characters: 2400; call latency: 80069.81 ms; inference latency: 80021.64 ms.
- Validation state: **needs_review**; compatibility: `unchecked`; confidence: **0.6000**, heuristic only. Components: `{"candidate_relevance":0.23125,"literal_value_support":0.15,"page_consistency":0.15,"repeated_corroboration":0,"unit_clarity":0.15,"year_match":0.2}`; model self-confidence separately retained: 0.9.
- Quality flags: `year_context_outside_excerpt`, `boundary_unknown`, `multi_year_alignment_requires_review`.
- Model status: `extracted`; model notes: "The year header is listed above the data in the passage.".
- Validation history: `extraction_quality/metric-quality-v2`: new → needs_review (event `33441be4-ae3f-4b2f-9d55-5f488ccf0cc1`).

Exact supporting excerpt:

```text
Energy consumption at business sites
GWh
 35,177 
 36,399 
38,772
```

### 5. Samsung Sustainability Report 2024 — scope_1_emissions

- Company: Samsung Electronics Co. Ltd. (`01900000-0000-4000-8000-000000000008`); reporting year: **2023**; raw reporting period: `2023`.
- Original: **3,733 1,000 tonnes CO₂e**; normalised: **3,733,000 tCO2e**; rule: `decimal-units-v1`.
- Boundary: unknown / unsupported (null); intensity denominator: not applicable.
- [Official source PDF](https://www.samsung.com/global/sustainability/media/pdf/Samsung_Electronics_Sustainability_Report_2024_ENG.pdf); physical page **62**. Stored document title: "Download" (discovery label, not a semantic report title).
- Report: `4c454a7e-542d-4fdd-a770-832cf02f0790`; PDF SHA-256: `10e8067428e488958c8558c831cfa4145e84865a372943040e47093852135d18`.
- Storage key under `data/reports/`: `01900000-0000-4000-8000-000000000008/2024/10e8067428e488958c8558c831cfa4145e84865a372943040e47093852135d18.pdf`.
- Parse run: `52f295eb-6675-44aa-9edd-2447d86ad2e1`; chunk: `ca05a196-fe2a-4d11-b7d9-ae5028134759`; chunk SHA-256: `50eb179054f400131ac64224d177c80471135f7e679451066263524ba4b2b73e`.
- Exact excerpt offsets (start-inclusive, end-exclusive): chunk **154–221**, ordered page text **154–221**. Year-context chunk spans: `[[73,77],[1369,1373],[2150,2154]]`.
- Metric definition: `8bef2924-5553-5f69-985c-8be8e5a06c0f`, version 1; observation: `af55e2d2-b79d-4e40-a2bd-dae39f5f0571`; extraction run: `64cd2a63-5c37-4308-9c69-a54bf22ec897`.
- Method: `local_structured_llm`; model: `qwen3:14b`; prompt: `1.1.0`; schema: `metric-candidate-v1`; extracted at: `2026-09-29T13:02:32.976376+00:00`.
- Prompt SHA-256: `bf139950ca73ef0a314cc8f817c589eefd2dd046a5f83e7e669b194f34f57aed`; schema SHA-256: `57386cf84670f5b50de33111d89a2ec28a0d78abbaf2709c61f71a90f77b8d86`; source characters: 2400; call latency: 63953.51 ms; inference latency: 63929.58 ms.
- Validation state: **needs_review**; compatibility: `unchecked`; confidence: **0.6000**, heuristic only. Components: `{"candidate_relevance":0.21875,"literal_value_support":0.15,"page_consistency":0.15,"repeated_corroboration":0,"unit_clarity":0.15,"year_match":0.2}`; model self-confidence separately retained: 0.95.
- Quality flags: `year_context_outside_excerpt`, `boundary_unknown`, `multi_year_alignment_requires_review`.
- Model status: `extracted`; model notes: "The year header is elsewhere in this supplied passage.".
- Validation history: `extraction_quality/metric-quality-v2`: new → needs_review (event `b3e3a884-5e71-4e89-acd9-104562f487dd`); `scope_row_recheck/metric-quality-v3`: needs_review → needs_review (event `a490e2b6-e361-4f94-928b-1009cfb83002`).

Exact supporting excerpt:

```text
Direct emissions (Scope 1)
1,000 tonnes CO₂e
 7,604 
 5,972 
 3,733
```

### 6. Samsung Sustainability Report 2024 — employees

- Company: Samsung Electronics Co. Ltd. (`01900000-0000-4000-8000-000000000008`); reporting year: **2023**; raw reporting period: `2023`.
- Original: **267,860 Individuals**; normalised: **267,860 persons**; rule: `decimal-units-v1`.
- Boundary: unknown / unsupported (null); intensity denominator: not applicable.
- [Official source PDF](https://www.samsung.com/global/sustainability/media/pdf/Samsung_Electronics_Sustainability_Report_2024_ENG.pdf); physical page **58**. Stored document title: "Download" (discovery label, not a semantic report title).
- Report: `4c454a7e-542d-4fdd-a770-832cf02f0790`; PDF SHA-256: `10e8067428e488958c8558c831cfa4145e84865a372943040e47093852135d18`.
- Storage key under `data/reports/`: `01900000-0000-4000-8000-000000000008/2024/10e8067428e488958c8558c831cfa4145e84865a372943040e47093852135d18.pdf`.
- Parse run: `52f295eb-6675-44aa-9edd-2447d86ad2e1`; chunk: `0713c875-7a02-45c6-b978-3adb33d99d49`; chunk SHA-256: `4c53e1568a72d4bd60c509a46f1da226716b6cc557cf0aed7cd53832129f7233`.
- Exact excerpt offsets (start-inclusive, end-exclusive): chunk **31–209**, ordered page text **31–209**. Year-context chunk spans: `[[26,30],[1387,1391]]`.
- Metric definition: `e80db8f2-a3c1-5c64-b7ab-98a1e9e3a232`, version 1; observation: `37ab52c0-13e5-4997-af16-b1fc3f9bd333`; extraction run: `7785b305-21bf-4a4b-8d90-1647009987f1`.
- Method: `local_structured_llm`; model: `qwen3:14b`; prompt: `1.1.0`; schema: `metric-candidate-v1`; extracted at: `2026-09-29T13:06:42.285974+00:00`.
- Prompt SHA-256: `151cbc5974ced5498e523243d93fbf3e04c15cea91ffe7a1da7d1b84318c54d6`; schema SHA-256: `57386cf84670f5b50de33111d89a2ec28a0d78abbaf2709c61f71a90f77b8d86`; source characters: 2364; call latency: 80670.91 ms; inference latency: 80623.34 ms.
- Validation state: **needs_review**; compatibility: `unchecked`; confidence: **0.6000**, heuristic only. Components: `{"candidate_relevance":0.20625,"literal_value_support":0.15,"page_consistency":0.15,"repeated_corroboration":0,"unit_clarity":0.15,"year_match":0.2}`; model self-confidence separately retained: 0.95.
- Quality flags: `year_context_outside_excerpt`, `boundary_unknown`, `multi_year_alignment_requires_review`.
- Model status: `extracted`; model notes: "The year header is explicitly stated in the passage.".
- Validation history: `extraction_quality/metric-quality-v2`: new → needs_review (event `24dda00b-9928-4df1-a109-12f7a98a0444`).

Exact supporting excerpt:

```text
Number of employees
Total number of employees
1) 
Individuals
266,644 
270,278 
267,860 
Korea
Individuals
111,126 
117,927 
120,756
Global*
Individuals
155,518 
152,351 
147,104
```

### 7. Samsung Sustainability Report 2024 — electricity_consumption

- Company: Samsung Electronics Co. Ltd. (`01900000-0000-4000-8000-000000000008`); reporting year: **2023**; raw reporting period: `2023`.
- Original: **29,956 GWh**; normalised: **107,841,600 GJ**; rule: `decimal-units-v1`.
- Boundary: unknown / unsupported (null); intensity denominator: not applicable.
- [Official source PDF](https://www.samsung.com/global/sustainability/media/pdf/Samsung_Electronics_Sustainability_Report_2024_ENG.pdf); physical page **62**. Stored document title: "Download" (discovery label, not a semantic report title).
- Report: `4c454a7e-542d-4fdd-a770-832cf02f0790`; PDF SHA-256: `10e8067428e488958c8558c831cfa4145e84865a372943040e47093852135d18`.
- Storage key under `data/reports/`: `01900000-0000-4000-8000-000000000008/2024/10e8067428e488958c8558c831cfa4145e84865a372943040e47093852135d18.pdf`.
- Parse run: `52f295eb-6675-44aa-9edd-2447d86ad2e1`; chunk: `3cb223b1-d93a-4535-9ea8-9dd167b450cc`; chunk SHA-256: `b2137c361f52c28123d0572b652c35a0e664298abe56b016f331ec0c28dc53f3`.
- Exact excerpt offsets (start-inclusive, end-exclusive): chunk **677–717**, ordered page text **3077–3117**. Year-context chunk spans: `[[569,573]]`.
- Metric definition: `400609e1-9acb-5f91-a4fd-b82bc6e44a70`, version 1; observation: `4d3774ff-c626-43cf-a8e6-80dc1258c553`; extraction run: `3ff4c3ac-faeb-4355-b164-7092d84c85c6`.
- Method: `local_structured_llm`; model: `qwen3:14b`; prompt: `1.1.0`; schema: `metric-candidate-v1`; extracted at: `2026-09-29T13:13:43.516254+00:00`.
- Prompt SHA-256: `0a961e5686c401d005f043028ec991665e519583b0072a8923b9f6cd538b27d2`; schema SHA-256: `57386cf84670f5b50de33111d89a2ec28a0d78abbaf2709c61f71a90f77b8d86`; source characters: 1513; call latency: 59883.89 ms; inference latency: 59849.68 ms.
- Validation state: **needs_review**; compatibility: `unchecked`; confidence: **0.6000**, heuristic only. Components: `{"candidate_relevance":0.18125,"literal_value_support":0.15,"page_consistency":0.15,"repeated_corroboration":0,"unit_clarity":0.15,"year_match":0.2}`; model self-confidence separately retained: 0.9.
- Quality flags: `year_context_outside_excerpt`, `boundary_unknown`, `metric_context_parent_section`, `multi_year_alignment_requires_review`.
- Model status: `extracted`; model notes: "The year header is elsewhere in this supplied passage.".
- Validation history: `extraction_quality/metric-quality-v3`: new → needs_review (event `2e4f710e-a63d-4876-84a4-9a8f683a831f`).

Exact supporting excerpt:

```text
Electricity
GWh
 25,767 
 28,316 
29,956
```

### 8. Apple Environmental Progress Report 2025 — scope_2_location_based

- Company: Apple Inc. (`01900000-0000-4000-8000-000000000005`); reporting year: **2024**; raw reporting period: `through September 30, 2024`.
- Original: **1,224,500 tCO2e**; normalised: **1,224,500 tCO2e**; rule: `decimal-units-v1`.
- Boundary: unknown / unsupported (null); intensity denominator: not applicable.
- [Official source PDF](https://www.apple.com/environment/pdf/Apple_Environmental_Progress_Report_2025.pdf); physical page **104**. Stored document title: "View (PDF)" (discovery label, not a semantic report title).
- Report: `6aeb395b-b23a-4340-9886-72e4277190ba`; PDF SHA-256: `597676e8b48ac45529303abc7ef47425ca62ff4efc3a375962a077a033525f74`.
- Storage key under `data/reports/`: `01900000-0000-4000-8000-000000000005/2025/597676e8b48ac45529303abc7ef47425ca62ff4efc3a375962a077a033525f74.pdf`.
- Parse run: `1bfcce1c-3818-458c-8f0d-fac191cf3a66`; chunk: `c1070643-99bc-4e72-92ad-86f53f4399ed`; chunk SHA-256: `0d1a23ce94d264afe2d3995187ab8c36533a02efd12880de9f2efbb5769febd4`.
- Exact excerpt offsets (start-inclusive, end-exclusive): chunk **591–706**, ordered page text **5328–5443**. Year-context chunk spans: `[[22,26]]`.
- Metric definition: `4664e5d4-f3ff-5c73-a1b2-02df84219fc8`, version 1; observation: `c704c853-1c17-4634-ba15-e478555c209a`; extraction run: `dac32d7d-c275-48a3-87ae-43badad676fe`.
- Method: `local_structured_llm`; model: `qwen3:14b`; prompt: `1.1.0`; schema: `metric-candidate-v1`; extracted at: `2026-09-29T13:09:31.085526+00:00`.
- Prompt SHA-256: `74a9446650332e2f92c0edaae1c994941b33c63873c3ef7b1de7955b4a82326a`; schema SHA-256: `57386cf84670f5b50de33111d89a2ec28a0d78abbaf2709c61f71a90f77b8d86`; source characters: 2397; call latency: 113352.79 ms; inference latency: 113306.91 ms.
- Validation state: **needs_review**; compatibility: `unchecked`; confidence: **0.6000**, heuristic only. Components: `{"candidate_relevance":0.14375,"literal_value_support":0.15,"page_consistency":0.15,"repeated_corroboration":0,"unit_clarity":0.15,"year_match":0.2}`; model self-confidence separately retained: 0.95.
- Quality flags: `year_context_outside_excerpt`, `boundary_not_in_chunk`, `multi_year_alignment_requires_review`.
- Model status: `extracted`; model notes: "The year header is mentioned in the passage as 'through September 30, 2024'.".
- Validation history: `extraction_quality/metric-quality-v3`: new → needs_review (event `30065f74-a069-488f-946b-21c8a7d3e205`); `scope_row_recheck/metric-quality-v3`: needs_review → needs_review (event `73277411-0ade-40c6-ae83-ed2d65573d65`).

Exact supporting excerpt:

```text
Worldwide occupied 
Scope 2 GHG Emissions 
(Location-Based) 
1,224,500 
tCO2e 
properties / WRI/WBCSD 
GHG Protocol
```

### 9. Apple Environmental Progress Report 2025 — electricity_consumption

- Company: Apple Inc. (`01900000-0000-4000-8000-000000000005`); reporting year: **2024**; raw reporting period: `through September 30, 2024`.
- Original: **3,800 Million kilowatt hours (mkWh)**; normalised: **withheld**; rule: `none`.
- Boundary: unknown / unsupported (null); intensity denominator: not applicable.
- [Official source PDF](https://www.apple.com/environment/pdf/Apple_Environmental_Progress_Report_2025.pdf); physical page **104**. Stored document title: "View (PDF)" (discovery label, not a semantic report title).
- Report: `6aeb395b-b23a-4340-9886-72e4277190ba`; PDF SHA-256: `597676e8b48ac45529303abc7ef47425ca62ff4efc3a375962a077a033525f74`.
- Storage key under `data/reports/`: `01900000-0000-4000-8000-000000000005/2025/597676e8b48ac45529303abc7ef47425ca62ff4efc3a375962a077a033525f74.pdf`.
- Parse run: `1bfcce1c-3818-458c-8f0d-fac191cf3a66`; chunk: `c1070643-99bc-4e72-92ad-86f53f4399ed`; chunk SHA-256: `0d1a23ce94d264afe2d3995187ab8c36533a02efd12880de9f2efbb5769febd4`.
- Exact excerpt offsets (start-inclusive, end-exclusive): chunk **217–338**, ordered page text **4954–5075**. Year-context chunk spans: `[[22,26]]`.
- Metric definition: `400609e1-9acb-5f91-a4fd-b82bc6e44a70`, version 1; observation: `daf926e0-ef48-43a8-a177-98b841d89f13`; extraction run: `8bd26683-7c7f-4036-ac0a-1548b60818bd`.
- Method: `local_structured_llm`; model: `qwen3:14b`; prompt: `1.1.0`; schema: `metric-candidate-v1`; extracted at: `2026-09-29T13:10:39.741121+00:00`.
- Prompt SHA-256: `b793a9882a797a84101b07f953192cdb74f7a9f330d07262e5fdf04ee8e462d5`; schema SHA-256: `57386cf84670f5b50de33111d89a2ec28a0d78abbaf2709c61f71a90f77b8d86`; source characters: 2397; call latency: 68317.35 ms; inference latency: 68229.57 ms.
- Validation state: **needs_review**; compatibility: `unchecked`; confidence: **0.6000**, heuristic only. Components: `{"candidate_relevance":0.18125,"literal_value_support":0.15,"page_consistency":0.15,"repeated_corroboration":0,"unit_clarity":0,"year_match":0.2}`; model self-confidence separately retained: 0.9.
- Quality flags: `year_context_outside_excerpt`, `boundary_not_in_chunk`, `unit_not_in_excerpt`, `multi_year_alignment_requires_review`, `unknown_or_incompatible_unit`.
- Model status: `extracted`; model notes: "The excerpt includes the metric label, unit, and value for the reporting period 'through September 30, 2024'.".
- Validation history: `extraction_quality/metric-quality-v3`: new → needs_review (event `2a52b121-eecb-4da2-8a43-08e21d9d5a09`).

Exact supporting excerpt:

```text
Worldwide occupied 
Million kilowatt hours 
Electricity Consumption 
3,800 
(mkWh) 
properties / Apple Internal 
Protocol
```

### 10. Apple Environmental Progress Report 2025 — water_withdrawal

- Company: Apple Inc. (`01900000-0000-4000-8000-000000000005`); reporting year: **2024**; raw reporting period: `through September 30, 2024`.
- Original: **1,800 Million gallons**; normalised: **withheld**; rule: `none`.
- Boundary: "properties / Apple Internal Protocol"; intensity denominator: not applicable.
- [Official source PDF](https://www.apple.com/environment/pdf/Apple_Environmental_Progress_Report_2025.pdf); physical page **104**. Stored document title: "View (PDF)" (discovery label, not a semantic report title).
- Report: `6aeb395b-b23a-4340-9886-72e4277190ba`; PDF SHA-256: `597676e8b48ac45529303abc7ef47425ca62ff4efc3a375962a077a033525f74`.
- Storage key under `data/reports/`: `01900000-0000-4000-8000-000000000005/2025/597676e8b48ac45529303abc7ef47425ca62ff4efc3a375962a077a033525f74.pdf`.
- Parse run: `1bfcce1c-3818-458c-8f0d-fac191cf3a66`; chunk: `c1070643-99bc-4e72-92ad-86f53f4399ed`; chunk SHA-256: `0d1a23ce94d264afe2d3995187ab8c36533a02efd12880de9f2efbb5769febd4`.
- Exact excerpt offsets (start-inclusive, end-exclusive): chunk **2178–2277**, ordered page text **6915–7014**. Year-context chunk spans: `[[22,26]]`.
- Metric definition: `7a4b19bd-b525-5af9-8ef2-c09be8a80469`, version 1; observation: `6871d113-18d3-4915-9e9a-b8c000e2a264`; extraction run: `8eba5b41-ddea-4806-aacc-e3fa673f3ec3`.
- Method: `local_structured_llm`; model: `qwen3:14b`; prompt: `1.1.0`; schema: `metric-candidate-v1`; extracted at: `2026-09-29T13:11:48.498292+00:00`.
- Prompt SHA-256: `3a140f0fe1f4726caf8e4f4cf314789640520905a2cd8ab878f904fce456531c`; schema SHA-256: `57386cf84670f5b50de33111d89a2ec28a0d78abbaf2709c61f71a90f77b8d86`; source characters: 2397; call latency: 68484.74 ms; inference latency: 68386.66 ms.
- Validation state: **needs_review**; compatibility: `unchecked`; confidence: **0.6000**, heuristic only. Components: `{"candidate_relevance":0.14375,"literal_value_support":0.15,"page_consistency":0.15,"repeated_corroboration":0,"unit_clarity":0,"year_match":0.2}`; model self-confidence separately retained: 0.9.
- Quality flags: `year_context_outside_excerpt`, `multi_year_alignment_requires_review`, `unknown_or_incompatible_unit`.
- Model status: `extracted`; model notes: "The year header is mentioned in the passage as 'through September 30, 2024'.".
- Validation history: `extraction_quality/metric-quality-v3`: new → needs_review (event `0c8a7b7f-90fb-4b47-8fc6-c5826a5c9491`).

Exact supporting excerpt:

```text
Worldwide occupied 
Water Withdrawal 
1,800 
Million gallons 
properties / Apple Internal 
Protocol
```

## Test and implementation handoff

- Backend: **263 passed, one optional live acquisition test skipped**, including 55 extraction tests and 53 adapter tests. Routine extraction tests use fictional fixtures and a mock local adapter.
- Fixtures cover clean emissions, missing Scope 3, targets versus actuals, multi-year tables, intensity-only data, conflicts and different units. Further tests cover cancellation, partial failures, source checks, persistence, idempotence and auditable rechecks.
- Python typing: all 48 application files passed. Scoped lint/formatting, dependency consistency and Alembic schema-drift checks passed.
- Unchanged frontend: 12 tests, TypeScript checking and production build passed.
- No schema migration, frontend/deployment update, scraping, OCR, external provider call or model download was introduced.

The local PostgreSQL evidence snapshot is preserved in `backend/storage/verification/extraction-smoke-2026-09-29.dump` (custom-format archive, approximately 10 MB; archive directory listing verified). This is a full snapshot of the task's development database, not a migration or a production seed. The temporary PostgreSQL instance on port 55432 was stopped after verification; its files and this backup remain available. Ollama was left unchanged. JSON provenance exports can be inspected without starting a database.

Changed files: `backend/app/extraction/{__init__,contracts,retrieval,prompts,normalisation,quality,recheck,service,cli}.py`; `backend/app/cli.py`; provider-neutral identity additions in `backend/app/llm/{contracts,ollama}.py`; `backend/tests/test_extraction.py`; `backend/tests/fixtures/extraction.json`; README and architecture/database/catalogue/local-AI/extraction documentation; these verification exports. The frozen metric catalogue and downloaded/parsed sources were not changed.
