/** Fictional test-only API responses. Never imported by production code. */
import { LABEL, type Company, type Evidence, type Metric, type CompanyBenchmark, type BenchmarkPage } from "../lib/benchmarks";

export const companies: Company[] = ["Aster Systems", "Boreal Systems", "Cedar Dynamics", "Delta Industries", "Elm Networks", "Fjord Software", "Granite Energy"].map((name, i) => ({id: `00000000-0000-4000-8000-${String(i + 1).padStart(12, "0")}`, company_name: name, ticker: ["AST", "BOR", "CED", "DEL", "ELM", "FJD", "GRT"][i], exchange: "XNAS", sector: i < 6 ? "Technology" : "Energy", country: i % 2 ? "GB" : "US", region: i % 2 ? "Europe" : "Americas", industry: i < 6 ? "Software" : "Energy", official_domain: `fixture-${i}.example.com`, reporting_year: 2025, active: true}));

export function source(index = 0, code = "scope_1_emissions", value = "14"): Evidence {
  return {id: `observation-${index}-${code}`, metric: code, kind: "observation", company_id: companies[index].id, report_id: `report-${index}`, report_title: "Fictional 2025 sustainability report", report_sha256: "a".repeat(64), source_policy: "official", reporting_year: 2025, source_url: `https://fixture-${index}.example.com/report.pdf`, source_page: 18, supporting_excerpt: `Synthetic test fixture: reported ${code} was ${value} in 2025. Not real company data.`, raw_value: String(Number(value) * 1000), raw_unit: "kgCO2e", normalised_value: value, normalised_unit: "tCO2e", validation_state: "validated", validation_audit_current: true, extraction_method: "manual_test_fixture", confidence: "1.0000", notes: "Fictional evidence for interface tests only.", validation_event: {actor_reference: "fixture-reviewer", reason: "Synthetic example verified for a UI test"}};
}
export function makeMetric(code: string, value: number | null, index = 0, changes: Partial<Metric> = {}): Metric {
  const percentage = /percent|adoption|completeness|change/.test(code);
  const v = value === null ? null : value.toFixed(6);
  const s = source(index, code, v ?? "0");
  if (percentage) {s.raw_value = v; s.raw_unit = "%"; s.normalised_unit = "%";}
  return {value: v, unit: percentage ? "%" : "tCO2e", eligibility_reason: value === null ? "missing_validated_evidence" : null, formula: code.startsWith("derived_") ? "Versioned synthetic fixture formula" : null, provenance: value === null ? [] : [s], comparison_dimensions: {organisational_boundary: "Consolidated group", period_start: "2025-01-01", period_end: "2025-12-31", scope2_method: "location_based"}, percentile: value === null ? null : String(index * 20), median: value === null ? null : "55.000000", distance_from_median: value === null ? null : (value - 55).toFixed(6), peer_sample_size: value === null ? 0 : 6, minimum_sample_size: 5, includes_subject: true, reason: value === null ? "missing_validated_evidence" : null, cohort_key: value === null ? null : `fixture-cohort-${code}`, flags: value === null ? [] : index === 0 ? ["lowest_value"] : index === 5 ? ["highest_value"] : [], sector_median: value === null ? null : "55.000000", sector_sample_size: value === null ? 0 : 6, ...changes};
}
const values: Record<string, (index: number) => number> = {
  scope_1_emissions: i => 14 + i,
  scope_2_location_based: i => 10 + i,
  scope_2_market_based: i => 8 + i,
  scope_3_emissions: i => 100 + i,
  derived_scope_1_2_total: i => 24 + i * 2,
  derived_yoy_emissions_change: i => -8 + i,
  renewable_energy_percent: i => 30 + i * 10,
  renewable_electricity_percent: i => 35 + i * 10,
  derived_renewable_energy_adoption: i => 30 + i * 10,
  derived_disclosure_completeness: () => 85.714286,
};
export function fixtureBenchmarks(year = 2025, missing = false): BenchmarkPage {
  const items: CompanyBenchmark[] = companies.map((c, i) => ({company_id: c.id, company_name: c.company_name, sector: c.sector, country: c.country, region: c.region, industry: c.industry, metrics: Object.fromEntries(Object.entries(values).map(([code, value]) => [code, makeMetric(code, missing || i === 6 ? null : value(i), i, year === 2025 ? {} : {comparison_dimensions: {reporting_year: year}})])), score: {label: LABEL, value: null, coverage_percent: "0", reason: "requires_trajectory_and_renewable_energy", ranking_eligible: false, components: []}, targets: missing || i === 6 ? [] : [{...source(i, "net_zero_target_year", "2050"), kind: "target", target_year: 2050, scope: "Scope 1 and 2", coverage: "Fictional consolidated group"}], context_evidence: [], disclosure_gaps: [{metric: "assurance_available", state: "unknown"}], target_flags: []}));
  for (const [index, item] of items.entries()) {
    for (const [code, metric] of Object.entries(item.metrics)) {
      if (metric.value === null) continue;
      const median = (values[code](2) + values[code](3)) / 2;
      metric.median = metric.sector_median = median.toFixed(6);
      metric.distance_from_median = (Number(metric.value) - median).toFixed(6);
      if (code === "derived_disclosure_completeness") {
        metric.percentile = "50"; metric.flags = [];
        metric.provenance = ["scope1_available", "scope2_available", "scope3_available", "methodology_stated", "boundaries_stated", "assurance_available", "base_year_stated"].map(key => ({...source(index, key), raw_value: key === "assurance_available" ? "false" : "true", raw_unit: null, normalised_value: null, normalised_unit: null}));
        item.disclosure_gaps = [{metric: "assurance_available", state: "verified_absent"}];
      }
    }
    for (const target of item.targets) { target.raw_value = "2050"; target.raw_unit = "year"; target.normalised_value = null; target.normalised_unit = null; }
  }
  return {items, total: items.length, page: 1, total_pages: 1, year, minimum_peers: 5, scope2_method: "location_based", peer_group: "sector", input_sha256: `fixture-hash-${year}`, methodology_version: "benchmark-v1", label: LABEL};
}
export function response(body: unknown, status = 200) {return new Response(JSON.stringify(body), {status, headers: {"Content-Type": "application/json"}});}
export function mockWorkspaceFetch(options: {missing?: boolean; mutate?: (data: BenchmarkPage) => void} = {}): typeof fetch {
  return async (input) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/api/library") return response({companies_total: companies.length, pilot_companies: companies.length, reports_downloaded: 0, observations_total: 0, observation_states: {}, items: companies.map(c => ({company_id: c.id, company_name: c.company_name, reports_downloaded: 0, observations: 0, observation_states: {}}))});
    if (/^\/api\/companies\/.+\/evidence$/.test(url.pathname)) return response({company_id: url.pathname.split("/")[3], observations: [], reports: []});
    if (url.pathname === "/api/companies") return response({items: companies, total: companies.length, page: 1, page_size: 100, total_pages: 1});
    if (url.pathname === "/api/benchmarks") {const data = fixtureBenchmarks(Number(url.searchParams.get("year")), options.missing); options.mutate?.(data); return response(data);}
    return response({detail: "No test handler"}, 404);
  };
}
