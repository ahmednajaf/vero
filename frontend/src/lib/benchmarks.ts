import { request } from "./api";
import { getLibrary, type Library } from "./library";

export interface Company {
  id: string; company_name: string; ticker: string; exchange: string;
  sector: string; country: string; region: string; industry: string;
  official_domain: string; reporting_year: number; active: boolean;
}
export interface Evidence {
  local_report_url?: string | null; report_year?: number | null; compatibility_state?: string;
  id?: string; kind?: string; metric?: string; company_id?: string; company_name?: string;
  report_id?: string; report_title?: string; report_sha256?: string | null;
  reporting_year?: number; source_url?: string; source_page?: number;
  supporting_excerpt?: string; raw_value?: string | null; raw_unit?: string | null;
  normalised_value?: string | null; normalised_unit?: string | null;
  validation_state?: string; validation_audit_current?: boolean; source_policy?: string;
  extraction_method?: string; notes?: string; confidence?: string | null;
  target_year?: number; target_raw_value?: string | null; target_raw_unit?: string | null;
  scope?: string | null; boundary?: string | null; coverage?: string | null;
  value?: string; currency?: string; validated?: boolean; source_verified?: boolean;
  validation_event?: { actor_reference?: string; reason?: string } | null;
}
export interface Metric {
  value: string | null; unit: string | null; eligibility_reason: string | null;
  formula: string | null; provenance: Evidence[]; comparison_dimensions: Record<string, unknown>;
  percentile: string | null; median: string | null; distance_from_median: string | null;
  peer_sample_size: number; minimum_sample_size: number; includes_subject: boolean;
  reason: string | null; cohort_key: string | null; flags: string[];
  sector_median: string | null; sector_sample_size: number;
}
export interface ComponentScore {
  component: string; metric: string | null; weight: string; score: string | null;
  reason: string | null; formula: string; provenance: Evidence[];
}
export interface CompanyBenchmark {
  company_id: string; company_name: string; sector: string; country: string;
  region: string; industry: string; metrics: Record<string, Metric>;
  score: { label: string; value: string | null; coverage_percent: string; reason: string | null; components: ComponentScore[]; ranking_eligible: boolean;
    ranking?: {rank: number | null; percentile: string | null; peer_sample_size: number; cohort_key: string | null; reason: string | null} };
  targets: Evidence[]; context_evidence: Evidence[];
  disclosure_gaps: { metric: string; state: string }[];
  target_flags: { target_id: string; target_year: number; flag: string }[];
}
export interface BenchmarkPage {
  items: CompanyBenchmark[]; total: number; page: number; total_pages: number;
  year: number; minimum_peers: number; scope2_method: string; peer_group: string;
  input_sha256: string; methodology_version: string; label: string;
}
export interface Cohort {
  metric: string; cohort_key: string; comparison_dimensions: Record<string, unknown>;
  unit: string | null; sample_size: number; median: string | null; reason: string | null;
}
export interface SectorSummary {
  sector: string; year: number; minimum_peers: number; companies_total: number;
  cohorts: Cohort[];
}
export interface WorkspaceData { companies: Company[]; benchmarks: BenchmarkPage; library?: Library; benchmarkError?: string; libraryError?: string }
export interface SourceSelection {
  company: string; label: string; metric?: Metric; evidence?: Evidence[]; explanation?: string;
  demo?: boolean;
  cohort?: {
    median: string | null; unit: string | null; sampleSize: number;
    dimensions: Record<string, unknown>;
    members: {company: string; value: string; unit: string | null}[];
  };
}

const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const string = (value: unknown): value is string => typeof value === "string";
const nullableString = (value: unknown) => value === null || string(value);
const integer = (value: unknown): value is number => typeof value === "number" && Number.isInteger(value) && value >= 0;
const decimal = (value: unknown) => value === null || (string(value) && value.trim() !== "" && /^[-+]?\d+(?:\.\d+)?$/.test(value) && Number.isFinite(Number(value)));
export function evidence(value: unknown): value is Evidence {
  return object(value) && ["id", "kind", "metric", "report_id", "report_title", "source_url", "supporting_excerpt", "validation_state", "source_policy", "extraction_method", "notes", "scope", "boundary", "coverage", "raw_value", "raw_unit", "normalised_value", "normalised_unit", "target_raw_value", "target_raw_unit", "value", "currency", "report_sha256"].every(key => value[key] === undefined || nullableString(value[key])) &&
    ["source_page", "reporting_year", "target_year"].every(key => value[key] === undefined || integer(value[key])) &&
    ["validation_audit_current", "source_verified", "validated"].every(key => value[key] === undefined || typeof value[key] === "boolean") &&
    (value.validation_event === undefined || value.validation_event === null || (object(value.validation_event) && [value.validation_event.actor_reference, value.validation_event.reason].every(v => v === undefined || string(v))));
}
function metric(value: unknown): value is Metric {
  return object(value) && [value.value, value.percentile, value.median, value.distance_from_median, value.sector_median].every(decimal) &&
    (value.percentile === null || (Number(value.percentile) >= 0 && Number(value.percentile) <= 100)) &&
    [value.unit, value.eligibility_reason, value.reason, value.formula, value.cohort_key].every(nullableString) &&
    [value.peer_sample_size, value.minimum_sample_size, value.sector_sample_size].every(integer) &&
    typeof value.includes_subject === "boolean" && object(value.comparison_dimensions) &&
    Array.isArray(value.provenance) && value.provenance.every(evidence) && Array.isArray(value.flags) && value.flags.every(string);
}
function raceRanking(value: unknown): boolean {
  return value === undefined || (object(value) && integer(value.peer_sample_size) && nullableString(value.cohort_key) && nullableString(value.reason) &&
    decimal(value.percentile) && (value.percentile === null || (Number(value.percentile) >= 0 && Number(value.percentile) <= 100)) &&
    (value.rank === null || (integer(value.rank) && value.rank > 0 && value.rank <= value.peer_sample_size)));
}
function companyBenchmark(value: unknown): value is CompanyBenchmark {
  return object(value) && [value.company_id, value.company_name, value.sector, value.country, value.region, value.industry].every(string) &&
    object(value.metrics) && Object.values(value.metrics).every(metric) && object(value.score) &&
    string(value.score.label) && decimal(value.score.value) && decimal(value.score.coverage_percent) && nullableString(value.score.reason) && typeof value.score.ranking_eligible === "boolean" && raceRanking(value.score.ranking) &&
    Array.isArray(value.score.components) && value.score.components.every(c => object(c) && string(c.component) && nullableString(c.metric) && decimal(c.weight) && decimal(c.score) && nullableString(c.reason) && string(c.formula) && Array.isArray(c.provenance) && c.provenance.every(evidence)) &&
    Array.isArray(value.targets) && value.targets.every(evidence) && Array.isArray(value.context_evidence) && value.context_evidence.every(evidence) &&
    Array.isArray(value.disclosure_gaps) && value.disclosure_gaps.every(g => object(g) && string(g.metric) && string(g.state)) &&
    Array.isArray(value.target_flags) && value.target_flags.every(f => object(f) && string(f.target_id) && integer(f.target_year) && string(f.flag));
}
function company(value: unknown): value is Company {
  return object(value) && [value.id, value.company_name, value.ticker, value.exchange, value.sector, value.country, value.region, value.industry, value.official_domain].every(string) && integer(value.reporting_year) && typeof value.active === "boolean";
}
function pagination(value: Record<string, unknown>) {
  return [value.page, value.total_pages, value.total].every(integer) && (value.total as number) <= 500 && (value.total_pages as number) <= 5;
}
async function benchmarkPage(year: number, page: number, signal?: AbortSignal): Promise<BenchmarkPage> {
  const response = await request(`/benchmarks?year=${year}&page=${page}&page_size=100`, signal);
  const body = response.body;
  if (response.status !== 200 || !object(body) || !pagination(body) || body.year !== year || body.page !== page || !integer(body.minimum_peers) || body.minimum_peers < 5 || ![body.input_sha256, body.methodology_version, body.label, body.scope2_method, body.peer_group].every(string) || !Array.isArray(body.items) || !body.items.every(companyBenchmark)) {
    throw new Error("Benchmark data could not be verified. Check the API connection and database migrations, then retry.");
  }
  return body as unknown as BenchmarkPage;
}
async function companyPage(page: number, signal?: AbortSignal): Promise<{items: Company[]; total_pages: number; total: number}> {
  const { status, body } = await request(`/companies?active=true&page=${page}&page_size=100`, signal);
  if (status !== 200 || !object(body) || !pagination(body) || body.page !== page || !Array.isArray(body.items) || !body.items.every(company)) throw new Error("The company universe is unavailable. Check the API connection and retry.");
  return body as unknown as {items: Company[]; total_pages: number; total: number};
}
export async function getWorkspace(year: number, signal?: AbortSignal): Promise<WorkspaceData> {
  const libraryPromise = getLibrary(signal).then(library => ({library})).catch(() => ({libraryError: "Report coverage unavailable"}));
  const benchmarkPromise = (async () => {
    const first = await benchmarkPage(year, 1, signal);
    const pages = await Promise.all(Array.from({length: Math.max(0, first.total_pages - 1)}, (_, i) => benchmarkPage(year, i + 2, signal)));
    const items = [first, ...pages].flatMap(p => p.items);
    if (items.length !== first.total || new Set(items.map(c => c.company_id)).size !== items.length || pages.some(p => p.input_sha256 !== first.input_sha256)) throw new Error("Benchmark snapshot changed. Reload to retry.");
    return {benchmarks: {...first, items}};
  })().catch((error: unknown) => ({benchmarkError: error instanceof Error ? error.message : "Benchmarks unavailable", benchmarks: {
    items: [], total: 0, page: 1, total_pages: 0, year, minimum_peers: 5,
    scope2_method: "location_based", peer_group: "sector", input_sha256: "", methodology_version: "", label: LABEL,
  } satisfies BenchmarkPage}));
  const firstCompanies = await companyPage(1, signal);
  const companyPages = await Promise.all(Array.from({length: Math.max(0, firstCompanies.total_pages - 1)}, (_, i) => companyPage(i + 2, signal)));
  const companies = [firstCompanies, ...companyPages].flatMap(p => p.items);
  if (companies.length !== firstCompanies.total || new Set(companies.map(c => c.id)).size !== companies.length) {
    throw new Error("The universe changed while loading. Retry to view one complete, consistent dataset.");
  }
  const [benchmarkResult, libraryResult] = await Promise.all([benchmarkPromise, libraryPromise]);
  if (!('benchmarkError' in benchmarkResult) && (companies.length !== benchmarkResult.benchmarks.items.length || companies.some(c => !benchmarkResult.benchmarks.items.some(b => b.company_id === c.id)))) {
    return {companies, ...libraryResult, benchmarks: {...benchmarkResult.benchmarks, items: [], total: 0}, benchmarkError: "Company roster changed. Reload benchmarks to retry."};
  }
  return {companies, ...benchmarkResult, ...libraryResult};
}
export async function getSectorSummary(sector: string, year: number, signal?: AbortSignal): Promise<SectorSummary> {
  const { status, body } = await request(`/sectors/${encodeURIComponent(sector)}/summary?year=${year}`, signal);
  if (status !== 200 || !object(body) || body.year !== year || !string(body.sector) || !integer(body.minimum_peers) || !integer(body.companies_total) || !Array.isArray(body.cohorts) || !body.cohorts.every(c => object(c) && string(c.metric) && string(c.cohort_key) && object(c.comparison_dimensions) && nullableString(c.unit) && integer(c.sample_size) && decimal(c.median) && nullableString(c.reason))) {
    throw new Error("Sector findings are unavailable. No trend has been inferred from missing data.");
  }
  return body as unknown as SectorSummary;
}

export const METRICS = {
  derived_yoy_emissions_change: "Emissions change · YoY",
  derived_scope_1_2_total: "Scope 1 + 2 emissions",
  scope_1_emissions: "Scope 1 emissions",
  scope_2_location_based: "Scope 2 · location-based",
  scope_2_market_based: "Scope 2 · market-based",
  scope_3_emissions: "Scope 3 emissions",
  total_ghg_reported: "Total GHG reported",
  derived_emissions_per_revenue: "Emissions per revenue",
  total_energy_consumption: "Total energy consumption",
  electricity_consumption: "Electricity consumption",
  renewable_energy_percent: "Renewable energy",
  renewable_electricity_percent: "Renewable electricity",
  derived_renewable_energy_adoption: "Renewable energy adoption",
  derived_disclosure_completeness: "Disclosure completeness",
} as const;
export type MetricKey = keyof typeof METRICS;
export const BENCHMARK_METRICS: MetricKey[] = ["derived_renewable_energy_adoption", "derived_yoy_emissions_change", "derived_scope_1_2_total", "scope_3_emissions", "derived_disclosure_completeness", "derived_emissions_per_revenue"];
export const LABEL = "Prototype benchmark score — not an external ESG rating.";
const CONTEXT_LABELS: Record<string, string> = {
  net_zero_target_year: "Net-zero target", carbon_neutral_target_year: "Carbon-neutral target", interim_emissions_target: "Interim emissions target", sbti_status: "SBTi status",
  scope1_available: "Scope 1 disclosed", scope2_available: "Scope 2 disclosed", scope3_available: "Scope 3 disclosed", methodology_stated: "Methodology stated", boundaries_stated: "Boundaries stated", assurance_available: "Assurance available", base_year_stated: "Base year stated",
  board_sustainability_oversight: "Board sustainability oversight", executive_sustainability_owner: "Executive sustainability owner", climate_linked_remuneration: "Climate-linked remuneration", tcfd_disclosure: "TCFD disclosure", issb_disclosure: "ISSB disclosure", assurance_status: "Assurance status",
  emissions_trajectory: "Emissions trajectory", renewable_energy: "Renewable energy", disclosure_completeness: "Disclosure completeness", governance: "Governance", net_zero_target: "Net-zero target",
};
export const metricName = (key: string) => METRICS[key as MetricKey] ?? CONTEXT_LABELS[key] ?? key.replaceAll("_", " ").replace(/^./, c => c.toUpperCase());
export const numeric = (value: string | null | undefined): number | null => value != null && value.trim() !== "" && Number.isFinite(Number(value)) ? Number(value) : null;
export const usable = (value?: Metric): value is Metric & {value: string; eligibility_reason: null} => !!value && value.eligibility_reason === null && numeric(value.value) !== null;
export const comparable = (value?: Metric): value is Metric & {value: string; percentile: string; eligibility_reason: null} => usable(value) && value.percentile !== null && value.peer_sample_size >= value.minimum_sample_size;
export function format(value: string | number | null | undefined, digits = 1): string {
  if (value == null || value === "") return "—";
  const n = Number(value); return Number.isFinite(n) ? new Intl.NumberFormat("en-GB", { maximumFractionDigits: digits }).format(n) : "—";
}
export function reasonText(reason?: string | null): string {
  if (!reason) return "Validated and comparable";
  const known: Record<string, string> = {
    missing_validated_evidence: "Awaiting validated evidence", insufficient_comparable_peers: "Not enough comparable peers", incomplete_disclosure_assessment: "Disclosure review incomplete", conflicting_validated_evidence: "Conflicting observations — review required", requires_two_comparable_years: "Two comparable years required", source_or_validation_audit_missing: "Source or validation review required", context_only_not_performance: "Context only · not performance", requires_trajectory_and_renewable_energy: "Trajectory and renewable-energy evidence required", comparability_not_reviewed: "Comparability review required",
  };
  return known[reason] ?? (reason.startsWith("missing_comparison_dimensions") ? "Comparison context incomplete" : reason.replaceAll("_", " ").replace(/^./, c => c.toUpperCase()));
}
export function countryName(code: string): string {
  try { return new Intl.DisplayNames(["en"], {type: "region"}).of(code) ?? code; } catch { return code; }
}
export function safeSourceUrl(url?: string, page?: number): string | null {
  if (!url) return null;
  try { const value = new URL(url); if (!["http:", "https:"].includes(value.protocol) || value.username || value.password) return null; if (page && Number.isInteger(page) && page > 0) value.hash = `page=${page}`; return value.href; } catch { return null; }
}
export function verifiedEvidence(source: Evidence): boolean {
  return source.validation_state === "validated" && source.validation_audit_current === true && source.source_policy === "official" && !!source.report_sha256 && !!source.supporting_excerpt && !!safeSourceUrl(source.source_url) && !!source.source_page;
}
export function netZero(benchmark?: CompanyBenchmark): {year: number | null; sources: Evidence[]; conflict: boolean} {
  const sources = benchmark?.targets.filter(t => t.metric === "net_zero_target_year") ?? [];
  const years = new Set(sources.filter(verifiedEvidence).map(t => t.target_year).filter((y): y is number => typeof y === "number"));
  return {year: years.size === 1 ? [...years][0] : null, sources, conflict: years.size > 1};
}
export function cohorts(items: CompanyBenchmark[], key: string): {sector: string; metric: Metric}[] {
  const groups = new Map<string, {sector: string; metric: Metric}>();
  for (const company of items) {
    const m = company.metrics[key];
    if (usable(m) && m.cohort_key) groups.set(`${company.sector}:${m.cohort_key}`, {sector: company.sector, metric: m});
  }
  return [...groups.values()].sort((a, b) => a.sector.localeCompare(b.sector) || (a.metric.cohort_key ?? "").localeCompare(b.metric.cohort_key ?? ""));
}

/** Expose every input from the same API snapshot; do not recalculate the server's median. */
export function cohortSource(items: CompanyBenchmark[], sector: string, key: string, metric: Metric): SourceSelection {
  const members = items.filter(c => c.sector === sector && usable(c.metrics[key]) && metric.cohort_key !== null && c.metrics[key].cohort_key === metric.cohort_key);
  return {
    company: `${sector} · comparable cohort`, label: `${metricName(key)} · sector median`,
    explanation: "The API calculates the median of all eligible company values in this cohort (the mean of the two middle values for an even sample). Each company contributes once. Derived company values retain all their supporting observations. A missing median means the peer threshold has not been met.",
    evidence: members.flatMap(c => c.metrics[key].provenance.map(s => ({...s, company_name: c.company_name}))),
    cohort: {median: metric.sector_median, unit: metric.unit, sampleSize: metric.sector_sample_size, dimensions: metric.comparison_dimensions, members: members.map(c => ({company: c.company_name, value: c.metrics[key].value!, unit: c.metrics[key].unit}))},
  };
}
