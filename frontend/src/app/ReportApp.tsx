import {useCallback, useEffect, useRef, useState} from "react";
import {GlassSidebar} from "../components/GlassSidebar";
import {SourceDrawer} from "../components/SourceDrawer";
import type {SourceSelection} from "../lib/benchmarks";
import {Link, NavigationProvider, useNavigation} from "../lib/navigation";
import "../intelligence.css";
import "../vero.css";
import "../report.css";
import "../liquid-glass.css";
import "../report-workspace.css";
import {ShaderBackground} from "../components/ShaderBackground";
import {RegionGlobe} from "../components/RegionGlobe";
import {loadReportLibrary, type Passage, type ReportLibrary} from "../lib/knowledge";
import {LibraryCompanyPage, LibraryDirectory, LibraryError, LibrarySources, passageSelection} from "../components/ReportLibrary";
import {Sustainobot, SustainobotLauncher} from "../components/Sustainobot";
import {CompanyIntelligence, IntelligenceOverview, PeerWorkspace} from "../components/IntelligenceWorkspace";
import {MetricFigures} from "../components/MetricFigures";
import {getBriefing} from "../lib/briefings";
import {Pricing, PackageEnquiry} from "../components/Pricing";
import {PanelsTopLeft, Library, Sparkles, ArrowLeft} from 'lucide-react';
import "../workspace-ui.css";

function Methodology() {
  return <section><header className="report-page-heading"><div><span className="report-eyebrow">How it works</span><h1>From reports to a clearer picture.</h1><p>Choose your peers. Explore the differences. Take the evidence with you.</p></div><Link className="report-button solid" href="/pricing">Explore packages ↗</Link></header>
    <div className="method-steps">
      <section className="workspace-panel"><span className="report-eyebrow">01 / Set the scope</span><h2>Start with your question.</h2><p>Choose a company, its peers and the topics that matter. We bring together annual, sustainability and supporting reports.</p></section>
      <section className="workspace-panel"><span className="report-eyebrow">02 / Discover the differences</span><h2>See what stands out.</h2><p>Vero connects disclosures across reports to surface peer differences, calculations, disclosure gaps and award candidates.</p></section>
      <section className="workspace-panel"><span className="report-eyebrow">03 / Use the findings</span><h2>Take it into your decisions.</h2><p>Explore the dashboard, ask follow-up questions and export findings with their source pages for Excel or a written briefing.</p></section>
    </div><section className="workspace-panel method-detail"><h2>A source behind every finding.</h2><p>Open a finding or figure to see the original report, page and excerpt.</p><details><summary>How are figures compared?</summary><p>Compatible units are converted automatically. Measurement years, emissions scopes and business boundaries stay attached to the figures, so unlike measurements are not silently combined.</p></details><details><summary>How are awards and scores calculated?</summary><p>Each calculated award shows its criterion, inputs, calculation and the companies included. There is no hidden overall ESG rating.</p></details><details><summary>What does AI do?</summary><p>AI finds relevant passages and proposes comparisons. Calculations use the reported inputs; citations let you check the reasoning. Missing evidence is not treated as zero.</p></details><details><summary>What happens after a package request?</summary><p>We agree the peer group, questions, reporting period and deliverables in a consultation. Client access follows that agreement. There is no online payment at this stage.</p></details></section>
  </section>;
}

export function ReportApp() {return <NavigationProvider><ReportWorkspace/></NavigationProvider>;}
function ReportWorkspace() {
  const {path, search, navigate} = useNavigation();
  const [attempt, setAttempt] = useState(0), [selected, setSelected] = useState<string[]>([]);
  const [source, setSource] = useState<SourceSelection | null>(null), [mobile, setMobile] = useState(false), [pinned, setPinned] = useState(false);
  const [library, setLibrary] = useState<ReportLibrary | null>(null), [libraryError, setLibraryError] = useState("");
  const [botOpen, setBotOpen] = useState(false), [botDraft, setBotDraft] = useState(""), [botCompanies, setBotCompanies] = useState<string[]>([]);
  const [botAnalysis, setBotAnalysis] = useState<string | null>(null);
  const [assistantLoading, setAssistantLoading] = useState(false), [assistantError, setAssistantError] = useState("");
  const routeRef = useRef(path + search); routeRef.current = path + search;
  const trigger = useRef<HTMLElement | null>(null);
  const close = useCallback(() => setSource(null), []), closeBot = useCallback(() => setBotOpen(false), []);
  const openSource = (value: SourceSelection) => {trigger.current = document.activeElement as HTMLElement; setSource(value);};
  const openPassage = (passage: Passage, related: Passage[] = []) => {
    const selection=passageSelection(passage);
    selection.evidence=[...(selection.evidence??[]),...related.flatMap(p=>passageSelection(p).evidence??[])];
    openSource(selection);
  };
  const ask = (question: string, ids: string[]) => {setBotDraft(question); setBotCompanies(ids); setBotAnalysis(new URLSearchParams(search).get('briefing')); setBotOpen(true);};
  async function openAssistant() {
    const route = path + search, analysisId = new URLSearchParams(search).get('briefing');
    setAssistantError("");
    if (analysisId) {
      setAssistantLoading(true);
      try {
        const analysis = await getBriefing(analysisId);
        if (routeRef.current !== route) return;
        setBotCompanies(analysis.definition.company_ids); setBotAnalysis(analysis.id);
        setBotDraft(""); setBotOpen(true);
      } catch (error) {if (routeRef.current === route) setAssistantError((error as Error).message);}
      finally {setAssistantLoading(false);}
    } else {
      setBotAnalysis(null); setBotCompanies(company ? [company.id] : selected);
      setBotDraft(""); setBotOpen(true);
    }
  }
  useEffect(() => {
    const c = new AbortController(); setLibraryError("");
    loadReportLibrary(c.signal).then(r => {if (!c.signal.aborted) setLibrary(r);}).catch(e => {if (!c.signal.aborted) setLibraryError(e.message);});
    return () => c.abort();
  }, [attempt]);
  useEffect(() => {setSource(null); window.scrollTo(0, 0); document.title = "Vero — Sustainability intelligence";}, [path]);
  useEffect(() => {if (path === "/edition") navigate("/workspace");}, [path, navigate]);
  const landing = path === "/", company = library?.companies.find(c => c.id === path.split("/")[2]);
  const params = new URLSearchParams(search);
  const workspaceRoute = ["/workspace", "/overview", "/insights", "/edition", "/companies", "/sources", "/compare"].includes(path) || path.startsWith("/workspace/") || path.startsWith("/companies/");
  const libraryRoute = ["/companies", "/sources", "/workspace/library"].includes(path);
  const reportsView = path === "/sources" || (path === "/workspace/library" && params.get("tab") === "reports");
  const workspaceNavigation = workspaceRoute ? <nav className="workspace-breadcrumb" aria-label="Workspace"><Link href="/workspace" aria-current={["/workspace","/overview","/insights"].includes(path)?"page":undefined}><PanelsTopLeft size={16}/>Workspace</Link><Link href="/workspace/library" aria-current={libraryRoute || company ? "page" : undefined}><Library size={16}/>Library</Link></nav> : <Link className="studio-back" href="/workspace"><ArrowLeft size={15}/>Workspace</Link>;
  let content;
  if (path === "/pricing") content = <Pricing/>;
  else if (path === "/contact") content = <PackageEnquiry/>;
  else if (path === "/methodology") content = <Methodology/>;
  else if (libraryError) content = <LibraryError message={libraryError} retry={() => setAttempt(n => n + 1)}/>;
  else if (!library) content = <p role="status" className="report-empty">Opening the company library…</p>;
  else if (["/workspace", "/overview", "/insights", "/edition"].includes(path)) content = <IntelligenceOverview library={library}/>;
  else if (libraryRoute) content = <><nav className="workspace-tabs" aria-label="Library views"><Link aria-current={!reportsView?"page":undefined} href="/workspace/library">Companies</Link><Link aria-current={reportsView?"page":undefined} href="/workspace/library?tab=reports">Reports</Link></nav>{reportsView ? <LibrarySources library={library} companyId={params.get("company") ?? undefined} open={openPassage} ask={ask}/> : <LibraryDirectory library={library} selected={selected} setSelected={setSelected}/>}</>;
  else if (["/compare", "/workspace/new", "/workspace/analysis"].includes(path)) content = <PeerWorkspace library={library} selected={selected} setSelected={setSelected} open={openPassage} ask={ask} openSource={openSource}/>;
  else if (company) content = <LibraryCompanyPage company={company} reports={library.reports.filter(r => r.company_id === company.id)} selected={selected} setSelected={setSelected} open={openPassage} ask={ask} figures={<MetricFigures key={company.id} library={library} ids={[company.id]} openSource={openSource}/>}>
    <CompanyIntelligence key={company.id} companyId={company.id}/>
  </LibraryCompanyPage>;
  else content = <section className="report-empty"><h1>This page has been retired.</h1><Link className="report-button" href="/workspace">Open your workspace ↗</Link></section>;
  return <div className="intelligence report-product" data-home={["/", "/overview", "/insights"].includes(path)} data-landing={landing}>
    <div inert={source || botOpen ? true : undefined}><a className="intel-skip-link" href="#workspace">Skip to content</a>
      <GlassSidebar reportView year={2025} selectedCount={selected.length} connection={libraryError ? "offline" : library ? "connected" : "loading"} onMobileOpenChange={setMobile} onPinnedChange={setPinned} onYearChange={() => navigate(path)}/>
      <main id="workspace" className="report-main" data-pinned={pinned} inert={mobile ? true : undefined}>
        <div className={landing ? "landing-silk-border" : "landing-silk-border report-inner-silk"} aria-hidden="true"><ShaderBackground/></div>
        <div className="report-topline"><span>GLOBAL SUSTAINABILITY INTELLIGENCE</span><span>VERO</span></div>
        {landing ? <section className="minimal-landing"><header className="minimal-intro"><h1>Explore company sustainability.</h1><p>Compare emissions, energy and climate commitments.</p><div className="landing-entry-links"><Link href="/pricing">Explore packages ↗</Link><Link href="/workspace">Open workspace ↗</Link></div></header><div className="report-globe-assistant"><RegionGlobe companies={library?.companies ?? []}/><SustainobotLauncher onOpen={() => setBotOpen(true)}/></div></section> : <><div className="studio-toolbar">{workspaceNavigation}{(params.get('briefing')||company)&&<div className="report-assistant-action"><button className="report-button" disabled={assistantLoading} onClick={() => void openAssistant()}><Sparkles size={15}/>{assistantLoading ? "Opening analysis…" : "Explore findings"}</button>{assistantError&&<p role="alert">{assistantError}</p>}</div>}</div>{content}<footer className="report-footer"><span>Vero · Sustainability intelligence</span><Link href="/methodology">How it works</Link><Link href="/pricing">Pricing</Link></footer></>}
        {landing && libraryError && <LibraryError message={libraryError} retry={() => setAttempt(n => n + 1)}/>}
      </main>
    </div>
    <Sustainobot workspace={!landing} open={botOpen} onClose={closeBot} companies={library?.companies ?? []} selected={botCompanies} onSelect={ids=>{setBotCompanies(ids);setBotAnalysis(null);}} analysisId={botAnalysis} onAnalysisChange={setBotAnalysis} draft={botDraft} setDraft={setBotDraft} openSource={openPassage} covered={!!source} configurationError={library?.status.research.configuration_error}/>
    {source && <SourceDrawer selection={source} onClose={close} returnFocusTo={trigger.current}/>}
  </div>;
}
