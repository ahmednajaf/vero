import {useEffect, useRef, useState} from "react";
import {knowledge, reportTitle, type ReportLibrary} from "../lib/knowledge";
import type {SourceSelection} from "../lib/benchmarks";
import {ReportedComparison} from "./ReportedComparison";

const metrics = {
  scope_1_emissions: "Scope 1 emissions",
  scope_2_location_based: "Scope 2 · location-based",
  scope_2_market_based: "Scope 2 · market-based",
  scope_3_emissions: "Scope 3 emissions",
  renewable_electricity_percent: "Renewable electricity",
  renewable_energy_percent: "Renewable energy",
  total_energy_consumption: "Energy consumption",
  water_consumption: "Water consumption",
  total_waste: "Total waste",
  employees: "Employees",
};
interface Result {status: string; observations: number; warnings: string[]}

/** Uses the existing observation store. Opening this panel never invokes AI. */
export function MetricFigures({library, ids, openSource}: {
  library: ReportLibrary; ids: string[]; openSource: (source: SourceSelection) => void;
}) {
  const companies = ids.map(id => library.companies.find(c => c.id === id)).filter(c => !!c);
  const [selectedReports, setReports] = useState<Record<string, string>>({});
  const [metric, setMetric] = useState("scope_1_emissions"), [year, setYear] = useState("");
  const [busy, setBusy] = useState(false), [progress, setProgress] = useState("");
  const [messages, setMessages] = useState<string[]>([]), [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const generation = useRef(0), alive = useRef(true);
  const group = ids.join(",");
  useEffect(() => {alive.current = true; return () => {alive.current = false; generation.current++;};}, []);
  useEffect(() => {generation.current++; setBusy(false); setProgress(""); setMessages([]); setError("");}, [group]);
  const reportsFor = (id: string) => [...new Map(library.reports
    .filter(r => r.company_id === id && r.knowledge_status === "indexed")
    .map(r => [r.sha256 || r.id, r])).values()];
  const reportFor = (id: string) => reportsFor(id).find(r => r.id === selectedReports[id]) ?? reportsFor(id)[0];
  async function extract() {
    const active = ++generation.current;
    const targets = companies.map(c => ({company: c, report: reportFor(c.id)}));
    setBusy(true); setError(""); setMessages([]);
    try {
      for (const {company, report} of targets) {
        if (!report) {setMessages(m => [...m, `${company.company_name}: no parsed source report available.`]); continue;}
        setProgress(`Reading ${company.company_name}…`);
        const result = await knowledge<Result>(`/reports/${report.id}/extract-metric`, {metric, observation_year: Number(year)});
        if (!alive.current || generation.current !== active) return;
        if (result.status === "busy") throw new Error("This report is already being processed. Reopen its figures when the current request finishes.");
        if (!Number.isInteger(result.observations)) throw new Error("The extraction result could not be read.");
        setMessages(m => [...m, result.observations ? `${company.company_name}: ${result.observations} source-linked figure${result.observations === 1 ? "" : "s"}${result.status === "unchanged" ? " (saved result)" : ""}.` : `${company.company_name}: no usable value in the selected passage. This does not establish non-disclosure.`]);
        setRefresh(n => n + 1);
      }
    } catch (e) {if (alive.current && generation.current === active) setError(e instanceof Error ? e.message : "Extraction could not finish.");}
    finally {if (alive.current && generation.current === active) {setBusy(false); setProgress("");}}
  }
  if (!companies.length) return null;
  return <section className="intelligence-company" aria-label="Reported figures">
    <h2>Reported figures</h2>
    <ReportedComparison companies={companies} openSource={openSource} refresh={refresh}/>
    <details className="intelligence-details"><summary>Extract figures from selected reports</summary>
      <p>Choose the measurement year—not the report’s publication year. Saved results are reused. Each selected report uses at most one AI call for this metric.</p>
      <div className="report-filters">
        <label>Metric <select aria-label="Metric to extract" disabled={busy} value={metric} onChange={e => setMetric(e.target.value)}>{Object.entries(metrics).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
        <label>Measurement year <input aria-label="Measurement year" type="number" min="1900" max="2100" placeholder="e.g. 2024" disabled={busy} value={year} onChange={e => setYear(e.target.value)}/></label>
      </div>
      {companies.map(c => <label className="report-select" key={c.id}>{c.company_name}<select disabled={busy || !reportsFor(c.id).length} aria-label={`${c.company_name} source report`} value={reportFor(c.id)?.id ?? ""} onChange={e => setReports(r => ({...r, [c.id]: e.target.value}))}>{!reportsFor(c.id).length && <option value="">No parsed source available</option>}{reportsFor(c.id).map(r => <option key={r.id} value={r.id}>{reportTitle(r.title, r.source_url)}</option>)}</select></label>)}
      <button className="report-button solid" disabled={busy || !companies.some(c => reportFor(c.id)) || !/^\d{4}$/.test(year) || Number(year) < 1900 || Number(year) > 2100 || !!library.status.research.configuration_error} onClick={() => void extract()}>Extract selected metric</button>
      <p className="report-caption">{library.status.research.model} · no automatic retry · figures remain labelled until reviewed.</p>
    </details>
    {progress && <p role="status">{progress}</p>}
    {messages.map((message, i) => <p className="report-caption" key={i}>{message}</p>)}
    {error && <p role="alert">{error}</p>}
  </section>;
}
