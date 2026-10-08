import { useId } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { usable, type CompanyBenchmark } from "../lib/benchmarks";
import { EmptyState } from "./intelligence";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "./ui/chart";
import { HatchedBar, HatchedBarPattern } from "./ui/hatched-bar";

export function GroupedChart({companies, kind}: {companies: CompanyBenchmark[]; kind: "emissions" | "energy"}) {
  const patternId = `hatch-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const series = kind === "emissions" ? [
    {key: "scope_1_emissions", name: "Scope 1", color: "#111315"},
    {key: "scope_2_location_based", name: "Scope 2 · location", color: "#26945a"},
  ] : [
    {key: "renewable_energy_percent", name: "Renewable energy", color: "#111315"},
    {key: "renewable_electricity_percent", name: "Renewable electricity", color: "#26945a"},
  ];
  const eligible = series.filter(s => {
    const metrics = companies.map(c => c.metrics[s.key]).filter(usable);
    return metrics.length >= 2 && metrics.every(m => m.cohort_key !== null && m.unit === (kind === "emissions" ? "tCO2e" : "%")) && new Set(metrics.map(m => m.cohort_key)).size === 1;
  });
  if (eligible.length !== series.length) return <EmptyState compact title="Like-for-like data required" description="This grouped chart needs at least two eligible values for each series, with matching definitions, boundaries, periods and units. Missing values are never drawn as zero."/>;
  const rows = companies.map((c, index) => ({name: `${index + 1}. ${c.company_name}`, ...Object.fromEntries(series.map(s => [s.key, usable(c.metrics[s.key]) ? Number(c.metrics[s.key].value) : null]))}));
  return <figure className="intel-chart"><div role="img" aria-label={`${kind === "emissions" ? "Scope 1 and Scope 2 emissions" : "Renewable energy and electricity shares"} for selected comparable companies`}>
    <ChartContainer config={Object.fromEntries(series.map((s, index) => [s.key, {label: s.name, color: s.color, hatched: index === 1}]))}><BarChart accessibilityLayer data={rows} margin={{top: 14, right: 12, bottom: 10, left: 6}} barGap={5}>
      <defs><HatchedBarPattern id={patternId} color={series[1].color}/></defs>
      <CartesianGrid strokeDasharray="2 6" vertical={false} stroke="#dce6e8"/>
      <XAxis dataKey="name" tick={{fontSize: 10, fill: "#697887"}} tickFormatter={value => `${String(value).slice(0, 17)}${String(value).length > 17 ? "…" : ""}`} axisLine={false} tickLine={false} interval={0}/>
      <YAxis tick={{fontSize: 11, fill: "#697887"}} tickFormatter={value => new Intl.NumberFormat("en", {notation: "compact"}).format(Number(value))} axisLine={false} tickLine={false} width={50} domain={kind === "energy" ? [0, 100] : [0, "auto"]}/>
      <ChartTooltip cursor={{fill: "#edf3f4", opacity: .65}} content={<ChartTooltipContent unit={kind === "energy" ? "%" : "tCO2e"}/>}/>
      {series.map((s, index) => <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} shape={<HatchedBar patternId={index === 1 ? patternId : undefined}/>} maxBarSize={46} isAnimationActive={false}/>)}
    </BarChart></ChartContainer>
  </div><figcaption>{kind === "emissions" ? "tCO2e · absolute reported emissions, not a measure of efficiency." : "Percent · energy and electricity use different denominators; each series is compared separately."} Exact source values are available in the table above.</figcaption></figure>;
}
