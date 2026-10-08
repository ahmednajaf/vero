// Adapted from the user's InteractiveGlobeExplorer source for the Vite workspace.
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { GlobeMethods } from "react-globe.gl";
import { COUNTRY_ANCHORS } from "../lib/globe";
import { countryName } from "../lib/benchmarks";
import { Link } from "../lib/navigation";
const REGIONS = [
  {id:"europe", name:"Europe", lat:48, lng:12, codes:["GB","DE","FR","CH","NL","IE","SE","NO","DK","FI"]},
  {id:"north-america", name:"North America", lat:35, lng:-95, codes:["US","CA","MX"]},
  {id:"asia-pacific", name:"Asia Pacific", lat:22, lng:115, codes:["JP","CN","IN","SG","AU","KR","NZ"]},
  {id:"middle-east", name:"Middle East", lat:25, lng:45, codes:["SA","AE","QA","IL"]},
  {id:"africa", name:"Africa", lat:-5, lng:22, codes:["ZA","NG","KE","EG"]},
  {id:"latin-america", name:"Latin America", lat:-20, lng:-60, codes:["BR","AR","CL","CO"]},
];
const Globe = lazy(() => import("react-globe.gl"));
export function RegionGlobe({companies}: {companies: {id: string; company_name: string; country: string}[]}) {
  const host = useRef<HTMLDivElement>(null);
  const globe = useRef<GlobeMethods | undefined>(undefined);
  const [size, setSize] = useState(500);
  const [active, setActive] = useState("europe");
  const [paused, setPaused] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const locations = useMemo(() => [...new Set(companies.map(c => c.country))].filter(code => COUNTRY_ANCHORS[code]).map(code => ({id:code, name:countryName(code), lat:COUNTRY_ANCHORS[code][0], lng:COUNTRY_ANCHORS[code][1], companies:companies.filter(c => c.country === code)})), [companies]);
  useEffect(() => {if (!host.current) return; const observer = new ResizeObserver(([entry]) => setSize(Math.min(1000, entry.contentRect.width))); observer.observe(host.current); return () => observer.disconnect();}, []);
  useEffect(() => {if (ready && globe.current) globe.current.controls().autoRotate = !paused;}, [paused, ready]);
  function select(id: string) {const location = REGIONS.find(l => l.id === id) ?? locations.find(l => l.id === id); if (!location) return; setActive(id); setDetailsOpen(true); setPaused(true); globe.current?.pointOfView({lat:location.lat,lng:location.lng,altitude:2.5},900);}
  const selected = REGIONS.find(l => l.id === active);
  const regionalCompanies = selected ? companies.filter(c => selected.codes.includes(c.country)) : companies.filter(c => c.country === active);
  const supported = typeof window.WebGLRenderingContext !== "undefined";
  return <div className="region-explorer" aria-label="Company region explorer" aria-description="Pins show registered company countries. Operating footprints await regional data.">
    <nav className="region-selector" aria-label="Select a region"><span className="region-selector-label">Explore by region</span>{REGIONS.map(region => <button key={region.id} aria-pressed={active === region.id} onClick={() => select(region.id)}><span>{region.name}</span></button>)}</nav>
    <div ref={host} className="region-globe-stage">{supported ? <Suspense fallback={<div className="region-loading" role="status">Preparing the globe…</div>}><Globe ref={globe} width={size} height={size} backgroundColor="rgba(0,0,0,0)" globeImageUrl="/earth-texture.jpg" atmosphereColor="#459cff" atmosphereAltitude={.10} pointsData={locations} pointLat="lat" pointLng="lng" pointColor={p => (p as {id:string}).id === active ? "#e8c989" : "#83ffc2"} pointRadius={.65} pointAltitude={.025} pointLabel={p => (p as {name:string}).name} onPointClick={p => select((p as {id:string}).id)} onGlobeReady={() => {setReady(true); globe.current?.pointOfView({lat:30,lng:12,altitude:2.5}); const controls=globe.current?.controls(); if(controls){controls.enableZoom=false;controls.autoRotate=!paused;controls.autoRotateSpeed=.4;}}}/></Suspense> : <div className="region-fallback" role="status">Explore regions from the menu.<span>3D globe requires WebGL.</span></div>}</div>
    {detailsOpen && <aside className="region-detail" aria-live="polite"><span className="region-selector-label">Selected region</span><strong>{selected?.name ?? countryName(active)}</strong>{regionalCompanies.length ? regionalCompanies.map(c => <Link key={c.id} href={`/companies/${c.id}`}>{c.company_name} ↗</Link>) : <p>{companies.length ? "No companies in this edition yet." : "Company coverage will appear when data connects."}</p>}<button aria-label="Close region details" onClick={() => setDetailsOpen(false)}>×</button></aside>}
    <p className="region-caption">Company countries · operating footprints coming soon</p>
    {supported && <button className="region-rotation-control" aria-label={paused ? "Resume globe rotation" : "Pause globe rotation"} title={paused ? "Resume rotation" : "Pause rotation"} onClick={() => setPaused(!paused)}>{paused ? <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 9 6-9 6Z"/></svg> : <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6v12M15 6v12"/></svg>}</button>}


  </div>;
}
