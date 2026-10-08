import { request } from "./api";
import { evidence as validEvidence, type BenchmarkPage, type CompanyBenchmark, type Evidence, type SourceSelection } from "./benchmarks";

export type GapContext = Pick<BenchmarkPage, "year" | "minimum_peers" | "scope2_method" | "peer_group" | "input_sha256">;
export interface GapFactor {
  metric: string; label: string; kind: string; company_value: string | null; unit: string | null;
  sector_median: string | null; percentile: string | null; difference: string | null; difference_unit: string | null;
  value_relation: string | null; preferred_direction: string | null; effect: string; status: string; reason: string | null;
  score_weight: string; component_score: string | null; weighted_points: string | null;
  peer_sample_size: number; cohort_key: string | null; peer_rate: string | null; peer_rate_kind: string | null;
  completeness: Record<string, number | string | boolean | null>;
  peer_members: {company_id: string; company_name: string; value: string; state?: string}[];
  provenance: Evidence[]; peer_provenance: Evidence[]; company_state?: string; common_gap?: boolean;
}
export interface PeerExplanation {
  version: string; title: string; company_id: string; company_name: string; sector: string; year: number;
  input_sha256: string; explanation_sha256: string; methodology_version: string; label: string;
  minimum_peers: number; peer_group: string; score: CompanyBenchmark["score"]; common_threshold_percent: string;
  factors: GapFactor[]; disclosure_opportunities: GapFactor[]; notice: string;
}
const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const nullableString = (v: unknown) => v === null || typeof v === "string";
const decimal = (v: unknown) => v === null || typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v) && Number.isFinite(Number(v));
const count = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0;
function factor(v: unknown): v is GapFactor {
  return object(v) && [v.metric, v.label, v.kind, v.effect, v.status, v.score_weight].every(s => typeof s === "string") &&
    [v.company_value, v.unit, v.reason, v.difference_unit, v.value_relation, v.preferred_direction, v.cohort_key, v.peer_rate_kind].every(nullableString) &&
    [v.sector_median, v.percentile, v.difference, v.peer_rate, v.component_score, v.weighted_points, v.score_weight].every(decimal) &&
    [v.percentile, v.peer_rate].every(n => n === null || Number(n) >= 0 && Number(n) <= 100) &&
    ["comparable", "missing_metric", "not_comparable", "insufficient_peers", "available"].includes(String(v.status)) &&
    count(v.peer_sample_size) && object(v.completeness) && Object.values(v.completeness).every(n => n === null || ["string", "boolean"].includes(typeof n) || typeof n === "number" && Number.isFinite(n)) &&
    Array.isArray(v.provenance) && v.provenance.every(validEvidence) && Array.isArray(v.peer_provenance) && v.peer_provenance.every(validEvidence) &&
    Array.isArray(v.peer_members) && v.peer_members.every(m => object(m) && [m.company_id, m.company_name, m.value].every(s => typeof s === "string")) &&
    (v.common_gap === undefined || typeof v.common_gap === "boolean") && (v.company_state === undefined || ["reported", "not_reported", "unknown"].includes(String(v.company_state)));
}
export function isPeerExplanation(v: unknown): v is PeerExplanation {
  return object(v) && [v.title, v.company_id, v.company_name, v.sector, v.input_sha256, v.explanation_sha256, v.methodology_version, v.label, v.notice].every(s => typeof s === "string") &&
    v.version === "peer-gap-v1" && v.peer_group === "sector" && count(v.year) && count(v.minimum_peers) && v.minimum_peers >= 5 &&
    object(v.score) && typeof v.score.ranking_eligible === "boolean" && decimal(v.score.value) && decimal(v.score.coverage_percent) &&
    decimal(v.common_threshold_percent) && Array.isArray(v.factors) && v.factors.every(factor) && Array.isArray(v.disclosure_opportunities) && v.disclosure_opportunities.every(factor);
}
export function explanationPath(id: string, context: GapContext, exportFormat?: "json" | "csv") {
  const params = new URLSearchParams({year: String(context.year), min_peers: String(context.minimum_peers), scope2_method: context.scope2_method, peer_group: context.peer_group, expected_input_sha256: context.input_sha256});
  if (exportFormat) params.set("format", exportFormat);
  return `/companies/${encodeURIComponent(id)}/peer-explanation${exportFormat ? "/export" : ""}?${params}`;
}
export async function getPeerExplanation(id: string, context: GapContext, signal?: AbortSignal) {
  const {status, body} = await request(explanationPath(id, context), signal);
  if (status === 409) throw new Error("Benchmark evidence changed. Refresh this page to use one consistent snapshot.");
  if (status !== 200 || !isPeerExplanation(body) || body.company_id !== id || body.year !== context.year || body.input_sha256 !== context.input_sha256) throw new Error("Peer explanations are unavailable or could not be verified. No comparison has been invented.");
  return body;
}
export function gapSource(explanation: PeerExplanation, row: GapFactor): SourceSelection {
  return {company: explanation.company_name, label: row.label, evidence: [...row.provenance, ...row.peer_provenance],
    explanation: `Structured benchmark output ${explanation.version}. Status: ${row.status.replaceAll("_", " ")}. ${row.peer_rate_kind === "verified_reporting_coverage" ? "Coverage is verified reporting divided by all other active sector companies, including unknowns in the denominator; it is a lower bound." : row.peer_rate_kind === "affirmative_prevalence" ? "Prevalence is yes divided by assessed comparable peers, excluding this company and unknowns." : "Numeric statistics use like-for-like sector peers including this company. Percentile is ascending, not direction-adjusted."} Input fingerprint: ${explanation.input_sha256}.`,
    ...(row.sector_median !== null ? {cohort: {median: row.sector_median, unit: row.unit, sampleSize: row.peer_sample_size, dimensions: {cohort_key: row.cohort_key, reporting_year: explanation.year}, members: row.peer_members.map(p => ({company: p.company_name, value: p.value, unit: row.unit}))}} : {})};
}
export async function downloadExplanation(data: PeerExplanation, context: GapContext, format: "json" | "csv", signal?: AbortSignal) {
  const controller = new AbortController(), abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener("abort", abort, {once: true});
  const timeout = setTimeout(abort, 15000);
  try {
    const base = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/+$/, "");
    const response = await fetch(base + explanationPath(data.company_id, context, format), {signal: controller.signal});
    if (response.status === 409) throw new Error("Evidence changed. Refresh before exporting.");
    if (!response.ok || response.headers.get("X-Explanation-SHA256") !== data.explanation_sha256) throw new Error("Export could not be matched to the displayed explanation.");
    const blob = await response.blob();
    if (controller.signal.aborted) return;
    const url = URL.createObjectURL(blob), anchor = document.createElement("a");
    anchor.href = url; anchor.download = `peer-gap-${data.company_id}-${data.year}.${format}`;
    document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } finally {clearTimeout(timeout); signal?.removeEventListener("abort", abort);}
}
