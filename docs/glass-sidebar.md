# Approved navigation refinement

The user selected Suraj Gaud's [Liquid Glass](https://21st.dev/@suraj-xd/components/liquid-glass) treatment combined with Manu Arora's [Sidebar](https://21st.dev/@manuarora700/components/sidebar) on 21st.dev. Only the local React navigation is changed. Globe colours, page content, charts, metric values, backend, database and the hosted site are unchanged.

## Sources and adaptation

- The sidebar's MIT-licensed source was inspected through the signed-in 21st.dev page. The compact rail, expanded link labels and hover behaviour are adapted to the existing React/Vite router. CSS handles width/opacity transitions instead of adding Next.js or Framer Motion to the application.
- The glass reference guides the surface, translucency and edge lighting. Its page did not display a license, so the implementation does not copy its source, water background, app icons or assets. The independently styled neutral glass does not introduce a new global colour scheme.
- Attribution and the sidebar's MIT notice ship in `frontend/public/third-party-notices.txt`.

## Behaviour

- Desktop: 76 px floating rail, expanding to 254 px on hover or keyboard entry. Temporary expansion overlays the page without moving charts. Pinning it open reserves page space so content is not obscured; minimising or Escape releases that space.
- Overview, Companies, Compare, Race, Trends and Methodology retain their routes. Company detail pages highlight Companies. Links retain the reporting year and native modified-click behaviour.
- Comparison selection count, reporting-year selection and connection state remain available. No account/avatar placeholder is introduced.
- Mobile: one menu button opens the same navigation as a modal panel; focus is contained, the page is inert, scrolling is locked, and Escape/backdrop/close restore focus. Navigation closes the panel. No duplicate hidden navigation tree.
- Reduced motion disables transitions; reduced transparency and unsupported backdrop filtering use an opaque fallback. Current page and accessible labels do not rely on colour alone.

## Checks

`cd frontend && npm test && npm run typecheck && npm run build`

Added tests cover the compact rail, hover, pin/minimise, keyboard/Escape, active routes, cycle retention, the reporting-year control, mobile focus trapping and scroll restoration, inert background, route/history closure, modifier clicks and backdrop dismissal. Browser checks use the actual local app, without substituted findings.

Verification: 79 frontend tests across nine files passed; TypeScript and the production build passed. The local app was inspected at its default desktop viewport and at 390 px phone width. The mobile document and viewport both measured 390 px (no horizontal overflow); selecting Companies closed the menu, removed the inert background and focused the Companies heading. The temporary viewport override was reset afterwards. The preview reported an unreadable data-service response, so this pass verifies navigation, not live-data availability. No backend service was started or changed.
