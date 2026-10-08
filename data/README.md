# Development company universe

## Source-backed 500-company registry (6 October 2026)

`company_universe_500.json` was imported into the existing PostgreSQL database: 210 existing identities preserved, 290 added from a revision-backed S&P 500 snapshot and company-page website metadata. It contains 500 unique companies, listings and domains across 18 countries and six coarse research sectors. It adds no financial or sustainability values. Per-company provenance, excluded identities, source revisions and country/sector mapping caveats are included in the JSON.

This is an international pilot expanded with S&P 500 members, not the world's 500 largest companies and not an equally balanced sector/country sample. New country labels use the index's headquarters location; they are not verified legal domicile. Country-level comparisons need a consistent definition before publication. Existing pharma import records lack historic import hashes; their named `pharma_sources.json` manifest is retained rather than inventing those hashes.

The repeatable builder is `scripts/build-company-universe.py`; it caches public metadata and refuses to overwrite an existing universe snapshot. Collection progress and report availability are separate from membership. See `docs/BULK_COLLECTION.md`.

## Curated 200-company pilot

`company_universe_200.csv` is a separate, import-compatible pilot of 200 listed companies, with 40 in each product sector across 13 countries. The full roster, classification decisions, limitations and approval gate are in `docs/pilot-universe-200.md`.

Company-level official source references are in `company_universe_200.sources.json`; structural counts, CSV checksum and dated DNS results are in `company_universe_200.validation.json`. A resolving domain is not a claim that a requested-year report is accessible. Unknown optional URLs and financial fields remain blank. Overlapping company UUIDs are preserved from the original seed.

No pipeline was started when this file was originally created. Its identities have since been imported and preserved in the 500-company registry. Document collection now runs with the user's explicit bulk-collection request. The separate metric-extraction pipeline still retains its original data-complete checkpoints. Offline validation tests are in `backend/tests/test_company_universe_200.py`.

## Original development seed

`company_universe.csv` contains 20 example public companies: four in each of the five product sectors, spanning eight countries. It is a development starting universe, not investment advice, a complete index membership list or a sustainability dataset.

Metadata reference date: 2026-09-29. `reporting_year=2025` selects the development research cycle; it does not assert that a report or metric has been collected. `active=true` means included in this development universe, not a verified trading-status flag.

The seed uses stable, explicitly assigned UUIDs. Do not regenerate them when names, tickers or URLs change. Companies use one representative listing each. `country` uses ISO alpha-2 domicile codes and `exchange` uses exchange MIC codes. Sector, industry and region are this product's manually assigned development classifications, not licensed GICS or index classifications. Company names are display names, not certified legal-entity identifiers.

Financial fields, index membership and sustainability-report URLs are blank where not collected. Blank values import as SQL NULL, never zero. In particular, this file includes **no sustainability metrics, revenue estimates or market-cap estimates**. Optional financial amounts, when supplied by an operator, are nominal whole currency units (not thousands or millions), with up to six decimal places. Revenue requires an explicit currency and revenue year. A single company market-cap field is administrative metadata, not a historical market-data series and must not be used for time-series comparisons.

Leading zeros in tickers such as `005930` matter. Treat ticker and UUID columns as text when editing in a spreadsheet application. Import the CSV as UTF-8; do not add titles or commentary above the header row. The row validator is defined in `backend/app/schemas/company.py`.

## Official metadata references

The investor-relations URL in each CSV row is also its official reference entry point. These pages were checked manually while preparing the seed; there is no scraper or URL fetching in the importer. References substantiate representative listings and corporate identity, not unpopulated financial data.

| Company | Official reference |
| --- | --- |
| JPMorgan Chase | [Investor relations](https://www.jpmorganchase.com/ir) |
| Bank of America | [Investor relations](https://investor.bankofamerica.com/) |
| HSBC | [Investor FAQs](https://www.hsbc.com/investors/shareholder-and-dividend-information/investor-faqs) |
| Santander | [General shareholder information](https://www.santander.com/en/shareholders-and-investors/general-information) |
| Apple | [Investor FAQ](https://investor.apple.com/faq/) |
| Microsoft | [SEC filings](https://www.microsoft.com/en-us/investor/sec-filings) |
| SAP | [Investor FAQ](https://www.sap.com/investors/en/resources/faq.html) |
| Samsung Electronics | [Listing information](https://www.samsung.com/global/ir/stock-information/listing-Info/) |
| ExxonMobil | [Investor relations](https://investor.exxonmobil.com/) |
| Chevron | [Stock and dividend information](https://www.chevron.com/investors/stock-and-dividend) |
| Shell | [Share prices and listings](https://www.shell.com/investors/information-for-shareholders/share-prices.html) |
| Saudi Aramco | [Investor FAQ](https://www.aramco.com/en/investors/investor-faq) |
| Walmart | [Investor relations](https://stock.walmart.com/) |
| Costco | [Stock information](https://investor.costco.com/stock-info/default.aspx) |
| Unilever | [Investor centre](https://www.unilever.com/investors/investor-centre/) |
| Nestlé | [Investor FAQ](https://www.nestle.com/investors/faqs) |
| Siemens | [Share information](https://www.siemens.com/de-de/company/investor-relations/share-bonds-rating/basic-data-key-share-figures/) |
| Schneider Electric | [Share information](https://www.se.com/ww/en/about-us/investor-relations/share-information/share-price/) |
| Caterpillar | [Stock trade history](https://investors.caterpillar.com/stock-info/stock-trade-history/default.aspx) |
| ABB | [Share listing data](https://global.abb/group/en/investors/investor-and-shareholder-resources/share-listing) |

Walmart's seed listing uses XNAS (Nasdaq), reflecting its listing transfer rather than retaining a stale NYSE value. The official reference is [Walmart's transfer announcement](https://stock.walmart.com/sec-filings/all-sec-filings/content/0000104169-25-000177/0000104169-25-000177.pdf). Seed classifications and URLs must be reviewed before treating this universe as production research input.
