# Curated 200-company pilot universe

Metadata reference date: 29 September 2026. Prepared for review; **not imported and no pipeline run started**.

The import-ready CSV is `data/company_universe_200.csv`. Its 18-column schema matches the existing importer. The original 20-company development seed is unchanged. All 17 overlapping company IDs are preserved; new IDs are assigned once and must be retained when metadata changes.

## Composition

| Sector | Companies |
| --- | ---: |
| Technology | 40 |
| Financial Services | 40 |
| Energy | 40 |
| Consumer / Retail | 40 |
| Industrials | 40 |

| Country (ISO) | Companies |
| --- | ---: |
| United States (US) | 80 |
| Canada (CA) | 19 |
| Japan (JP) | 18 |
| France (FR) | 17 |
| United Kingdom (GB) | 14 |
| Germany (DE) | 13 |
| Australia (AU) | 8 |
| Switzerland (CH) | 8 |
| Netherlands (NL) | 7 |
| Sweden (SE) | 7 |
| Finland (FI) | 4 |
| Norway (NO) | 3 |
| Denmark (DK) | 2 |

## Validation and limitations

- 200 unique companies, UUIDs, exchange/ticker pairs and official domains. All five sectors contain 40 companies. All 13 country codes are valid ISO alpha-2 codes.
- 200/200 domains resolved in the DNS check; 0 failed. The dated per-domain results and CSV SHA-256 are in `data/company_universe_200.validation.json`.
- 196 investor-relations URLs and 70 reporting entry points were confirmed in official references. Remaining optional URLs are blank. Reporting entry points may be archives, HTML hubs, integrated reports or PDFs; none is marked as a selected, downloaded or validated report.
- Investor-relations URLs left blank: Adobe Inc.; Barclays PLC; BP p.l.c.; Heineken N.V.. Barclays' known investor page returned HTTP 403; no controls were bypassed.
- Country means legal domicile. Airbus is therefore Netherlands with a Paris listing; Prudential is UK despite its international business footprint. Exchanges use MICs; tickers use exchange symbols, not vendor suffixes. Only one security per company is included.
- Official domains are hostnames, not necessarily registrable roots. Eight companies use their confirmed `www` hostname because the bare hostname did not resolve. One initial EOG lookup timed out and resolved on recheck. Company IDs were retained when canonical hostnames were corrected.
- Sector and industry are transparent pilot classifications, not licensed GICS. Amazon is Consumer / Retail despite AWS; power-equipment manufacturers such as Vestas and GE Vernova are Industrials, while fuel producers, refiners, pipelines and energy services are Energy. This is a curated large-company sample, not the largest 40 by current market capitalisation.
- These broad sectors are not sufficient peer groups for ranking. Compare industry, business model, boundary, fiscal period and denominator before benchmarking. Energy is intentionally oil/gas-heavy; banks, insurers and payment networks need separate peer cohorts.
- Imperial Oil is a separately listed company majority-owned by ExxonMobil. Do not sum its observations with consolidated ExxonMobil observations. Crédit Agricole S.A. is the listed entity, not automatically the wider Crédit Agricole Group. Corporate actions and reporting-boundary changes require review.
- `reporting_year=2025` retains the existing requested research cycle; it is not a claim about fiscal years or report availability. `active=true` means selected for this pilot, not a live trading-status assertion. Revenue, revenue year, reporting currency, market cap and index membership are blank. There are no sustainability metrics.
- Company-level source references are in `data/company_universe_200.sources.json`. DNS resolution and search-indexed official pages are not evidence of permission to crawl or successful report retrieval. This curation is not a 200-site pipeline test.

## Full roster

Every row below is included in the CSV. “Reporting” links are starting points, not approved primary reports. A dash means the optional URL was not confirmed.

### Technology — 40

| Company | Ticker / MIC | Country | Industry | Official domain | References |
| --- | --- | --- | --- | --- | --- |
| Adobe Inc. | ADBE / XNAS | US | Software | adobe.com | [Metadata](https://www.adobe.com/cc-shared/assets/investor-relations/pdfs/01906202/au56y4ter.pdf) · [Reporting](https://www.adobe.com/corporate-responsibility/corporate-responsibility-reports.html) |
| Advanced Micro Devices Inc. | AMD / XNAS | US | Semiconductors | amd.com | [IR](https://ir.amd.com/contacts-faq/faq) · Reporting — |
| Analog Devices Inc. | ADI / XNAS | US | Semiconductors | analog.com | [IR](https://investor.analog.com/) · Reporting — |
| Apple Inc. | AAPL / XNAS | US | Technology Hardware | apple.com | [IR](https://investor.apple.com/faq/) · [Reporting](https://www.apple.com/environment/) |
| Applied Materials Inc. | AMAT / XNAS | US | Semiconductor Equipment | appliedmaterials.com | [IR](https://ir.appliedmaterials.com/shareholder-services/investor-faqs) · Reporting — |
| ASM International N.V. | ASM / XAMS | NL | Semiconductor Equipment | asm.com | [IR](https://www.asm.com/investors) · Reporting — |
| ASML Holding N.V. | ASML / XAMS | NL | Semiconductor Equipment | asml.com | [IR](https://www.asml.com/en/investors) · [Reporting](https://www.asml.com/en/investors/annual-report/2025/sustainability) |
| Autodesk Inc. | ADSK / XNAS | US | Software | autodesk.com | [IR](https://investors.autodesk.com/) · Reporting — |
| Broadcom Inc. | AVGO / XNAS | US | Semiconductors and Infrastructure Software | broadcom.com | [IR](https://investors.broadcom.com/) · Reporting — |
| Capgemini SE | CAP / XPAR | FR | IT Services | capgemini.com | [IR](https://investors.capgemini.com/en/capital-structure/) · [Reporting](https://investors.capgemini.com/en/esg-reporting/) |
| CGI Inc. | GIB.A / XTSE | CA | IT Services | cgi.com | [IR](https://www.cgi.com/en/investors/investor-stock-information) · Reporting — |
| Cisco Systems Inc. | CSCO / XNAS | US | Networking Equipment | cisco.com | [IR](https://investor.cisco.com/overview/default.aspx) · [Reporting](https://www.cisco.com/c/m/en_us/about/purpose/reporting-hub/governance/frameworks/gri.html) |
| Constellation Software Inc. | CSU / XTSE | CA | Software | csisoftware.com | [IR](https://www.csisoftware.com/investor-relations/) · Reporting — |
| Dassault Systèmes SE | DSY / XPAR | FR | Software | 3ds.com | [IR](https://investor.3ds.com/) · Reporting — |
| Dell Technologies Inc. | DELL / XNYS | US | Technology Hardware | dell.com | [IR](https://investors.delltechnologies.com/) · Reporting — |
| Fujitsu Limited | 6702 / XTKS | JP | IT Services | global.fujitsu | [IR](https://global.fujitsu/en-global/ir) · [Reporting](https://global.fujitsu/en-global/sustainability) |
| Hewlett Packard Enterprise Company | HPE / XNYS | US | Enterprise Technology Hardware | hpe.com | [IR](https://investors.hpe.com/) · Reporting — |
| HP Inc. | HPQ / XNYS | US | Technology Hardware | hp.com | [IR](https://investor.hp.com/) · Reporting — |
| Infineon Technologies AG | IFX / XETR | DE | Semiconductors | infineon.com | [IR](https://www.infineon.com/about/investor) · [Reporting](https://www.infineon.com/about/company/sustainability/csr-reporting) |
| Intel Corporation | INTC / XNAS | US | Semiconductors | intel.com | [IR](https://www.intc.com/) · [Reporting](https://www.intel.com/content/www/us/en/corporate-responsibility/resource-center.html) |
| International Business Machines Corporation | IBM / XNYS | US | IT Services and Software | ibm.com | [IR](https://www.ibm.com/investor/help/general-faqs) · Reporting — |
| Intuit Inc. | INTU / XNAS | US | Software | intuit.com | [IR](https://investors.intuit.com/company-information/faq) · Reporting — |
| KLA Corporation | KLAC / XNAS | US | Semiconductor Equipment | kla.com | [IR](https://ir.kla.com/) · Reporting — |
| Lam Research Corporation | LRCX / XNAS | US | Semiconductor Equipment | lamresearch.com | [IR](https://investor.lamresearch.com/) · Reporting — |
| Logitech International S.A. | LOGN / XSWX | CH | Computer Peripherals | logitech.com | [IR](https://ir.logitech.com/) · Reporting — |
| Micron Technology Inc. | MU / XNAS | US | Semiconductors | micron.com | [IR](https://investors.micron.com/overview/default.aspx) · Reporting — |
| Microsoft Corporation | MSFT / XNAS | US | Software | microsoft.com | [IR](https://www.microsoft.com/en-us/investor/faq) · [Reporting](https://www.microsoft.com/en-us/corporate-responsibility/sustainability/report) |
| NEC Corporation | 6701 / XTKS | JP | IT Services and Networking Equipment | nec.com | [IR](https://www.nec.com/en/global/ir/map/index.html) · Reporting — |
| Nokia Oyj | NOKIA / XHEL | FI | Telecommunications Equipment | nokia.com | [IR](https://www.nokia.com/about-us/investors/) · Reporting — |
| NVIDIA Corporation | NVDA / XNAS | US | Semiconductors | nvidia.com | [IR](https://investor.nvidia.com/investor-resources/faqs/default.aspx) · [Reporting](https://www.nvidia.com/en-us/foundation/archives/) |
| Oracle Corporation | ORCL / XNYS | US | Software | oracle.com | [IR](https://investor.oracle.com/faq/default.aspx) · [Reporting](https://www.oracle.com/social-impact/) |
| QUALCOMM Incorporated | QCOM / XNAS | US | Semiconductors | qualcomm.com | [IR](https://investor.qualcomm.com/overview/default.aspx) · Reporting — |
| Renesas Electronics Corporation | 6723 / XTKS | JP | Semiconductors | renesas.com | [IR](https://www.renesas.com/en/about/investor-relations) · Reporting — |
| Salesforce Inc. | CRM / XNYS | US | Software | salesforce.com | [IR](https://investor.salesforce.com/overview/default.aspx) · [Reporting](https://www.salesforce.com/en-us/wp-content/uploads/sites/4/documents/white-papers/salesforce-fy25-stakeholder-impact-report.pdf?bc=OTH) |
| SAP SE | SAP / XETR | DE | Software | sap.com | [IR](https://www.sap.com/investors/en/stock.html) · [Reporting](https://www.sap.com/integrated-reports/2025/en/csrd.html) |
| ServiceNow Inc. | NOW / XNYS | US | Software | servicenow.com | [IR](https://investor.servicenow.com/stock-info/default.aspx) · Reporting — |
| Telefonaktiebolaget LM Ericsson | ERIC B / XSTO | SE | Telecommunications Equipment | ericsson.com | [IR](https://www.ericsson.com/en/investors) · Reporting — |
| Texas Instruments Incorporated | TXN / XNAS | US | Semiconductors | ti.com | [IR](https://investor.ti.com/) · Reporting — |
| The Sage Group plc | SGE / XLON | GB | Software | sage.com | [IR](https://www.sage.com/investors/) · Reporting — |
| Tokyo Electron Limited | 8035 / XTKS | JP | Semiconductor Equipment | www.tel.com | [IR](https://www.tel.com/ir/) · Reporting — |

### Financial Services — 40

| Company | Ticker / MIC | Country | Industry | Official domain | References |
| --- | --- | --- | --- | --- | --- |
| Allianz SE | ALV / XETR | DE | Insurance | allianz.com | [IR](https://www.allianz.com/en/investor_relations/shareholders/app.html) · [Reporting](https://www.allianz.com/en/investor_relations/results-reports/sustainability.html) |
| American Express Company | AXP / XNYS | US | Consumer Finance and Payments | americanexpress.com | [IR](https://ir.americanexpress.com/investor-relations/default.aspx) · [Reporting](https://www.americanexpress.com/en-us/company/corporate-sustainability/) |
| ANZ Group Holdings Limited | ANZ / XASX | AU | Diversified Banks | anz.com | [IR](https://www.anz.com/shareholder/centre/contact/) · Reporting — |
| AXA SA | CS / XPAR | FR | Insurance | axa.com | [IR](https://www.axa.com/investor) · Reporting — |
| Bank of America Corporation | BAC / XNYS | US | Diversified Banks | bankofamerica.com | [IR](https://investor.bankofamerica.com/) · [Reporting](https://about.bankofamerica.com/en/making-an-impact/report-center) |
| Bank of Montreal | BMO / XTSE | CA | Diversified Banks | bmo.com | [IR](https://www.bmo.com/en-ca/main/about-bmo/banking/investor-relations/home/) · Reporting — |
| Barclays PLC | BARC / XLON | GB | Diversified Banks | home.barclays | [Metadata](https://www.sec.gov/Archives/edgar/data/312069/000031206926000100/bplcq126resultsannouncement.htm) · Reporting — |
| BlackRock Inc. | BLK / XNYS | US | Asset Management | blackrock.com | [IR](https://ir.blackrock.com/) · [Reporting](https://www.blackrock.com/corporate/literature/continuous-disclosure-and-important-information/climate-report-blkinc.pdf?trk=public_post_comment-text) |
| BNP Paribas SA | BNP / XPAR | FR | Diversified Banks | group.bnpparibas | [IR](https://invest.bnpparibas/en/) · Reporting — |
| Citigroup Inc. | C / XNYS | US | Diversified Banks | citigroup.com | [IR](https://www.citigroup.com/global/investors) · [Reporting](https://www.citigroup.com/global/our-impact/environmental-sustainability/sustainability-resources) |
| Commonwealth Bank of Australia | CBA / XASX | AU | Diversified Banks | commbank.com.au | [IR](https://www.commbank.com.au/about-us/investors.html) · [Reporting](https://www.commbank.com.au/about-us/opportunity-initiatives/performance-reporting/archive.html) |
| Crédit Agricole S.A. | ACA / XPAR | FR | Diversified Banks | credit-agricole.com | [IR](https://www.credit-agricole.com/finance/shares-and-dividend) · Reporting — |
| Deutsche Bank AG | DBK / XETR | DE | Diversified Banks | db.com | [IR](https://investor-relations.db.com/faq/) · Reporting — |
| HSBC Holdings plc | HSBA / XLON | GB | Diversified Banks | hsbc.com | [IR](https://www.hsbc.com/investors) · [Reporting](https://www.hsbc.com/who-we-are/esg-and-responsible-business/esg-reporting-centre?page=1&programme-type=schools-and-apprentices&take=20) |
| ING Groep N.V. | INGA / XAMS | NL | Diversified Banks | ing.com | [IR](https://ing.com/investors/share-information/shares) · Reporting — |
| JPMorgan Chase & Co. | JPM / XNYS | US | Diversified Banks | jpmorganchase.com | [IR](https://www.jpmorganchase.com/ir) · [Reporting](https://www.jpmorganchase.com/about/governance/sustainability) |
| Lloyds Banking Group plc | LLOY / XLON | GB | Diversified Banks | lloydsbankinggroup.com | [IR](https://www.lloydsbankinggroup.com/investors.html) · Reporting — |
| Manulife Financial Corporation | MFC / XTSE | CA | Life Insurance and Asset Management | manulife.com | [IR](https://www.manulife.com/ca/en/about-us/investors) · Reporting — |
| Mastercard Incorporated | MA / XNYS | US | Payment Networks | mastercard.com | [IR](https://investor.mastercard.com/overview/default.aspx) · [Reporting](https://investor.mastercard.com/Sustainability/) |
| Mitsubishi UFJ Financial Group Inc. | 8306 / XTKS | JP | Diversified Banks | www.mufg.jp | [IR](https://www.mufg.jp/english/ir/) · Reporting — |
| Mizuho Financial Group Inc. | 8411 / XTKS | JP | Diversified Banks | mizuhogroup.com | [IR](https://www.mizuhogroup.com/investors) · Reporting — |
| Morgan Stanley | MS / XNYS | US | Investment Banking and Wealth Management | morganstanley.com | [IR](https://www.morganstanley.com/about-us-ir/faq) · [Reporting](https://www.morganstanley.com/about-us/sustainability-reports-archive) |
| Münchener Rückversicherungs-Gesellschaft AG | MUV2 / XETR | DE | Reinsurance | munichre.com | [IR](https://www.munichre.com/en/company/investors/reports-and-presentations/results-reports.html) · Reporting — |
| National Australia Bank Limited | NAB / XASX | AU | Diversified Banks | nab.com.au | [IR](https://www.nab.com.au/about-us/shareholder-centre) · Reporting — |
| NatWest Group plc | NWG / XLON | GB | Diversified Banks | natwestgroup.com | [IR](https://investors.natwestgroup.com/) · Reporting — |
| NN Group N.V. | NN / XAMS | NL | Insurance | nn-group.com | [IR](https://www.nn-group.com/investors) · Reporting — |
| Prudential plc | PRU / XLON | GB | Life Insurance | prudentialplc.com | [IR](https://www.prudentialplc.com/en/investors/overview/) · Reporting — |
| Royal Bank of Canada | RY / XTSE | CA | Diversified Banks | rbc.com | [IR](https://www.rbc.com/investor-relations/) · [Reporting](https://www.rbc.com/our-impact/_assets-custom/pdf/RBC-2025-sustainability-report.pdf) |
| Société Générale SA | GLE / XPAR | FR | Diversified Banks | societegenerale.com | [IR](https://investors.societegenerale.com/en/financial-non-financial-information/share-performance/share-capital) · Reporting — |
| Sumitomo Mitsui Financial Group Inc. | 8316 / XTKS | JP | Diversified Banks | www.smfg.co.jp | [IR](https://www.smfg.co.jp/investor/) · Reporting — |
| Swiss Re AG | SREN / XSWX | CH | Reinsurance | swissre.com | [IR](https://www.swissre.com/investors.html) · Reporting — |
| The Bank of Nova Scotia | BNS / XTSE | CA | Diversified Banks | scotiabank.com | [IR](https://www.scotiabank.com/ca/en/about/investors-shareholders/frequently-asked-questions.html) · Reporting — |
| The Goldman Sachs Group Inc. | GS / XNYS | US | Investment Banking | goldmansachs.com | [IR](https://www.goldmansachs.com/investor-relations) · [Reporting](https://www.goldmansachs.com/investor-relations/corporate-governance/sustainability-reporting) |
| The Toronto-Dominion Bank | TD / XTSE | CA | Diversified Banks | td.com | [IR](https://www.td.com/us/en/about-us/investor-relations) · Reporting — |
| Tokio Marine Holdings Inc. | 8766 / XTKS | JP | Insurance | www.tokiomarinehd.com | [IR](https://www.tokiomarinehd.com/en/ir/) · Reporting — |
| UBS Group AG | UBSG / XSWX | CH | Banking and Wealth Management | ubs.com | [IR](https://www.ubs.com/global/en/investor-relations.html) · [Reporting](https://www.ubs.com/global/en/sustainability-impact/sustainability-reporting.html) |
| Visa Inc. | V / XNYS | US | Payment Networks | visa.com | [IR](https://investor.visa.com/) · [Reporting](https://corporate.visa.com/en/about-visa/crs.html) |
| Wells Fargo & Company | WFC / XNYS | US | Diversified Banks | wellsfargo.com | [IR](https://www.wellsfargo.com/about/investor-relations/shareholder-information/) · [Reporting](https://www.wellsfargo.com/about/responsibility-and-impact/reporting-and-resources/) |
| Westpac Banking Corporation | WBC / XASX | AU | Diversified Banks | westpac.com.au | [IR](https://www.westpac.com.au/about-westpac/investor-centre/contact-investor-relations/) · Reporting — |
| Zurich Insurance Group AG | ZURN / XSWX | CH | Insurance | zurich.com | [IR](https://www.zurich.com/investor-relations) · Reporting — |

### Energy — 40

| Company | Ticker / MIC | Country | Industry | Official domain | References |
| --- | --- | --- | --- | --- | --- |
| Aker BP ASA | AKRBP / XOSL | NO | Oil and Gas Exploration and Production | akerbp.com | [IR](https://akerbp.com/en/investor/) · Reporting — |
| ARC Resources Ltd. | ARX / XTSE | CA | Oil and Gas Exploration and Production | arcresources.com | [IR](https://www.arcresources.com/investors/) · Reporting — |
| Baker Hughes Company | BKR / XNAS | US | Energy Equipment and Services | bakerhughes.com | [IR](https://investors.bakerhughes.com/) · Reporting — |
| BP p.l.c. | BP. / XLON | GB | Integrated Oil and Gas | bp.com | [Metadata](https://www.bp.com/content/dam/bp/business-sites/en/global/corporate/pdfs/investors/bp-memorandum-and-articles-of-association-2018.pdf) · Reporting — |
| Canadian Natural Resources Limited | CNQ / XTSE | CA | Oil and Gas Exploration and Production | cnrl.com | [IR](https://www.cnrl.com/investors/) · Reporting — |
| Cenovus Energy Inc. | CVE / XTSE | CA | Integrated Oil and Gas | cenovus.com | [IR](https://www.cenovus.com/Investors) · Reporting — |
| Cheniere Energy Inc. | LNG / XNYS | US | Liquefied Natural Gas | cheniere.com | [IR](https://www.cheniere.com/investors) · Reporting — |
| Chevron Corporation | CVX / XNYS | US | Integrated Oil and Gas | chevron.com | [IR](https://www.chevron.com/investors) · [Reporting](https://www.chevron.com/investors/reports-and-filings) |
| ConocoPhillips | COP / XNYS | US | Oil and Gas Exploration and Production | conocophillips.com | [IR](https://www.conocophillips.com/investor-relations/) · [Reporting](https://www.conocophillips.com/company-reports-resources/) |
| Devon Energy Corporation | DVN / XNYS | US | Oil and Gas Exploration and Production | devonenergy.com | [IR](https://investors.devonenergy.com/investors/) · [Reporting](https://www.devonenergy.com/about-our-report) |
| Diamondback Energy Inc. | FANG / XNAS | US | Oil and Gas Exploration and Production | www.diamondbackenergy.com | [IR](https://www.diamondbackenergy.com/investors) · Reporting — |
| Enbridge Inc. | ENB / XTSE | CA | Energy Pipelines and Storage | enbridge.com | [IR](https://www.enbridge.com/reports/annual-letter-to-shareholders-2026/investor-information) · Reporting — |
| ENEOS Holdings Inc. | 5020 / XTKS | JP | Integrated Oil and Gas | hd.eneos.co.jp | [IR](https://www.hd.eneos.co.jp/english/ir/) · Reporting — |
| EOG Resources Inc. | EOG / XNYS | US | Oil and Gas Exploration and Production | eogresources.com | [IR](https://investors.eogresources.com/) · [Reporting](https://www.eogresources.com/sustainability/) |
| EQT Corporation | EQT / XNYS | US | Natural Gas Exploration and Production | eqt.com | [IR](https://ir.eqt.com/investor-relations/stock-information/transfer-agent-info/default.aspx) · Reporting — |
| Equinor ASA | EQNR / XOSL | NO | Integrated Energy | equinor.com | [IR](https://www.equinor.com/investors) · [Reporting](https://www.equinor.com/sustainability/sustainability-reports-archive) |
| ExxonMobil | XOM / XNYS | US | Integrated Oil and Gas | exxonmobil.com | [IR](https://investor.exxonmobil.com/) · [Reporting](https://corporate.exxonmobil.com/publications/about-our-sustainability-and-reports-and-legal-information) |
| Halliburton Company | HAL / XNYS | US | Oilfield Services | halliburton.com | [IR](https://ir.halliburton.com/) · Reporting — |
| Harbour Energy plc | HBR / XLON | GB | Oil and Gas Exploration and Production | harbourenergy.com | [IR](https://www.harbourenergy.com/investors/) · Reporting — |
| Idemitsu Kosan Co. Ltd. | 5019 / XTKS | JP | Oil Refining and Marketing | idemitsu.com | [IR](https://www.idemitsu.com/en/ir/stock/data/index.html) · Reporting — |
| Imperial Oil Limited | IMO / XTSE | CA | Integrated Oil and Gas | imperialoil.ca | [IR](https://www.imperialoil.ca/investors/investor-relations) · Reporting — |
| INPEX Corporation | 1605 / XTKS | JP | Oil and Gas Exploration and Production | inpex.com | [IR](https://www.inpex.com/english/ir/) · [Reporting](https://www.inpex.com/english/sustainability/data/downloads/) |
| Kinder Morgan Inc. | KMI / XNYS | US | Energy Pipelines and Storage | kindermorgan.com | [IR](https://ir.kindermorgan.com/home/) · Reporting — |
| Marathon Petroleum Corporation | MPC / XNYS | US | Oil Refining and Marketing | marathonpetroleum.com | [IR](https://www.marathonpetroleum.com/Investors/) · Reporting — |
| Neste Oyj | NESTE / XHEL | FI | Renewable Fuels and Oil Refining | neste.com | [IR](https://www.neste.com/investors) · Reporting — |
| Occidental Petroleum Corporation | OXY / XNYS | US | Oil and Gas Exploration and Production | oxy.com | [IR](https://www.oxy.com/investors/) · [Reporting](https://calciumchloride-prod.oxy.com/siteassets/documents/publications/2025-sustainability-report-web.pdf) |
| ONEOK Inc. | OKE / XNYS | US | Energy Pipelines and Storage | oneok.com | [IR](https://ir.oneok.com/) · Reporting — |
| Pembina Pipeline Corporation | PPL / XTSE | CA | Energy Pipelines and Storage | pembina.com | [IR](https://www.pembina.com/investors) · Reporting — |
| Phillips 66 | PSX / XNYS | US | Oil Refining and Marketing | phillips66.com | [IR](https://investor.phillips66.com/stock-information/2025/default.aspx) · [Reporting](https://www.phillips66.com/sustainability/) |
| Santos Limited | STO / XASX | AU | Oil and Gas Exploration and Production | santos.com | [IR](https://www.santos.com/investors/) · Reporting — |
| Shell plc | SHEL / XLON | GB | Integrated Oil and Gas | shell.com | [IR](https://www.shell.com/investors) · [Reporting](https://www.shell.com/what-we-do/our-strategy/sustainability/reporting-centre.html) |
| Suncor Energy Inc. | SU / XTSE | CA | Integrated Oil and Gas | suncor.com | [IR](https://www.suncor.com/en-ca/investors) · Reporting — |
| TC Energy Corporation | TRP / XTSE | CA | Energy Pipelines and Storage | tcenergy.com | [IR](https://www.tcenergy.com/investors/stock-information/) · Reporting — |
| The Williams Companies Inc. | WMB / XNYS | US | Energy Pipelines and Storage | williams.com | [IR](https://investor.williams.com/) · Reporting — |
| TotalEnergies SE | TTE / XPAR | FR | Integrated Energy | totalenergies.com | [IR](https://totalenergies.com/investors) · [Reporting](https://totalenergies.com/sustainability/our-approach/esg-documentation) |
| Tourmaline Oil Corp. | TOU / XTSE | CA | Natural Gas Exploration and Production | tourmalineoil.com | [IR](https://www.tourmalineoil.com/investors) · Reporting — |
| Valero Energy Corporation | VLO / XNYS | US | Oil Refining and Renewable Fuels | valero.com | [IR](https://investorvalero.com/) · [Reporting](https://www.valero.com/responsibility/guiding-principles) |
| Vår Energi ASA | VAR / XOSL | NO | Oil and Gas Exploration and Production | varenergi.no | [IR](https://varenergi.no/en/investor/) · Reporting — |
| Whitecap Resources Inc. | WCP / XTSE | CA | Oil and Gas Exploration and Production | wcap.ca | [IR](https://www.wcap.ca/investors) · Reporting — |
| Woodside Energy Group Ltd | WDS / XASX | AU | Oil and Gas Exploration and Production | woodside.com | [IR](https://www.woodside.com/investors) · [Reporting](https://www.woodside.com/investors/reports-investor-briefings/report/annual-report-2025) |

### Consumer / Retail — 40

| Company | Ticker / MIC | Country | Industry | Official domain | References |
| --- | --- | --- | --- | --- | --- |
| adidas AG | ADS / XETR | DE | Apparel and Footwear | adidas-group.com | [IR](https://www.adidas-group.com/en/investors) · Reporting — |
| Amazon.com Inc. | AMZN / XNAS | US | E-commerce and Diversified Retail | aboutamazon.com | [IR](https://ir.aboutamazon.com/contact-us-and-request-documents/) · [Reporting](https://sustainability.aboutamazon.com/reports) |
| Associated British Foods plc | ABF / XLON | GB | Food and Apparel Retail | abf.co.uk | [IR](https://www.abf.co.uk/investors) · Reporting — |
| Beiersdorf AG | BEI / XETR | DE | Personal Products | beiersdorf.com | [IR](https://www.beiersdorf.com/investor-relations/service/faq) · Reporting — |
| Carlsberg A/S | CARL B / XCSE | DK | Beverages | carlsberggroup.com | [IR](https://carlsberggroup.com/investor-relations/shares/) · Reporting — |
| Carrefour SA | CA / XPAR | FR | Food Retail | carrefour.com | [IR](https://www.carrefour.com/en/finance/shareholder-section) · Reporting — |
| Coles Group Limited | COL / XASX | AU | Food Retail | colesgroup.com.au | [IR](https://www.colesgroup.com.au/investors) · Reporting — |
| Colgate-Palmolive Company | CL / XNYS | US | Household and Personal Products | colgatepalmolive.com | [IR](https://investor.colgatepalmolive.com/shareholder-services/contact-us) · Reporting — |
| Costco Wholesale Corporation | COST / XNAS | US | Warehouse Retail | costco.com | [IR](https://investor.costco.com/overview/) · [Reporting](https://www.costco.com/f/-/sustainability-resources) |
| Danone SA | BN / XPAR | FR | Food and Beverages | danone.com | [IR](https://www.danone.com/investors.html) · Reporting — |
| Diageo plc | DGE / XLON | GB | Beverages | diageo.com | [IR](https://www.diageo.com/en/investors) · Reporting — |
| Fast Retailing Co. Ltd. | 9983 / XTKS | JP | Apparel Retail | www.fastretailing.com | [IR](https://www.fastretailing.com/eng/ir/index.html) · Reporting — |
| H & M Hennes & Mauritz AB | HM B / XSTO | SE | Apparel Retail | hmgroup.com | [IR](https://hmgroup.com/investors/) · Reporting — |
| Heineken N.V. | HEIA / XAMS | NL | Beverages | theheinekencompany.com | [Metadata](https://www.theheinekencompany.com/sites/heineken-corp/files/2026-02/2025_Heineken_NV_Annual_Report_Interactive_100226_FINAL.pdf) · [Reporting](https://www.theheinekencompany.com/sites/heineken-corp/files/2026-02/2025_Heineken_NV_Annual_Report_Interactive_100226_FINAL.pdf) |
| Henkel AG & Co. KGaA | HEN3 / XETR | DE | Household Products and Adhesive Technologies | henkel.com | [IR](https://www.henkel.com/investors-and-analysts) · Reporting — |
| Kao Corporation | 4452 / XTKS | JP | Household and Personal Products | kao.com | [IR](https://www.kao.com/global/en/investor-relations/) · [Reporting](https://www.kao.com/global/en/sustainability/pdf/sustainability-report/backnumber/) |
| Kering SA | KER / XPAR | FR | Luxury Goods | kering.com | [IR](https://www.kering.com/en/finance/shareholders-information/your-publications/) · Reporting — |
| Koninklijke Ahold Delhaize N.V. | AD / XAMS | NL | Food Retail | aholddelhaize.com | [IR](https://aholddelhaize.com/investors) · Reporting — |
| L'Oréal SA | OR / XPAR | FR | Personal Products | loreal.com | [IR](https://www.loreal-finance.com/eng/loreal-individual-shareholder-relations) · [Reporting](https://www.loreal.com/en/esg-performance/) |
| Loblaw Companies Limited | L / XTSE | CA | Food and Pharmacy Retail | loblaw.ca | [IR](https://www.loblaw.ca/en/investors-overview/) · Reporting — |
| Lowe's Companies Inc. | LOW / XNYS | US | Home Improvement Retail | lowes.com | [IR](https://corporate.lowes.com/investors) · [Reporting](https://corporate.lowes.com/our-responsibilities/corporate-responsibility-reports-policies) |
| LVMH Moët Hennessy Louis Vuitton SE | MC / XPAR | FR | Luxury Goods | lvmh.com | [IR](https://www.lvmh.com/en/investors) · Reporting — |
| McDonald's Corporation | MCD / XNYS | US | Restaurants | mcdonalds.com | [IR](https://corporate.mcdonalds.com/corpmcd/config/investors0.html) · Reporting — |
| Mondelez International Inc. | MDLZ / XNAS | US | Packaged Food | mondelezinternational.com | [IR](https://www.mondelezinternational.com/investors/) · [Reporting](https://www.mondelezinternational.com/snacking-made-right/our-positions/sustainability/) |
| Nestlé S.A. | NESN / XSWX | CH | Food and Beverages | nestle.com | [IR](https://www.nestle.com/investors) · [Reporting](https://www.nestle.com/sustainability/performance-reporting/downloads-archive) |
| NIKE Inc. | NKE / XNYS | US | Apparel and Footwear | nike.com | [IR](https://investors.nike.com/investors/stock-information/) · Reporting — |
| PepsiCo Inc. | PEP / XNAS | US | Food and Beverages | pepsico.com | [IR](https://www.pepsico.com/investors) · [Reporting](https://www.pepsico.com/en/sustainability/report-downloads) |
| PUMA SE | PUM / XETR | DE | Apparel and Footwear | about.puma.com | [IR](https://about.puma.com/en/investor-relations) · Reporting — |
| Reckitt Benckiser Group plc | RKT / XLON | GB | Household and Personal Products | reckitt.com | [IR](https://www.reckitt.com/investors/) · Reporting — |
| Seven & i Holdings Co. Ltd. | 3382 / XTKS | JP | Convenience Retail | www.7andi.com | [IR](https://www.7andi.com/en/ir/stocks/) · Reporting — |
| Starbucks Corporation | SBUX / XNAS | US | Restaurants | starbucks.com | [IR](https://investor.starbucks.com/ir-home/default.aspx) · Reporting — |
| Target Corporation | TGT / XNYS | US | General Merchandise Retail | target.com | [IR](https://corporate.target.com/investors) · [Reporting](https://corporate.target.com/getmedia/391e0902-54da-4a88-9325-4fa0098c2665/2025-Sustainability-and-Governance-Report.pdf) |
| Tesco PLC | TSCO / XLON | GB | Food Retail | tescoplc.com | [IR](https://www.tescoplc.com/investors/share-price-information/share-price) · Reporting — |
| The Coca-Cola Company | KO / XNYS | US | Beverages | coca-colacompany.com | [IR](https://investors.coca-colacompany.com/) · [Reporting](https://www.coca-colacompany.com/policies-and-practices/sustainability) |
| The Home Depot Inc. | HD / XNYS | US | Home Improvement Retail | homedepot.com | [IR](https://ir.homedepot.com/investor-resources/contact-investor-relations) · [Reporting](https://ir.homedepot.com/sustainability) |
| The Kraft Heinz Company | KHC / XNAS | US | Packaged Food | kraftheinzcompany.com | [IR](https://ir.kraftheinzcompany.com/) · Reporting — |
| The Procter & Gamble Company | PG / XNYS | US | Household and Personal Products | pg.com | [IR](https://www.pginvestor.com/financials/annual-reports/default.aspx) · [Reporting](https://us.pg.com/sustainability-reports/) |
| Unilever PLC | ULVR / XLON | GB | Household and Personal Products | unilever.com | [IR](https://www.unilever.com/investors/) · [Reporting](https://www.unilever.com/files/unilever-sustainability-statement.pdf) |
| Walmart Inc. | WMT / XNAS | US | General Merchandise Retail | walmart.com | [IR](https://stock.walmart.com/) · [Reporting](https://corporate.walmart.com/content/dam/corporate/documents/esgreport/2025/FY2025-Walmart-ESG-Report.pdf) |
| Woolworths Group Limited | WOW / XASX | AU | Food Retail | woolworthsgroup.com.au | [IR](https://www.woolworthsgroup.com.au/au/en/investors.html) · [Reporting](https://www.woolworthsgroup.com.au/content/dam/wwg/sustainability/reports/2025_WG_Sustainability_Report_Interactive_SPREADS.pdf) |

### Industrials — 40

| Company | Ticker / MIC | Country | Industry | Official domain | References |
| --- | --- | --- | --- | --- | --- |
| AB SKF | SKF B / XSTO | SE | Industrial Components | skf.com | [IR](https://www.skf.com/group/investors) · Reporting — |
| AB Volvo | VOLV B / XSTO | SE | Commercial Vehicles | volvogroup.com | [IR](https://www.volvogroup.com/en/investors/the-volvo-share.html) · Reporting — |
| ABB Ltd | ABBN / XSWX | CH | Electrical Equipment | global.abb | [IR](https://global.abb/group/en/investors/investor-and-shareholder-resources) · Reporting — |
| Airbus SE | AIR / XPAR | NL | Aerospace and Defense | airbus.com | [IR](https://www.airbus.com/en/investors) · Reporting — |
| ASSA ABLOY AB | ASSA B / XSTO | SE | Building Products | assaabloy.com | [IR](https://www.assaabloy.com/group/en/investors) · Reporting — |
| Atlas Copco AB | ATCO A / XSTO | SE | Industrial Machinery | atlascopcogroup.com | [IR](https://www.atlascopcogroup.com/en/investors) · Reporting — |
| Bouygues SA | EN / XPAR | FR | Construction and Diversified Services | bouygues.com | [IR](https://www.bouygues.com/en/becoming-a-shareholder/) · Reporting — |
| Canadian National Railway Company | CNR / XTSE | CA | Rail Transportation | cn.ca | [IR](https://www.cn.ca/investors) · Reporting — |
| Caterpillar Inc. | CAT / XNYS | US | Construction Machinery | caterpillar.com | [IR](https://investors.caterpillar.com/stock-info/) · [Reporting](https://www.caterpillar.com/en/company/sustainability/sustainability-report.html) |
| Daikin Industries Ltd. | 6367 / XTKS | JP | Heating Ventilation and Air Conditioning | www.daikin.com | [IR](https://www.daikin.com/investor) · Reporting — |
| Deere & Company | DE / XNYS | US | Agricultural Machinery | deere.com | [IR](https://investor.deere.com/Home/) · Reporting — |
| DHL Group | DHL / XETR | DE | Logistics | group.dhl.com | [IR](https://group.dhl.com/en/investors/preview/investors.html) · Reporting — |
| Emerson Electric Co. | EMR / XNYS | US | Industrial Automation | emerson.com | [IR](https://ir.emerson.com/) · Reporting — |
| FedEx Corporation | FDX / XNYS | US | Logistics | fedex.com | [IR](https://investor.fedex.com/) · Reporting — |
| GE Aerospace | GE / XNYS | US | Aerospace Engines | geaerospace.com | [IR](https://www.geaerospace.com/investor-relations/ir-updates) · [Reporting](https://www.geaerospace.com/sustainability/reporting) |
| GE Vernova Inc. | GEV / XNYS | US | Power Equipment | gevernova.com | [IR](https://www.gevernova.com/investors) · [Reporting](https://www.gevernova.com/sustainability/reports-data) |
| Geberit AG | GEBN / XSWX | CH | Building Products | geberit.com | [IR](https://www.geberit.com/investors/) · Reporting — |
| General Dynamics Corporation | GD / XNYS | US | Aerospace and Defense | gd.com | [IR](https://investorrelations.gd.com/investor-resources/contact-investor-relations/default.aspx) · [Reporting](https://www.gd.com/-/media/gd-corporate/pdf/gd-2025-sustainability-report.ashx) |
| Hitachi Ltd. | 6501 / XTKS | JP | Industrial Technology and Infrastructure | hitachi.com | [IR](https://www.hitachi.com/en/ir/investor/) · [Reporting](https://www.hitachi.com/en/sustainability/download/) |
| Illinois Tool Works Inc. | ITW / XNAS | US | Diversified Industrial Equipment | itw.com | [IR](https://investor.itw.com/) · [Reporting](https://www.itw.com/media/cwbkuwfa/itw_2025sustainabilityreport_final.pdf) |
| Komatsu Ltd. | 6301 / XTKS | JP | Construction Machinery | komatsu.jp | [IR](https://www.komatsu.jp/en/ir) · Reporting — |
| KONE Oyj | KNEBV / XHEL | FI | Elevators and Escalators | kone.com | [IR](https://www.kone.com/global/en/investors.html) · Reporting — |
| Legrand SA | LR / XPAR | FR | Electrical Equipment | legrandgroup.com | [IR](https://www.legrandgroup.com/en/investors-and-shareholders/share-price) · Reporting — |
| Lockheed Martin Corporation | LMT / XNYS | US | Aerospace and Defense | lockheedmartin.com | [IR](https://investors.lockheedmartin.com/) · [Reporting](https://sustainability.lockheedmartin.com/sustainability/disclosure-hub/) |
| Metso Oyj | METSO / XHEL | FI | Industrial Machinery | metso.com | [IR](https://www.metso.com/corporate/investors/) · Reporting — |
| Mitsubishi Heavy Industries Ltd. | 7011 / XTKS | JP | Industrial Machinery and Aerospace | mhi.com | [IR](https://www.mhi.com/finance) · Reporting — |
| MTU Aero Engines AG | MTX / XETR | DE | Aerospace Engines | mtu.de | [IR](https://www.mtu.de/investors/) · Reporting — |
| Northrop Grumman Corporation | NOC / XNYS | US | Aerospace and Defense | northropgrumman.com | [IR](https://investor.northropgrumman.com/) · [Reporting](https://www.northropgrumman.com/corporate-responsibility/sustainability-reports) |
| Rockwell Automation Inc. | ROK / XNYS | US | Industrial Automation | rockwellautomation.com | [IR](https://www.rockwellautomation.com/en-ca/company/investor-relations/investor-resources/faq.html) · Reporting — |
| RTX Corporation | RTX / XNYS | US | Aerospace and Defense | rtx.com | [IR](https://investors.rtx.com/) · [Reporting](https://www.rtx.com/who-we-are/our-responsibility) |
| Safran SA | SAF / XPAR | FR | Aerospace Equipment | safran-group.com | [IR](https://www.safran-group.com/finance/analysts-and-investors) · Reporting — |
| Sandvik AB | SAND / XSTO | SE | Industrial Machinery | home.sandvik | [IR](https://www.home.sandvik/en/investors/) · Reporting — |
| Schindler Holding Ltd | SCHN / XSWX | CH | Elevators and Escalators | group.schindler.com | [IR](https://group.schindler.com/en/investor-relations.html) · Reporting — |
| Schneider Electric SE | SU / XPAR | FR | Electrical Equipment | se.com | [IR](https://www.se.com/ww/en/about-us/investor-relations/) · [Reporting](https://www.se.com/ww/en/download/document/2025_Sustainability_Report/) |
| Siemens AG | SIE / XETR | DE | Industrial Automation | siemens.com | [IR](https://www.siemens.com/sk-sk/company/investor-relations/faq/) · [Reporting](https://www.siemens.com/en-gb/company/sustainability/reports-figures/) |
| Siemens Energy AG | ENR / XETR | DE | Power Equipment | siemensenergy.com | [IR](https://www.siemensenergy.com/global/en/home/investor-relations.html) · Reporting — |
| Union Pacific Corporation | UNP / XNYS | US | Rail Transportation | up.com | [IR](https://investor.unionpacific.com/) · [Reporting](https://www.up.com/investors/sustainability/sustainability-reports) |
| United Parcel Service Inc. | UPS / XNYS | US | Logistics | ups.com | [IR](https://investors.ups.com/) · Reporting — |
| Vestas Wind Systems A/S | VWS / XCSE | DK | Wind Turbine Equipment | vestas.com | [IR](https://www.vestas.com/en/investor) · [Reporting](https://www.vestas.com/en/sustainability/reports-and-ratings) |
| VINCI SA | DG / XPAR | FR | Construction and Infrastructure | vinci.com | [IR](https://www.vinci.com/en/finance/investors) · Reporting — |

## Approval gate

No import or pipeline execution is authorised by this deliverable. Obtain user approval before starting work toward the 200-company pilot. Retain the existing **5 → 20 → 50 → 100 → 200** checkpoints and the user’s data-complete success criterion: every company must have a downloaded, parsed report and extracted metrics. Stop at an unsuccessful checkpoint; do not skip blocked companies or weaken the criterion.
