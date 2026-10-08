import { request } from "./api";
import { evidence, type Evidence } from "./benchmarks";

export interface LibraryCompany {
  company_id: string; company_name: string; reports_downloaded: number;
  observations: number; observation_states: Record<string, number>;
}
export interface Library {
  companies_total: number; pilot_companies: number; reports_downloaded: number;
  observations_total: number; observation_states: Record<string, number>; items: LibraryCompany[];
}
export interface StoredReport {
  primary_source_exclusion?: "specialised_financing_disclosure" | null;
  detected_year?: number | null; requested_year?: number | null;
  id: string; title: string; reporting_year: number | null; source_url: string;
  sha256: string | null; pages: number | null; parse_status: string;
  source_policy: string | null; local_url: string;
}
export interface CompanyEvidence {
  company_id: string; observations: Evidence[]; reports: StoredReport[];
}
const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
const count = (v: unknown): v is number => Number.isInteger(v) && Number(v) >= 0;
const states = (v: unknown) => object(v) && Object.values(v).every(count);
export async function getLibrary(signal?: AbortSignal): Promise<Library> {
  const {status, body} = await request("/library", signal);
  if (status !== 200 || !object(body) || ![body.companies_total, body.pilot_companies, body.reports_downloaded, body.observations_total].every(count) || !states(body.observation_states) || !Array.isArray(body.items) || !body.items.every(v => object(v) && typeof v.company_id === "string" && typeof v.company_name === "string" && count(v.reports_downloaded) && count(v.observations) && states(v.observation_states))) throw new Error("Report coverage is unavailable.");
  return body as unknown as Library;
}
export async function getCompanyEvidence(id: string, signal?: AbortSignal): Promise<CompanyEvidence> {
  const {status, body} = await request(`/companies/${encodeURIComponent(id)}/evidence`, signal);
  if (status !== 200 || !object(body) || body.company_id !== id || !Array.isArray(body.observations) || !body.observations.every(evidence) || !Array.isArray(body.reports) || !body.reports.every(r => object(r) && [r.id, r.title, r.source_url, r.parse_status, r.local_url].every(v => typeof v === "string") && (r.reporting_year === null || count(r.reporting_year)) && (r.pages === null || count(r.pages)))) throw new Error("Source library unavailable. Please retry.");
  return body as unknown as CompanyEvidence;
}
/** Only our UUID-addressed, checksum-verified endpoint; never arbitrary URLs. */
export function localReportUrl(value?: string | null, page?: number): string | null {
  if (!value || !/^\/api\/(?:reports\/[0-9a-f-]{36}|benchmarks\/sessions\/[0-9a-f-]{36}\/documents\/[0-9a-f-]{36})\/file$/.test(value)) return null;
  const api = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/+$/, "");
  return api + value.slice(4) + (page && Number.isInteger(page) && page > 0 ? `#page=${page}&view=FitH` : "");
}
