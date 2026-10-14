export interface LibraryCompany {
  id: string; company_name: string; ticker: string; country: string; region: string;
  sector: string; industry: string; official_domain: string; exchange: string;
  reports_downloaded: number; reports_indexed: number; pages_indexed: number;
  text_gaps: boolean; availability: "searchable" | "downloaded" | "not_collected";
  collection_status: string;
  collection_reason?: string | null;
}
export interface ResearchUsage {
  monthly_accounted_usd:string; monthly_recorded_estimate_usd:string; monthly_reserved_usd:string;
  monthly_remaining_usd:string; daily_tokens_accounted:number; daily_tokens_remaining:number; daily_resets_at:string;
}
export const analysisLimitErrors = new Set(["monthly_budget_exceeded","daily_token_limit_exceeded","trial_budget_exceeded","trial_budget_expired"]);
export interface LibraryStatus {
  companies_in_scope: number; official_reports_downloaded: number; reports_indexed: number;
  companies_with_indexed_reports: number; pages_indexed: number; reports_with_text_gaps: number;
  research: {provider: string; model: string | null; enabled: boolean; configuration_error: string | null; monthly_budget_usd: number; daily_app_token_limit?:number; usage?:ResearchUsage};
}
export interface LibraryReport {
  id: string; company_id: string; company: string; title: string; document_role: string;
  reporting_year: number | null; detected_year: number | null; source_url: string;
  sha256: string; file_url: string; knowledge_status: string; parse_status: string;
  retrieved_at: string | null;
  quality: {pages_total?: number; coverage?: string} | null;
}
export interface ReportLibrary {
  companies: LibraryCompany[];
  status: LibraryStatus;
  reports: LibraryReport[];
}
export async function loadReportLibrary(signal?: AbortSignal): Promise<ReportLibrary> {
  const [directory,status]=await Promise.all([
    knowledge<{items:LibraryCompany[]}>("/knowledge/companies",undefined,signal),
    knowledge<LibraryStatus>("/knowledge/status",undefined,signal),
  ]);
  if(!Array.isArray(directory.items)||!directory.items.every(c=>typeof c.id==="string"&&typeof c.company_name==="string"&&Number.isInteger(c.reports_indexed))||!Number.isInteger(status.companies_in_scope))
    throw new KnowledgeError("invalid_response","The company library response is incomplete. No replacement data has been loaded.");
  const reports:LibraryReport[]=[];
  for(let offset=0;;offset+=100){
    const page=await knowledge<{items:LibraryReport[]}>(`/knowledge/reports?limit=100&offset=${offset}`,undefined,signal);
    if(!Array.isArray(page.items))throw new KnowledgeError("invalid_response");
    reports.push(...page.items);
    if(page.items.length<100)break;
  }
  return {companies:directory.items,status,reports};
}
/** Discovery link labels are not document titles. Display the retained filename instead. */
export function reportTitle(title:string,url:string):string {
  if(!/^(view\b|download\b|pdf\b|click here\b|20\d{2}$)/i.test(title.trim()))return title;
  try {const filename=decodeURIComponent(new URL(url).pathname.split("/").pop()||"");return filename.replace(/\.pdf$/i,"").replace(/[_-]+/g," ")||title;}catch{return title;}
}
export interface Passage {
  evidence_id: string; company_id: string; company: string; report_id: string; report: string;
  page: number; page_url: string; source_url: string; text: string; quote?: string;
  report_sha256: string; reporting_year: number | null; detected_year: number | null;
  kind: string; page_text?: string; tables?: {id: string; cells: (string | null)[][]}[];
}
export interface Scope {company_ids?: string[]; sector?: string | null; country?: string | null; report_year?: number | null; report_ids?: string[]}
export interface Coverage {
  companies_supplied: number; passages_supplied: number; exhaustive: boolean;
  companies: {company_id: string; company: string | null; status: string; matching_passages: number}[];
}
export interface Answer {
  analysis_id?: string; calculation_basis?: string;
  answer_id?: string; question?: string; status: "answered" | "partial" | "needs_clarification" | "insufficient_evidence";
  claims: {text: string; citations: Passage[]}[]; coverage: Coverage;
  model?: string; cached: boolean; model_called: boolean; estimated_cost_usd?: string;
  usage?: {latency_ms: number; total_latency_ms?:number; input_tokens: number; output_tokens: number};
  request_scope?: Scope; parent_answer_id?: string | null; limitation?: string;
  notes?: string[]; follow_up_question?: string | null;
  calculations?: {label:string;value:number;source:string}[];
  research_plan?: {intent:string;queries:string[];company_names:string[];comparison_basis:string|null};
  validation?: {withheld_statements:number;reasons:string[]};
}
export interface SavedAnswer {answer_id: string; question: string; status: string; sources_current: boolean; result: Answer}
export interface HistoryItem {answer_id: string; question: string; created_at: string; model: string; request_scope: Scope}
const messages: Record<string, string> = {
  briefing_busy: "This analysis is already running. Its progress is saved; refresh to see the current stage.",
  briefing_sources_changed: "A source changed after this analysis was created. Start a new analysis; the historical result is preserved.",
  briefing_no_searchable_reports: "No selected company has a searchable report yet. Choose companies with reports or inspect their source availability.",
  briefing_company_unavailable: "One of the selected companies is no longer in the active library.",
  briefing_report_unavailable: "One of the chosen reports is not searchable for these companies. Check the selected sources.",
  briefing_processing_failed: "This topic could not finish. Completed topics are saved. Retry the unfinished topic when ready.",
  openai_billing_not_active: "OpenAI API billing is not active for this key’s project. Activate it in your OpenAI account, then retry. Your question is saved here.",
  openai_quota_exhausted: "The OpenAI project has no available API quota. Check its credits and spending limits, then retry.",
  openai_rate_limit: "OpenAI is temporarily rate-limiting requests. Please wait, then retry.",
  openai_timeout: "OpenAI did not finish within the time limit. Your question is retained. A retry may incur another charge.",
  openai_authentication: "OpenAI rejected the API key. Update backend/.env and restart the backend.",
  openai_access_denied: "This OpenAI project does not have access to the selected model.",
  monthly_budget_exceeded: "Analysis paused: Vero’s local monthly allowance cannot cover the next AI step. This is an app limit, not an OpenAI error. Completed work is saved; resume after the allowance is updated.",
  trial_budget_exceeded: "This analysis has reached its agreed AI test budget. Your calculated results and completed findings are saved.",
  trial_budget_expired: "The approved test budget has expired. Your saved results are still available.",
  daily_token_limit_exceeded: "Vero’s conservative daily token limit has been reached. Saved results and source search still work. The daily window resets in UTC.",
  openai_model_not_allowed: "This model is blocked by Vero’s explicit model allowlist. No AI call was made.",
  report_not_ready_for_extraction: "This report needs a successful page-aware parse before figures can be extracted.",
  unsupported_extraction_metric: "This metric is not supported by the reported-figure extractor.",
  research_busy_or_interrupted: "Another analysis is running. Try again when it finishes. An interrupted job may need operator recovery.",
  unsupported_citation: "The answer failed its source check and was withheld. Try a narrower question or inspect the matching passages.",
  unsupported_number: "A number could not be matched to its cited excerpt. The answer was withheld; no replacement figures were invented.",
  population_question_requires_company_by_company_assessment: "This question needs a company-by-company assessment. Select specific peers and ask about their reported disclosures instead.",
  population_claim_requires_assessment: "The model generalised beyond the supplied evidence. Its answer was withheld. Try a narrower peer group.",
  conversation_scope_changed: "The selected companies changed. Start a new conversation for this peer group.",
  conversation_not_found: "That earlier answer is unavailable. Start a new conversation.",
  hosted_ai_disabled: "AI research is disabled in the backend configuration. Source search is still available.",
  openai_key_missing: "Add your OpenAI key to backend/.env and restart the backend. Do not enter it in this interface.",
};
export class KnowledgeError extends Error {
  constructor(public code: string, message?: string) {super(message || messages[code] || "Vero could not complete this request. Your sources and saved research are unchanged.");}
}
const base = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/+$/, "");
export async function knowledge<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, {once: true});
  if (signal?.aborted) abort();
  const timer = setTimeout(abort, path === "/knowledge/ask" || path.endsWith("/advance") || path.endsWith("/explain") || path.endsWith("/extract-metric") ? 205000 : 30000);
  try {
    const response = await fetch(`${base}${path}`, {method: body === undefined ? "GET" : "POST", headers: {Accept:"application/json", ...(body === undefined ? {} : {"Content-Type":"application/json"})}, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal});
    let data: unknown;
    try {data = await response.json();} catch {throw new KnowledgeError("invalid_response", "The API returned an unreadable response. Check that the backend is running.");}
    if (!response.ok) {
      const detail = (data as {detail?: {code?: string} | string})?.detail;
      throw new KnowledgeError(typeof detail === "object" && detail?.code ? detail.code : "request_failed", response.status === 404 ? "This record is no longer available." : undefined);
    }
    return data as T;
  } catch (error) {
    if (error instanceof KnowledgeError) throw error;
    if (controller.signal.aborted) throw new KnowledgeError("request_timeout", "The request was interrupted or timed out. Any submitted analysis may still finish; check saved research before retrying.");
    throw new KnowledgeError("network_error", "Vero cannot reach the backend. Check the connection and retry.");
  } finally {clearTimeout(timer); signal?.removeEventListener("abort", abort);}
}
export function safeUrl(value: string): string | undefined {
  try {const u = new URL(value, window.location.origin); return ["https:","http:"].includes(u.protocol) ? u.href : undefined;} catch {return undefined;}
}
export function exportAnswer(question: string, answer: Answer) {
  const esc = (v: string) => v.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]!));
  const html = `<!doctype html><html lang="en"><meta charset="utf-8"><title>Vero research briefing</title><style>body{font:16px/1.7 system-ui;max-width:820px;margin:70px auto;padding:24px;color:#17221b}h1{font-size:32px;line-height:1.2}article{padding:22px 0;border-bottom:1px solid #ddd}small,footer{color:#56665b}blockquote{border-left:3px solid #218653;padding-left:18px}a{color:#17683c}@media print{body{margin:0}article{break-inside:avoid}}</style><header><b>Vero / Research briefing</b><h1>${esc(question)}</h1><p>${esc(answer.model || "")} · AI-generated, citations mechanically checked · Not an ESG rating</p></header>${(answer.notes??[]).map(n=>`<p>${esc(n)}</p>`).join("")}${(answer.calculations??[]).map(c=>`<p><b>${c.value}</b> ${esc(c.label)} · database count</p>`).join("")}${answer.claims.map(c=>`<article><p>${esc(c.text)}</p>${c.citations.map(s=>`<small>${esc(s.company)} · ${esc(s.report)} · physical PDF page ${s.page}</small><blockquote>${esc(s.quote || s.text)}</blockquote><a href="${esc(safeUrl(s.source_url)||"#")}">Official source</a><br><small>Document SHA-256: ${esc(s.report_sha256)}</small>`).join("")}</article>`).join("")}<footer><p>${esc(answer.limitation || "Selected passages only, not an exhaustive assessment.")}</p><p>Companies with supplied evidence: ${answer.coverage.companies_supplied}. Missing evidence is not zero or proof of non-disclosure.</p></footer></html>`;
  const url = URL.createObjectURL(new Blob([html], {type:"text/html"}));
  const a = document.createElement("a"); a.href=url; a.download="vero-research-briefing.html"; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
