import {knowledge, type Answer, type Passage} from "./knowledge";

export const topics = {emissions:"Emissions & progress",energy:"Energy",targets:"Targets & transition",assurance:"Assurance & governance",nature:"Water & nature",supply_chain:"Supply chain"};
export type Topic = keyof typeof topics;
export interface BriefCompany {id:string;company_name:string;sector:string;country:string;reports_indexed:number}
export interface BriefSummary {id:string;title:string;status:string;created_at:string;companies:BriefCompany[];topics:number;completed_topics:number;findings:number}
export interface BriefSection {id:Topic;title:string;status:string;result:Answer|null;error_code:string|null}
export interface Briefing {
  id:string;title:string;primary_company_id:string;status:string;created_at:string;updated_at:string;sources_current:boolean;can_resume:boolean;
  completed_topics:number;findings_count:number;estimated_cost_usd:number;cost_note:string;
  new_reports_available?:number;
  definition:{company_ids:string[];report_ids:string[];companies:BriefCompany[];focus:string};sections:BriefSection[];
  matrix:{topic_id:Topic;topic:string;cells:{company_id:string;status:string;sources:Passage[]}[]}[];
  review_opportunities:{topic_id:Topic;topic:string;peer_evidence_count:number;peer_count:number;primary_status:string;sources:Passage[];meaning:string}[];
}
export const evidenceStates:Record<string,string>={evidence_found:"Evidence cited",report_unavailable:"No searchable report",pending:"Not analysed",passages_retrieved:"Needs a closer look",not_identified:"Not identified"};
export const listBriefings=(companyId?:string,signal?:AbortSignal)=>knowledge<{items:BriefSummary[]}>(`/knowledge/briefings${companyId?`?company_id=${encodeURIComponent(companyId)}`:""}`,undefined,signal);
export const getBriefing=(id:string,signal?:AbortSignal)=>knowledge<Briefing>(`/knowledge/briefings/${encodeURIComponent(id)}`,undefined,signal);
export function exportLink(id:string,format:"html"|"csv"|"json") {return `${(import.meta.env.VITE_API_BASE_URL||"/api").replace(/\/+$/,"")}/knowledge/briefings/${encodeURIComponent(id)}/export?format=${format}`;}
