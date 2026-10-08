# Sustainability Race

An arcade-inspired, supplementary view at `/race`: CSS top-down cars, a moving navy circuit, peer-relative exhaust, explicit ranks, disclosure badges and an evidence-led companion panel. No game engine, Three.js, new dependency, model call, collection run or database mutation is involved.

## Data policy and current limitation

**The current backend deliberately disables composite rankings. This change does not override that policy.** Live mode starts with an honest empty starting grid. The frontend adapter accepts future, explicitly eligible engine outputs; it does not invent overall ranks from existing partial scores or substitute a single metric for an overall score. Enabling real composite ranking requires a separate methodology decision and backend implementation. No real-company race coverage is claimed.

The explicitly selected **Fictional demo** is a separately loaded module: 24 fictional companies in each of five sectors, with deterministic illustrative values. A banner, circuit badge, company label, table caption and source-drawer warning identify it as synthetic. A connection failure never activates it. It writes nothing to storage or the API. Its source drawers contain no invented report URL, page or validation claim. Changing its year changes a fictional scenario, not recorded company history.

The runtime contract includes the requested fields:

```ts
{
  id, name, ticker, sector,
  benchmarkScore, peerPercentile, rank,
  emissionsIntensity, emissionsYoYChange,
  renewableEnergyPercent, disclosureCompleteness,
  netZeroTargetYear
}
```

It additionally carries country, reporting year, score-cohort key, peer sample size, intensity unit/cohort/percentile, metric provenance, the original benchmark record and an explicit demo flag.

For live entries, `score.ranking_eligible` must be true and `score.ranking` must contain rank, percentile, peer sample size, cohort key and no exclusion reason. The score must have 100% coverage, three usable components with the expected weights and current official provenance, no score exclusion reason, and the engine's minimum peer sample (currently five). The response parser rejects malformed rank objects. This is a defensive display gate, **not an implementation of backend score comparability or validation**.

## Deterministic mappings

Let `P` be the supplied score percentile clamped to 0–100, `q` be a comparable intensity percentile divided by 100, and `Δ` the eligible YoY absolute emissions percentage change. Missing values remain missing.

| Signal | Exact mapping |
| --- | --- |
| Vertical anchor | `Y = 66 + 410 × (1 − P/100)` pixels. P100 = 66, P50 = 271, P0 = 476. Tied percentiles have identical Y. |
| Horizontal lane | Stable ID ordering within the displayed heat. Layout only; no analytical meaning. |
| Rank label | Engine-supplied rank in the comparable sector score cohort. It is not a ranking of all companies in that sector. |
| Exhaust length | `28 + 96q` pixels. |
| Exhaust width | `14 + 22q` pixels. |
| Exhaust opacity | `0.14 + 0.32q`. |
| Exhaust particles | `2 + round(4q)`; particle cycle `2.8 − q` seconds. |
| Exhaust appearance | Teal for Δ < 0, sand for Δ > 0, grey for unchanged/unknown. Exact signed Δ remains in the detail/table/list. |
| Acceleration accent | One 0.9-second pulse: maximum displacement `5 × min(max(−Δ, 0)/30, 1)` pixels, then back to the same data anchor. Unknown Δ produces no pulse. |
| Disclosure badge | `D round(completeness)%`; unknown is `D —`. Detail/table retain the underlying displayed precision. |

Intensity is currently the engine's derived emissions per revenue, with its own cohort key and denominator/currency/period checks. Only one comparable intensity cohort is visualised at once. A selector appears if the eligible score cohort contains multiple intensity bases. Other bases and missing/undersized intensity samples get **E —**, not a zero-emissions or “clean” plume. The exhaust sample size is shown separately from the score sample size.

The exhaust is a comparative metaphor, **not physical pollution, concentration, exact particulate emissions or an ozone model**. An emissions decrease is not proof of broad sustainability improvement. There is no net-zero finish line.

### Score and percentile illustration

The demo illustrates the existing prototype weights, requiring complete inputs:

```text
trajectory = clamp(50 − 2.5 × YoY percentage change, 0, 100)
score = 0.45 × trajectory + 0.35 × renewable energy % + 0.20 × disclosure %
rank = 1 + number of peer scores strictly greater
percentile = 100 × (number below + (number tied − 1)/2) / (n − 1)
```

All-equal peers receive P50 and competition rank 1. Demo calculations use all 24 fictional sector peers before country/top-N filtering. They are isolated from live mode. Exhaust, car paint, net-zero promises and animation never enter the score.

The current production engine can show a prototype score with only its two performance components and 80% weight coverage, but **the Race rejects such partial scores**. This UI does not change the backend scoring methodology. Label everywhere: **Prototype benchmark score — not an external ESG rating.**

## Motion versus aesthetics

- Supplied percentile changes drive a 0.85-second vertical transform transition. Retained IDs keep a position cache across year/heat changes; no random walk or simulated race result exists.
- Layout changes reposition lanes over the same duration. No passing or winning event changes rank.
- Exhaust geometry, count, cycle and treatment depend on the defined measurements above. The small acceleration accent is keyed to the reporting year/YoY value, not continuously accruing points.
- Constant road motion (67 pixels per 1.7 seconds), car paint, shadows, chassis styling, selected-car glow and particle staggering are purely aesthetic. They imply neither real-time environmental progress nor changes to score.
- Manual pause, system reduced-motion preference, a hidden document and an offscreen circuit pause motion. Reduced-motion rules also remove transitions. Numeric information remains available.

**Benchmark inputs determine ranking. Animation never determines, updates or feeds back into ranking.**

## Interaction and evidence

Default is Technology/top 10 when available. Sector, country, top 10/top 20, reporting year and, when necessary, comparable score cohort can be changed. Country and top-N filters retain the original sector positions and peer sample; they do not produce a country-specific rank. Reporting year changes request that API cycle; unavailable years stay unavailable. There is no live historical replay because eligible reviewed multi-year overall rankings are not available.

Hover, focus or click selects a car. The panel contains all requested fields, sector-cohort rank and sample size. Every factor opens the existing source drawer with report title, year, page, excerpt, raw and normalised value/unit, validation state, audit information and original report link where present. The “Why this position?” median explanations include all contributing peer observations from the same API snapshot, not only the selected company. Derived values retain their input observations and formula.

Median differences for percentage metrics are expressed in **percentage points**, not ambiguously as “percent worse”. Unknown Scope 3 disclosure is not called absent; source-reviewed presence and absence are separate. Net-zero target years are commitments, not achieved performance. The frontend does not promote an extracted observation to validated.

## Table, accessibility and responsive behaviour

The **Data table** has rank, company/ticker/country, percentile, score, intensity/unit, YoY emissions, renewable energy, disclosure and target year. The **Accessible company list** exposes the same values, sector/year and sample sizes without relying on motion or colour. Native buttons support keyboard selection and open the same companion panel/evidence actions. The source drawer retains focus trapping, Escape, inert background and focus restoration.

Desktop renders up to 20 cars with a side panel and horizontal track scrolling as needed. Tablet renders six per heat; mobile renders four. Next/previous heats select a visible company. Selecting a company from the table/list also selects its heat when returning to the track. The full selected top-N population remains in the table and list. Wide tables scroll within their container.

## Performance and verification

DOM/CSS implementation; no new renderer or dependency. At most 20 car elements and 120 smoke particles, six tablet/four mobile cars. One transformed road-marking layer, transform/opacity smoke animation and one `requestAnimationFrame` update per changed car anchor; no JavaScript simulation loop. Horizontal lane transitions can incur layout, but only on selection/filter changes across the bounded set. Blur/shadows still incur rendering work and need device-level profiling; no measured FPS claim is made.

The demo is lazy-loaded (approximately 2.9 kB minified / 1.3 kB gzip). Whole-app main JavaScript is approximately 337 kB / 102 kB gzip; existing chart and globe chunks remain separate. These are build sizes, not runtime performance measurements.

```bash
cd frontend
npm test
npm run typecheck
npm run build
npm run dev
```

Open `http://127.0.0.1:5173/race`, then explicitly choose Fictional demo to inspect the illustration. Routine tests do not need PostgreSQL, network access or a model. Vitest covers position/ties, intensity, trend, disclosure, all filters, retained peer ranks, live gating/provenance, median evidence, selection, detail/source fields, keyboard/table/list, mobile heats, pause/reduced motion and year/position transitions.

Race implementation verification: **59 tests passed across seven files**, TypeScript and production build passed. Browser visual verification and requested desktop/mobile screenshots remain **pending: the Mac was locked and browser automation could not unlock it**. No screenshot has been fabricated or represented as captured, and no alternative browser path was used to bypass that lock. Earlier screenshots elsewhere in the repository predate this Race and do not verify it.

This update is local only. The existing React/Vite + FastAPI/PostgreSQL architecture is preserved; no Sites/Cloudflare deployment or modification to the hosted product has been made.
