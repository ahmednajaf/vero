import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChartContainer, ChartTooltipContent } from "../components/ui/chart";
import { GroupedChart } from "../components/BenchmarkCharts";
import { fixtureBenchmarks } from "./benchmarkFixtures";

describe("sourced chart components", () => {
  it("preserves a real zero in its tooltip and omits missing values", () => {
    render(<ChartContainer config={{energy: {label: "Renewable energy", color: "#173e64"}}}><ChartTooltipContent active label="Test company" unit="%" payload={[
      {dataKey: "energy", value: 0, graphicalItemId: "energy"},
      {dataKey: "missing", value: undefined, graphicalItemId: "missing"},
    ]}/></ChartContainer>);
    expect(screen.getByText("0%")).toBeInTheDocument(); expect(screen.queryByText("missing")).not.toBeInTheDocument();
  });
  it("uses unique hatched patterns for simultaneous charts", () => {
    const companies = fixtureBenchmarks().items.slice(0, 2);
    const {container} = render(<><GroupedChart kind="emissions" companies={companies}/><GroupedChart kind="energy" companies={companies}/></>);
    const ids = [...container.querySelectorAll("pattern")].map(p => p.id);
    expect(ids).toHaveLength(2); expect(new Set(ids).size).toBe(2);
    for (const id of ids) expect(container.querySelector(`rect[fill="url(#${id})"]`)).toBeInTheDocument();
  });
});
