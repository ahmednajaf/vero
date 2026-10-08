import { useEffect, useState } from "react";
import { getCompanyEvidence, type CompanyEvidence } from "../lib/library";
import { metricName, type Company, type SourceSelection } from "../lib/benchmarks";
import { Link } from "../lib/navigation";
import { SourceButton } from "./intelligence";
import {exportCsv} from "./ReportLibrary";

function distinctObservations(items: CompanyEvidence["observations"]) {
  const seen = new Set<string>();
  return items.filter(o => {
    const key = JSON.stringify([o.metric, o.reporting_year, o.raw_value, o.raw_unit, o.boundary, o.report_sha256 || o.report_id, o.source_page, o.validation_state]);
    if (o.validation_state === "rejected" || seen.has(key)) return false;
    seen.add(key); return true;
  });
}

export function ReportedComparison({companies, openSource, refresh = 0}: {companies: Pick<Company, "id" | "company_name">[]; openSource: (value: SourceSelection) => void; refresh?: number}) {
  const [records, setRecords] = useState<Record<string, CompanyEvidence>>({});
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const ids = companies.map(c => c.id).join(",");
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setRecords({}); setErrors([]);
    void Promise.all(ids.split(",").filter(Boolean).map(async id => {
      try {const data = await getCompanyEvidence(id, controller.signal); return {id, data: {...data, observations: distinctObservations(data.observations)}};}
      catch {return {id, data: null};}
    })).then(results => {if (!controller.signal.aborted) {setRecords(Object.fromEntries(results.filter(r => r.data).map(r => [r.id, r.data!]))); setErrors(results.filter(r => !r.data).map(r => r.id)); setLoading(false);}});
    return () => controller.abort();
  }, [ids, attempt, refresh]);
  const key = (metric?: string, year?: number, _unit?: string | null) => JSON.stringify([metric, year]);
  const visible = (id: string) => (records[id]?.observations ?? []).filter(o => o.validation_state !== "rejected");
  const rows = [...new Map(Object.keys(records).flatMap(visible).map(o => [key(o.metric, o.reporting_year, o.raw_unit), o])).values()];
  if (loading) return <p role="status">Loading reported figures…</p>;
  return <section className="vero-reported-comparison">
    <div className="report-peer-actions"><p className="report-caption">Original reported units. Periods and boundaries may differ; these figures are not a ranking.</p><button className="report-button" disabled={!rows.length} onClick={() => exportCsv("vero-reported-figures.csv", [["Company","Metric","Observation year","Raw value","Raw unit","Normalised value","Normalised unit","Status","Boundary","Report","Page","Source URL","Supporting excerpt","SHA-256"], ...companies.flatMap(c => visible(c.id).map(o => [c.company_name,o.metric??"",o.reporting_year??null,o.raw_value??null,o.raw_unit??null,o.normalised_value??null,o.normalised_unit??null,o.validation_state??"",o.boundary??null,o.report_title??"",o.source_page??null,o.source_url??"",o.supporting_excerpt??"",o.report_sha256??""]))])}>Figures & sources CSV ↓</button></div>
    {!!errors.length && <p role="alert" className="vero-service-note">Some sources could not be loaded. <button onClick={() => setAttempt(a => a + 1)}>Retry sources</button></p>}
    <div className="report-table-scroll" role="region" aria-label="Reported figures comparison" tabIndex={0}><table className="report-peer-table"><thead><tr><th>Reported metric</th>{companies.map(c => <th key={c.id}><Link href={`/companies/${c.id}`}>{c.company_name} ↗</Link></th>)}</tr></thead><tbody>
      <tr><th>Reports available</th>{companies.map(c => <td key={c.id}>{records[c.id] ? new Set(records[c.id].reports.map(r => r.sha256 || r.id)).size : "Unavailable"}</td>)}</tr>
      {rows.map(row => <tr key={key(row.metric, row.reporting_year, row.raw_unit)}><th scope="row">{metricName(row.metric ?? "Observation")}<small>{row.reporting_year}</small></th>{companies.map(c => <td key={c.id}>{errors.includes(c.id) ? "Source unavailable" : records[c.id]?.observations.filter(o => key(o.metric, o.reporting_year, o.raw_unit) === key(row.metric, row.reporting_year, row.raw_unit)).map(o => <div className="vero-comp-observation" key={o.id}><strong>{o.raw_value ?? "Not reported"}</strong><small>{o.raw_unit ?? "Unit not stated"}</small><small className="vero-observation-boundary" title={o.boundary??undefined}>{o.boundary??"Boundary not stated"}</small><span className={`vero-status ${o.validation_state}`}>{o.validation_state?.replaceAll("_", " ")}</span><SourceButton label={`${c.company_name} ${metricName(o.metric ?? "Observation")} ${o.reporting_year} page ${o.source_page}`} onClick={() => openSource({company: c.company_name, label: metricName(o.metric ?? "Observation"), evidence: [o]})}/></div>) || "—"}{!errors.includes(c.id) && records[c.id] && !records[c.id].observations.some(o => key(o.metric, o.reporting_year, o.raw_unit) === key(row.metric, row.reporting_year, row.raw_unit)) && "—"}</td>)}</tr>)}
    </tbody></table></div>
    {!rows.length && <p className="vero-empty-line">No extracted figures for this selection yet.</p>}
  </section>;
}
