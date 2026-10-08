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
import {LibraryCompanyPage, LibraryDirectory, LibraryError, LibraryPeerComparison, LibrarySources, passageSelection} from "../components/ReportLibrary";
import {Sustainobot, SustainobotLauncher} from "../components/Sustainobot";
import {CompanyIntelligence, IntelligenceOverview, PeerWorkspace} from "../components/IntelligenceWorkspace";
import {MetricFigures} from "../components/MetricFigures";
import {Pricing} from "../components/Pricing";

function Methodology() {
  return <><header className="report-page-heading"><div><span className="report-eyebrow">Methodology</span><h1>Follow every figure to its source.</h1></div></header>
    <div className="report-method">
      <section><h2>Official reports</h2><p>Company-published PDFs are retained with source URLs, download dates and file fingerprints. Missing reports are shown explicitly.</p></section>
      <section><h2>Source-backed AI</h2><p>AI reads selected page-aware passages. Quotes, units, years and numbers are checked. AI interpretation can still be wrong.</p></section>
      <section><h2>Comparable when the evidence allows</h2><p>Electricity and energy, different emissions scopes, fiscal periods and reporting boundaries remain distinct. Reported figures are visible before review, with their status; they are not automatically ranked.</p></section>
      <section><h2>Gaps, not assumptions</h2><p>Not identified does not mean not disclosed. Missing is not zero. Targets are commitments, not achieved results. Vero is not an independent ESG rating or investment advice.</p></section>
    </div></>;
}

export function ReportApp() {return <NavigationProvider><ReportWorkspace/></NavigationProvider>;}
function ReportWorkspace() {
  const {path, search, navigate} = useNavigation();
  const [attempt, setAttempt] = useState(0), [selected, setSelected] = useState<string[]>([]);
  const [source, setSource] = useState<SourceSelection | null>(null), [mobile, setMobile] = useState(false), [pinned, setPinned] = useState(false);
  const [library, setLibrary] = useState<ReportLibrary | null>(null), [libraryError, setLibraryError] = useState("");
  const [botOpen, setBotOpen] = useState(false), [botDraft, setBotDraft] = useState(""), [botCompanies, setBotCompanies] = useState<string[]>([]);
  const trigger = useRef<HTMLElement | null>(null);
  const close = useCallback(() => setSource(null), []), closeBot = useCallback(() => setBotOpen(false), []);
  const openSource = (value: SourceSelection) => {trigger.current = document.activeElement as HTMLElement; setSource(value);};
  const openPassage = (passage: Passage, related: Passage[] = []) => {
    const selection=passageSelection(passage);
    selection.evidence=[...(selection.evidence??[]),...related.flatMap(p=>passageSelection(p).evidence??[])];
    openSource(selection);
  };
  const ask = (question: string, ids: string[]) => {setBotDraft(question); setBotCompanies(ids); setBotOpen(true);};
  useEffect(() => {
    const c = new AbortController(); setLibraryError("");
    loadReportLibrary(c.signal).then(r => {if (!c.signal.aborted) setLibrary(r);}).catch(e => {if (!c.signal.aborted) setLibraryError(e.message);});
    return () => c.abort();
  }, [attempt]);
  useEffect(() => {setSource(null); window.scrollTo(0, 0); document.title = "Vero — Sustainability intelligence";}, [path]);
  useEffect(() => {if (path === "/edition") navigate("/overview");}, [path, navigate]);
  const landing = path === "/", company = library?.companies.find(c => c.id === path.split("/")[2]);
  const sourceComparison = new URLSearchParams(search).get("view") === "reports";
  let content;
  if (path === "/pricing") content = <Pricing/>;
  else if (path === "/methodology") content = <Methodology/>;
  else if (libraryError) content = <LibraryError message={libraryError} retry={() => setAttempt(n => n + 1)}/>;
  else if (!library) content = <p role="status" className="report-empty">Opening the company library…</p>;
  else if (["/overview", "/insights", "/edition"].includes(path)) content = <IntelligenceOverview library={library}/>;
  else if (path === "/companies") content = <LibraryDirectory library={library} selected={selected} setSelected={setSelected}/>;
  else if (path === "/sources") content = <LibrarySources library={library} companyId={new URLSearchParams(search).get("company") ?? undefined} open={openPassage} ask={ask}/>;
  else if (path === "/compare") content = <>
    <div className="report-view-tabs" aria-label="Comparison view"><Link aria-current={!sourceComparison ? "page" : undefined} href="/compare">Company & peer analysis</Link><Link aria-current={sourceComparison ? "page" : undefined} href="/compare?view=reports">Source comparison</Link></div>
    {sourceComparison ? <LibraryPeerComparison library={library} selected={selected} setSelected={setSelected} open={openPassage} ask={ask}/> : <PeerWorkspace key={new URLSearchParams(search).get("company") ?? "workspace"} library={library} selected={selected} setSelected={setSelected} open={openPassage} ask={ask} openSource={openSource}/>}
  </>;
  else if (company) content = <LibraryCompanyPage company={company} reports={library.reports.filter(r => r.company_id === company.id)} selected={selected} setSelected={setSelected} open={openPassage} ask={ask}>
    <MetricFigures key={company.id} library={library} ids={[company.id]} openSource={openSource}/><CompanyIntelligence key={company.id} companyId={company.id}/>
  </LibraryCompanyPage>;
  else content = <section className="report-empty"><h1>This page has been retired.</h1><Link className="report-button" href="/overview">Open your workspace ↗</Link></section>;
  return <div className="intelligence report-product" data-home={["/", "/overview", "/insights"].includes(path)} data-landing={landing}>
    <div inert={source || botOpen ? true : undefined}><a className="intel-skip-link" href="#workspace">Skip to content</a>
      <GlassSidebar reportView year={2025} selectedCount={selected.length} connection={libraryError ? "offline" : library ? "connected" : "loading"} onMobileOpenChange={setMobile} onPinnedChange={setPinned} onYearChange={() => navigate(path)}/>
      <main id="workspace" className="report-main" data-pinned={pinned} inert={mobile ? true : undefined}>
        <div className={landing ? "landing-silk-border" : "landing-silk-border report-inner-silk"} aria-hidden="true"><ShaderBackground/></div>
        <div className="report-topline"><span>GLOBAL SUSTAINABILITY INTELLIGENCE</span><span>VERO</span></div>
        {landing ? <section className="minimal-landing"><header className="minimal-intro"><h1>Explore company sustainability.</h1><p>Compare emissions, energy and climate commitments.</p><Link href="/overview">Open the research ↗</Link></header><div className="report-globe-assistant"><RegionGlobe companies={library?.companies ?? []}/><SustainobotLauncher onOpen={() => setBotOpen(true)}/></div></section> : <><div className="report-assistant-action"><button className="report-button" onClick={() => setBotOpen(true)}>Ask Sustainobot ↗</button></div>{content}<footer className="report-footer"><span>Vero · Sustainability intelligence</span><Link href="/methodology">Methodology</Link><Link href="/pricing">Pricing</Link></footer></>}
        {landing && libraryError && <LibraryError message={libraryError} retry={() => setAttempt(n => n + 1)}/>}
      </main>
    </div>
    <Sustainobot open={botOpen} onClose={closeBot} companies={library?.companies ?? []} selected={botCompanies} onSelect={setBotCompanies} draft={botDraft} setDraft={setBotDraft} openSource={openPassage} covered={!!source} configurationError={library?.status.research.configuration_error}/>
    {source && <SourceDrawer selection={source} onClose={close} returnFocusTo={trigger.current}/>}
  </div>;
}
