import { countryName, netZero, usable, verifiedEvidence, type WorkspaceData } from "./benchmarks";

// Natural Earth country LABEL_Y / LABEL_X, not company headquarters or operations.
// Public-domain source and retrieval details: docs/component-sources.md.
export const COUNTRY_ANCHORS: Record<string, [number, number]> = {
  US: [39.538479, -97.482602], GB: [54.402739, -2.116346], DE: [50.961733, 9.678348],
  FR: [46.696113, 2.552275], NL: [52.422211, 5.61144], CH: [46.719114, 7.463965],
  JP: [36.142538, 138.44217], CA: [60.324287, -101.9107], AU: [-24.129522, 134.04972],
  NO: [61.357092, 9.679975], SE: [65.85918, 19.01705], DK: [55.966965, 9.018163],
  FI: [63.252361, 27.276449], IE: [53.078726, -7.798588], SA: [23.806908, 44.6996],
};
export type GlobeLens = "companies" | "evidence" | "targets";
export interface GlobeMarket { code: string; name: string; companies: number; evidence: number; targets: number; location?: [number, number] }
export function globeMarkets(data: WorkspaceData | null): GlobeMarket[] {
  const markets = new Map<string, GlobeMarket>();
  const byId = new Map(data?.benchmarks.items.map(c => [c.company_id, c]) ?? []);
  for (const company of data?.companies ?? []) {
    const code = company.country;
    const market = markets.get(code) ?? {code, name: countryName(code), companies: 0, evidence: 0, targets: 0, location: COUNTRY_ANCHORS[code]};
    const benchmark = byId.get(company.id);
    market.companies++;
    // Count companies, not documents or observations. Never imply complete validation.
    if (benchmark && Object.values(benchmark.metrics).some(m => usable(m) && m.provenance.some(verifiedEvidence))) market.evidence++;
    if (netZero(benchmark).year !== null) market.targets++;
    markets.set(code, market);
  }
  return [...markets.values()].sort((a, b) => a.name.localeCompare(b.name));
}
