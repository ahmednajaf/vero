# Globe and chart component provenance

Selected using the signed-in 21st.dev account on 2026-09-29. No credits, purchases, API keys or paid generator were used. Source code was read from the component pages; example chart datasets were not included. This is a local frontend change, not a hosted deployment or a collection run.

| Component | Source | Adaptation |
| --- | --- | --- |
| COBE Globe, Shu Ding | [21st.dev](https://21st.dev/@shuding/components/cobe-globe), [upstream](https://github.com/shuding/cobe) | Real WebGL globe; dynamic local dependency; responsive sizing; pause/reduced motion; off-screen suspension; fallback; market pins and pointer hit-testing. No Three.js, external imagery or remote geocoding. |
| Hatched Multiple Bar Chart, Evil Charts | [21st.dev](https://21st.dev/@LegionWebDev/components/bar-chart/hatched-multiple-bar-chart), [upstream](https://github.com/legions-developer/evilcharts) | Reusable patterned bar shapes, unique SVG IDs, restrained teal/navy series. Pattern denotes the second series, not uncertainty or ESG quality. No example numbers or decorative percentage claims. |
| Chart primitives, shadcn | [21st.dev](https://21st.dev/@shadcn/components/chart), [upstream](https://ui.shadcn.com/docs/components/chart) | Config/context/container, tooltip and legend, adapted to Recharts 3 and this CSS system. Real zero remains visible; missing values are omitted; exact data and sources remain in the adjacent table. |

All three are MIT licensed. Full retained notices: `frontend/public/third-party-notices.txt`, copied into every production build by Vite.

## Map source and claim boundaries

Country anchors are Natural Earth's `LABEL_Y`/`LABEL_X` from [110m country data](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson), retrieved 2026-09-29. Natural Earth data is [public domain](https://www.naturalearthdata.com/about/terms-of-use/). The current static subset covers US, GB, DE, FR, NL, CH, JP, CA, AU, NO, SE, DK, FI, IE and SA. These are cartographic label positions, not capital-city coordinates, headquarters or facility locations. Other countries remain in the market selector and counts but are explicitly unplotted until an anchor is sourced.

Each equal-sized pin represents a country with at least one company in the selected lens. It does not encode emissions volume, intensity, company count, territorial coverage or national sustainability performance. Selected pins are larger and amber solely for interaction feedback. Nearby European pins can overlap; the keyboard-accessible selector exposes every market.

- **Companies:** active companies from the loaded company universe.
- **Reviewed evidence:** companies with at least one eligible metric and an official, current, attributed source observation. Not a count of fully validated reports or complete disclosures.
- **Net-zero targets:** companies with one unambiguous validated net-zero target year. Conflicts and stale/unvalidated evidence are excluded. No target-year ambition ranking or achieved progress is inferred.

All lenses are dataset coverage, not global population estimates. Clicking a pin selects its market; the market action opens the country-filtered company table, retaining reporting year. Source inspection continues through each company's existing evidence drawer. The imported universe is current; only metric and target evidence is reporting-cycle-specific. This is not a historical company-membership database.

The atmosphere halo is illustrative. It is not an ozone, temperature or emissions layer. [NASA distinguishes ozone depletion from greenhouse warming](https://science.nasa.gov/climate-change/faq/is-the-ozone-hole-causing-climate-change/). Adding a scientific layer would require its own dataset, physical quantity, timestamp, units, attribution and legend, kept separate from corporate disclosures.

## Product direction: an annual research briefing

The adoption path is **choose year → find company → compare peers → inspect source**, with the globe as an optional entry point. The familiar table remains available immediately; there is no new interaction system to learn. Existing annual reports are the inputs. No corporate system integration, authentication or bespoke data-upload workflow was introduced.

Future annual refreshes should produce a versioned reporting-cycle snapshot and a concise change brief: newly available evidence, revisions/restatements, changes within consistent boundaries and peer context. Scheduling, notifications and an automatic yearly refresh are not implemented by this frontend work.

Do not add a “progress towards net zero” percentage until target scope/boundary, base year, current year, comparable achieved emissions, methodology and treatment of offsets are all explicit. A future progress layer must show source-backed achieved reductions separately from promises and abstain where those inputs are incomplete. The current UI deliberately says **targets**, not progress.

## Local visual QA

With Vite running, `/visual-qa.html` is an explicitly watermarked, dev-only visual harness using the existing fictional test fixtures. It never contacts the API or changes saved data. Navigation works within the test session; refreshing returns to the real entry point. The production build includes only `index.html`, not this test entry or its data. Use `/` to inspect actual backend availability.
