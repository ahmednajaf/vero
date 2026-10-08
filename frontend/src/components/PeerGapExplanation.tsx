import { useEffect, useRef, useState } from "react";
import { format, reasonText, type SourceSelection } from "../lib/benchmarks";
import { downloadExplanation, gapSource, getPeerExplanation, type GapContext, type GapFactor, type PeerExplanation } from "../lib/peer-gaps";
import "../peer-gaps.css";

const effects: Record<string, string> = {
  above_peer_median: "Above peer median performance", below_peer_median: "Below peer median performance", at_peer_median: "At peer median",
  missing_evidence: "Missing reviewed evidence", not_comparable: "Not comparable", insufficient_peers: "Insufficient comparable peers",
  context_only: "Context only · not scored", disclosure_gap: "Verified disclosure gap", review_gap: "Not established · review needed", reported: "Verified reporting",
};
function value(row: GapFactor) {
  if (row.company_state === "not_reported") return "Not reported · reviewed";
  if (row.company_state === "unknown") return "Not established";
  if (row.company_value === "true") return row.metric === "scope3_available" ? "Reported" : "Yes";
  if (row.company_value === "false") return "No";
  return row.company_value === null ? "—" : `${row.unit === "year" ? row.company_value : format(row.company_value)}${row.unit === "%" ? "%" : row.unit && row.unit !== "year" ? ` ${row.unit}` : ""}`;
}
export function PeerGapExplanation({companyId, context, openSource}: {companyId: string; context: GapContext; openSource: (source: SourceSelection) => void}) {
  const [data, setData] = useState<PeerExplanation | null>(null), [error, setError] = useState("");
  const [retry, setRetry] = useState(0), [exporting, setExporting] = useState(false), [exportError, setExportError] = useState("");
  const lifecycle = useRef<AbortController | null>(null);
  const {year, input_sha256, minimum_peers, scope2_method, peer_group} = context;
  useEffect(() => {
    const controller = new AbortController(); lifecycle.current = controller;
    setData(null); setError(""); setExportError(""); setExporting(false);
    getPeerExplanation(companyId, {year, input_sha256, minimum_peers, scope2_method, peer_group}, controller.signal)
      .then(result => {if (!controller.signal.aborted) setData(result);})
      .catch(cause => {if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Peer explanation unavailable.");});
    return () => controller.abort();
  }, [companyId, year, input_sha256, minimum_peers, scope2_method, peer_group, retry]);
  async function exportFile(format: "json" | "csv") {
    if (!data || exporting) return;
    const signal = lifecycle.current?.signal;
    setExporting(true); setExportError("");
    try {await downloadExplanation(data, context, format, signal);}
    catch (cause) {if (!signal?.aborted) setExportError(cause instanceof Error ? cause.message : "Export unavailable.");}
    finally {if (!signal?.aborted) setExporting(false);}
  }
  const source = (row: GapFactor) => <button className="peer-gap-source" aria-label={`View peer-gap evidence: ${row.label}`} onClick={() => data && openSource(gapSource(data, row))}>View evidence ↗</button>;
  return <section id="why-position" className="peer-gap-explanation" aria-labelledby="peer-gap-title">
    <header><div><p className="intel-eyebrow">STRUCTURED PEER INTELLIGENCE</p><h2 id="peer-gap-title">Why this position?</h2><p>Company values, like-for-like peers and the evidence behind each gap.</p></div><div className="peer-gap-exports"><button className="intel-button" disabled={!data || exporting} onClick={() => void exportFile("csv")}>Export CSV</button><button className="intel-button" disabled={!data || exporting} onClick={() => void exportFile("json")}>Export JSON</button></div></header>
    {exportError && <p role="alert">{exportError}</p>}
    {!data && !error && <p role="status">Loading structured peer comparisons…</p>}
    {error && <div role="alert"><p>{error}</p><button className="intel-button" onClick={() => setRetry(n => n + 1)}>Retry explanation</button></div>}
    {data && <>
      <p className="peer-gap-notice">{data.label} {data.score.ranking_eligible ? "Comparisons explain individual factors, not the causal effect of any factor on rank." : "No eligible overall rank is available. These explain individual factors, not an invented rank."}</p>
      <div className="peer-gap-table-wrap" role="region" aria-label="Structured peer comparison" tabIndex={0}><table className="peer-gap-table"><caption>{data.sector} · {data.year} · numeric cohorts include the company; disclosure/prevalence peers exclude it.</caption>
        <thead><tr><th scope="col">Factor</th><th scope="col">Company</th><th scope="col">Peer reference</th><th scope="col">Gap & assessment</th></tr></thead>
        <tbody>{data.factors.map(row => <tr key={row.metric}>
          <th scope="row"><strong>{row.label}</strong><small>{Number(row.score_weight) > 0 ? `${format(Number(row.score_weight) * 100, 0)}% nominal score weight` : "Context only · 0% score weight"}</small>{row.weighted_points !== null && <small>{format(row.weighted_points)} contributed score points</small>}{source(row)}</th>
          <td><strong>{value(row)}</strong><small>{row.completeness.company_complete ? "Assessment complete" : "Assessment incomplete"}</small>{row.completeness.required_inputs != null && <small>{row.completeness.assessed_inputs}/{row.completeness.required_inputs} inputs assessed</small>}</td>
          <td>{row.peer_rate_kind ? <><strong>{row.peer_rate === null ? "—" : `${format(row.peer_rate)}%`}</strong><small>{row.peer_rate_kind === "affirmative_prevalence" ? "Peer prevalence · yes / assessed" : "Verified reporting / all sector peers"}</small><small>{row.completeness.reported_peers}/{row.completeness.denominator} · {row.completeness.assessed_peers} assessed · {row.completeness.unknown_peers} unknown or incompatible</small></> : <><strong>{row.sector_median === null ? "—" : `${format(row.sector_median)}${row.unit === "%" ? "%" : ""}`}</strong><small>Sector median · n={row.peer_sample_size}</small><small>Percentile {row.percentile === null ? "—" : `${format(row.percentile)} / 100`}</small>{row.completeness.sector_companies != null && <small>{row.completeness.comparable_companies}/{row.completeness.sector_companies} sector companies comparable</small>}</>}</td>
          <td><strong>{effects[row.effect] ?? "Comparison unavailable"}</strong>{row.difference !== null && <small>Company − median: {Number(row.difference) > 0 ? "+" : ""}{format(row.difference)} {row.difference_unit === "percentage_points" ? "percentage points" : row.difference_unit}</small>}{row.preferred_direction && <small>{row.preferred_direction === "lower" ? "Lower is preferred for this component" : "Higher is preferred for this component"}</small>}{row.reason && <small>{reasonText(row.reason)}</small>}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="peer-gap-footnote">Percentiles are ascending numeric positions, not merit scores. For emissions trajectory, −4% versus −9% is +5 percentage points but a smaller reduction. Renewable electricity is never substituted for total renewable energy. Governance and commitments do not affect the prototype score.</p>
      <div className="peer-gap-opportunities"><h3>Peers commonly disclose metrics you do not</h3><p>Only source-reviewed absence can establish nondisclosure. “Common” means verified reporting by at least {data.common_threshold_percent}% of other sector companies, with at least {data.minimum_peers} assessed peers.</p>
        {!data.disclosure_opportunities.some(row => row.common_gap && row.company_state === "not_reported") && <p>No confirmed common disclosure gaps are established by the reviewed evidence.</p>}
        {data.disclosure_opportunities.filter(row => row.common_gap && row.company_state === "not_reported").map(row => <div className="peer-gap-opportunity" key={row.metric}><strong>{row.label}</strong><span>Verified reporting: {format(row.peer_rate)}% of peers</span>{source(row)}</div>)}
        {data.disclosure_opportunities.some(row => row.common_gap && row.company_state === "unknown") && <><h4>Not yet established for this company</h4><p>These are review priorities, not confirmed reporting failures.</p>{data.disclosure_opportunities.filter(row => row.common_gap && row.company_state === "unknown").map(row => <div className="peer-gap-opportunity" key={row.metric}><strong>{row.label}</strong><span>{format(row.peer_rate)}% verified peer coverage · {row.completeness.reported_peers}/{row.completeness.denominator}</span>{source(row)}</div>)}</>}
        <details><summary>Inspect all disclosure checks and completeness</summary>{data.disclosure_opportunities.map(row => <div className="peer-gap-opportunity" key={row.metric}><strong>{row.label}</strong><span>{row.company_state === "unknown" ? "Company: not established" : `Company: ${row.company_state?.replaceAll("_", " ")}`} · {row.peer_rate === null ? reasonText(row.reason ?? "unavailable") : `${format(row.peer_rate)}% verified peer reporting`} · {row.completeness.assessed_peers}/{row.completeness.peer_companies} peers assessed</span>{source(row)}</div>)}</details>
      </div><details className="peer-gap-audit"><summary>Calculation identity & limitations</summary><p>{data.notice}</p><p>Rules: {data.version} · benchmark: {data.methodology_version}</p><code>{data.input_sha256}</code><p>Exports retain values, denominators, exclusion reasons, company and peer provenance, and the calculation fingerprints. Empty values stay empty.</p></details>
    </>}
  </section>;
}
