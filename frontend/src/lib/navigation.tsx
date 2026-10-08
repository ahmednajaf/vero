import { createContext, useContext, useEffect, useState, type AnchorHTMLAttributes, type ReactNode } from "react";

const Navigation = createContext({path: "/", search: "", navigate: (_to: string) => {}});
export function NavigationProvider({children}: {children: ReactNode}) {
  const [location, setLocation] = useState({path: window.location.pathname, search: window.location.search});
  useEffect(() => { const update = () => setLocation({path: window.location.pathname, search: window.location.search}); window.addEventListener("popstate", update); return () => window.removeEventListener("popstate", update); }, []);
  function navigate(to: string) {
    const next = new URL(to, window.location.origin);
    const year = new URLSearchParams(window.location.search).get("year");
    const benchmark = new URLSearchParams(window.location.search).get("benchmark");
    if (benchmark && !next.searchParams.has("benchmark")) next.searchParams.set("benchmark",benchmark);
    if (year && !next.searchParams.has("year")) next.searchParams.set("year", year);
    window.history.pushState(null, "", next.pathname + next.search);
    setLocation({path: next.pathname, search: next.search});
  }
  return <Navigation.Provider value={{...location, navigate}}>{children}</Navigation.Provider>;
}
export const useNavigation = () => useContext(Navigation);
export function Link({href = "/", onClick, children, ...props}: AnchorHTMLAttributes<HTMLAnchorElement>) {
  const {navigate, search} = useNavigation();
  const year = new URLSearchParams(search).get("year");
  const next = new URL(href, window.location.origin);
  const benchmark = new URLSearchParams(search).get("benchmark");
  if (benchmark && !next.searchParams.has("benchmark")) next.searchParams.set("benchmark",benchmark);
  if (year && !next.searchParams.has("year")) next.searchParams.set("year", year);
  const target = next.pathname + next.search;
  return <a {...props} href={target} onClick={event => { onClick?.(event); if (!event.defaultPrevented && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {event.preventDefault(); navigate(target);} }}>{children}</a>;
}
