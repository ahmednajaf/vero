import { useState } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PeerGapExplanation } from "../components/PeerGapExplanation";
import { SourceDrawer } from "../components/SourceDrawer";
import { type SourceSelection } from "../lib/benchmarks";
import { getPeerExplanation, isPeerExplanation, type GapContext, type GapFactor, type PeerExplanation } from "../lib/peer-gaps";
import { companies, fixtureBenchmarks, response, source } from "./benchmarkFixtures";

const context: GapContext = {year: 2025, input_sha256: "a".repeat(64), minimum_peers: 5, scope2_method: "location_based", peer_group: "sector"};
function row(changes: Partial<GapFactor> = {}): GapFactor {
  return {metric: "derived_yoy_emissions_change", label: "Emissions trajectory", kind: "score_component", company_value: "-4", unit: "%", sector_median: "-9", percentile: "100", difference: "5", difference_unit: "percentage_points", value_relation: "above", preferred_direction: "lower", effect: "below_peer_median", status: "comparable", reason: null, score_weight: "0.45", component_score: "60", weighted_points: "33.75", peer_sample_size: 6, cohort_key: "fixture-cohort", peer_rate: null, peer_rate_kind: null,
    completeness: {company_complete: true, comparable_companies: 6, sector_companies: 7}, peer_members: [{company_id: companies[0].id, company_name: companies[0].company_name, value: "-4"}], provenance: [source()], peer_provenance: [source(1)], ...changes};
}
function example(): PeerExplanation {
  return {version: "peer-gap-v1", title: "Why this position?", company_id: companies[0].id, company_name: companies[0].company_name, sector: "Technology", year: 2025, input_sha256: context.input_sha256, explanation_sha256: "b".repeat(64), methodology_version: "benchmark-v1", label: "Prototype benchmark score — not an external ESG rating.", minimum_peers: 5, peer_group: "sector", score: fixtureBenchmarks().items[0].score, common_threshold_percent: "50", notice: "Fictional structured test data, not real sustainability findings.", factors: [row(), row({metric: "renewable_electricity_percent", label: "Renewable electricity", kind: "context_metric", company_value: "72", sector_median: "64", percentile: "80", difference: "8", score_weight: "0", preferred_direction: "higher", effect: "above_peer_median", weighted_points: null})],
    disclosure_opportunities: [row({metric: "water_consumption", label: "Water consumption", kind: "disclosure_coverage", company_value: null, company_state: "unknown", sector_median: null, percentile: null, difference: null, peer_rate: "70", peer_rate_kind: "verified_reporting_coverage", common_gap: true, status: "available", effect: "review_gap", completeness: {company_complete: false, peer_companies: 10, reported_peers: 7, assessed_peers: 7, unknown_peers: 3, denominator: 10}})]};
}
function Harness() {
  const [selected, setSelected] = useState<SourceSelection | null>(null);
  return <><PeerGapExplanation companyId={companies[0].id} context={context} openSource={setSelected}/>{selected && <SourceDrawer selection={selected} onClose={() => setSelected(null)}/>}</>;
}
beforeEach(() => {vi.stubGlobal("fetch", vi.fn(async () => response(example())));});

describe("structured peer explanations", () => {
  it("shows direction-aware effects separately from signed differences and ascending percentiles", async () => {
    render(<Harness/>);
    expect(await screen.findByText("Below peer median performance")).toBeInTheDocument();
    expect(screen.getByText("Above peer median performance")).toBeInTheDocument();
    expect(screen.getByText("Company − median: +5 percentage points")).toBeInTheDocument();
    expect(screen.getByText("Company − median: +8 percentage points")).toBeInTheDocument();
    expect(screen.getByText("Percentile 100 / 100")).toBeInTheDocument();
    expect(screen.getByText(/No eligible overall rank is available/)).toBeInTheDocument();
    expect(screen.getByText("Context only · 0% score weight")).toBeInTheDocument();
  });
  it.each([['missing_metric', 'missing_evidence', 'Missing reviewed evidence'], ['not_comparable', 'not_comparable', 'Not comparable'], ['insufficient_peers', 'insufficient_peers', 'Insufficient comparable peers']])("explains %s without inventing comparisons", async (status, effect, label) => {
    const data = example(); data.factors = [row({status, effect, company_value: null, sector_median: null, percentile: null, difference: null, reason: status, completeness: {company_complete: false}})];
    vi.stubGlobal("fetch", vi.fn(async () => response(data))); render(<Harness/>);
    expect(await screen.findByText(label, {selector: "strong"})).toBeInTheDocument();
    expect(screen.queryByText(/Company − median:/)).not.toBeInTheDocument();
    expect(screen.getByText("Assessment incomplete")).toBeInTheDocument();
  });
  it("separates common review priorities from confirmed nondisclosure", async () => {
    render(<Harness/>);
    expect(await screen.findByText("Not yet established for this company")).toBeInTheDocument();
    expect(screen.getByText(/No confirmed common disclosure gaps/)).toBeInTheDocument();
    expect(screen.getByText("70% verified peer coverage · 7/10")).toBeInTheDocument();
  });
  it("opens company and peer provenance in the source drawer", async () => {
    const user = userEvent.setup(); render(<Harness/>);
    await user.click(await screen.findByRole("button", {name: "View peer-gap evidence: Emissions trajectory"}));
    const drawer = screen.getByRole("dialog", {name: "Source evidence"});
    expect(within(drawer).getByText("Fictional 2025 sustainability report")).toBeInTheDocument();
    for (const label of ["Raw value", "Normalised value", "Validation status", "Reporting year", "Page"]) expect(within(drawer).getByText(label)).toBeInTheDocument();
    expect(within(drawer).getByRole("combobox", {name: "Supporting observation"})).toBeInTheDocument();
    await user.keyboard("{Escape}"); expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("rejects stale snapshots, invalid rates and malformed evidence", async () => {
    const data = example(); data.input_sha256 = "wrong";
    vi.stubGlobal("fetch", vi.fn(async () => response(data)));
    await expect(getPeerExplanation(companies[0].id, context)).rejects.toThrow(/could not be verified/);
    const bad = example(); bad.factors[0].percentile = "101"; expect(isPeerExplanation(bad)).toBe(false);
    bad.factors[0].percentile = "10"; (bad.factors[0].provenance[0] as unknown as {source_url: number}).source_url = 9;
    expect(isPeerExplanation(bad)).toBe(false);
  });
  it("reports changed-evidence conflicts and does not export stale data", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({detail: "changed"}, 409)));
    render(<Harness/>); expect(await screen.findByRole("alert")).toHaveTextContent("Benchmark evidence changed");
    expect(screen.getByRole("button", {name: "Export CSV"})).toBeDisabled();
  });
  it.each(["CSV", "JSON"])("exports %s only when the calculation fingerprint matches", async format => {
    const data = example(), create = vi.fn(() => "blob:fixture");
    vi.stubGlobal("fetch", vi.fn(async input => String(input).includes("/export?") ? new Response(format === "JSON" ? JSON.stringify(data) : "metric,value\nfictional,72", {headers: {"X-Explanation-SHA256": data.explanation_sha256}}) : response(data)));
    vi.stubGlobal("URL", Object.assign(URL, {createObjectURL: create, revokeObjectURL: vi.fn()}));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const user = userEvent.setup(); render(<Harness/>); await screen.findByText("Below peer median performance");
    await user.click(screen.getByRole("button", {name: `Export ${format}`}));
    await waitFor(() => expect(create).toHaveBeenCalledOnce()); expect(click).toHaveBeenCalledOnce();
    expect(vi.mocked(fetch).mock.calls.at(-1)?.[0]).toContain(`format=${format.toLowerCase()}`);
    expect(vi.mocked(fetch).mock.calls.at(-1)?.[0]).toContain(`expected_input_sha256=${context.input_sha256}`);
  });
  it("never downloads an export from a different calculation", async () => {
    const create = vi.fn(); vi.stubGlobal("URL", Object.assign(URL, {createObjectURL: create, revokeObjectURL: vi.fn()}));
    vi.stubGlobal("fetch", vi.fn(async input => String(input).includes("/export?") ? new Response("wrong", {headers: {"X-Explanation-SHA256": "wrong"}}) : response(example())));
    const user = userEvent.setup(); render(<Harness/>); await screen.findByText("Below peer median performance");
    await user.click(screen.getByRole("button", {name: "Export JSON"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be matched");
    expect(create).not.toHaveBeenCalled();
  });
});
