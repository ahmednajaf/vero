import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link, useNavigation } from "../lib/navigation";
import "../sidebar.css";

// Adapted from Manu Arora's MIT-licensed Aceternity Sidebar on 21st.dev.
// https://21st.dev/@manuarora700/components/sidebar
// Keeps its compact rail / hover expansion, using our router and CSS motion.
// Glass material is a visual interpretation of Suraj Gaud's approved reference:
// https://21st.dev/@suraj-xd/components/liquid-glass (no demo assets copied).
export const NAVIGATION = [
  { name: "Overview", path: "/", icon: "overview" },
  { name: "Annual research", path: "/edition", icon: "methodology" },
  { name: "Companies", path: "/companies", icon: "companies" },
  { name: "Compare", path: "/compare", icon: "compare" },
  { name: "Race", path: "/race", icon: "race" },
  { name: "Trends", path: "/trends", icon: "trends" },
  { name: "Methodology", path: "/methodology", icon: "methodology" },
] as const;

type IconName = typeof NAVIGATION[number]["icon"] | "panel" | "menu" | "close";
function NavigationIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    overview: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
    companies: <><rect x="4" y="7" width="7" height="14" rx="1"/><path d="M11 21h9V3H9v4M7 11h1m-1 4h1m7-8h1m-1 4h1m-1 4h1"/></>,
    compare: <><path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"/></>,
    race: <><path d="M5 21V4m0 0c5-4 9 4 15 0v10c-6 4-10-4-15 0"/><path d="M10 4v9m5-7v9M5 9c5-4 9 4 15 0"/></>,
    trends: <><path d="M4 4v16h17M7 14l4-4 4 2 5-7m-5 0h5v5"/></>,
    methodology: <><path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1m0-15c3-2 6-2 9-1v15c-3-1-6-1-9 1V5"/></>,
    panel: <><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16m5-11 3 3-3 3"/></>,
    menu: <path d="M5 7h14M5 12h14M5 17h14"/>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function useMobileNavigation() {
  const [mobile, setMobile] = useState(() => window.matchMedia?.("(max-width: 767px)").matches ?? false);
  useEffect(() => {
    if (!window.matchMedia) return;
    const media = window.matchMedia("(max-width: 767px)");
    const update = () => setMobile(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return mobile;
}

interface GlassSidebarProps {
  reportView?: boolean;
  researchView?: boolean;
  selfService?: boolean;
  year: number;
  selectedCount: number;
  connection: "loading" | "connected" | "offline";
  onYearChange: (year: number) => void;
  onMobileOpenChange: (open: boolean) => void;
  onPinnedChange?: (pinned: boolean) => void;
}

function LegacyGlassSidebar({ year, selectedCount, connection, onYearChange, onMobileOpenChange, onPinnedChange, researchView = false, selfService = false, reportView = false }: GlassSidebarProps) {
  const navigation = reportView ? [
    {name:"Briefing", path:"/overview", icon:"methodology" as const},
    {name:"Compare", path:"/compare", icon:"compare" as const},
    {name:"Companies", path:"/companies", icon:"companies" as const},
    {name:"Sources", path:"/sources", icon:"methodology" as const},
    {name:"Methodology", path:"/methodology", icon:"trends" as const},
  ] : selfService ? NAVIGATION.filter(n=>n.path!=="/edition" && n.path!=="/race").map(n=>n.path==="/"?{...n,path:"/overview"}:n.path==="/trends"?{...n,name:"Insights",path:"/insights"}:n.path==="/methodology"?{...n,name:"Sources",path:"/sources"}:n) : researchView ? NAVIGATION.filter(n => n.path !== "/edition").map(n => n.path === "/trends" ? {...n, name:"Insights", path:"/insights"} : n) : NAVIGATION;
  const { path, search } = useNavigation();
  const mobile = useMobileNavigation();
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const sidebar = useRef<HTMLElement>(null);
  const mobileTrigger = useRef<HTMLButtonElement>(null);
  const panelToggle = useRef<HTMLButtonElement>(null);
  const previousLocation = useRef(path + search);
  const expanded = mobile ? mobileOpen : !dismissed && (pinned || hovered || focused);
  const status = connection === "connected" ? "Data connected" : connection === "loading" ? "Connecting" : "Data unavailable";
  const cleanPath = path.replace(/\/$/, "") || "/";

  // Close on navigation/history/year changes without stealing the page's heading focus.
  useEffect(() => {
    if (previousLocation.current !== path + search) {
      setMobileOpen(false);
      previousLocation.current = path + search;
    }
  }, [path, search]);
  useEffect(() => { if (!mobile) setMobileOpen(false); }, [mobile]);
  useEffect(() => { onMobileOpenChange(mobile && mobileOpen); }, [mobile, mobileOpen, onMobileOpenChange]);
  useEffect(() => { onPinnedChange?.(!mobile && pinned); }, [mobile, pinned, onPinnedChange]);
  useEffect(() => {
    if (!mobile || !mobileOpen) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    sidebar.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => { document.body.style.overflow = overflow; };
  }, [mobile, mobileOpen]);

  function closeMobile() {
    setMobileOpen(false);
    mobileTrigger.current?.focus();
  }
  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      if (mobile) closeMobile();
      else { setPinned(false); setDismissed(true); panelToggle.current?.focus(); }
    }
    if (event.key === "Tab" && mobile && mobileOpen) {
      const controls = sidebar.current?.querySelectorAll<HTMLElement>('a[href], button, select');
      if (!controls?.length) return;
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  }

  return <>
    <svg className="glass-filter-defs" aria-hidden="true" width="0" height="0"><defs><filter id="vero-refraction" x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB"><feTurbulence type="fractalNoise" baseFrequency="0.009 0.018" numOctaves="1" seed="7" result="noise"/><feGaussianBlur in="noise" stdDeviation="2" result="softNoise"/><feDisplacementMap in="SourceGraphic" in2="softNoise" scale="12" xChannelSelector="R" yChannelSelector="G"/></filter></defs></svg>
    <button ref={mobileTrigger} className="glass-mobile-trigger" aria-label="Open navigation" aria-expanded={mobileOpen} aria-controls="workspace-navigation" onClick={() => setMobileOpen(true)} inert={mobileOpen ? true : undefined}>
      <NavigationIcon name="menu"/><img src="/brand/vero-wordmark.png" alt="Vero"/>
    </button>
    {mobile && mobileOpen && <div className="glass-nav-backdrop" aria-hidden="true" onClick={closeMobile}/>}
    <aside ref={sidebar} id="workspace-navigation" className="glass-sidebar" data-expanded={expanded} hidden={mobile && !mobileOpen} role={mobile && mobileOpen ? "dialog" : undefined} aria-modal={mobile && mobileOpen ? true : undefined} aria-label="Workspace navigation"
      onMouseEnter={() => { if (!mobile) { setHovered(true); setDismissed(false); } }}
      onMouseLeave={() => { setHovered(false); }}
      onFocus={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) { setFocused(true); setDismissed(false); } }}
      onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) { setFocused(false); setDismissed(false); } }}
      onKeyDown={onKeyDown}>
      <div className="glass-sidebar-content">
        <div className="glass-sidebar-heading">
          <Link href="/" className="glass-sidebar-brand" aria-label="Vero home">
            <span className="glass-brand-wordmark" aria-hidden="true"><img src="/brand/vero-wordmark.png" alt=""/></span>
          </Link>
          {mobile && <button className="glass-mobile-close" onClick={closeMobile} aria-label="Close navigation"><NavigationIcon name="close"/></button>}
        </div>
        <nav aria-label="Main navigation" className="glass-sidebar-links">
          {navigation.map(item => {
            const active = item.path === "/companies" ? cleanPath === "/companies" || cleanPath.startsWith("/companies/") : item.path === "/" ? cleanPath === "/" || cleanPath === "/overview" : cleanPath === item.path;
            return <Link key={item.path} className="glass-sidebar-link" href={item.path} aria-label={item.name} aria-current={active ? "page" : undefined} title={!expanded ? item.name : undefined} onClick={event => {
              if (selfService && !mobile && !pinned) { setDismissed(true); setHovered(false); }
              if (mobile && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { setMobileOpen(false); onMobileOpenChange(false); }
            }}>
              <span className="glass-nav-icon"><NavigationIcon name={item.icon}/>{item.path === "/compare" && selectedCount > 0 && <span className="glass-compare-count" aria-label={`${selectedCount} selected`}>{selectedCount}</span>}</span>
              <span className="glass-reveal" aria-hidden="true">{item.name}</span>
            </Link>;
          })}
        </nav>
        <div className="glass-sidebar-bottom">
          <label className="glass-sidebar-year"><select aria-label="Reporting year" title="Reporting year" value={year} onChange={event => onYearChange(Number(event.target.value))}>
            {(selfService || reportView ? [year] : researchView ? [2025] : [...new Set([year, 2026, 2025, 2024, 2023, 2022])].sort((a, b) => b - a)).map(y => <option key={y}>{y}</option>)}
          </select><span className="glass-reveal">Reporting year</span></label>
          <div className="glass-sidebar-status" title={status}><span className={`glass-status-dot ${connection}`} aria-hidden="true"/><span className="glass-reveal">{status}</span></div>
          {!mobile && <button ref={panelToggle} className="glass-sidebar-toggle" aria-label={pinned ? "Minimise navigation" : "Keep navigation expanded"} aria-pressed={pinned} aria-expanded={expanded} aria-controls="workspace-navigation" onClick={() => {
            if (pinned) { setPinned(false); setDismissed(true); }
            else { setPinned(true); setDismissed(false); }
          }}><span className="glass-nav-icon"><NavigationIcon name="panel"/></span><span className="glass-reveal" aria-hidden="true">{pinned ? "Minimise" : "Keep expanded"}</span></button>}
        </div>
      </div>
    </aside>
  </>;
}


export function GlassSidebar(props: GlassSidebarProps) {
  return props.reportView ? <NavigationWheel {...props}/> : <LegacyGlassSidebar {...props}/>;
}
function NavigationWheel({year,onYearChange,onMobileOpenChange,onPinnedChange}: GlassSidebarProps) {
  const {path}=useNavigation();
  const [open,setOpen]=useState(false),[rotation,setRotation]=useState(0);
  const trigger=useRef<HTMLButtonElement>(null),panel=useRef<HTMLDivElement>(null),stage=useRef<HTMLElement>(null);
  const current=useRef(0),velocity=useRef(0),frame=useRef(0),drag=useRef<{y:number;rotation:number;last:number;moved:boolean}|null>(null),suppressClick=useRef(false);
  const mobile=useMobileNavigation();
  const items=[{name:"Overview",path:"/overview",icon:"methodology" as const},{name:"Compare",path:"/compare",icon:"compare" as const},{name:"Companies",path:"/companies",icon:"companies" as const},{name:"Sources",path:"/sources",icon:"methodology" as const},{name:"Methodology",path:"/methodology",icon:"trends" as const},{name:"Pricing",path:"/pricing",icon:"methodology" as const}];
  const count=items.length;
  const reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches??false;
  function commit(value:number){current.current=value;setRotation(value);}
  function animate(){if(frame.current)return;function tick(){frame.current=0;if(drag.current)return;let next=current.current;if(Math.abs(velocity.current)>.0008&&!reduced){next+=velocity.current;velocity.current*=.9;}else{velocity.current=0;const delta=Math.round(next)-next;if(Math.abs(delta)<.001||reduced){commit(Math.round(next));return;}next+=delta*.22;}commit(next);frame.current=requestAnimationFrame(tick);}frame.current=requestAnimationFrame(tick);}
  function move(amount:number){velocity.current=0;commit(current.current+amount);animate();}
  useEffect(()=>{setOpen(false);},[path]);
  useEffect(()=>{onMobileOpenChange(mobile&&open);onPinnedChange?.(false);if(!open){cancelAnimationFrame(frame.current);frame.current=0;}},[open,mobile,onMobileOpenChange,onPinnedChange]);
  useEffect(()=>{if(open)stage.current?.focus();},[open]);
  useEffect(()=>()=>cancelAnimationFrame(frame.current),[]);
  useEffect(()=>{const el=stage.current;if(!open||!el)return;function wheel(event:WheelEvent){if(event.ctrlKey||event.metaKey)return;event.preventDefault();const delta=event.deltaY*(event.deltaMode===1?16:1)*.008;commit(current.current+delta);velocity.current=delta*.2;animate();}el.addEventListener('wheel',wheel,{passive:false});return()=>el.removeEventListener('wheel',wheel);},[open]);
  function close(){setOpen(false);requestAnimationFrame(()=>trigger.current?.focus());}
  function keys(e:KeyboardEvent<HTMLDivElement>){if(e.key==='Escape'){e.preventDefault();close();}if(['ArrowDown','ArrowRight','ArrowUp','ArrowLeft'].includes(e.key)){e.preventDefault();move(['ArrowDown','ArrowRight'].includes(e.key)?1:-1);}if(e.key==='Home'||e.key==='End'){e.preventDefault();velocity.current=0;commit(e.key==='Home'?0:count-1);}if(e.key==='Tab'&&open){const controls=panel.current?.querySelectorAll<HTMLElement>('button,a,[tabindex="0"]');if(!controls?.length)return;const first=controls[0],last=controls[controls.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}}
  const selected=((Math.round(rotation)%count)+count)%count;
  return <div className="carousel-navigation" onKeyDown={keys}>
    <button ref={trigger} className="carousel-menu-trigger" aria-label="Open navigation" aria-expanded={open} aria-controls="workspace-navigation" onClick={()=>setOpen(true)} hidden={open}><img src="/brand/vero-wordmark.png" alt="Vero"/><span aria-hidden="true">≡</span></button>
    {open&&<><div className="carousel-dismiss" onClick={close}/><div ref={panel} className="glass-wheel-carousel" id="workspace-navigation" role="dialog" aria-modal="true" aria-label="Workspace navigation">
      <header><Link href="/" aria-label="Vero home" onClick={close}><img src="/brand/vero-wordmark.png" alt="Vero"/></Link><button onClick={close} aria-label="Close navigation">×</button></header>
      <nav ref={stage} className="carousel-wheel-stage" aria-label="Main navigation" tabIndex={0}
        onPointerDown={e=>{if(!e.isPrimary||e.button!==0)return;velocity.current=0;suppressClick.current=false;drag.current={y:e.clientY,rotation:current.current,last:current.current,moved:false};}}
        onPointerMove={e=>{const d=drag.current;if(!d)return;const distance=e.clientY-d.y;if(Math.abs(distance)>5){d.moved=true;e.currentTarget.setPointerCapture(e.pointerId);}if(!d.moved)return;const next=d.rotation-distance*.02;velocity.current=next-d.last;d.last=next;commit(next);}}
        onPointerUp={e=>{if(!drag.current)return;suppressClick.current=drag.current.moved;drag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);animate();}}
        onPointerCancel={()=>{drag.current=null;velocity.current=0;animate();}}>
        <span className="carousel-apex-marker" aria-hidden="true"/>
        {items.map((item,index)=>{let offset=index-rotation;offset=((offset+count/2)%count+count)%count-count/2;const angle=offset*17,radians=angle*Math.PI/180;const x=-260*(1-Math.cos(radians)),y=260*Math.sin(radians);return <Link key={item.path} className="carousel-wheel-item" href={item.path} aria-label={item.name} aria-current={path===item.path?'page':undefined} data-selected={Math.abs(offset)<.5} style={{transform:`translate(${x}px,${y}px) translateY(-50%) rotate(${angle}deg) scale(${1-Math.abs(offset)*.04})`,opacity:Math.cos(Math.min(Math.abs(offset)/3,1)*Math.PI/2)}} onClick={e=>{if(suppressClick.current){e.preventDefault();suppressClick.current=false;return;}setOpen(false);}}><NavigationIcon name={item.icon}/><span>{item.name}</span></Link>;})}
      </nav>
      <label className="carousel-year-selector"><span className="carousel-year-label">Year</span><span className="carousel-year-input"><select aria-label="Reporting year" value={year} onChange={event=>onYearChange(Number(event.target.value))}><option value={year}>{year}</option></select><span aria-hidden="true">⌄</span></span></label>
      <span className="sr-only" aria-live="polite">{items[selected].name}</span>
    </div></>}
  </div>;
}
