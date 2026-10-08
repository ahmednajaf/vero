import { useEffect, useRef, useState } from "react";
import { format, reasonText, safeSourceUrl, type SourceSelection } from "../lib/benchmarks";
import { Icon } from "./intelligence";
import { localReportUrl } from "../lib/library";

// Remove storage padding without converting exact decimal evidence to a float.
const compactDecimal = (value: string | number | undefined | null) =>
  typeof value === "string" && /^-?\d+\.\d+$/.test(value)
    ? value.replace(/0+$/, "").replace(/\.$/, "")
    : value;

export function SourceDrawer({selection, returnFocusTo, onClose}: {selection: SourceSelection; returnFocusTo?: HTMLElement | null; onClose: () => void}) {
  const drawer = useRef<HTMLElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const [index, setIndex] = useState(0);
  const evidence = selection.evidence ?? selection.metric?.provenance ?? [];
  const source = evidence[index];
  useEffect(() => {
    const previous = returnFocusTo ?? document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButton.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); }
      if (event.key !== "Tab") return;
      const controls = [...(drawer.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], select, input, [tabindex="0"]') ?? [])];
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && (document.activeElement === first || !drawer.current?.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !drawer.current?.contains(document.activeElement))) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.body.style.overflow = overflow; document.removeEventListener("keydown", keydown); if (previous?.isConnected) previous.focus(); };
  }, [onClose, returnFocusTo]);
  const href = safeSourceUrl(source?.source_url, source?.source_page);
  const localHref = localReportUrl(source?.local_report_url, source?.source_page);
  let readableNotes = source?.notes;
  let qualityFlags: string[] = [];
  try {const note: unknown = JSON.parse(source?.notes ?? ""); if (typeof note === "object" && note !== null) {const record = note as Record<string, unknown>; readableNotes = typeof record.model_notes === "string" ? record.model_notes : undefined; if (Array.isArray(record.quality_flags)) qualityFlags = record.quality_flags.filter((v): v is string => typeof v === "string");}} catch { /* Plain-text source notes are preserved. */ }
  const status = source?.validation_state ?? (source?.kind === "reviewed_revenue" && source.validated && source.source_verified ? "validated" : "Not available");
  const isPassage = source?.kind === "report_passage";
  const fields = [
    ["Page", source?.source_page],
    isPassage ? ["Report label year", source?.report_year] : ["Reporting year", source?.reporting_year],
    ...(!isPassage ? [
    ["Reporting boundary", source?.boundary],
    ["Raw value", source?.raw_value ?? source?.target_raw_value], ["Raw unit", source?.raw_unit ?? source?.target_raw_unit],
    ["Normalised value", compactDecimal(source?.normalised_value ?? (source?.kind === "reviewed_revenue" ? source.value : undefined))],
    ["Normalised unit", source?.normalised_unit ?? (source?.kind === "reviewed_revenue" ? source.currency : undefined)],
    ] : []),
    ["Validation status", status.replaceAll("_", " ")], ["Extraction method", source?.extraction_method],
  ];
  return <div className="source-backdrop" onMouseDown={event => {if (event.target === event.currentTarget) onClose();}}>
    <aside ref={drawer} className="source-drawer" role="dialog" aria-modal="true" aria-labelledby="source-title">
      <header className="source-drawer-header"><div><h2 id="source-title">Source evidence</h2></div><button ref={closeButton} className="icon-button" aria-label="Close source drawer" onClick={onClose}><Icon name="close"/></button></header>
      <div className="source-drawer-body"><p className="source-company">{selection.company}</p><h3>{selection.label}</h3>
        {selection.demo && <div className="race-demo-banner">DEMO ONLY · Fictional illustration. No underlying corporate report or validation decision.</div>}
        {selection.metric?.formula && <div className="source-calculation"><span className="intel-eyebrow">DERIVED CALCULATION</span><strong>{format(selection.metric.value)} {selection.metric.unit}</strong><code>{selection.metric.formula}</code><p>{reasonText(selection.metric.eligibility_reason)}</p></div>}
        {selection.explanation && <p className="source-explanation">{selection.explanation}</p>}
        {selection.cohort && <section className="source-cohort"><div className="source-calculation"><span className="intel-eyebrow">API-CALCULATED SECTOR MEDIAN</span><strong>{format(selection.cohort.median)} {selection.cohort.median !== null ? selection.cohort.unit : ""}</strong><p>Peer sample size: {selection.cohort.sampleSize}</p></div><details className="source-details"><summary>All contributing company values ({selection.cohort.members.length})</summary><dl>{selection.cohort.members.map(member => <div className="source-cohort-member" key={member.company}><dt>{member.company}</dt><dd>{format(member.value, 6)} {member.unit}</dd></div>)}</dl></details><details className="source-details"><summary>Cohort definition, period & boundary</summary><pre>{JSON.stringify(selection.cohort.dimensions, null, 2)}</pre></details></section>}
        {evidence.length > 1 && <label className="intel-select-label source-evidence-selector">Supporting observations<select aria-label="Supporting observation" value={index} onChange={event => setIndex(Number(event.target.value))}>{evidence.map((entry, i) => <option key={i} value={i}>{entry.company_name ?? `Evidence ${i + 1}`} · {entry.reporting_year ?? (entry.report_year ? `Report ${entry.report_year}` : "Year not recorded")} · {entry.metric ?? "Observation"} · {entry.source_page ? `page ${entry.source_page}` : "Page not recorded"}</option>)}</select></label>}
        {source ? <><div className="source-document"><Icon name="source" size={23}/><div><span className="intel-eyebrow">{selection.demo ? "DEMO SCENARIO" : "SOURCE REPORT"}</span><strong>{source.report_title ?? "Report title not recorded"}</strong><span>{selection.demo ? "Synthetic illustration, not evidence" : source.source_policy === "official" ? "Official company source" : source.kind === "reviewed_revenue" && source.source_verified ? "Reviewed financial source" : "Source requires review"}</span></div></div>
          <div className="source-quote"><span className="intel-eyebrow">SUPPORTING EXCERPT</span><blockquote>{source.supporting_excerpt ?? "No excerpt retained for this observation."}</blockquote></div>
          <dl className="source-facts">{fields.map(([label, value]) => <div key={String(label)}><dt>{label}</dt><dd className={label === "Validation status" ? `evidence-status ${status}` : ""}>{value ?? "Not recorded"}</dd></div>)}</dl>
          {source.target_year && <div className="source-context"><h4>Target, not achieved performance</h4><p>Target year: {source.target_year} · Scope: {source.scope ?? "not recorded"}</p><p>{source.coverage ?? source.boundary ?? "Boundary not recorded"}</p></div>}
          {source.validation_event && <div className="source-context"><h4>Validation decision</h4><p>{source.validation_event.reason}</p><small>{source.validation_event.actor_reference} · {source.validation_audit_current ? "Current audit" : "Audit requires review"}</small></div>}
          {source.notes && <div className="source-context"><h4>Observation notes</h4>{readableNotes && <p>{readableNotes}</p>}{qualityFlags.length > 0 && <ul>{qualityFlags.map(flag => <li key={flag}>{flag.replaceAll("_", " ")}</li>)}</ul>}<details className="source-details"><summary>Extraction metadata</summary><pre>{source.notes}</pre></details></div>}
          {selection.metric && <details className="source-details"><summary>Comparison boundary & method</summary><pre>{JSON.stringify(selection.metric.comparison_dimensions, null, 2)}</pre></details>}
          {source.report_sha256 && <details className="source-details"><summary>Document fingerprint</summary><code>{source.report_sha256}</code></details>}
        </> : <div className="source-no-evidence"><Icon name="source" size={32}/><h4>No source evidence available</h4><p>{reasonText(selection.metric?.eligibility_reason ?? "missing_validated_evidence")}. A missing observation is not zero or proof of nondisclosure.</p></div>}
      </div>
      <footer className="source-drawer-footer">{localHref && <a className="intel-button primary" href={localHref} target="_blank" rel="noopener noreferrer">Open saved PDF · page {source?.source_page} ↗</a>}{href ? <a className={`intel-button ${localHref ? "" : "primary"}`} href={href} target="_blank" rel="noopener noreferrer">Open original report <span aria-hidden="true">↗</span></a> : <span className="intel-muted">No verified report link available</span>}</footer>
    </aside>
  </div>;
}
