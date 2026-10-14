"""Curate the first energy edition from locally retained, page-aware official reports.

This is an editorial research fixture, not an unattended model extraction run.
No network or inference calls. The workbook builder calculates derived results.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "tmp/energy-2025"
OUT = ROOT / "data/editions/energy-2025"
manifest = json.loads((OUT / "sources.json").read_text())
docs = {s["key"]: json.loads((DOCS / f'{s["key"]}.json').read_text())
        for s in manifest if (DOCS / f'{s["key"]}.json').exists()}
facts = []


def add(id, company, metric, value, unit, doc, page, printed, anchor, notes="", year=2025):
    source = docs[doc]
    text = re.sub(r"\s+", " ", source["pages"][page - 1]["text"])
    match = re.search(anchor, text, re.I)
    if not match:
        raise ValueError(f"Source anchor missing: {id} / {doc} p{page}: {anchor}")
    excerpt = text[max(0, match.start() - 70):match.end() + 340]
    facts.append(dict(id=id, company=company, metric=metric, value=value, unit=unit,
                      year=year, document=doc, title=source["title"], pdf_page=page,
                      printed_page=str(printed), excerpt=excerpt, notes=notes,
                      url=source["source_url"] + f"#page={page}",
                      report_id=source["report_id"], sha256=source["sha256"]))


# Reuse the earlier Aramco extraction, retaining its printed/PDF page distinction.
old = json.loads((ROOT / "tmp/pdfs/aramco-kpis-20261010/kpis.json").read_text())
aramco = {
    "a_s1": 0, "a_s2": 1, "a_s2loc": 2, "a_upstream": 3,
    "a_fatal": 17, "a_fatalrate": 18, "a_employees": 25,
    "a_nationalities": 27, "a_women_n": 34, "a_women": 35,
    "a_lead": 37, "a_hires": 38, "a_train_total": 39, "a_train": 40,
    "a_social": 71, "a_revenue": 79, "a_tech_value": 95, "a_credits": 117,
}
for id, index in aramco.items():
    f = old[index]
    page = f["primary_page"]
    number = format(f["value"], ",")
    add(id, "Aramco", f["metric"], f["value"], f["unit"], "aramco", page // 2 + 2,
        page, r"(?<!\d)" + re.escape(number) + r"(?!\d)",
        f.get("boundary", "") + ". " + f.get("note", ""))
add("a_prior", "Aramco", "Scope 1+2 market-based", 68.5, "MtCO2e", "aramco", 16, 28, r"68\.5", year=2024)
add("a_avoided", "Aramco", "Emissions avoided through energy-efficiency initiatives", 1.57, "MtCO2e", "aramco", 18, 32, r"1\.57")
add("a_ai_admin", "Aramco", "Reduction in manual energy-reporting effort", 95, "%", "aramco", 18, 32, r"95%", "Administrative effort, not energy consumption.")
add("a_ai_assets", "Aramco", "Assets monitored by energy forecasting", 27, "assets", "aramco", 18, 32, r"27")
add("a_contractor_fatal", "Aramco", "Contractor fatalities", 4, "people", "aramco", 25, 46, r"contractor", "All four workforce fatalities were contractors.")
add("a_employee_fatal", "Aramco", "Employee fatalities", 0, "people", "aramco", 25, 46, r"contractor", "All four fatalities were contractors; employee remainder is zero.")
add("a_sdg", "Aramco", "SDGs mapped in the report", "3, 4, 5, 6, 7, 8, 9, 12, 13, 14, 15, 17", "SDG identifiers", "aramco", 11, "18–19", r"SDG|Sustainable Development", "Company mapping; use related operating outcomes rather than counting logos.")

# Shell's annual report contains the financial and sustainability statements.
for id, metric, value, unit, page, printed, anchor, notes in [
    ("s_s1", "Scope 1 gross operational emissions", 46, "MtCO2e", 90, 88, "46", "Operational control."),
    ("s_s2", "Scope 2 gross market-based emissions", 7, "MtCO2e", 90, 88, "Scope 2", "Operational control."),
    ("s_prior", "Scope 1+2 gross rounded total", 58, "MtCO2e", 90, 88, "58", "2024 components 50 + 8; no claim of an unrounded bridge."),
    ("s_acquire", "Emissions added through acquisitions", 1.4, "MtCO2e", 91, 89, "1.4", "2024–2025 emissions bridge."),
    ("s_divest", "Emissions removed through divestments", 4.8, "MtCO2e", 91, 89, "4.8", "2024–2025 emissions bridge."),
    ("s_abate", "Reduction activities including purchased renewable electricity", 1238, "ktCO2e", 91, 89, "1,238", "Includes 20 ktCO2e from purchased renewable electricity."),
    ("s_credit", "Credits included in energy-product net carbon intensity", 5.5, "MtCO2e", 92, 90, "5.5", "Equity energy-product boundary; not operational Scope 1+2."),
    ("s_credit_prior", "Credits included in energy-product net carbon intensity", 16.4, "MtCO2e", 92, 90, "16.4", "2024."),
    ("s_nci", "Net carbon intensity of energy products", 71, "gCO2e/MJ", 92, 90, "71", "Rounded; same as 2024."),
    ("s_employees", "Employees", 85000, "people", 116, 114, "85,000", "Year-end workforce."),
    ("s_women", "Women in workforce", 35, "%", 116, 114, "35%", "Reported rounded percentage."),
    ("s_lead", "Women in senior leadership", 35, "%", 116, 114, "35%", "Company senior-leadership definition."),
    ("s_train_days", "Formal training", 253000, "days", 116, 114, "253,000", "Employees and JV partners; not converted to hours without a stated day length."),
    ("s_revenue", "Revenue", 266886, "USD million", 269, 267, "266,886", "Includes commodity derivative revenue."),
    ("s_sales", "Revenue from contracts with customers", 257352, "USD million", 269, 267, "257,352", "Sales denominator for the social-spend ratio."),
    ("s_social", "Social investment", 115, "USD million", 121, 119, "115", "12 million mandatory/contractual; 103 million voluntary."),
    ("s_voluntary", "Voluntary social investment", 103, "USD million", 121, 119, "103", "Subset of social investment."),
    ("s_employee_fatal", "Employee work-related fatalities", 0, "people", 420, 418, "fatalit", "Four fatalities, all contractors."),
    ("s_contractor_fatal", "Contractor work-related fatalities", 4, "people", 420, 418, "fatalit", "Operational safety reporting."),
    ("s_scope3", "Scope 3 total, ESRS significant categories", 1065, "MtCO2e", 369, 367, "1,065", "Financial-control sustainability statement; not the energy-product NCI total."),
    ("s_ai", "Pearl GTL machine vision and equipment monitoring", "Deployed", "application", 73, 71, "Pearl GTL", "Named AI application; no numeric benefit in this passage."),
]:
    add(id, "Shell", metric, value, unit, "shell", page, printed, anchor, notes, 2024 if id in {"s_prior", "s_credit_prior"} else 2025)

for id, metric, value, unit, page, anchor, notes in [
    ("t_s1", "Scope 1, operated perimeter", 31800000, "tCO2e", 349, "31,800,000", "Operated perimeter."),
    ("t_s2", "Scope 2 market-based, operated perimeter", 1300000, "tCO2e", 349, "1,300,000", "Operated perimeter."),
    ("t_prior", "Scope 1+2, operated perimeter", 34300000, "tCO2e", 349, "34,300,000", "2024 table value; narrative elsewhere rounds the annual decline differently."),
    ("t_consolidated_s1", "Scope 1, consolidated accounting group", 33700000, "tCO2e", 349, "33,700,000", "Consolidated accounting group subset."),
    ("t_consolidated_s2", "Scope 2 market-based, consolidated accounting group", 1400000, "tCO2e", 349, "1,400,000", "Consolidated accounting group subset."),
    ("t_scope3", "Scope 3 significant category 11", 335000000, "tCO2e", 350, "335,000,000", "Category 11 retained as significant; not a full 15-category sum."),
    ("t_women", "Women in workforce", 36.7, "%", 393, "36.7%", "Year-end workforce."),
    ("t_lead", "Women among senior executives", 30.2, "%", 393, "30.2%", "Senior executives, not all management grades."),
    ("t_hires", "Women among permanent contract hires", 39.2, "%", 393, "39.2%", "Permanent hires."),
    ("t_train_f", "Average training hours — women", 24.6, "hours/person", 389, "24.6", "Formal training, excludes on-the-job learning."),
    ("t_train_m", "Average training hours — men", 26.6, "hours/person", 389, "26.6", "Formal training, excludes on-the-job learning."),
    ("t_train", "Average formal training hours", 25.9, "hours/person", 389, "25.9", "Formal training."),
    ("t_training_access", "Employees receiving training", 98.1, "%", 389, "98.1", "Training participation."),
    ("t_employee_fatal", "Employee occupational fatalities", 0, "people", 380, "occupational fatalities", "Contractor split shown separately."),
    ("t_contractor_fatal", "Contractor occupational fatalities", 1, "people", 380, "Contractors’ personnel", "Fatality during unloading in Angola."),
    ("t_revenue", "Revenue from sales", 182344, "USD million", 453, "182,344", "After excise tax expenses."),
    ("t_ai_solutions", "Digital solutions created since 2020", "Close to 100; half integrate AI", "applications", 43, "100 digital", "Cumulative deployment pipeline; not 100 new applications in 2025."),
    ("t_nationalities", "Nationalities in workforce", "Nearly 170", "nationalities", 392, "170", "Approximate reported count."),
]:
    add(id, "TotalEnergies", metric, value, unit, "total", page, page, anchor, notes, 2024 if id == "t_prior" else 2025)
add("t_credits", "TotalEnergies", "Planned annual nature-based carbon credits", 5, "MtCO2e/year", "total-climate", 47, 47, "5 Mt|5 million|5 million", "2030 plan, not 2025 retirement.", 2030)
add("t_abate", "TotalEnergies", "Annual reduction from emissions projects", .7, "MtCO2e", "total-climate", 47, 47, "0.7", "More than 85 projects.")

for id, metric, value, unit, page, anchor, notes in [
    ("q_s1", "Scope 1 emissions, own operations", 7.8, "MtCO2e", 113, "7.8", "Company own-operations perimeter."),
    ("q_s2", "Scope 2 market-based, own operations", 1.2, "MtCO2e", 113, "1.2", "Location-based 0.08 MtCO2e."),
    ("q_s1_prior", "Scope 1 emissions, own operations", 8.3, "MtCO2e", 113, "8.3", "2024."),
    ("q_s2_prior", "Scope 2 market-based, own operations", 1.5, "MtCO2e", 113, "1.5", "2024."),
    ("q_scope3", "Scope 3 significant categories", 287.6, "MtCO2e", 113, "287.6", "Multiple material categories, not category 11 alone."),
    ("q_scope3_prior", "Scope 3 significant categories", 278.9, "MtCO2e", 113, "278.9", "2024."),
    ("q_employees", "Employees", 24620, "people", 138, "24,620", "Permanent and temporary; all reported genders."),
    ("q_women_n", "Female employees", 7996, "people", 138, "7,996", "Permanent and temporary."),
    ("q_lead", "Women in level-2 leadership", 46, "%", 140, "46", "Leaders reporting to the corporate executive committee; not all managers."),
    ("q_train_f", "Average training hours — women", 22.6, "hours/person", 142, "22.6", "Formal learning."),
    ("q_train_m", "Average training hours — men", 28.7, "hours/person", 142, "28.7", "Formal learning."),
    ("q_train", "Average training hours", 26.7, "hours/person", 142, "26.7", "Formal learning."),
    ("q_credits", "Carbon credits retired for business flights", 41385, "tCO2e", 114, "41,385", "Flights outside Europe; 100% reduction credits, Verra VCS."),
    ("q_employee_fatal", "Employee work-related injury fatalities", 0, "people", 162, "work-related injuries", "Dash represents none in company table."),
    ("q_contractor_fatal", "Non-employee work-related injury fatalities", 1, "people", 162, "work-related injuries", "ESRS non-employees category."),
    ("q_revenue", "Revenue from contracts with customers", 105242, "USD million", 202, "105,242", "Excludes other revenue and income."),
    ("q_rd", "R&D and digital expenditure", 730, "USD million", 80, "730", "Combined R&D and digital; not AI spending alone."),
    ("q_ai", "AI-assisted seismic interpretation", "Hours instead of months", "reported operating effect", 80, "hours", "Reported time compression; no multiplier inferred without exact durations."),
]:
    add(id, "Equinor", metric, value, unit, "equinor", page, page, anchor, notes, 2024 if "prior" in id else 2025)

for id, metric, value, unit, page, anchor, notes in [
    ("e_s1", "Scope 1, ESRS perimeter", 28.4, "MtCO2e", 166, "28.4", "Consolidated group plus operational-control assets."),
    ("e_s2", "Scope 2 market-based, ESRS perimeter", .8, "MtCO2e", 166, "0.8", "ESRS perimeter."),
    ("e_s1_prior", "Scope 1, ESRS perimeter", 31.1, "MtCO2e", 166, "31.1", "2024."),
    ("e_s2_prior", "Scope 2 market-based, ESRS perimeter", .9, "MtCO2e", 166, "0.9", "2024."),
    ("e_consolidated_s1", "Scope 1, consolidated group", 26.2, "MtCO2e", 166, "26.2", "Consolidated group subset."),
    ("e_consolidated_s2", "Scope 2 market-based, consolidated group", .7, "MtCO2e", 166, "0.7", "Consolidated group subset."),
    ("e_scope3", "Scope 3 use of sold products", 182.3, "MtCO2e", 167, "182.3", "Category 11 only."),
    ("e_women", "Women in workforce", 28.6, "%", 201, "28.6", "Reported rounded percentage."),
    ("e_lead", "Women in senior and middle management", 30.8, "%", 201, "30.8", "Broader population than senior managers only."),
    ("e_senior", "Women among senior managers", 19.8, "%", 207, "19.8", "174 of 878 senior managers."),
    ("e_train_f", "Average training hours — women", 27.5, "hours/person", 207, "27.5", "Reported average."),
    ("e_train_m", "Average training hours — men", 35.9, "hours/person", 207, "35.9", "Reported average."),
    ("e_train", "Average training hours", 33.5, "hours/person", 207, "33.5", "Reported average."),
    ("e_credits", "Credits supporting 2025 equity targets", 7, "MtCO2e", 166, "7 Mt|7 million|7.0|7,000", "Retired February 2026 for 2025 reporting; 100% reduction credits, Verra."),
    ("e_credits_prior", "Credits supporting equity targets", 5.9, "MtCO2e", 166, "5.9", "2024."),
    ("e_employee_fatal", "Employee work-related injury fatalities", 0, "people", 213, "fatal events", "Employee and contractor split."),
    ("e_contractor_fatal", "Contractor work-related injury fatalities", 0, "people", 213, "fatal events", "2025; five contractor fatalities in 2024."),
    ("e_revenue", "Sales from operations", 82151, "EUR million", 376, "82,151", "Consolidated sales."),
    ("e_fx", "Annual average EUR to USD exchange rate", 1.13, "USD/EUR", 89, "1.130", "Eni cites ECB annual average; applied to 2025 flows."),
    ("e_social", "Local development investments", 81, "EUR million", 225, "81.0", "Eni share; includes 4.2 million resettlement/compensation."),
    ("e_education", "Education and vocational training investment", 21.3, "EUR million", 225, "21.3", "Subset of local development investment."),
    ("e_ai_alerts", "Safety Presence AI alerts since deployment", "About 800", "alerts", 210, "800", "Alerts prompting preventive actions; not 800 accidents avoided."),
    ("e_avoided", "Potentially avoided emissions", 17.3, "MtCO2e", 167, "17.3", "Company counterfactual calculation."),
    ("e_lng_avoided", "LNG portion of potentially avoided emissions", 13.2, "MtCO2e", 167, "13.2", "Counterfactual comparison, not an inventory reduction."),
]:
    add(id, "Eni", metric, value, unit, "eni", page, page - 2, anchor, notes, 2024 if "prior" in id else 2025)
add("e_rdshare", "Eni", "R&D allocated to decarbonisation, circular economy and transition", 80, "%", "eni-for", 6, 9, "80%", "Broader than climate-only R&D.")
add("e_beneficiaries", "Eni", "People reached through community initiatives", "About 3 million", "people", "eni-for", 6, 9, "3 mln", "Includes clean-cooking projects.")
add("e_sdg", "Eni", "SDG 7 energy-access narrative", "Natural gas linked to energy access", "narrative", "eni-for", 59, 115, "SDG 7", "Connects SDG positioning to the gas business, not only renewables.")

findings = [
    ("Training opportunity", "The training headline hides a gender gap", "TotalEnergies provides the closest female-to-male training-hours ratio of the three disclosing a split. Eni has the highest overall hours in that three-company subset, but the widest gender gap.", "Ask for participation and hours by gender, not only the total training budget.", ["t_train_f", "t_train_m", "e_train_f", "e_train_m", "q_train_f", "q_train_m"]),
    ("Representation", "Hiring is moving faster than the workforce at Aramco", "Women represent 26% of Aramco new hires against 8.2% of its workforce. That is a recruitment pipeline signal; TotalEnergies still leads current workforce representation at 36.7%.", "Track whether the hiring mix translates into retention and promotion over subsequent years.", ["a_hires", "a_women", "t_women"]),
    ("Leadership", "A management label can change the story by 11 points", "Eni reports 30.8% women across senior and middle management, but 19.8% among senior managers alone. Equinor separately exposes the layers of its leadership pipeline.", "Request leadership levels instead of relying on a single aggregate diversity measure.", ["e_lead", "e_senior", "q_lead"]),
    ("Safety", "The fatalities are outside the employee headcount", "Across the five reports, 10 work-related injury fatalities were contractors or non-employees; none were own employees. Employee-only safety KPIs would miss all 10.", "Keep contractor outcomes alongside employee outcomes in board and procurement reporting.", ["a_contractor_fatal", "s_contractor_fatal", "t_contractor_fatal", "q_contractor_fatal", "e_contractor_fatal"]),
    ("Carbon progress", "Selling assets can move the emissions line faster than abatement", "Shell's net portfolio effect removed 3.4 MtCO2e from its bridge, versus 1.238 Mt from reduction activities and purchased renewable electricity. Equinor also attributes its Scope 1 decline primarily to divestments.", "Separate portfolio change, physical operating reductions and measurement changes when assessing progress.", ["s_acquire", "s_divest", "s_abate", "q_s1", "q_s1_prior"]),
    ("Carbon progress", "Avoided emissions and rising emissions can coexist", "Aramco reports 1.57 MtCO2e avoided through energy-efficiency initiatives while its Scope 1+2 emissions increased from 68.5 to 72.0 MtCO2e.", "A savings initiative answers a different question from the company's absolute emissions trajectory.", ["a_avoided", "a_s1", "a_s2", "a_prior"]),
    ("Carbon credits", "Credit volume is not a common currency for climate progress", "Eni uses credits for equity targets, Shell for energy-product intensity, Aramco for corporate Scope 1+2, and Equinor for business flights. TotalEnergies' 5 Mt figure is a future annual plan.", "Ask what claim the credit supports, when it was retired, and which emissions it offsets.", ["e_credits", "s_credit", "a_credits", "q_credits", "t_credits"]),
    ("Innovation", "AI disclosures range from deployment counts to operating outcomes", "TotalEnergies describes a portfolio of close to 100 digital solutions, half using AI. Aramco quantifies 95% less manual energy-reporting effort. Eni reports about 800 safety alerts; Equinor describes seismic interpretation in hours instead of months.", "Benchmark evidence of deployment and operating benefit, not the number of AI mentions.", ["t_ai_solutions", "a_ai_admin", "e_ai_alerts", "q_ai"]),
    ("Social investment", "Revenue-normalised community spending changes the comparison", "Aramco, Eni and Shell disclose annual community investment amounts. Dividing each by sales creates a scale-adjusted spending lens; Eni's ratio is unchanged by converting both euro inputs at the same exchange rate.", "Pair spending intensity with programme outcomes and voluntary versus mandatory allocations.", ["a_social", "a_revenue", "e_social", "e_revenue", "e_fx", "s_social", "s_sales"]),
    ("SDGs", "Energy access links the SDGs to the core gas business", "Eni explicitly links natural gas to SDG 7 and attributes most of its potentially avoided emissions to LNG. Aramco maps 12 SDGs across its report.", "Assess the operating mechanism and beneficiaries behind each SDG claim, not the number of SDG icons.", ["e_sdg", "e_avoided", "e_lng_avoided", "a_sdg", "e_beneficiaries"]),
]

companies = ["Aramco", "Shell", "TotalEnergies", "Equinor", "Eni"]
checklist = [
    ("Scope 1 and Scope 2 separately", [["a_s1", "a_s2"], ["s_s1", "s_s2"], ["t_s1", "t_s2"], ["q_s1", "q_s2"], ["e_s1", "e_s2"]]),
    ("Quantified Scope 3 with stated category/boundary", [[], ["s_scope3"], ["t_scope3"], ["q_scope3"], ["e_scope3"]]),
    ("Female workforce representation", [["a_women"], ["s_women"], ["t_women"], ["q_women_n", "q_employees"], ["e_women"]]),
    ("Female leadership representation", [["a_lead"], ["s_lead"], ["t_lead"], ["q_lead"], ["e_lead"]]),
    ("Training hours split by gender", [[], [], ["t_train_f", "t_train_m"], ["q_train_f", "q_train_m"], ["e_train_f", "e_train_m"]]),
    ("Fatalities split by employee / contractor", [["a_contractor_fatal"], ["s_contractor_fatal"], ["t_contractor_fatal"], ["q_contractor_fatal"], ["e_contractor_fatal"]]),
    ("Credit quantity, purpose and timing (actual or plan)", [["a_credits"], ["s_credit"], ["t_credits"], ["q_credits"], ["e_credits"]]),
]

assert len({f["id"] for f in facts}) == len(facts)
ids = {f["id"] for f in facts}
assert all(set(f[4]) <= ids for f in findings)
output = dict(title="Energy, decoded", year=2025, edition_date="2026-10-13",
              companies=companies, facts=facts,
              findings=[dict(theme=t, headline=h, observation=o, implication=i, fact_ids=refs) for t,h,o,i,refs in findings],
              checklist=[dict(topic=t, evidence=dict(zip(companies, refs))) for t,refs in checklist],
              documents=[{k:v for k,v in d.items() if k not in {"pages", "path"}} for d in docs.values()],
              method="AI-assisted reading and editorial synthesis; calculations are deterministic. Seven equally weighted disclosure topics, one point for explicit disclosure. Scores describe this reviewed source bundle, not overall sustainability. No live paid-model calls in this edition build.")
(OUT / "edition.json").write_text(json.dumps(output, ensure_ascii=False, indent=2))
print(f"{len(facts)} source-backed facts; {len(findings)} findings; {len(docs)} documents")
