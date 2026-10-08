export interface HealthResponse {
  status: "ok";
  service: "sustainability-benchmarking-api";
  version: string;
  reporting_year: number;
}

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  database: "reachable" | "unavailable";
  detail: string;
}

const baseUrl = (import.meta.env.VITE_API_BASE_URL || "/api").replace(
  /\/+$/,
  "",
);
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

export async function request(
  path: string,
  signal?: AbortSignal,
): Promise<{ status: number; body: unknown }> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  const timeout = setTimeout(abort, 6000);
  if (signal?.aborted) abort();
  signal?.addEventListener("abort", abort, { once: true });
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    let body: unknown;
    try { body = await response.json(); }
    catch (cause) {
      if (controller.signal.aborted) throw cause;
      throw new Error("The data service returned an unreadable response. Check that the API and database are running.");
    }
    return { status: response.status, body };
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const { status, body } = await request("/health", signal);
  if (
    status !== 200 ||
    !record(body) ||
    body.status !== "ok" ||
    body.service !== "sustainability-benchmarking-api" ||
    typeof body.version !== "string" ||
    typeof body.reporting_year !== "number" ||
    !Number.isInteger(body.reporting_year) ||
    body.reporting_year < 2000 ||
    body.reporting_year > 2100
  ) {
    throw new Error("The API did not return a valid health response.");
  }
  return body as unknown as HealthResponse;
}

export async function getReadiness(
  signal?: AbortSignal,
): Promise<ReadinessResponse> {
  const { status, body } = await request("/health/ready", signal);
  if (
    !record(body) ||
    typeof body.detail !== "string" ||
    !(
      (status === 200 &&
        body.status === "ready" &&
        body.database === "reachable") ||
      (status === 503 &&
        body.status === "not_ready" &&
        body.database === "unavailable")
    )
  ) {
    throw new Error("The API did not return a valid readiness response.");
  }
  return body as unknown as ReadinessResponse;
}

export const reportStates = ["discovered", "downloaded", "needs_review", "unavailable", "failed"] as const;
export type ReportState = (typeof reportStates)[number];
export interface ReportCandidate {
  id: string;
  url: string;
  title: string;
  discovered_from: string | null;
  detected_year: number | null;
  mime_type: string | null;
  file_size: number | null;
  sha256: string | null;
  confidence: number | null;
  selection_reason: string | null;
  retrieved_at: string | null;
  status: ReportState;
  is_selected: boolean;
  source_policy: string | null;
}
export interface ReportRun {
  run_id: string;
  company_name: string;
  requested_year: number;
  status: ReportState;
  selection_reason: string;
  finished_at: string;
  pages_visited: number;
  http_requests: number;
  selected_report: ReportCandidate | null;
  candidates: ReportCandidate[];
  diagnostics: { code: string; message: string; url?: string }[];
}
export interface ReportStatusPage {
  year: number;
  companies_processed: number;
  counts: Record<ReportState, number>;
  items: ReportRun[];
  page: number;
  total_pages: number;
  total: number;
}
const isReportState = (value: unknown): value is ReportState => reportStates.some(state => state === value);
const nullableString = (value: unknown) => value === null || typeof value === "string";
const nullableNumber = (value: unknown) => value === null || (typeof value === "number" && Number.isFinite(value));
function isCandidate(value: unknown): value is ReportCandidate {
  return record(value) && typeof value.id === "string" && typeof value.title === "string" &&
    typeof value.url === "string" && isReportState(value.status) && typeof value.is_selected === "boolean" &&
    [value.discovered_from, value.mime_type, value.sha256, value.selection_reason, value.retrieved_at, value.source_policy].every(nullableString) &&
    [value.detected_year, value.file_size, value.confidence].every(nullableNumber);
}
function isRun(value: unknown): value is ReportRun {
  return record(value) && typeof value.run_id === "string" && typeof value.company_name === "string" &&
    typeof value.requested_year === "number" && isReportState(value.status) && typeof value.selection_reason === "string" &&
    typeof value.finished_at === "string" && typeof value.pages_visited === "number" && typeof value.http_requests === "number" &&
    (value.selected_report === null || isCandidate(value.selected_report)) &&
    Array.isArray(value.candidates) && value.candidates.every(isCandidate) &&
    Array.isArray(value.diagnostics) && value.diagnostics.every(item => record(item) && typeof item.code === "string" && typeof item.message === "string");
}
export async function getReportStatus(year: number, page: number, signal?: AbortSignal): Promise<ReportStatusPage> {
  const { status, body } = await request(`/admin/report-status?year=${year}&page=${page}&page_size=20`, signal);
  if (status !== 200 || !record(body) || !record(body.counts) ||
    ![body.year, body.companies_processed, body.page, body.total_pages, body.total].every(value => typeof value === "number" && Number.isInteger(value) && value >= 0) ||
    !reportStates.every(state => typeof (body.counts as Record<string, unknown>)[state] === "number") ||
    !Array.isArray(body.items) || !body.items.every(isRun)) {
    throw new Error("Report status is unavailable. Check the API connection and database migrations.");
  }
  return body as unknown as ReportStatusPage;
}
