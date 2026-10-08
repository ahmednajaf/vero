import { useEffect, useState } from "react";
import { getCompanyEvidence, localReportUrl, type CompanyEvidence as EvidenceLibrary } from "../lib/library";
import { metricName, safeSourceUrl, type SourceSelection } from "../lib/benchmarks";
import { Icon, SourceButton } from "./intelligence";

export function CompanyEvidence({companyId, companyName, openSource}: {companyId: string; companyName: string; openSource: (value: SourceSelection) => void}) {
  const [data, setData] = useState<EvidenceLibrary | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [year, setYear] = useState("");
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError(""); setYear("");
    void getCompanyEvidence(companyId, controller.signal).then(result => {if (!controller.signal.aborted) setData(result);}).catch((e: unknown) => {if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Evidence unavailable");});
    return () => controller.abort();
  }, [companyId, attempt]);
  if (error) return <section className="vero-evidence"><p role="alert">{error} <button className="intel-inline-link" onClick={() => setAttempt(n => n + 1)}>Retry sources</button></p></section>;
  if (!data) return <p className="vero-evidence" role="status">Loading reports…</p>;
  const years = [...new Set(data.observations.map(o => o.reporting_year).filter((y): y is number => !!y))].sort((a,b) => b-a);
  const observations = data.observations.filter(o => !year || String(o.reporting_year) === year);
  return <section id="reported-evidence" className="vero-evidence" aria-label="Reported evidence">
    <header><div><h2>Reported figures</h2><p>Source claims, with review status. Not benchmark rankings.</p></div>{years.length > 0 && <select aria-label="Evidence year" value={year} onChange={e => setYear(e.target.value)}><option value="">All performance years</option>{years.map(y => <option key={y}>{y}</option>)}</select>}</header>
    {data.observations.length > 0 ? <div className="intel-table-wrap"><table className="vero-evidence-table"><thead><tr><th>Metric</th><th>Year</th><th>Reported value</th><th>Review</th><th><span className="sr-only">Evidence</span></th></tr></thead><tbody>{observations.map(o => <tr key={o.id} className={o.validation_state === "rejected" ? "is-rejected" : ""}><th scope="row">{metricName(o.metric ?? "Observation")}</th><td>{o.reporting_year}</td><td><strong>{o.raw_value ?? "Not reported"}</strong> <span>{o.raw_unit}</span></td><td><span className={`vero-status ${o.validation_state}`}>{o.validation_state?.replaceAll("_", " ")}</span></td><td><SourceButton label={`${metricName(o.metric ?? "Observation")} · ${o.reporting_year} · page ${o.source_page}`} onClick={() => openSource({company: companyName, label: metricName(o.metric ?? "Observation"), evidence: [o]})}/></td></tr>)}</tbody></table></div> : <div className="vero-empty-line">No extracted figures yet. This company is in the research queue.</div>}
    <div className="vero-report-list"><h3>Reports <span>{data.reports.length}</span></h3>{data.reports.map(r => <article key={r.id}>
      <Icon name="source" size={20}/>
      <div><strong>{r.title}</strong><small>{r.pages ? `${r.pages} pages · ` : ""}{r.parse_status.replaceAll("_", " ")}{r.source_policy === "official" ? " · official source" : " · source review needed"}</small>
        {r.primary_source_exclusion && <small>Financing disclosure — not a company-wide source</small>}
      </div>
      {localReportUrl(r.local_url) && <a className="intel-button" href={localReportUrl(r.local_url)!} target="_blank" rel="noopener noreferrer">Open PDF ↗</a>}
      {safeSourceUrl(r.source_url) && <a className="vero-original-link" href={safeSourceUrl(r.source_url)!} target="_blank" rel="noopener noreferrer" aria-label={`Original ${r.detected_year ?? r.reporting_year ?? "Undated"} report`}>Original ↗</a>}
    </article>)}{!data.reports.length && <p>No report downloaded yet.</p>}</div>
  </section>;
}
