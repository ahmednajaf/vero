import {knowledge, type Answer, type Passage} from "./knowledge";

export const topics = {emissions:"Emissions & progress",energy:"Energy",targets:"Targets & transition",assurance:"Assurance & governance",nature:"Water & nature",supply_chain:"Supply chain",people:"People & opportunity",innovation:"AI & innovation",carbon_credits:"Carbon credits & real-world progress",social:"Social investment & SDGs"};
export type Topic = keyof typeof topics;
export interface BriefCompany {id:string;company_name:string;sector:string;country:string;reports_indexed:number}
export interface BriefSummary {id:string;title:string;status:string;created_at:string;companies:BriefCompany[];topics:number;completed_topics:number;findings:number}
export interface ReportAward {
  contextual?:boolean;
  id?:string;question?:string;interpretation?:string;formula?:string;reference_value?:string|null;
  name:string;criterion:string;operation:string;direction:string;caveat:string;status:string;winner_ids:string[];sample_size:number;cohort_size:number;basis:string;
  excluded:{company_id:string;reason:string}[];unassessed_company_ids:string[];
  rows:{company_id:string;company:string;value:string;unit:string;year:number|null;inputs:{raw_value:string;raw_unit:string;value:string;unit:string;year:number|null;source:Passage}[]}[];
}
export interface AnalyticalFinding {id:string;headline:string;takeaway:string;explanation:string;business_implication:string;counterpoint:string;priority:string;citations:Passage[]}
export interface AnalyticalBadge {id:string;name:string;why_it_matters:string;basis:string;metric_id:string|null;winner_ids:string[];status:string;sample_size:number;rows:{company_id:string;company:string;value:string;sources:Passage[]}[];rubric:{id:string;criterion:string;max_points:number}[];assessments:{company_id:string;criterion_id:string;points:number;explanation:string}[]}
export interface DisclosureScores {policy:string;meaning:string;criteria:{id:string;definition:string;disclosed_by:string[]}[];rows:{company_id:string;company:string;score:number|null;disclosed:number;total:number;deductions:{criterion:string;points:number;peer_ids:string[];reason:string}[];pending:string[]}[]}
export interface PromiseRecord {company_id:string;company:string;commitment:string;deadline:string|null;assessment:string;citations:Passage[]}
export interface ReportedFact {id:string;company_id:string;metric:string;value:string;unit:string|null;year:number|null;population:string;kind:string;source:Passage}
export interface PublishedChapter {id:string;title:string;paragraphs:{heading:string;text:string;citations:Passage[]}[]}
export interface BriefSection {id:string;kind?:string;topic_id?:Topic;title:string;status:string;result:(Answer & {analysis_title?:string;facts?:ReportedFact[];analytical_findings?:AnalyticalFinding[];metrics?:ReportAward[];badges?:AnalyticalBadge[];disclosure_scores?:DisclosureScores;promises?:PromiseRecord[];awards?:ReportAward[];paragraphs?:{heading:string;text:string;record_ids?:string[];citations:Passage[]}[];follow_up_questions?:string[]})|null;error_code:string|null}
export interface Briefing {
  id:string;title:string;primary_company_id:string;status:string;created_at:string;updated_at:string;sources_current:boolean;can_resume:boolean;
  completed_topics:number;findings_count:number;estimated_cost_usd:number;cost_note:string;
  new_reports_available?:number;
  analysis_summary?:{disclosure_scores:DisclosureScores;promises:PromiseRecord[];metrics?:ReportAward[];badges?:AnalyticalBadge[];chapters?:PublishedChapter[]}|null;
  definition:{company_ids:string[];report_ids:string[];companies:BriefCompany[];focus:string;package?:"company"|"sector";report_method?:string};sections:BriefSection[];
  matrix:{topic_id:Topic;topic:string;cells:{company_id:string;status:string;sources:Passage[]}[]}[];
  review_opportunities:{topic_id:Topic;topic:string;peer_evidence_count:number;peer_count:number;primary_status:string;sources:Passage[];meaning:string}[];
}
export const evidenceStates:Record<string,string>={evidence_found:"Evidence cited",report_unavailable:"No searchable report",pending:"Not analysed",passages_retrieved:"Needs a closer look",not_identified:"Not identified"};
export const listBriefings=(companyId?:string,signal?:AbortSignal)=>knowledge<{items:BriefSummary[]}>(`/knowledge/briefings${companyId?`?company_id=${encodeURIComponent(companyId)}`:""}`,undefined,signal);
export const getBriefing=(id:string,signal?:AbortSignal)=>knowledge<Briefing>(`/knowledge/briefings/${encodeURIComponent(id)}`,undefined,signal);
export function exportLink(id:string,format:"html"|"pdf"|"xlsx"|"csv"|"json") {return `${(import.meta.env.VITE_API_BASE_URL||"/api").replace(/\/+$/,"")}/knowledge/briefings/${encodeURIComponent(id)}/export?format=${format}`;}
