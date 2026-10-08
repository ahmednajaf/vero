import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { globeMarkets } from "../lib/globe";
import { Globe, projectMarker } from "../components/ui/globe";
import { fixtureBenchmarks, companies } from "./benchmarkFixtures";

const renderer = vi.hoisted(() => ({update: vi.fn(), destroy: vi.fn(), create: vi.fn()}));
vi.mock("cobe", () => ({default: renderer.create.mockImplementation(() => renderer)}));
afterEach(() => {vi.restoreAllMocks(); vi.clearAllMocks();});

describe("globe evidence contract", () => {
  it("counts companies separately from reviewed metrics and commitments", () => {
    const result = globeMarkets({companies, benchmarks: fixtureBenchmarks()});
    expect(result.find(m => m.code === "US")).toMatchObject({companies: 4, evidence: 3, targets: 3});
    expect(result.find(m => m.code === "GB")).toMatchObject({companies: 3, evidence: 3, targets: 3});
  });
  it("never promotes missing, stale or conflicting evidence into map claims", () => {
    const benchmarks = fixtureBenchmarks(2025, true);
    const result = globeMarkets({companies, benchmarks});
    expect(result.every(m => m.evidence === 0 && m.targets === 0)).toBe(true);
    const fresh = fixtureBenchmarks();
    fresh.items[0].targets.push({...fresh.items[0].targets[0], target_year: 2040});
    fresh.items[2].targets[0].validation_audit_current = false;
    expect(globeMarkets({companies, benchmarks: fresh}).find(m => m.code === "US")?.targets).toBe(1);
    expect(globeMarkets(null)).toEqual([]);
  });
  it("retains unmapped countries without inventing coordinates", () => {
    const result = globeMarkets({companies: [{...companies[0], country: "ZZ"}], benchmarks: fixtureBenchmarks()});
    expect(result[0].companies).toBe(1); expect(result[0].location).toBeUndefined();
  });
  it("projects front-facing pins and rejects the back hemisphere", () => {
    expect(projectMarker([0, -90], 0, 0)).toMatchObject({x: expect.closeTo(.5), y: .5, visible: true});
    expect(projectMarker([0, 90], 0, 0).visible).toBe(false);
  });
});

describe("globe lifecycle", () => {
  function webgl(reduced = false) {
    vi.stubGlobal("WebGLRenderingContext", class {});
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as WebGLRenderingContext);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 0, 400, 400));
    vi.stubGlobal("matchMedia", vi.fn(() => ({matches: reduced, addEventListener: vi.fn(), removeEventListener: vi.fn()})));
    vi.stubGlobal("requestAnimationFrame", vi.fn(() => 1));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
  }
  it("offers an honest non-WebGL fallback without loading the renderer", () => {
    vi.stubGlobal("WebGLRenderingContext", undefined);
    render(<Globe markers={[]} onSelect={() => {}}/>);
    expect(screen.getByText("3D unavailable")).toBeInTheDocument();
    expect(renderer.create).not.toHaveBeenCalled();
  });
  it("respects reduced motion, allows pause/resume and cleans up the renderer", async () => {
    webgl(true); const user = userEvent.setup();
    const view = render(<Globe markers={[]} onSelect={() => {}}/>);
    await user.click(await screen.findByRole("button", {name: "Resume globe rotation"}));
    expect(screen.getByRole("button", {name: "Pause globe rotation"})).toBeInTheDocument();
    await user.click(screen.getByRole("button", {name: "Pause globe rotation"}));
    expect(screen.getByRole("button", {name: "Resume globe rotation"})).toBeInTheDocument();
    view.unmount(); expect(renderer.destroy).toHaveBeenCalledOnce();
    expect(cancelAnimationFrame).toHaveBeenCalled();
  });
  it("updates markers without recreating the WebGL renderer", async () => {
    webgl(); const select = vi.fn(); const view = render(<Globe markers={[]} onSelect={select}/>);
    await screen.findByRole("button", {name: "Pause globe rotation"});
    view.rerender(<Globe markers={[{id: "US", location: [39, -97], selected: true}]} onSelect={select}/>);
    expect(renderer.create).toHaveBeenCalledOnce();
    expect(renderer.update).toHaveBeenLastCalledWith(expect.objectContaining({markers: [expect.objectContaining({id: "US", location: [39, -97]})]}));
  });
  it("switches to a fallback after WebGL context loss", async () => {
    webgl(); const view = render(<Globe markers={[]} onSelect={() => {}}/>);
    await waitFor(() => expect(renderer.create).toHaveBeenCalledOnce());
    act(() => {fireEvent(view.container.querySelector("canvas")!, new Event("webglcontextlost"));});
    expect(screen.getByText("3D unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("button", {name: "Pause globe rotation"})).not.toBeInTheDocument();
  });
});
