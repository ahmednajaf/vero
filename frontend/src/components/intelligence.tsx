import type { ReactNode } from "react";
import { BENCHMARK_METRICS, comparable, format, metricName, reasonText, usable, type Metric, type MetricKey, type SourceSelection, type WorkspaceData } from "../lib/benchmarks";
import { Link } from "../lib/navigation";

export interface ViewProps {
  data: WorkspaceData | null; year: number; openSource: (source: SourceSelection) => void;
  metricKey: MetricKey; setMetricKey: (key: MetricKey) => void;
  selected: string[]; toggle: (id: string) => void;
}
export function Icon({name, size = 18}: {name: "arrow" | "search" | "source" | "close" | "check" | "columns" | "chart" | "chevron" | "compare" | "globe" | "info"; size?: number}) {
  const paths = {
    arrow: <><path d="M5 12h14m-6-6 6 6-6 6"/></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
    source: <><path d="M14 3H5v18h14V8l-5-5Zm0 0v6h5M8 13h8M8 17h6"/></>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
    check: <path d="m5 12 4 4L19 6"/>,
    columns: <><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16m6-16v16"/></>,
    chart: <><path d="M4 4v16h17M8 15v-4m5 4V6m5 9V9"/></>,
    chevron: <path d="m7 10 5 5 5-5"/>,
    compare: <><path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"/></>,
    globe: <><circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/></>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
export function PageHeading({title, description, children}: {kicker: string; title: string; description?: string; children?: ReactNode}) {
  return <div className="intel-page-heading"><div><h1 tabIndex={-1}>{title}</h1>{description && <p className="intel-description">{description}</p>}</div>{children}</div>;
}
export function SectionHeading({eyebrow, title, children}: {eyebrow?: string; title: string; children?: ReactNode}) {
  return <div className="intel-section-heading"><div>{eyebrow && <p className="intel-eyebrow">{eyebrow}</p>}<h2>{title}</h2></div>{children}</div>;
}
export function EmptyState({title = "Evidence comes first.", description = "Findings will appear once source-backed observations are validated and comparable.", compact = false, children}: {title?: string; description?: string; compact?: boolean; children?: ReactNode}) {
  return <div className={`intel-empty ${compact ? "compact" : ""}`}><span className="intel-empty-icon"><Icon name="chart" size={23}/></span><h3>{title}</h3><p>{description}</p>{children}</div>;
}
export function SourceButton({onClick, label}: {onClick: () => void; label?: string}) {
  return <button className="intel-source-button" onClick={onClick} aria-label={label ? `View source: ${label}` : "View source"}><Icon name="source" size={14}/><span>View source</span></button>;
}
export function MetricValue({metric, unit = true, trend = false}: {metric?: Metric; unit?: boolean; trend?: boolean}) {
  if (!usable(metric)) return <span className="intel-missing" title={reasonText(metric?.eligibility_reason ?? "missing_validated_evidence")}>—<span className="sr-only"> {reasonText(metric?.eligibility_reason ?? "missing_validated_evidence")}</span></span>;
  return <span className={`intel-metric-value ${trend ? "trend-value" : ""}`}>{trend && Number(metric.value) > 0 ? "+" : ""}{format(metric.value)}{unit && metric.unit && <span className={metric.unit === "%" ? "percent-sign" : "intel-unit"}>{metric.unit === "%" ? "%" : ` ${metric.unit}`}</span>}</span>;
}
export function Percentile({metric, detailed = false}: {metric?: Metric; detailed?: boolean}) {
  return comparable(metric) ? <span className="intel-percentile"><span className="percentile-track" aria-hidden="true"><span style={{width: `${Math.max(0, Math.min(100, Number(metric.percentile)))}%`}}/></span><strong>{format(metric.percentile, 0)}</strong>{detailed && <small> / 100 · n={metric.peer_sample_size}</small>}</span> : <span className="intel-missing" title={reasonText(metric?.reason)}>—{detailed && <small> n={metric?.peer_sample_size ?? 0} · needs {metric?.minimum_sample_size ?? 5}</small>}</span>;
}
export function MetricPicker({value, onChange, label = "Benchmark metric"}: {value: MetricKey; onChange: (key: MetricKey) => void; label?: string}) {
  return <label className="intel-select-label">{label}<select value={value} onChange={event => onChange(event.target.value as MetricKey)}>{BENCHMARK_METRICS.map(key => <option key={key} value={key}>{metricName(key)}</option>)}</select></label>;
}
export function CompanyIdentity({name, ticker, id, compact = false}: {name: string; ticker?: string; id?: string; compact?: boolean}) {
  const content = <><span className={`intel-monogram ${compact ? "small" : ""}`} aria-hidden="true">{name.split(/\s+/).filter(Boolean).slice(0, 2).map(word => word[0]).join("")}</span><span className="intel-company-name"><strong>{name}</strong>{ticker && <small>{ticker}</small>}</span></>;
  return id ? <Link className="intel-company-identity" href={`/companies/${id}`}>{content}</Link> : <span className="intel-company-identity">{content}</span>;
}
export function DataNote({children}: {children: ReactNode}) { return <p className="intel-data-note"><Icon name="info" size={15}/><span>{children}</span></p>; }
