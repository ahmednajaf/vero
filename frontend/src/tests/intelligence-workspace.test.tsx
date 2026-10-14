import {useState} from "react";
import {act,render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {beforeEach,expect,it,vi} from "vitest";
import {CompanyIntelligence,IntelligenceOverview,PeerWorkspace} from "../components/IntelligenceWorkspace";
import {NavigationProvider} from "../lib/navigation";
import type {Briefing} from "../lib/briefings";
import type {ReportLibrary} from "../lib/knowledge";

const companies=Array.from({length:3},(_,i)=>({id:`c${i}`,company_name:`Fixture ${i}`,ticker:`F${i}`,country:"GB",region:"Test",sector:"Technology",industry:"Test",official_domain:"example.com",exchange:"TEST",reports_downloaded:i===2?0:1,reports_indexed:i===2?0:1,pages_indexed:10,text_gaps:false,availability:i===2?"not_collected" as const:"searchable" as const,collection_status:"succeeded"}));
const library:ReportLibrary={companies,reports:[],status:{companies_in_scope:3,companies_with_indexed_reports:2,official_reports_downloaded:2,reports_indexed:2,pages_indexed:20,reports_with_text_gaps:0,research:{provider:"openai",model:"fixture",enabled:true,configuration_error:null,monthly_budget_usd:5}}};
const source={evidence_id:"e0",company_id:"c0",company:"Fixture 0",report_id:"r0",report:"Fixture report",page:2,page_url:"/api/reports/r0/file#page=2",source_url:"https://example.com/report.pdf",report_sha256:"hash",text:"Fixture disclosure",quote:"Fixture disclosure",kind:"text",reporting_year:2025,detected_year:2025};
const result={status:"answered" as const,claims:[{text:"A source-backed test finding.",citations:[source]}],coverage:{companies_supplied:1,passages_supplied:1,exhaustive:false,companies:[]},cached:false,model_called:true,notes:["Reporting periods differ."]};
const base:Briefing={id:"b1",title:"Fixture 0 · Peer comparison",primary_company_id:"c0",status:"pending",created_at:"2026-10-08",updated_at:"2026-10-08",sources_current:true,can_resume:true,completed_topics:0,findings_count:0,estimated_cost_usd:0,cost_note:"Known usage only",definition:{company_ids:["c0","c1"],report_ids:["r0"],companies:companies.slice(0,2),focus:""},sections:[{id:"energy",title:"Energy",status:"pending",result:null,error_code:null}],matrix:[],review_opportunities:[]};
const done:Briefing={...base,status:"partial",can_resume:false,completed_topics:1,findings_count:1,sections:[{id:"energy",title:"Energy",status:"completed",result,error_code:null}],matrix:[{topic_id:"energy",topic:"Energy",cells:[{company_id:"c0",status:"evidence_found",sources:[source]},{company_id:"c1",status:"not_identified",sources:[]}]}]};
const reply=(body:unknown,status=200)=>({ok:status<400,status,json:async()=>body} as Response);
let saved:Briefing;
beforeEach(()=>{saved=structuredClone(base);window.history.replaceState(null,"","/compare");vi.stubGlobal("fetch",vi.fn(async(url,options)=>{
 const path=String(url);
 if(path.endsWith('/knowledge/status'))return reply(library.status);
 if(path.endsWith("/briefings")&&options?.method==="POST")return reply(saved,201);
 if(path.includes("/briefings")&&!path.includes("/b1"))return reply({items:[]});
 if(path.endsWith("/advance")){saved=structuredClone(done);return reply(saved);}
 if(path.endsWith("/b1"))return reply(saved);
 throw Error(`Unexpected request ${path}`);
}));});
function Workspace({open=vi.fn(),ask=vi.fn(),data=library}){const [selected,setSelected]=useState<string[]>([]);return <NavigationProvider><PeerWorkspace library={data} selected={selected} setSelected={setSelected} open={open} ask={ask}/></NavigationProvider>;}

it('shows a resumable allowance pause and never loops on a rejected step',async()=>{
 const original=vi.mocked(fetch).getMockImplementation()!;
 vi.mocked(fetch).mockImplementation((...args)=>{if(String(args[0]).endsWith('/advance')){saved={...base,status:'paused',sections:[{...base.sections[0],status:'failed',error_code:'monthly_budget_exceeded'}]};return Promise.resolve(reply(saved));}return original(...args);});
 const user=userEvent.setup();render(<Workspace/>);
 await user.selectOptions(screen.getByRole('combobox',{name:'Primary company'}),'c0');
 await user.click(screen.getByRole('button',{name:/Generate analysis/}));
 expect(await screen.findByRole('heading',{name:'Analysis paused · allowance reached'})).toBeInTheDocument();
 expect(screen.getByRole('status')).toHaveTextContent('not an OpenAI error');
 expect(screen.getByRole('button',{name:'Continue unfinished topics'})).toBeEnabled();
 expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith('/advance'))).toHaveLength(1);
});

it('shows remaining allowance before generation and disables exhausted allowance',async()=>{
 const data=structuredClone(library);
 data.status.research.usage={monthly_accounted_usd:'5',monthly_recorded_estimate_usd:'4.5',monthly_reserved_usd:'0.5',monthly_remaining_usd:'0',daily_tokens_accounted:0,daily_tokens_remaining:1000,daily_resets_at:'2026-10-15T00:00:00Z'};
 const original=vi.mocked(fetch).getMockImplementation()!;
 vi.mocked(fetch).mockImplementation((...args)=>String(args[0]).endsWith('/knowledge/status')?Promise.resolve(reply(data.status)):original(...args));
 render(<Workspace data={data}/>);
 await userEvent.setup().selectOptions(screen.getByRole('combobox',{name:'Primary company'}),'c0');
 expect(screen.getByRole('status')).toHaveTextContent('$0.00 remaining of $5.00');
 expect(screen.getByRole('button',{name:/Generate analysis/})).toBeDisabled();
 expect(vi.mocked(fetch).mock.calls.every(([,options])=>options?.method==='GET')).toBe(true);
});

it("keeps reading progress across a pending stage boundary without starting AI calls",async()=>{
 vi.useFakeTimers();
 try {
  saved={...base,status:'running'};window.history.replaceState(null,'','/workspace/analysis?briefing=b1');
  const view=render(<Workspace/>);
  await act(async()=>{});
  saved=structuredClone(base);
  await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});
  saved=structuredClone(done);
  await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});
  expect(screen.getByRole('button',{name:'Calculations'})).toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.every(([,o])=>o?.method==='GET')).toBe(true);
  view.unmount();
 } finally {vi.useRealTimers();}
});

it("requires explicit generation, persists selection and opens source evidence",async()=>{
 const user=userEvent.setup(),open=vi.fn();render(<Workspace open={open}/>);
 expect(screen.getByRole("button",{name:/Generate analysis/})).toBeDisabled();
 await user.selectOptions(screen.getByRole("combobox",{name:"Primary company"}),"c0");await user.click(screen.getByRole("button",{name:"Fixture 1 ＋"}));
 expect(vi.mocked(fetch).mock.calls.every(([,o])=>o?.method!=="POST")).toBe(true);
 await user.click(screen.getByRole("button",{name:/Generate analysis/}));
 expect(await screen.findByText("A source-backed test finding.")).toBeInTheDocument();
 const create=vi.mocked(fetch).mock.calls.find(([url,o])=>String(url).endsWith("/briefings")&&o?.method==="POST");expect(JSON.parse(String(create?.[1]?.body))).toMatchObject({primary_company_id:"c0",peer_ids:["c1"]});
 await user.click(screen.getByRole("button",{name:"View source: Fixture 0, page 2"}));expect(open).toHaveBeenCalledWith(source, []);
 expect(screen.getByRole("link",{name:/Export for Excel/})).toHaveAttribute("href","/api/knowledge/briefings/b1/export?format=xlsx");
 await user.click(screen.getByRole("button",{name:"Sources"})); await user.click(screen.getByText("Evidence coverage"));expect(screen.getByRole("table")).toHaveTextContent("Not identified");
});
it("reopens a completed result with no model calls and keeps contextual chat scoped",async()=>{
 saved=structuredClone(done);window.history.replaceState(null,"","/compare?briefing=b1");const ask=vi.fn();render(<Workspace ask={ask}/>);
 await screen.findByText("A source-backed test finding.");await userEvent.setup().click(screen.getByRole("button",{name:"Findings"})); await userEvent.setup().selectOptions(screen.getByRole("combobox",{name:"Finding topic"}),"energy"); await userEvent.setup().click(screen.getByRole("button",{name:/Explain these findings/}));
 expect(ask).toHaveBeenCalledWith(expect.stringContaining("energy"),["c0","c1"]);expect(vi.mocked(fetch).mock.calls.every(([,o])=>o?.method==="GET")).toBe(true);
});
it("does not automatically retry failed analysis and retains partial results",async()=>{
 saved={...done,status:"failed",can_resume:true,sections:[...done.sections,{id:"targets",title:"Targets",status:"failed",result:null,error_code:"openai_timeout"}]};window.history.replaceState(null,"","/compare?briefing=b1");render(<Workspace/>);
 await screen.findByRole("heading",{name:"Analysis needs attention"}); expect(screen.getByRole("button",{name:"Continue unfinished topics"})).toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(1); await userEvent.setup().click(screen.getByRole("button",{name:"View saved findings"})); expect(screen.getByText("A source-backed test finding.")).toBeInTheDocument();
});
it("shows missing report availability before spending and preserves topic choice",async()=>{
 render(<Workspace/>);const user=userEvent.setup();await user.selectOptions(screen.getByRole("combobox",{name:"Primary company"}),"c2");
 expect(screen.getByText(/No searchable report for Fixture 2/)).toBeInTheDocument();expect(screen.getByRole("button",{name:/Generate analysis/})).toBeDisabled();
 await user.click(screen.getByRole("button",{name:"Fixture 0 ＋"}));expect(screen.getByRole("button",{name:/Generate analysis/})).toBeEnabled();
});
it("marks historical analyses and does not offer continuation with stale sources",async()=>{
 saved={...base,sources_current:false};window.history.replaceState(null,"","/compare?briefing=b1");render(<Workspace/>);expect(await screen.findByRole("alert")).toHaveTextContent("historical");expect(screen.queryByRole("button",{name:"Continue unfinished topics"})).not.toBeInTheDocument();
});
it("shows review opportunities without claiming confirmed non-disclosure",async()=>{
 saved={...done,review_opportunities:[{topic_id:"energy",topic:"Energy",peer_evidence_count:1,peer_count:1,primary_status:"not_identified",sources:[source],meaning:"Review only"}]};window.history.replaceState(null,"","/compare?briefing=b1");render(<Workspace/>);await screen.findByText("A source-backed test finding.");await userEvent.setup().click(screen.getByRole("button",{name:"Disclosure gaps"}));expect(screen.getByText(/not confirmed omissions/)).toBeInTheDocument();expect(screen.getByRole("button",{name:/Investigate this topic/})).toBeInTheDocument();
});
it("connects company analysis and the insights overview to saved workspace APIs",async()=>{
 const r=render(<NavigationProvider><CompanyIntelligence companyId="c0"/></NavigationProvider>);expect(screen.getByRole("link",{name:/Analyse company/})).toHaveAttribute("href","/workspace/new?company=c0");await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));r.unmount();
 render(<NavigationProvider><IntelligenceOverview library={library}/></NavigationProvider>);expect(screen.getByRole("heading",{name:"Your reports."})).toBeInTheDocument();expect(screen.getByRole("link",{name:/Company & report library 2 companies with searchable reports/})).toHaveAttribute("href","/workspace/library");
});

it("uses concise highlights with expandable detail and a topic filter",async()=>{
 const long="A detailed evidence-grounded finding. ".repeat(12);
 saved={...done,sections:[{id:"energy",title:"Energy",status:"completed",result:{...result,claims:[{text:long,citations:[source]}]},error_code:null},{id:"targets",title:"Targets",status:"completed",result:{...result,claims:[{text:"A target commitment is not achieved performance.",citations:[source]}]},error_code:null}]};
 window.history.replaceState(null,"","/compare?briefing=b1");render(<Workspace/>);
 const user=userEvent.setup(); await screen.findByRole("button",{name:"Findings"});
 expect(screen.queryByLabelText("Analysis progress")).not.toBeInTheDocument();
 await user.click(screen.getByRole("button",{name:"Findings"}));
 await user.selectOptions(screen.getByRole("combobox",{name:"Finding topic"}),"energy");
 const reading=screen.getByText(long.trim()).closest("details")!;
 expect(reading).not.toHaveAttribute("open"); await user.click(reading.querySelector("summary")!); expect(reading).toHaveAttribute("open");
 expect(screen.queryByText("A target commitment is not achieved performance.")).not.toBeInTheDocument();
 await user.selectOptions(screen.getByRole("combobox",{name:"Finding topic"}),"targets"); expect(screen.getByText("A target commitment is not achieved performance.")).toBeInTheDocument();
});

it("separates real progress from results, without fake percentages",async()=>{
 let release!: (value:Response)=>void;
 const original=vi.mocked(fetch).getMockImplementation()!;
 vi.mocked(fetch).mockImplementation((...args)=>String(args[0]).endsWith("/advance")?new Promise(resolve=>{release=resolve;}):original(...args));
 const user=userEvent.setup();render(<Workspace/>);
 await user.selectOptions(screen.getByRole("combobox",{name:"Primary company"}),"c0");
 await user.click(screen.getByRole("button",{name:/Generate analysis/}));
 expect(await screen.findByLabelText("Analysis progress")).toHaveTextContent("0 of 1 topics completed");
 expect(screen.queryByRole("button",{name:"Calculations"})).not.toBeInTheDocument();
 expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument();
 release(reply(done)); await screen.findByRole("button",{name:"Calculations"});
 expect(screen.queryByLabelText("Analysis progress")).not.toBeInTheDocument();
});

it("presents the two client deliverables and a readable report without new AI calls",async()=>{
 saved=structuredClone(done);window.history.replaceState(null,"","/workspace/analysis?briefing=b1");render(<Workspace/>);
 expect(await screen.findByRole("link",{name:'Client report PDF · findings, calculations & peer distinctions'})).toHaveAttribute("href","/api/knowledge/briefings/b1/export?format=pdf");
 expect(screen.getByRole("link",{name:/Analysis workbook Excel/})).toHaveAttribute("href","/api/knowledge/briefings/b1/export?format=xlsx");
 await userEvent.setup().click(screen.getByRole("button",{name:"Report"}));
 expect(screen.getByRole("heading",{name:"Your report"})).toBeInTheDocument();
 expect(screen.getByText("A source-backed test finding.")).toBeInTheDocument();
 expect(vi.mocked(fetch).mock.calls.every(([,o])=>o?.method==="GET")).toBe(true);
});

it("passes the selected package to the reproducible research workflow",async()=>{
 render(<Workspace/>);const user=userEvent.setup();
 await user.selectOptions(screen.getByRole("combobox",{name:"Report package"}),"sector");
 await user.selectOptions(screen.getByRole("combobox",{name:"Primary company"}),"c0");
 await user.click(screen.getByRole("button",{name:/Generate analysis/}));
 await screen.findByRole("button",{name:"Report"});
 const call=vi.mocked(fetch).mock.calls.find(([url,o])=>String(url).endsWith("/briefings")&&o?.method==="POST");
 expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({package:"sector"});
 expect(JSON.parse(String(call?.[1]?.body)).topics).toHaveLength(10);
});

it("does not continue after navigation unmounts a running workspace",async()=>{
 let release!: (value:Response)=>void;
 const original=vi.mocked(fetch).getMockImplementation()!;
 vi.mocked(fetch).mockImplementation((...args)=>String(args[0]).endsWith("/advance")?new Promise(resolve=>{release=resolve;}):original(...args));
 const user=userEvent.setup();const view=render(<Workspace/>);
 await user.selectOptions(screen.getByRole("combobox",{name:"Primary company"}),"c0");
 await user.click(screen.getByRole("button",{name:/Generate analysis/}));
 await screen.findByLabelText("Analysis progress"); view.unmount(); release(reply({...base,completed_topics:1}));
 await waitFor(()=>expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith("/advance"))).toHaveLength(1));
});
