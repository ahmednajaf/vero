import {useState} from "react";
import {exportLink, evidenceStates, type Briefing, type ReportAward, type ReportedFact, type PromiseRecord} from "../lib/briefings";
import type {ReportLibrary, Answer} from "../lib/knowledge";
import type {SourceSelection} from "../lib/benchmarks";
import {type AskReport, type OpenPassage, ReportCards} from "./ReportLibrary";
import {MetricFigures} from "./MetricFigures";
import {DashboardStats, ComparisonChart, PeerAwards, DisclosureCard, QuickActions} from './ui/research-dashboard';
import '../research-dashboard.css';

export function ReportedData({facts,open}:{facts:ReportedFact[];open:OpenPassage}) {
  const [query,setQuery]=useState(''),[company,setCompany]=useState(''),[page,setPage]=useState(1);
  const filtered=facts.filter(f=>(!company||f.company_id===company)&&`${f.metric} ${f.value} ${f.population}`.toLowerCase().includes(query.toLowerCase()));
  const companies=[...new Map(facts.map(f=>[f.company_id,f.source.company])).entries()];
  return <section className="workspace-panel"><header><h2>Reported data</h2><input type="search" className="workspace-search" aria-label="Search reported data" placeholder="Find a metric" value={query} onChange={e=>{setQuery(e.target.value);setPage(1);}}/></header>
    <label className="workspace-select">Company<select aria-label="Reported data company" value={company} onChange={e=>{setCompany(e.target.value);setPage(1);}}><option value="">All companies</option>{companies.map(([id,name])=><option value={id} key={id}>{name}</option>)}</select></label>
    <div className="report-table-scroll"><table className="report-peer-table compact-table"><thead><tr><th>Company</th><th>Metric</th><th>Reported value</th><th>Year</th><th>Source</th></tr></thead><tbody>{filtered.slice((page-1)*12,page*12).map(f=><tr key={f.id}><th>{f.source.company}</th><td>{f.metric}{f.kind==='target'&&<small>Target</small>}</td><td>{f.value} {f.unit==='%'&&f.value.endsWith('%')?'':f.unit}</td><td>{f.year??'—'}</td><td><button className="workspace-text-button" onClick={()=>open(f.source)}>p. {f.source.page} ↗</button></td></tr>)}</tbody></table></div>
    {!filtered.length&&<p className="report-caption">No matching metric.</p>}
    <div className="report-pagination"><span>{filtered.length} reported items</span><div><button className="report-button" disabled={page===1} onClick={()=>setPage(p=>p-1)}>Previous</button><button className="report-button" disabled={page*12>=filtered.length} onClick={()=>setPage(p=>p+1)}>Next</button></div></div>
  </section>;
}
function AwardResults({awards,open}:{awards:ReportAward[];open:OpenPassage}) {
  const fmt=(value:string)=>new Intl.NumberFormat("en-GB",{maximumFractionDigits:3}).format(Number(value));
  return <>{awards.map((award,i)=><section className="intelligence-finding" key={`${award.name}-${i}`}>
    <h3>{award.name}</h3><p>{award.criterion}</p>
    <p><strong>{award.winner_ids.length?award.rows.filter(r=>award.winner_ids.includes(r.company_id)).map(r=>r.company).join(" · "):"Contextual comparison"}</strong> <span className="report-caption">{award.sample_size} of {award.cohort_size} selected companies</span></p>
    <div className="report-table-scroll"><table className="report-peer-table compact-table"><thead><tr><th>Company</th><th>Result</th><th>Year</th><th>Source</th></tr></thead><tbody>{award.rows.map(row=><tr key={row.company_id}><th>{row.company}</th><td>{fmt(row.value)} {row.unit}</td><td>{row.year}</td><td>{row.inputs.map((input,n)=><button className="report-button" key={n} onClick={()=>open(input.source)} title={`${input.raw_value} ${input.raw_unit} → ${input.value} ${input.unit}`}>{input.source.report} · p. {input.source.page} ↗</button>)}</td></tr>)}</tbody></table></div>
    <details className="intelligence-details"><summary>Calculation & context</summary><p>{award.formula??award.operation.replaceAll("_"," ")}</p><p>{award.caveat}</p><p>{award.direction==='near_reference'?`Closer to ${award.reference_value} leads on this criterion.`:award.direction==='none'?'Contextual comparison, without a preferred direction.':`${award.direction==='higher'?'Higher':'Lower'} values lead on this criterion.`}</p>{(award.excluded.length>0||award.unassessed_company_ids.length>0)&&<p>Some selected companies have no calculated result for this criterion.</p>}</details>
  </section>)}</>;
}

export function PromiseRegister({promises,open}:{promises:PromiseRecord[];open:OpenPassage}) {
  const [company,setCompany]=useState(''),[query,setQuery]=useState(''),[page,setPage]=useState(1);
  const filtered=promises.filter(p=>(!company||p.company_id===company)&&`${p.commitment} ${p.assessment}`.toLowerCase().includes(query.toLowerCase()));
  const companies=[...new Map(promises.map(p=>[p.company_id,p.company])).entries()];
  return <section className="workspace-panel"><header><h2>Promises & delivery</h2><span className="report-caption">{filtered.length} commitments</span></header><div className="report-filters"><input type="search" aria-label="Search commitments" placeholder="Find a commitment…" value={query} onChange={e=>{setQuery(e.target.value);setPage(1);}}/><select aria-label="Commitment company" value={company} onChange={e=>{setCompany(e.target.value);setPage(1);}}><option value="">All companies</option>{companies.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></div>{filtered.slice((page-1)*6,page*6).map((p,i)=><article className="promise-record" key={`${page}-${i}`}><span>{p.company}{p.deadline?` · ${p.deadline}`:''}</span><h3>{p.commitment}</h3><details><summary>Reported progress</summary><p>{p.assessment}</p></details>{p.citations.length>0&&<button className="workspace-text-button" onClick={()=>open(p.citations[0],p.citations.slice(1))}>View source ↗</button>}</article>)}{!filtered.length&&<p className="report-caption">{promises.length?'No matching commitments.':'No promise register is saved in this analysis.'}</p>}<div className="report-pagination"><span>{filtered.length?`${(page-1)*6+1}–${Math.min(page*6,filtered.length)} of ${filtered.length}`:'0 commitments'}</span><div><button className="report-button" disabled={page===1} onClick={()=>setPage(p=>p-1)}>Previous</button><button className="report-button" disabled={page*6>=filtered.length} onClick={()=>setPage(p=>p+1)}>Next</button></div></div></section>;
}

function Finding({claim, open, number}: {claim: Answer["claims"][number]; open: OpenPassage; number: number}) {
  const sources = [...new Map(claim.citations.map(c => [`${c.report_id}:${c.page}`, c])).values()];
  const split = claim.text.search(/ — |\n/);
  const headline = split > 15 && split < 190 ? claim.text.slice(0, split) : claim.text.length > 175 ? `${claim.text.slice(0, 175).replace(/\s+\S*$/, "")}…` : claim.text;
  return <article className="finding-card">
    <span className="finding-index">{String(number).padStart(2, "0")}</span>
    <div>{headline === claim.text ? <p className="finding-headline">{headline}</p> : <details className="finding-reading"><summary>{headline}</summary><p>{claim.text}</p></details>}
      {!!sources.length && <button className="workspace-text-button" onClick={() => open(sources[0], sources.slice(1))} aria-label={`View source: ${sources[0].company}, page ${sources[0].page}`}>{sources.length} source{sources.length === 1 ? "" : "s"} ↗</button>}
    </div>
  </article>;
}

export function AnalysisDashboard({brief, library, open, openSource, ask, regenerate}: {brief: Briefing; library: ReportLibrary; open: OpenPassage; openSource?: (s: SourceSelection) => void; ask: AskReport; regenerate?:()=>void}) {
  const [tab, setTab] = useState("summary"), [topic, setTopic] = useState("all"), [page, setPage] = useState(1);
  const [metricIndex,setMetricIndex]=useState(0);
  const analyticalResults=brief.sections.filter(s=>s.kind==='analyse'&&s.result).map(s=>s.result!);
  const analysis=analyticalResults.length?{...analyticalResults[0],
    ...brief.analysis_summary,
    metrics:brief.analysis_summary?.metrics??analyticalResults.flatMap(r=>r.metrics??[]),
    analytical_findings:analyticalResults.flatMap(r=>r.analytical_findings??[]),
    badges:brief.analysis_summary?.badges??analyticalResults.flatMap(r=>r.badges??[])}:undefined;
  const chapters = brief.sections.filter(s=>s.kind==='chapter');
  const authored = new Set(chapters.filter(s=>s.result?.paragraphs?.length && chapters.filter(c=>c.topic_id===s.topic_id).every(c=>c.result?.paragraphs?.length)).map(s=>s.topic_id));
  const sections = brief.sections.filter(s => s.result && !['compile','derive','collect','analyse'].includes(s.kind??'') && !(s.kind==='research'&&authored.has(s.topic_id)));
  const publishedIds=new Set(sections.filter(s=>s.kind==='publish').flatMap(s=>s.result?.paragraphs?.flatMap(p=>p.record_ids??[])??[]));
  const publicationChapters=brief.analysis_summary?.chapters;
  const unpublishedFindings=publicationChapters?[]:(analysis?.analytical_findings??[]).filter(f=>!publishedIds.has(f.id));
  const all = sections.flatMap(s => s.result!.claims.map(claim => ({claim, topic: s.id, title: s.title})));
  const synthesis = all.filter(c => c.topic === "synthesis");
  const analyticClaims=publicationChapters?publicationChapters.flatMap(c=>c.paragraphs.map(p=>({claim:{text:`${p.heading} — ${p.text}`,citations:p.citations},topic:c.id,title:c.title}))):[...new Map((analysis?.analytical_findings??[]).map(f=>{
    const published=sections.filter(s=>s.kind==='publish').flatMap(s=>s.result?.paragraphs??[]).find(p=>p.record_ids?.includes(f.id));
    return {claim:published?{text:`${published.heading} — ${published.text}`,citations:published.citations}:{text:`${f.headline} — ${f.explanation} ${f.business_implication}`,citations:f.citations},topic:'analysis',title:'Peer insights'};
  }).map(item=>[item.claim.text,item])).values()];
  const highlights = (analyticClaims.length?analyticClaims:synthesis.length ? synthesis : all).slice(0, 3);
  const displayFindings=analyticClaims.length?analyticClaims:all;
  const findings = displayFindings.filter(c => topic === "all" || c.topic === topic);
  const awards = brief.sections.flatMap(s => s.result?.awards ?? []);
  const metrics=(analysis?.metrics??awards).filter(m=>m.rows.length>0);
  const reports = library.reports.filter(r => brief.definition.report_ids.includes(r.id));
  const reported=[...new Map(brief.sections.filter(s=>s.kind==='collect').flatMap(s=>s.result?.facts??[]).map(f=>[JSON.stringify([f.company_id,f.metric,f.value,f.unit,f.year,f.population]),f])).values()];
  const readingSections=publicationChapters?publicationChapters.map(c=>({...c,result:{paragraphs:c.paragraphs,claims:[]}})):sections.filter(s=>s.result!.claims.length||s.result!.paragraphs?.length);
  return <>
    <nav className="workspace-tabs" aria-label="Analysis sections">{[["summary", "Summary"], ["report", "Report"], ["findings", "Findings"], ["figures", "Calculations"], ["promises", "Promises"], ["gaps", "Disclosure gaps"], ["sources", "Sources"]].map(([id, label]) => <button key={id} aria-pressed={tab === id} onClick={() => setTab(id)}>{label}</button>)}</nav>
    {tab === 'summary' && <><div className="research-dashboard" aria-label="Analysis summary">
      <DashboardStats metrics={metrics} primaryId={brief.primary_company_id} onMetric={setMetricIndex}/>
      <ComparisonChart metrics={metrics} selection={metricIndex} setSelection={setMetricIndex} open={open}/>
      {analysis&&<PeerAwards badges={analysis.badges??[]} open={open}/>}
      {analysis?.disclosure_scores&&<DisclosureCard scores={analysis.disclosure_scores}/>}
      {!analysis&&!metrics.length&&<section className="research-card research-half analytical-upgrade"><span className="report-eyebrow">Saved research</span><h2>Turn the findings into a benchmark.</h2><p>This saved version predates calculated metrics and awards.</p>{regenerate&&<button className="report-button" onClick={regenerate}>Create analytical report ↗</button>}</section>}
      <QuickActions brief={brief} ask={ask}/>
    </div><section className="research-reading"><header><h2>Selected findings</h2><button className="workspace-text-button" onClick={()=>setTab('report')}>Read the report ↗</button></header>{highlights.map((item,i)=><Finding key={`${item.topic}-${i}`} claim={item.claim} open={open} number={i+1}/>)}</section></>}
    {tab==='report'&&<div className="research-reading"><header><h2>Your report</h2><a className="report-button" href={exportLink(brief.id,'pdf')}>Download PDF ↓</a></header>{readingSections.map(section=><section key={section.id}><header><h2>{section.title}</h2></header>{section.result?.paragraphs?.length?section.result.paragraphs.map((p,i)=><article key={i}><h3>{p.heading}</h3><p>{p.text}</p>{p.citations.length>0&&<button className="workspace-text-button" onClick={()=>open(p.citations[0],p.citations.slice(1))}>View sources ↗</button>}</article>):section.result!.claims.map((claim,i)=><Finding key={i} claim={claim} open={open} number={i+1}/>)}</section>)}{unpublishedFindings.map(f=><article key={f.id}><h3>{f.headline}</h3><p>{f.explanation}</p><p>{f.business_implication}</p>{!!f.citations.length&&<button className="workspace-text-button" onClick={()=>open(f.citations[0],f.citations.slice(1))}>View sources ↗</button>}</article>)}{!!awards.length&&<AwardResults awards={awards} open={open}/>}</div>}
    {tab === "findings" && <section className="workspace-panel"><header><h2>Findings</h2>{!analysis&&<label className="workspace-select">Topic<select aria-label="Finding topic" value={topic} onChange={e => {setTopic(e.target.value); setPage(1);}}><option value="all">All topics ({all.length})</option>{sections.map(s => <option key={s.id} value={s.id}>{s.title} ({s.result!.claims.length})</option>)}</select></label>}</header>
      {findings.slice((page - 1) * 6, page * 6).map((item, i) => <Finding key={`${topic}-${page}-${i}`} claim={item.claim} open={open} number={(page - 1) * 6 + i + 1}/>)}
      {!findings.length && <p className="report-caption">No findings saved for this topic.</p>}
      <div className="report-pagination"><span>{findings.length} findings</span><div><button className="report-button" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</button><button className="report-button" disabled={page * 6 >= findings.length} onClick={() => setPage(p => p + 1)}>Next</button></div></div>
      <button className="report-button" onClick={() => ask(`Explain the reported differences in ${sections.find(s => s.id === topic)?.title.toLowerCase() ?? "these findings"} for these companies, with sources.`, brief.definition.company_ids)}>Explain these findings ↗</button>
    </section>}
    {tab === "figures" && <>{metrics.length>0&&<section className="workspace-panel"><label className="workspace-select">Explore a calculation<select aria-label="Calculation metric" value={metricIndex} onChange={e=>setMetricIndex(Number(e.target.value))}>{metrics.map((m,i)=><option key={m.id??i} value={i}>{m.name}</option>)}</select></label><AwardResults awards={[metrics[metricIndex]??metrics[0]]} open={open}/></section>}<details className="intelligence-details"><summary>Underlying reported figures</summary>{reported.length?<ReportedData facts={reported} open={open}/>:openSource&&<MetricFigures library={library} ids={brief.definition.company_ids} openSource={openSource}/>}</details></>}
    {tab==='promises'&&<PromiseRegister promises={analysis?.promises??[]} open={open}/>}
    {tab === "gaps" && (analysis?.disclosure_scores?<DisclosureCard scores={analysis.disclosure_scores} detail/>:<section className="workspace-panel"><header><h2>Disclosure gaps to investigate</h2></header><p className="report-caption">Topics identified for peers but not yet established for the primary company—not confirmed omissions.</p>
      {brief.review_opportunities.length ? brief.review_opportunities.map(g => <article className="workspace-gap" key={g.topic_id}><div><h3>{g.topic}</h3><p>{g.peer_evidence_count} / {g.peer_count} peers have cited evidence · {evidenceStates[g.primary_status]}</p></div><button className="report-button" onClick={() => ask(`Investigate ${g.topic.toLowerCase()} across these companies, including what the primary company reports.`, brief.definition.company_ids)}>Investigate this topic ↗</button></article>) : <p className="report-caption">No peer disclosure gaps identified in this analysis.</p>}
    </section>)}
    {tab === "sources" && <section className="workspace-panel"><header><h2>Source reports</h2><a className="workspace-text-button" href={exportLink(brief.id, "csv")}>Evidence CSV ↓</a></header><ReportCards reports={reports}/>
      {reports.length < brief.definition.report_ids.length && <p className="report-caption">Some historical documents are no longer in the current library. Their saved citations remain in the evidence export.</p>}
      <details className="intelligence-details"><summary>Evidence coverage</summary><div className="report-table-scroll"><table className="report-peer-table compact-table"><thead><tr><th>Topic</th>{brief.definition.companies.map(c => <th key={c.id}>{c.company_name}</th>)}</tr></thead><tbody>{brief.matrix.map(row => <tr key={row.topic_id}><th>{row.topic}</th>{row.cells.map(cell => <td key={cell.company_id}>{cell.sources.length ? <button className="workspace-text-button" onClick={() => open(cell.sources[0])}>{evidenceStates[cell.status]} ↗</button> : evidenceStates[cell.status]}</td>)}</tr>)}</tbody></table></div></details>
    </section>}
    <details className="intelligence-details analysis-record"><summary>Analysis details</summary><p>Saved {new Date(brief.created_at).toLocaleString("en-GB")} · {brief.completed_topics} of {brief.sections.length} steps completed · ${brief.estimated_cost_usd.toFixed(4)} estimated known AI usage.</p><p>{brief.cost_note}</p>{brief.sections.filter(s => s.status !== "completed").map(s => <p key={s.id}>{s.title}: {s.status}{s.error_code ? ` (${s.error_code})` : ""}</p>)}<a href={exportLink(brief.id, "json")}>Download analysis JSON</a></details>
  </>;
}
