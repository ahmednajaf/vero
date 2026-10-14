import {useEffect, useRef, useState} from "react";
import {Link, useNavigation} from "../lib/navigation";
import {knowledge, KnowledgeError, analysisLimitErrors, type LibraryStatus, type ReportLibrary} from "../lib/knowledge";
import {exportLink, getBriefing, listBriefings, topics, type Briefing, type BriefSummary, type Topic} from "../lib/briefings";
import {LibraryError, type AskReport, type OpenPassage} from "./ReportLibrary";
import "../intelligence-workspace.css";
import {AnalysisDashboard} from "./AnalysisDashboard";
import type {SourceSelection} from "../lib/benchmarks";
import {ReportFolder} from './ui/report-folder';
import {PressDepth} from './ui/press-depth';
import {ArrowUpRight, Plus, Search, Library, Layers3} from 'lucide-react';

function SavedAnalyses({items}:{items:BriefSummary[]}) {
  return <div className="intelligence-saved">{items.map(item=><Link key={item.id} href={`/workspace/analysis?briefing=${item.id}`}><strong>{item.title}</strong><span>{item.findings} findings · {item.completed_topics}/{item.topics} topics · {new Date(item.created_at).toLocaleDateString("en-GB")}</span><small>{item.status === "ready"?"Ready":item.status === "partial"?"Ready · coverage notes":item.status === "failed"?"Needs attention":item.status === "running"?"In progress":"Continue analysis"} ↗</small></Link>)}</div>;
}

export function CompanyIntelligence({companyId}:{companyId:string}) {
  const [items,setItems]=useState<BriefSummary[]>([]),[error,setError]=useState("");
  useEffect(()=>{const c=new AbortController();listBriefings(companyId,c.signal).then(r=>{if(!c.signal.aborted)setItems(r.items);}).catch(e=>{if(!c.signal.aborted)setError(e.message);});return()=>c.abort();},[companyId]);
  return <section className="intelligence-company"><div className="report-peer-actions"><h2>Company intelligence</h2><Link className="report-button solid" href={`/workspace/new?company=${companyId}`}>Analyse company / add peers ↗</Link></div>{items.length?<SavedAnalyses items={items}/>:<p className="report-caption">Create a source-backed analysis of this company, on its own or against selected peers.</p>}{error&&<LibraryError message={error}/>}</section>;
}

export function IntelligenceOverview({library}:{library:ReportLibrary}) {
  const {navigate}=useNavigation();
  const [items,setItems]=useState<BriefSummary[]>([]),[error,setError]=useState(""),[query,setQuery]=useState("");
  const [loading,setLoading]=useState(true);
  useEffect(()=>{const c=new AbortController();listBriefings(undefined,c.signal).then(r=>{if(!c.signal.aborted)setItems(r.items);}).catch(e=>{if(!c.signal.aborted)setError(e.message);}).finally(()=>{if(!c.signal.aborted)setLoading(false);});return()=>c.abort();},[]);
  const filtered=items.filter(i=>`${i.title} ${i.companies.map(c=>c.company_name).join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  const ready=filtered.filter(i=>['ready','partial'].includes(i.status));
  return <><header className="report-page-heading"><div><span className="report-eyebrow">Research studio</span><h1>Your reports.</h1><p>Open an edition or start a new peer analysis.</p></div><PressDepth onClick={()=>navigate('/workspace/new')}><Plus size={16}/>New analysis</PressDepth></header>
    <section className="studio-editions"><header><div><h2>Saved analyses</h2><span>{loading?"Opening your reports…":`${items.length} editions in your workspace`}</span></div><label className="studio-search"><Search size={16}/><input type="search" aria-label="Search saved analysis" placeholder="Find an analysis…" value={query} onChange={e=>setQuery(e.target.value)}/></label></header>
    {error?<LibraryError message={error}/>:loading?<p className="report-empty" role="status">Opening saved reports…</p>:filtered.length?<><div className="studio-edition-grid">{ready.slice(0,3).map(item=><article className="studio-edition" key={item.id}><ReportFolder id={item.id} label={item.title.includes("Company benchmark")?"Company benchmark":item.title.includes("Sector")?"Sector intelligence":"Peer analysis"} meta={`${item.companies.length} companies · saved ${new Date(item.created_at).toLocaleDateString("en-GB",{day:"numeric",month:"short"})}`} onOpen={()=>navigate(`/workspace/analysis?briefing=${item.id}`)}/><div className="studio-edition-caption"><Link href={`/workspace/analysis?briefing=${item.id}`}><h3>{item.title}</h3></Link><p>{item.companies.map(c=>c.company_name).join(' · ')}</p></div></article>)}</div>{filtered.some(i=>!ready.slice(0,3).includes(i))&&<details className="studio-history"><summary>More saved analyses</summary><SavedAnalyses items={filtered.filter(i=>!ready.slice(0,3).includes(i))}/></details>}</>:<p className="report-empty">{query?'No saved analyses match.':'Choose your companies to create your first report.'}</p>}
    </section><div className="studio-shortcuts"><Link href="/workspace/library"><Library/><div><strong>Company & report library</strong><span>{library.status.companies_with_indexed_reports} companies with searchable reports</span></div><ArrowUpRight/></Link><Link href="/pricing"><Layers3/><div><strong>A report built around your questions</strong><span>Company benchmark or sector intelligence</span></div><ArrowUpRight/></Link></div>
  </>;
}

export function PeerWorkspace({library,selected,setSelected,open,ask,openSource}:{library:ReportLibrary;selected:string[];setSelected:(ids:string[])=>void;open:OpenPassage;ask:AskReport;openSource?:(source:SourceSelection)=>void}) {
  const {search,navigate}=useNavigation();const params=new URLSearchParams(search);const id=params.get("briefing"),initialCompany=params.get("company");
  const [primary,setPrimary]=useState(initialCompany||selected[0]||"");
  const [query,setQuery]=useState(""),[sector,setSector]=useState(library.companies.find(c=>c.id===primary)?.sector??""),[focus,setFocus]=useState("");
  const [chosen,setChosen]=useState<Topic[]>(Object.keys(topics) as Topic[]);
  const [packageType,setPackageType]=useState<'company'|'sector'>('company');
  const [brief,setBrief]=useState<Briefing|null>(null),[error,setError]=useState("");
  const [busy,setBusy]=useState(false),[activeTopic,setActiveTopic]=useState<string|null>(null),[loading,setLoading]=useState(false);
  const [showResults,setShowResults]=useState(false);
  const [research,setResearch]=useState(library.status.research);
  const limitCode=brief?.sections.find(s=>s.error_code&&analysisLimitErrors.has(s.error_code))?.error_code;
  const budgetPaused=!!limitCode&&!busy;
  const usage=research.usage;
  const allowanceExhausted=!!usage&&(Number(usage.monthly_remaining_usd)<=0||usage.daily_tokens_remaining<=0);
  useEffect(()=>{
    if(id&&!limitCode)return;
    const controller=new AbortController();
    knowledge<LibraryStatus>('/knowledge/status',undefined,controller.signal).then(r=>{if(!controller.signal.aborted)setResearch(r.research);}).catch(()=>{});
    return()=>controller.abort();
  },[id,limitCode]);
  const generation=useRef(0),stop=useRef(false),mounted=useRef(true),currentId=useRef(id);
  currentId.current=id;
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;stop.current=true;generation.current++;};},[]);
  useEffect(()=>{if(initialCompany){setPrimary(initialCompany);setSelected([initialCompany,...selected.filter(s=>s!==initialCompany)].slice(0,5));}},[initialCompany]); // URL is an explicit company action.
  useEffect(()=>{
    if(!id){setBrief(null);setError("");return;}
    const c=new AbortController();setLoading(true);setError("");setBrief(existing=>existing?.id===id?existing:null);
    getBriefing(id,c.signal).then(r=>{if(!c.signal.aborted){setBrief(r);setPrimary(r.primary_company_id);setSelected(r.definition.company_ids);setPackageType(r.definition.package??'company');setFocus(r.definition.focus);}}).catch(e=>{if(!c.signal.aborted)setError(e.message);}).finally(()=>{if(!c.signal.aborted)setLoading(false);});
    return()=>c.abort();
  },[id]);
  // Read-only progress refresh also recovers a disconnected browser. No automatic inference.
  useEffect(()=>{if(!brief||!["running","pending"].includes(brief.status)||busy)return;const c=new AbortController();const timer=setInterval(()=>{getBriefing(brief.id,c.signal).then(r=>{if(mounted.current&&!c.signal.aborted&&currentId.current===r.id)setBrief(r);}).catch(()=>{});},3000);return()=>{clearInterval(timer);c.abort();};},[brief?.id,brief?.status,busy]);
  const maxCompanies=packageType==='sector'?20:5;
  const ids=[primary,...selected.filter(x=>x!==primary)].filter(Boolean).slice(0,maxCompanies);
  const companies=ids.map(i=>library.companies.find(c=>c.id===i)).filter(c=>!!c);
  const matches=library.companies.filter(c=>!ids.includes(c.id)&&(!sector||c.sector===sector)&&(!query||`${c.company_name} ${c.ticker}`.toLowerCase().includes(query.toLowerCase()))).sort((a,b)=>b.reports_indexed-a.reports_indexed||a.company_name.localeCompare(b.company_name)).slice(0,8);
  async function run(start:Briefing) {
    const runGeneration=++generation.current;stop.current=false;setBusy(true);setShowResults(false);setError("");let result=start;
    try {
      while(result.can_resume&&!stop.current){
        const section=result.sections.find(s=>s.status!=="completed");setActiveTopic(section?.title??null);
        result=await knowledge<Briefing>(`/knowledge/briefings/${result.id}/advance`,{});
        if(!mounted.current||generation.current!==runGeneration||currentId.current!==result.id)return;
        setBrief(result);
        if(result.status==="failed"||result.status==="paused"){const failed=result.sections.find(s=>s.error_code);if(!analysisLimitErrors.has(failed?.error_code??''))setError(new KnowledgeError(failed?.error_code||"briefing_processing_failed").message);break;}
      }
    } catch(e) {if(mounted.current&&generation.current===runGeneration&&currentId.current===result.id)setError((e as Error).message);}
    finally{if(mounted.current&&generation.current===runGeneration){setBusy(false);setActiveTopic(null);}}
  }
  async function create() {
    const createGeneration=++generation.current;setBusy(true);setError("");
    try {const created=await knowledge<Briefing>("/knowledge/briefings",{primary_company_id:primary,peer_ids:ids.filter(i=>i!==primary),topics:chosen,focus,package:packageType});if(!mounted.current||generation.current!==createGeneration)return;setBrief(created);currentId.current=created.id;setShowResults(false);navigate(`/workspace/analysis?briefing=${created.id}`);await run(created);}
    catch(e){if(mounted.current&&generation.current===createGeneration){setError((e as Error).message);setBusy(false);}}
  }
  function newAnalysis(){stop.current=true;generation.current++;setBusy(false);setBrief(null);navigate("/workspace/new");}
  const missing=companies.filter(c=>!c.reports_indexed);
  const finished = brief && ["ready", "partial"].includes(brief.status);
  const processing = !!brief && (busy || (!finished && !showResults));
  if(loading&&!brief)return <p className="report-empty" role="status">Opening saved analysis…</p>;
  return <>
    {error&&<LibraryError message={error} retry={id?()=>{void getBriefing(id).then(setBrief).catch(e=>setError(e.message));}:undefined}/>}
    {!brief&&!id ? <>
      <header className="report-page-heading"><div><span className="report-eyebrow">New report</span><h1>Choose your peer group.</h1><p>AI research, calculated comparisons and a written report.</p></div></header>
      <div className="workspace-panel studio-setup">
        <label className="workspace-select">Report package<select aria-label="Report package" value={packageType} onChange={e=>{setPackageType(e.target.value as 'company'|'sector');if(e.target.value==='company')setSelected(selected.slice(0,5));}}><option value="company">Company benchmark · up to 5 companies</option><option value="sector">Sector intelligence · up to 20 companies</option></select></label>
        <div className="report-controls intelligence-setup">
          <label className="report-select">Your company<select aria-label="Primary company" value={primary} onChange={e=>{setPrimary(e.target.value);setSector(library.companies.find(c=>c.id===e.target.value)?.sector??"");setSelected([e.target.value,...selected.filter(i=>i!==primary&&i!==e.target.value)].filter(Boolean).slice(0,maxCompanies));}}><option value="">Choose a company</option>{library.companies.map(c=><option value={c.id} key={c.id}>{c.company_name}{!c.reports_indexed?" · report unavailable":""}</option>)}</select></label>
          <div><span className="report-caption">Peers · up to {maxCompanies - 1}</span><div className="report-topic-actions">{companies.filter(c=>c.id!==primary).map(c=><button className="report-button" key={c.id} onClick={()=>setSelected(ids.filter(i=>i!==c.id))}>{c.company_name} ×</button>)}</div>{ids.length<maxCompanies&&<><div className="report-filters"><input type="search" aria-label="Find peers" placeholder="Company or ticker" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="Peer sector" value={sector} onChange={e=>setSector(e.target.value)}><option value="">All sectors</option>{[...new Set(library.companies.map(c=>c.sector))].sort().map(s=><option key={s}>{s}</option>)}</select></div><div className="report-peer-matches">{matches.map(c=><button className="report-button" key={c.id} disabled={!primary||ids.length>=maxCompanies} onClick={()=>{setSelected([...ids,c.id]);setQuery("");}}>{c.company_name}{!c.reports_indexed?" · no report":""} ＋</button>)}</div></>}</div>
        </div>
        <details className="studio-topics" open={false}><summary>Research topics <span>{chosen.length} selected</span></summary><fieldset className="intelligence-topics"><legend>What would you like to explore?</legend>{Object.entries(topics).map(([key,label])=><label key={key}><input type="checkbox" checked={chosen.includes(key as Topic)} onChange={()=>setChosen(chosen.includes(key as Topic)?chosen.filter(k=>k!==key):[...chosen,key as Topic])}/>{label}</label>)}</fieldset></details>
        <label className="intelligence-focus">Any particular question? <span>Optional</span><input aria-label="Analysis focus" maxLength={350} placeholder="For example, who is investing most in workforce skills?" value={focus} onChange={e=>setFocus(e.target.value)}/></label>
        {!!missing.length&&<p className="report-library-notice">No searchable report for {missing.map(c=>c.company_name).join(", ")}. They will appear as gaps in this analysis.</p>}
        {library.status.research.configuration_error&&<LibraryError message={new KnowledgeError(library.status.research.configuration_error).message}/>}
        {usage&&<p className="report-caption" role="status">AI allowance: ${Number(usage.monthly_remaining_usd).toFixed(2)} remaining of ${research.monthly_budget_usd.toFixed(2)} this month.{allowanceExhausted?' Allowance exhausted; update the app limit before generating.':Number(usage.monthly_remaining_usd)<1?' Low allowance — an analysis may pause before finishing.':''}</p>}
        <div className="report-peer-actions"><PressDepth disabled={busy||!primary||!chosen.length||!companies.some(c=>c.reports_indexed)||!!library.status.research.configuration_error||allowanceExhausted} onClick={()=>void create()}>{busy?"Preparing…":"Generate analysis ↗"}</PressDepth><span>{companies.length} companies · {chosen.length} topics · saved automatically</span></div>
        <details className="intelligence-details"><summary>Research & AI usage</summary><p>Read each company's reports, discover cross-company relationships, calculate the metrics, then write the report. Each step is saved within the existing ${library.status.research.monthly_budget_usd} monthly app limit. Reopening or exporting makes no model calls.</p></details>
      </div>
    </> : brief ? <>
      {!brief.sources_current&&<p role="alert" className="report-library-notice">A source has changed. This is a historical analysis; start a new one to include current reports.</p>}
      {processing ? <section className="analysis-progress" aria-label="Analysis progress">
        <div className={busy || brief.status==="running" ? "analysis-spinner" : "analysis-paused"} aria-hidden="true">{!busy&&brief.status!=="running"?"Ⅱ":""}</div>
        <span className="report-eyebrow">{brief.definition.company_ids.length} companies · {brief.definition.report_ids.length} reports</span>
        <h1>{budgetPaused?"Analysis paused · allowance reached":brief.status==="failed"&&!busy?"Analysis needs attention":busy||brief.status==="running"?"Building your analysis.":"Your progress is saved."}</h1>
        <p role="status">{busy ? `Researching ${activeTopic ?? "selected reports"}…` : budgetPaused ? new KnowledgeError(limitCode!).message : brief.status==="running" ? "Processing the current topic…" : brief.status==="failed" ? new KnowledgeError(brief.sections.find(s=>s.error_code)?.error_code || "briefing_processing_failed").message : "Continue when you’re ready."}</p>
        {budgetPaused&&usage&&<p className="report-caption">${Number(usage.monthly_accounted_usd).toFixed(2)} of ${research.monthly_budget_usd.toFixed(2)} accounted for across Vero this month, including ${Number(usage.monthly_reserved_usd).toFixed(2)} reserved for calls with an uncertain outcome. {usage.daily_tokens_remaining.toLocaleString()} tokens remain in today’s app allowance.</p>}
        <span className="report-caption">{brief.completed_topics} of {brief.sections.length} {brief.definition.package?'steps':'topics'} completed</span>
        <div className="report-actions">{busy ? <button className="report-button" onClick={()=>{stop.current=true;}}>Pause after this topic</button> : brief.can_resume&&brief.sources_current&&brief.status!=="running"&&<button className="report-button solid" onClick={()=>void run(brief)}>Continue unfinished topics</button>}{!busy&&brief.findings_count>0&&<button className="report-button" onClick={()=>setShowResults(true)}>View saved findings</button>}</div>
        <details className="intelligence-details"><summary>Processing details</summary><ol className="analysis-stage-list">{brief.sections.map(s=><li key={s.id}><span>{s.title}</span><span>{s.status.replaceAll("_"," ")}</span></li>)}</ol></details>
      </section> : <>
        <header className="report-page-heading"><div><span className="report-eyebrow">{brief.definition.package==='sector'?'Sector intelligence':'Peer analysis'} · {new Date(brief.created_at).toLocaleDateString("en-GB")}</span><h1>{brief.title}</h1></div><div className="report-actions"><a className="report-button solid" href={exportLink(brief.id,"xlsx")}>Export for Excel ↓</a><button className="report-button" onClick={newAnalysis}>New analysis</button></div></header>
        {brief.can_resume&&<p role="status" className="report-caption">{brief.status==='running'?'Analysis in progress':brief.status==='failed'?'Analysis needs attention':'Analysis paused'} · {brief.completed_topics}/{brief.sections.length} steps saved. <button className="workspace-text-button" onClick={()=>setShowResults(false)}>View progress ↗</button></p>}
        <AnalysisDashboard key={brief.id} brief={brief} library={library} open={open} ask={ask} openSource={openSource} regenerate={newAnalysis}/>
      </>}
    </> : id&&!loading ? <button className="report-button" onClick={newAnalysis}>Start a new analysis</button> : null}
  </>;
}
