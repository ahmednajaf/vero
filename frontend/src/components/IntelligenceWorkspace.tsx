import {useEffect, useRef, useState} from "react";
import {Link, useNavigation} from "../lib/navigation";
import {knowledge, KnowledgeError, type ReportLibrary, type Answer} from "../lib/knowledge";
import {evidenceStates, exportLink, getBriefing, listBriefings, topics, type Briefing, type BriefSummary, type Topic} from "../lib/briefings";
import {LibraryError, type AskReport, type OpenPassage} from "./ReportLibrary";
import "../intelligence-workspace.css";
import {MetricFigures} from "./MetricFigures";
import type {SourceSelection} from "../lib/benchmarks";

function SavedAnalyses({items}:{items:BriefSummary[]}) {
  return <div className="intelligence-saved">{items.map(item=><Link key={item.id} href={`/compare?briefing=${item.id}`}><strong>{item.title}</strong><span>{item.findings} findings · {item.completed_topics}/{item.topics} topics · {new Date(item.created_at).toLocaleDateString("en-GB")}</span><small>{item.status === "ready"?"Ready":item.status === "partial"?"Findings with limits":item.status === "failed"?"Needs attention":item.status === "running"?"In progress":"Continue analysis"} ↗</small></Link>)}</div>;
}

function Finding({claim, open}: {claim: Answer["claims"][number]; open: OpenPassage}) {
  const [expanded, setExpanded] = useState(false);
  const long = claim.text.length > 320;
  return <article className="intelligence-finding" data-expanded={!long || expanded}>
    <p>{claim.text}</p>
    {long && <button className="finding-expand" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? "Show less" : "Read full finding"}</button>}
    <div className="report-citations">{[...new Map(claim.citations.map(c=>[`${c.report_id}:${c.page}`,c])).values()].map(c=><button key={`${c.report_id}:${c.page}`} onClick={()=>open(c)} aria-label={`View source: ${c.company}, page ${c.page}`}>{c.company} · p. {c.page} ↗</button>)}</div>
  </article>;
}

export function CompanyIntelligence({companyId}:{companyId:string}) {
  const [items,setItems]=useState<BriefSummary[]>([]),[error,setError]=useState("");
  useEffect(()=>{const c=new AbortController();listBriefings(companyId,c.signal).then(r=>{if(!c.signal.aborted)setItems(r.items);}).catch(e=>{if(!c.signal.aborted)setError(e.message);});return()=>c.abort();},[companyId]);
  return <section className="intelligence-company"><div className="report-peer-actions"><h2>Company intelligence</h2><Link className="report-button solid" href={`/compare?company=${companyId}`}>Analyse company / add peers ↗</Link></div>{items.length?<SavedAnalyses items={items}/>:<p className="report-caption">Create a source-backed analysis of this company, on its own or against selected peers.</p>}{error&&<LibraryError message={error}/>}</section>;
}

export function IntelligenceOverview({library}:{library:ReportLibrary}) {
  const [items,setItems]=useState<BriefSummary[]>([]),[error,setError]=useState(""),[query,setQuery]=useState("");
  useEffect(()=>{const c=new AbortController();listBriefings(undefined,c.signal).then(r=>{if(!c.signal.aborted)setItems(r.items);}).catch(e=>{if(!c.signal.aborted)setError(e.message);});return()=>c.abort();},[]);
  const filtered=items.filter(i=>`${i.title} ${i.companies.map(c=>c.company_name).join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  return <><header className="report-page-heading"><div><span className="report-eyebrow">Your intelligence workspace</span><h1>Your workspace.</h1><p>Company analysis and peer comparisons.</p></div><Link className="report-button solid" href="/compare">New analysis ↗</Link></header>
    <div className="intelligence-coverage"><Link href="/companies"><strong>{library.status.companies_with_indexed_reports}</strong><span>companies with searchable reports</span></Link><Link href="/sources"><strong>{library.reports.length}</strong><span>retained source documents</span></Link><div><strong>{items.length}</strong><span>saved analyses (latest 50)</span></div></div>
    <div className="report-peer-actions"><h2>Saved insights & comparisons</h2><Link className="report-button" href="/sources">Source library ↗</Link></div><div className="report-filters"><input type="search" aria-label="Search saved analysis" placeholder="Find a company or analysis" value={query} onChange={e=>setQuery(e.target.value)}/></div>
    {error?<LibraryError message={error}/>:filtered.length?<SavedAnalyses items={filtered}/>:<p className="report-empty">{query?"No saved analyses match.":"Choose a company to build its analysis. Completed findings and their sources stay here, ready to reopen or export."}</p>}
    <details className="intelligence-details"><summary>What is covered?</summary><p>{library.companies.length} registered companies are not {library.companies.length} analysed companies. {library.status.companies_with_indexed_reports} currently have searchable reports. Reported figures retain their extraction and review status.</p><p>New source collection does not automatically rerun AI or change a saved result. Sources and reporting periods stay visible; partial findings remain useful without creating an overall rating.</p><Link href="/companies">Inspect report availability by company ↗</Link></details>
  </>;
}

export function PeerWorkspace({library,selected,setSelected,open,ask,openSource}:{library:ReportLibrary;selected:string[];setSelected:(ids:string[])=>void;open:OpenPassage;ask:AskReport;openSource?:(source:SourceSelection)=>void}) {
  const {search,navigate}=useNavigation();const params=new URLSearchParams(search);const id=params.get("briefing"),initialCompany=params.get("company");
  const [primary,setPrimary]=useState(initialCompany||selected[0]||"");
  const [query,setQuery]=useState(""),[sector,setSector]=useState(""),[focus,setFocus]=useState("");
  const [chosen,setChosen]=useState<Topic[]>(["emissions","energy","targets","assurance"]);
  const [brief,setBrief]=useState<Briefing|null>(null),[items,setItems]=useState<BriefSummary[]>([]),[error,setError]=useState("");
  const [busy,setBusy]=useState(false),[activeTopic,setActiveTopic]=useState<string|null>(null),[loading,setLoading]=useState(false);
  const [panel,setPanel]=useState("findings");
  const [topicView,setTopicView]=useState("");
  const generation=useRef(0),stop=useRef(false),mounted=useRef(true),currentId=useRef(id);
  currentId.current=id;
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;stop.current=true;generation.current++;};},[]);
  useEffect(()=>{listBriefings().then(r=>{if(mounted.current)setItems(r.items);}).catch(e=>{if(mounted.current)setError(e.message);});},[id]);
  useEffect(()=>{if(initialCompany){setPrimary(initialCompany);setSelected([initialCompany,...selected.filter(s=>s!==initialCompany)].slice(0,5));}},[initialCompany]); // URL is an explicit company action.
  useEffect(()=>{
    if(!id){setBrief(null);setError("");return;}
    const c=new AbortController();setLoading(true);setError("");setBrief(existing=>existing?.id===id?existing:null);
    getBriefing(id,c.signal).then(r=>{if(!c.signal.aborted){setBrief(r);setPrimary(r.primary_company_id);setSelected(r.definition.company_ids);}}).catch(e=>{if(!c.signal.aborted)setError(e.message);}).finally(()=>{if(!c.signal.aborted)setLoading(false);});
    return()=>c.abort();
  },[id]);
  // Read-only progress refresh also recovers a disconnected browser. No automatic inference.
  useEffect(()=>{if(!brief||brief.status!=="running"||busy)return;const c=new AbortController();const timer=setInterval(()=>{getBriefing(brief.id,c.signal).then(r=>{if(mounted.current&&!c.signal.aborted&&currentId.current===r.id)setBrief(r);}).catch(()=>{});},3000);return()=>{clearInterval(timer);c.abort();};},[brief?.id,brief?.status,busy]);
  const ids=[primary,...selected.filter(x=>x!==primary)].filter(Boolean).slice(0,5);
  const companies=ids.map(i=>library.companies.find(c=>c.id===i)).filter(c=>!!c);
  const matches=library.companies.filter(c=>!ids.includes(c.id)&&(!sector||c.sector===sector)&&(!query||`${c.company_name} ${c.ticker}`.toLowerCase().includes(query.toLowerCase()))).sort((a,b)=>b.reports_indexed-a.reports_indexed||a.company_name.localeCompare(b.company_name)).slice(0,8);
  async function run(start:Briefing) {
    const runGeneration=++generation.current;stop.current=false;setBusy(true);setError("");let result=start;
    try {
      while(result.can_resume&&!stop.current){
        const section=result.sections.find(s=>s.status!=="completed");setActiveTopic(section?.title??null);
        result=await knowledge<Briefing>(`/knowledge/briefings/${result.id}/advance`,{});
        if(!mounted.current||generation.current!==runGeneration||currentId.current!==result.id)return;
        setBrief(result);
        if(result.status==="failed"){const failed=result.sections.find(s=>s.error_code);setError(new KnowledgeError(failed?.error_code||"briefing_processing_failed").message);break;}
      }
    } catch(e) {if(mounted.current&&generation.current===runGeneration&&currentId.current===result.id)setError((e as Error).message);}
    finally{if(mounted.current&&generation.current===runGeneration){setBusy(false);setActiveTopic(null);}}
  }
  async function create() {
    const createGeneration=++generation.current;setBusy(true);setError("");
    try {const created=await knowledge<Briefing>("/knowledge/briefings",{primary_company_id:primary,peer_ids:ids.filter(i=>i!==primary),topics:chosen,focus});if(!mounted.current||generation.current!==createGeneration)return;setBrief(created);navigate(`/compare?briefing=${created.id}`);await run(created);}
    catch(e){if(mounted.current&&generation.current===createGeneration){setError((e as Error).message);setBusy(false);}}
  }
  function newAnalysis(){stop.current=true;generation.current++;setBusy(false);setBrief(null);navigate("/compare");}
  const missing=companies.filter(c=>!c.reports_indexed);
  const completedSections = brief?.sections.filter(s=>s.result) ?? [];
  const shownSection = completedSections.find(s=>s.id===topicView) ?? completedSections[0];
  if(loading&&!brief)return <p className="report-empty" role="status">Opening saved analysis…</p>;
  return <><header className="report-page-heading"><div><span className="report-eyebrow">Company & peer intelligence</span><h1>{brief?brief.title:"Understand the differences."}</h1><p>{brief?`${brief.definition.companies.length} ${brief.definition.companies.length===1?"company":"companies"} · ${brief.completed_topics}/${brief.sections.length} topics analysed · ${brief.findings_count} source-backed findings`:"Choose a company, add peers, and explore the topics that matter."}</p></div>{brief&&<button className="report-button" disabled={busy} onClick={newAnalysis}>New analysis</button>}</header>
    {error&&<LibraryError message={error} retry={id?()=>{void getBriefing(id).then(setBrief).catch(e=>setError(e.message));}:undefined}/>}
    {!brief&&!id?<><div className="report-controls intelligence-setup"><label className="report-select">Primary company<select aria-label="Primary company" value={primary} onChange={e=>{setPrimary(e.target.value);setSelected([e.target.value,...selected.filter(i=>i!==primary&&i!==e.target.value)].filter(Boolean).slice(0,5));}}><option value="">Choose a company</option>{library.companies.map(c=><option value={c.id} key={c.id}>{c.company_name}{!c.reports_indexed?" · report unavailable":""}</option>)}</select></label><div><span className="report-caption">Peers · optional, up to four</span><div className="report-topic-actions">{companies.filter(c=>c.id!==primary).map(c=><button className="report-button" key={c.id} onClick={()=>setSelected(ids.filter(i=>i!==c.id))}>{c.company_name} ×</button>)}</div><div className="report-filters"><input type="search" aria-label="Find peers" placeholder="Company or ticker" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="Peer sector" value={sector} onChange={e=>setSector(e.target.value)}><option value="">All sectors</option>{[...new Set(library.companies.map(c=>c.sector))].sort().map(s=><option key={s}>{s}</option>)}</select></div><div className="report-peer-matches">{matches.map(c=><button className="report-button" key={c.id} disabled={!primary||ids.length>=5} onClick={()=>{setSelected([...ids,c.id]);setQuery("");}}>{c.company_name}{!c.reports_indexed?" · no report":""} ＋</button>)}</div></div></div>
      <fieldset className="intelligence-topics"><legend>Topics</legend>{Object.entries(topics).map(([key,label])=><label key={key}><input type="checkbox" checked={chosen.includes(key as Topic)} onChange={()=>setChosen(chosen.includes(key as Topic)?chosen.filter(k=>k!==key):[...chosen,key as Topic])}/>{label}</label>)}</fieldset>
      <label className="intelligence-focus">What else matters to you? <span>Optional</span><input aria-label="Analysis focus" maxLength={350} placeholder="For example, supplier engagement or changes since the previous year" value={focus} onChange={e=>setFocus(e.target.value)}/></label>
      {!!missing.length&&<p className="report-library-notice">No searchable report for {missing.map(c=>c.company_name).join(", ")}. You can analyse the available evidence; these companies will remain explicit gaps.</p>}
      {library.status.research.configuration_error&&<LibraryError message={new KnowledgeError(library.status.research.configuration_error).message}/>}
      <div className="report-peer-actions"><button className="report-button solid" disabled={busy||!primary||!chosen.length||!companies.some(c=>c.reports_indexed)||!!library.status.research.configuration_error} onClick={()=>void create()}>Generate analysis ↗</button><span>Up to {chosen.length*2} AI calls · existing ${library.status.research.monthly_budget_usd} monthly app limit · saved automatically</span></div>
      {!!items.length&&<><h2 className="report-section-heading">Reopen saved work</h2><SavedAnalyses items={items}/></>}
    </>:brief?<>
      {!brief.sources_current&&<p role="alert" className="report-library-notice">A source has changed. This is a historical analysis; start a new one before treating it as current.</p>}
      {!!brief.new_reports_available&&<p className="report-library-notice">{brief.new_reports_available} additional searchable reports are now available for this group. Start a new analysis to include them; this saved result is unchanged.</p>}
      <div className="intelligence-stage" role="status">{busy?`Researching ${activeTopic??"selected reports"}…`:brief.status==="running"?"Research is running. Progress is saved on the server.":brief.status==="ready"?"Analysis complete":brief.status==="partial"?"Analysis complete · some questions remain unresolved":"Progress saved"}</div>
      <ol className="intelligence-steps">{brief.sections.map(s=><li key={s.id} data-state={s.status}><span>{s.status==="completed"?"✓":s.status==="failed"?"!":"○"}</span>{s.title}</li>)}</ol>
      <div className="report-peer-actions">{busy?<button className="report-button" onClick={()=>{stop.current=true;}}>Pause after this topic</button>:brief.can_resume&&brief.sources_current&&<button className="report-button solid" onClick={()=>void run(brief)}>Continue unfinished topics</button>}<a className="report-button" href={exportLink(brief.id,"html")}>Export briefing ↓</a><a className="report-button" href={exportLink(brief.id,"csv")}>Evidence CSV ↓</a><a className="report-button" href={exportLink(brief.id,"json")}>Data JSON ↓</a><Link className="report-button" href={`/sources?company=${brief.primary_company_id}`}>Source reports ↗</Link></div>
      <div className="report-view-tabs" aria-label="Analysis sections">{[["findings","Findings"],["evidence","Evidence coverage"],["gaps","Gaps to investigate"]].map(([key,label])=><button key={key} aria-pressed={panel===key} onClick={()=>setPanel(key)}>{label}</button>)}</div>
      {panel==="findings"?<div className="intelligence-findings"><div className="report-view-tabs" aria-label="Finding topics">{completedSections.map(s=><button key={s.id} aria-pressed={shownSection?.id===s.id} onClick={()=>setTopicView(s.id)}>{s.title} <small>{s.result!.claims.length}</small></button>)}</div>{(shownSection ? [shownSection] : []).map(section=><section key={section.id}><header><h2>{section.title}</h2><button className="report-button" onClick={()=>ask(`Explain the most important reported differences in ${section.title.toLowerCase()} for these companies. Distinguish measured results from commitments and cite the evidence.`,brief.definition.company_ids)}>Explore with Sustainobot ↗</button></header>{section.result!.claims.length?section.result!.claims.map((claim,i)=><Finding key={`${section.id}-${i}`} claim={claim} open={open}/>):<p className="report-caption">No supported finding established from the retrieved passages. This is not a finding of non-disclosure.</p>}{!!section.result!.notes?.length&&<details className="intelligence-details"><summary>Scope & comparison notes</summary>{section.result!.notes.map(n=><p key={n}>{n}</p>)}</details>}</section>)}</div>:panel==="evidence"?<><p className="report-caption">Evidence cited in this analysis—not a disclosure-completeness score. Each cell links to its source.</p><div className="report-table-scroll"><table className="report-peer-table"><thead><tr><th>Topic</th>{brief.definition.companies.map(c=><th key={c.id}><Link href={`/companies/${c.id}`}>{c.company_name}</Link></th>)}</tr></thead><tbody>{brief.matrix.map(row=><tr key={row.topic_id}><th>{row.topic}</th>{row.cells.map(cell=><td key={cell.company_id}>{cell.sources.length?<button className="report-value" onClick={()=>open(cell.sources[0])}>{evidenceStates[cell.status]} ↗</button>:evidenceStates[cell.status]}</td>)}</tr>)}</tbody></table></div></>:<><p className="report-caption">Topics with peer evidence but no cited finding for your primary company. These are review opportunities, not confirmed omissions.</p>{brief.review_opportunities.length?brief.review_opportunities.map(g=><section className="intelligence-gap" key={g.topic_id}><h2>{g.topic}</h2><p>Evidence cited for {g.peer_evidence_count} / {g.peer_count} selected peers. Your company: {evidenceStates[g.primary_status].toLowerCase()}.</p><div className="report-citations">{g.sources.map(s=><button key={s.evidence_id} onClick={()=>open(s)}>{s.company} · p. {s.page} ↗</button>)}</div><button className="report-button" onClick={()=>ask(`Investigate what this company explicitly reports about ${g.topic.toLowerCase()}. Look for evidence before concluding information is missing.`,[brief.primary_company_id])}>Investigate this topic ↗</button></section>):<p className="report-empty">No peer-evidence gaps identified in the completed topics. This does not establish complete disclosure.</p>}</>}
      {!brief.completed_topics&&<p className="report-empty">Findings appear here as each topic finishes. You can leave and reopen this analysis; only unfinished topics need to run.</p>}
      <details className="intelligence-details"><summary>Analysis record & export details</summary><p>Created {new Date(brief.created_at).toLocaleString("en-GB")} · {brief.definition.report_ids.length} frozen source documents · ${brief.estimated_cost_usd.toFixed(4)} estimated known usage.</p><p>{brief.cost_note} Reopening and exporting do not call the model. Open the HTML briefing and use Print → Save as PDF for a portable copy.</p><p>AI-assisted analysis is not an independent ESG rating. Quotes and numbers are mechanically checked; interpretation can still be wrong.</p></details>
    </>:id&&!loading?<button className="report-button" onClick={newAnalysis}>Start a new analysis</button>:null}
    {openSource && <MetricFigures library={library} ids={brief?.definition.company_ids ?? ids} openSource={openSource}/>}
  </>;
}
