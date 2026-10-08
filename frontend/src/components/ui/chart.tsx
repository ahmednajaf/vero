// Adapted from shadcn Chart, distributed by Evil Charts on 21st.dev (MIT).
// Recharts 3 types, scoped CSS, and zero-preserving tooltips. See notices.
import { createContext, useContext, useId, type ComponentProps, type CSSProperties } from "react";
import { ResponsiveContainer, Tooltip, type TooltipContentProps } from "recharts";
import { format } from "../../lib/benchmarks";

export type ChartConfig = Record<string, {label: string; color: string; hatched?: boolean}>;
const ChartContext = createContext<ChartConfig | null>(null);
function useChart() { const config = useContext(ChartContext); if (!config) throw new Error("Chart primitives require ChartContainer"); return config; }

export function ChartContainer({config, children}: {config: ChartConfig; children: ComponentProps<typeof ResponsiveContainer>["children"]}) {
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  return <ChartContext.Provider value={config}><div className="sbi-chart-container" data-chart={`chart-${id}`}>
    <ResponsiveContainer width="100%" height={270} initialDimension={{width: 600, height: 270}}>{children}</ResponsiveContainer>
    <ChartLegendContent/>
  </div></ChartContext.Provider>;
}
export const ChartTooltip = Tooltip;
type ContentProps = Partial<Pick<TooltipContentProps, "active" | "payload" | "label">> & {unit: string};
export function ChartTooltipContent({active, payload, label, unit}: ContentProps) {
  const config = useChart();
  if (!active || !payload?.length) return null;
  return <div className="sbi-chart-tooltip"><strong>{label}</strong><dl>{payload.filter(item => item.type !== "none" && item.value != null).map((item, index) => {
    const key = String(item.dataKey ?? item.name ?? index), series = config[key];
    return <div key={key}><dt><i className={series?.hatched ? "is-hatched" : ""} style={{"--series-color": series?.color ?? item.color} as CSSProperties}/>{series?.label ?? item.name}</dt><dd>{format(String(item.value))}{unit === "%" ? "%" : ` ${unit}`}</dd></div>;
  })}</dl><small>Exact values & evidence in the table</small></div>;
}
function ChartLegendContent() {
  const config = useChart();
  return <div className="sbi-chart-legend" aria-label="Chart legend">{Object.entries(config).map(([key, series]) => <span key={key}><i className={series.hatched ? "is-hatched" : ""} style={{"--series-color": series.color} as CSSProperties}/>{series.label}</span>)}</div>;
}
