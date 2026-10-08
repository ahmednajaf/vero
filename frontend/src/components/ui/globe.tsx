// Adapted from Shuding's COBE Globe on 21st.dev (MIT). See /third-party-notices.txt.
import { useEffect, useRef, useState } from "react";
import type { Globe as CobeGlobe } from "cobe";

export interface GlobeMarker { id: string; location: [number, number]; selected: boolean }
interface Props { markers: GlobeMarker[]; onSelect: (id: string) => void }

// Same orthographic projection as COBE, for pointer hit-testing (not geocoding).
export function projectMarker([lat, lon]: [number, number], phi: number, theta: number) {
  const latitude = lat * Math.PI / 180, longitude = lon * Math.PI / 180 - Math.PI;
  const radius = .81, x = -Math.cos(latitude) * Math.cos(longitude) * radius;
  const y = Math.sin(latitude) * radius, z = Math.cos(latitude) * Math.sin(longitude) * radius;
  return {
    x: (Math.cos(phi) * x + Math.sin(phi) * z + 1) / 2,
    y: (-Math.sin(phi) * Math.sin(theta) * x - Math.cos(theta) * y + Math.cos(phi) * Math.sin(theta) * z + 1) / 2,
    visible: -Math.sin(phi) * Math.cos(theta) * x + Math.sin(theta) * y + Math.cos(phi) * Math.cos(theta) * z >= 0,
  };
}

export function Globe({markers, onSelect}: Props) {
  const host = useRef<HTMLDivElement>(null);
  const update = useRef<() => void>(() => {});
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [paused, setPaused] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  const state = useRef({markers, onSelect, paused});
  useEffect(() => {state.current = {markers, onSelect, paused}; update.current();}, [markers, onSelect, paused]);
  useEffect(() => {
    const motion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const change = () => {if (motion?.matches) setPaused(true);};
    motion?.addEventListener("change", change);
    return () => motion?.removeEventListener("change", change);
  }, []);

  useEffect(() => {
    const element = host.current;
    if (!element || typeof window.WebGLRenderingContext === "undefined") {setFailed(true); return;}
    let disposed = false, contextLost = false, globe: CobeGlobe | undefined, frame = 0, width = 0;
    let visible = true, phi = 5.7, theta = .27, previous = 0, warmUntil = 0;
    let pointer: {id: number; x: number; y: number; startX: number; startY: number} | null = null;
    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-hidden", "true");
    // COBE v2 wraps the canvas. React owns only the host, so cleanup is safe.
    element.append(canvas);
    const draw = () => {if (contextLost) return; globe?.update({phi, theta, markers: state.current.markers.map(m => ({
      id: m.id, location: m.location, size: m.selected ? .055 : .035,
      color: m.selected ? [.05, .4, .2] : [.196, .949, .529],
    }))});};
    const loop = (time: number) => {
      frame = 0;
      if (disposed || contextLost || !visible || document.hidden) return;
      const spin = !state.current.paused && !pointer;
      if (spin) phi += Math.min(time - previous, 50) * .000075;
      previous = time;
      draw();
      if (spin || time < warmUntil) frame = requestAnimationFrame(loop);
    };
    const wake = () => {
      if (!disposed && !contextLost && globe && !frame && visible && !document.hidden) {previous = performance.now(); frame = requestAnimationFrame(loop);}
    };
    update.current = () => {draw(); wake();};
    const resize = () => {
      const next = Math.round(element.getBoundingClientRect().width);
      if (next && next !== width) {width = next; globe?.update({width, height: width}); draw(); wake();}
    };
    const resizeObserver = new ResizeObserver(resize); resizeObserver.observe(element);
    const intersection = typeof IntersectionObserver !== "undefined" ? new IntersectionObserver(entries => {visible = entries[0].isIntersecting; if (visible) wake(); else {cancelAnimationFrame(frame); frame = 0;}}) : null;
    intersection?.observe(element);
    const visibility = () => {if (document.hidden) {cancelAnimationFrame(frame); frame = 0;} else wake();};
    document.addEventListener("visibilitychange", visibility);
    const down = (event: PointerEvent) => {
      if (event.button !== 0) return;
      pointer = {id: event.pointerId, x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY};
      canvas.setPointerCapture(event.pointerId); canvas.style.cursor = "grabbing";
    };
    const move = (event: PointerEvent) => {
      if (!pointer || event.pointerId !== pointer.id) return;
      phi += (event.clientX - pointer.x) / 240;
      theta = Math.max(-.65, Math.min(.75, theta + (event.clientY - pointer.y) / 500));
      pointer.x = event.clientX; pointer.y = event.clientY; draw();
    };
    const up = (event: PointerEvent) => {
      if (!pointer || event.pointerId !== pointer.id) return;
      if (event.type === "pointerup" && Math.hypot(event.clientX - pointer.startX, event.clientY - pointer.startY) < 5) {
        const rect = canvas.getBoundingClientRect();
        const nearest = state.current.markers.map(m => {
          const position = projectMarker(m.location, phi, theta);
          return {id: m.id, distance: position.visible ? Math.hypot(rect.left + position.x * rect.width - event.clientX, rect.top + position.y * rect.height - event.clientY) : Infinity};
        }).sort((a, b) => a.distance - b.distance)[0];
        if (nearest && nearest.distance < 18) state.current.onSelect(nearest.id);
      }
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
      pointer = null; canvas.style.cursor = "grab"; wake();
    };
    const lost = (event: Event) => {event.preventDefault(); contextLost = true; setFailed(true); setReady(false); cancelAnimationFrame(frame); frame = 0;};
    canvas.addEventListener("pointerdown", down); canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up); canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("webglcontextlost", lost);
    void import("cobe").then(({default: createGlobe}) => {
      if (disposed) return;
      // Check support before COBE's silent no-op fallback; expose a truthful fallback.
      const context = canvas.getContext("webgl2", {alpha: true, antialias: true}) ?? canvas.getContext("webgl", {alpha: true, antialias: true});
      if (!context) throw new Error("WebGL unavailable");
      width = Math.max(1, Math.round(element.getBoundingClientRect().width));
      globe = createGlobe(canvas, {width, height: width, devicePixelRatio: Math.min(window.devicePixelRatio || 1, 1.5),
        phi, theta, dark: 1, diffuse: 1.35, mapSamples: 26000, mapBrightness: 5,
        baseColor: [.62, .65, .63], markerColor: [.196, .949, .529], glowColor: [.91, .93, .91],
        opacity: 1, markerElevation: .01, markers: [],
      });
      warmUntil = performance.now() + 500; setReady(true); wake();
    }).catch(() => {if (!disposed) {setFailed(true); setReady(false);}});
    return () => {
      disposed = true; update.current = () => {}; cancelAnimationFrame(frame);
      resizeObserver.disconnect(); intersection?.disconnect(); document.removeEventListener("visibilitychange", visibility);
      canvas.removeEventListener("pointerdown", down); canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", up); canvas.removeEventListener("pointercancel", up); canvas.removeEventListener("webglcontextlost", lost);
      globe?.destroy(); element.replaceChildren();
    };
  }, []);

  return <div className={`earth-globe ${ready ? "ready" : ""}`}>
    <div className="earth-atmosphere" aria-hidden="true"/>
    {!ready && <svg className="earth-fallback" viewBox="0 0 400 400" aria-hidden="true"><circle cx="200" cy="200" r="157"/><ellipse cx="200" cy="200" rx="65" ry="157"/><ellipse cx="200" cy="200" rx="125" ry="157"/><ellipse cx="200" cy="200" rx="157" ry="60"/><path d="M43 200h314M200 43v314"/></svg>}
    <div className="earth-canvas" ref={host}/>
    <div className="earth-globe-controls">{ready ? <><span>{markers.length ? "Drag to explore · select a market pin" : "Drag to explore"}</span><button onClick={() => setPaused(p => !p)} aria-label={paused ? "Resume globe rotation" : "Pause globe rotation"}>{paused ? "▷" : "Ⅱ"}</button></> : <span>{failed ? "3D unavailable" : "Preparing the globe…"}</span>}</div>
  </div>;
}
