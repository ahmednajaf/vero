import {render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {beforeEach, expect, it, vi} from "vitest";
import {MetricFigures} from "../components/MetricFigures";
import {NavigationProvider} from "../lib/navigation";
import type {ReportLibrary} from "../lib/knowledge";

const companies = [0, 1].map(i => ({id: `c${i}`, company_name: `Test ${i}`, ticker: `T${i}`, country: "GB", region: "Europe", sector: "Technology", industry: "Test", official_domain: "example.com", exchange: "TEST", reports_downloaded: 1, reports_indexed: 1, pages_indexed: 20, text_gaps: false, availability: "searchable" as const, collection_status: "succeeded"}));
const reports = companies.map((c, i) => ({id: `r${i}`, company_id: c.id, company: c.company_name, title: `Annual report ${i}`, document_role: "primary_report", reporting_year: 2025, detected_year: 2025, source_url: `https://example.com/${i}.pdf`, sha256: `hash${i}`, file_url: `/api/reports/r${i}/file`, knowledge_status: "indexed", parse_status: "parsed", retrieved_at: null, quality: null}));
const library: ReportLibrary = {companies, reports, status: {companies_in_scope: 2, official_reports_downloaded: 2, reports_indexed: 2, companies_with_indexed_reports: 2, pages_indexed: 40, reports_with_text_gaps: 0, research: {provider: "openai", model: "test-mini", enabled: true, configuration_error: null, monthly_budget_usd: 5}}};
const observation = {id: "o1", metric: "scope_1_emissions", report_id: "r0", report_sha256: "hash0", reporting_year: 2024, raw_value: "0", raw_unit: "tCO2e", normalised_value: "0", normalised_unit: "tCO2e", source_page: 2, supporting_excerpt: "Scope 1 2024: 0 tCO2e", source_url: "https://example.com/0.pdf", validation_state: "needs_review"};
const response = (body: unknown, status = 200) => ({ok: status < 400, status, json: async () => body} as Response);
let extractionReply: Response;
beforeEach(() => {
  extractionReply = response({status: "unchanged", observations: 1, warnings: []});
  vi.stubGlobal("fetch", vi.fn(async (url: string, opts?: RequestInit) => {
    if (opts?.method === "POST") return extractionReply;
    const id = url.includes("c0") ? "c0" : "c1";
    return response({company_id: id, observations: id === "c0" ? [observation, {...observation, id: "older"}] : [], reports: [{...reports[0], pages: 20, local_url: reports[0].file_url}, {...reports[0], id: "duplicate", pages: 20, local_url: reports[0].file_url}]});
  }));
});
const postCalls = () => vi.mocked(fetch).mock.calls.filter(([, opts]) => opts?.method === "POST");
function View({ids = ["c0", "c1"]}: {ids?: string[]}) {return <NavigationProvider><MetricFigures library={library} ids={ids} openSource={vi.fn()}/></NavigationProvider>;}
async function openExtraction() {
  const user = userEvent.setup();
  await user.click(screen.getByText("Extract figures from selected reports"));
  await user.type(screen.getByRole("spinbutton", {name: "Measurement year"}), "2024");
  return user;
}
it("makes no model call on mount, deduplicates identical evidence and preserves zero", async () => {
  render(<View/>);
  const table = await screen.findByRole("table");
  expect(within(table).getAllByText("0")).toHaveLength(1);
  expect(within(table).getAllByText("1")).toHaveLength(2);
  expect(postCalls()).toHaveLength(0);
});
it("requires a year, sends one explicit call per selected report and shows cached results", async () => {
  render(<View/>);
  expect(screen.getByRole("button", {name: "Extract selected metric", hidden: true})).toBeDisabled();
  const user = await openExtraction();
  await user.click(screen.getByRole("button", {name: "Extract selected metric"}));
  await screen.findByText("Test 1: 1 source-linked figure (saved result).");
  expect(postCalls()).toHaveLength(2);
  expect(JSON.parse(String(postCalls()[0][1]?.body))).toEqual({metric: "scope_1_emissions", observation_year: 2024});
});
it("stops on provider failure without retrying or moving to another company", async () => {
  extractionReply = response({detail: {code: "daily_token_limit_exceeded"}}, 409);
  render(<View/>); const user = await openExtraction();
  await user.click(screen.getByRole("button", {name: "Extract selected metric"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("daily token limit");
  expect(postCalls()).toHaveLength(1);
});
it("does not call missing values confirmed non-disclosure", async () => {
  extractionReply = response({status: "completed", observations: 0, warnings: []});
  render(<View ids={["c0"]}/>); const user = await openExtraction();
  await user.click(screen.getByRole("button", {name: "Extract selected metric"}));
  expect(await screen.findByText(/does not establish non-disclosure/)).toBeInTheDocument();
});
it("does not continue an old company group after the selection changes", async () => {
  let release!: (value: Response) => void;
  vi.mocked(fetch).mockImplementationOnce(async () => response({company_id: "c0", observations: [], reports: []}));
  const {rerender} = render(<View/>); await screen.findByRole("table");
  const original = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation((...args) => args[1]?.method === "POST" ? new Promise(resolve => {release = resolve;}) : original(...args));
  const user = await openExtraction(); await user.click(screen.getByRole("button", {name: "Extract selected metric"}));
  await waitFor(() => expect(postCalls()).toHaveLength(1));
  rerender(<View ids={["c1"]}/>); release(extractionReply);
  await waitFor(() => expect(screen.queryByText(/source-linked figure/)).not.toBeInTheDocument());
  expect(postCalls()).toHaveLength(1);
});
