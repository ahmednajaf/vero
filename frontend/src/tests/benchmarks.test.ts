import { describe, expect, it, vi } from "vitest";
import { comparable, format, getWorkspace, safeSourceUrl, usable, verifiedEvidence } from "../lib/benchmarks";
import { companies, fixtureBenchmarks, makeMetric, mockWorkspaceFetch, response, source } from "./benchmarkFixtures";

describe("benchmark data contract", () => {
  it("preserves zero and does not convert null or unreviewed values to measurements", () => {
    expect(usable(makeMetric("scope_1_emissions", 0))).toBe(true);
    expect(format("0.000000")).toBe("0"); expect(format(null)).toBe("—");
    expect(usable(makeMetric("scope_1_emissions", 4, 0, {eligibility_reason: "comparability_not_reviewed"}))).toBe(false);
    expect(comparable(makeMetric("scope_1_emissions", 4, 0, {peer_sample_size: 4}))).toBe(false);
    expect(comparable(makeMetric("scope_1_emissions", 4, 0, {percentile: "0"}))).toBe(true);
  });
  it("uses only safe source links and keeps validated targets dependent on current audits", () => {
    expect(safeSourceUrl("javascript:alert(1)")).toBeNull(); expect(safeSourceUrl("https://user:password@example.com/a")).toBeNull(); expect(safeSourceUrl("/not-an-absolute-source")).toBeNull();
    expect(safeSourceUrl("https://example.com/report.pdf", 2)).toBe("https://example.com/report.pdf#page=2");
    expect(verifiedEvidence(source())).toBe(true); expect(verifiedEvidence({...source(), validation_audit_current: false})).toBe(false);
  });
  it("loads the complete dataset with an explicit reporting year", async () => {
    const fetcher = vi.fn(mockWorkspaceFetch()); vi.stubGlobal("fetch", fetcher);
    const data = await getWorkspace(2025); expect(data.companies).toHaveLength(7); expect(data.benchmarks.year).toBe(2025);
    expect(fetcher.mock.calls.some(([url]) => String(url).includes("year=2025"))).toBe(true);
  });
  it("rejects malformed metrics rather than passing untrusted shapes into views", async () => {
    vi.stubGlobal("fetch", vi.fn(mockWorkspaceFetch({mutate: data => {data.items[0].metrics.scope_1_emissions.value = "NaN";}})));
    const data = await getWorkspace(2025); expect(data.benchmarkError).toContain("could not be verified"); expect(data.benchmarks.items).toEqual([]); expect(data.companies).toHaveLength(7);
  });
  it("rejects malformed optional overall ranking outputs", async () => {
    vi.stubGlobal("fetch", vi.fn(mockWorkspaceFetch({mutate: data => {data.items[0].score.ranking = {rank: 8, percentile: "110", peer_sample_size: 6, cohort_key: "invalid", reason: null};}})));
    const data = await getWorkspace(2025); expect(data.benchmarkError).toContain("could not be verified"); expect(data.benchmarks.items).toEqual([]); expect(data.companies).toHaveLength(7);
  });
  it("rejects partial or mismatched company universes", async () => {
    vi.stubGlobal("fetch", vi.fn(mockWorkspaceFetch({mutate: data => {data.items.pop(); data.total -= 1;}})));
    const data = await getWorkspace(2025); expect(data.benchmarkError).toContain("roster changed"); expect(data.benchmarks.items).toEqual([]); expect(data.companies).toHaveLength(7);
  });
  it("loads all pages and refuses changing benchmark snapshots across pages", async () => {
    const base = fixtureBenchmarks();
    const allCompanies = Array.from({length: 101}, (_, i) => ({...companies[0], id: `fixture-${i}`, company_name: `Fictional ${i}`}));
    const allBenchmarks = allCompanies.map(c => ({...base.items[0], company_id: c.id, company_name: c.company_name}));
    let changed = false;
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockImplementation(async input => {
      const url = new URL(String(input), "http://localhost"); const page = Number(url.searchParams.get("page"));
      const pagination = {page, total: 101, total_pages: 2};
      return url.pathname === "/api/companies" ? response({...pagination, items: allCompanies.slice((page - 1) * 100, page * 100)}) : response({...base, ...pagination, input_sha256: changed && page === 2 ? "changed" : base.input_sha256, items: allBenchmarks.slice((page - 1) * 100, page * 100)});
    }));
    expect((await getWorkspace(2025)).benchmarks.items).toHaveLength(101);
    changed = true; const data = await getWorkspace(2025); expect(data.benchmarkError).toContain("snapshot changed"); expect(data.benchmarks.items).toEqual([]); expect(data.companies).toHaveLength(101);
  });
});
