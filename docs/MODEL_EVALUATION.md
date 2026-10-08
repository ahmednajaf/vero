# Local model evaluation — 1 October 2026

Historical baseline, retained for the measured failures. This is not the active
provider configuration or evidence that the current hosted model has passed a
full accuracy benchmark. Current configuration and release limits are in the
[README](../README.md).

Gemma 3 4B (`gemma3:4b`, approximately 3.3 GB) was downloaded with the user's approval. Ollama had no installed models beforehand. No Qwen model was downloaded, no hosted calls were made and no paid fallback was used.

| Measure | Result |
|---|---:|
| Frozen pharma cases | 18 |
| Schema-valid output | 17 / 18 |
| Fully correct cases | 5 / 18 |
| Source-grounding checks | 9 / 18 |
| Unsupported inference failures | 12 |
| Incomplete outputs | 1 |
| Median latency, successful calls | 19.52 s |
| Mean latency, successful calls | 23.38 s |
| Hosted inference cost | $0 |

**Decision: not approved for unattended extraction or publication.** The functioning report uses the pre-existing source-checked study, not these new model answers. Disk fit is not evidence of analytical reliability.

## Test method

The unchanged `data/model-evaluation/pharma-v1.json` supplies 18 previously frozen real-report cases covering neighbouring Scope 1/2 rows, Scope 2 accounting methods, Scope 3 totals/categories, mixed years, targets, renewable electricity versus energy, missing values and source pages. Gold answers are never passed to the model. Input is the supplied pages, not an entire PDF. Sequential local calls use temperature 0, 8,192 context tokens and a 1,024-token output bound.

The test requires metric/value/year agreement, an exact raw unit match after case/whitespace normalisation, the expected physical page and a verbatim source excerpt. Scope 1/2 row checks reject values belonging to another scope. Missing cases require null value/unit/year/page with an empty excerpt. Unit matching is deliberately strict and can penalise equivalent wording; the result is not a general model capability rating. It measures this prompt/input/scorer combination and does not validate full-document retrieval.

Unsupported inference counts any non-null answer where gold is absent, grounding fails, metric/value/year is wrong, or a scope-row check fails. Source grounding alone is not truth: some wrong-year table values still appear literally on the cited page.

## Failures found

- GSK table years/values were misassociated in Scope 1/2 cases.
- Missing disclosures sometimes produced non-null values.
- A net-zero target's future year was confused with its reporting year.
- Scope 3/category and water-consumption cases failed.
- One missing-target case exhausted the output bound.
- Table quotations and pages did not consistently identify the requested value.

All outputs, flags, latency, model digest, fixture fingerprint and prompt hashes are retained in `output/model-evaluation/local-gemma3-4b.json`. No gold values or failed cases were altered, excluded or promoted to research evidence.

## Next experiment

Evaluate header-preserving table context and row/year association before trying another larger model. Keep this baseline, repeat the same cases under a new prompt version and separately test unseen reports. Any automation decision needs both error rate and review burden, not merely valid JSON. Do not download a larger model without approval.
