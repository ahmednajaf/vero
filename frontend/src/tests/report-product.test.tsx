import {render, screen, within, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {beforeEach, expect, it, vi} from "vitest";
import {ReportApp} from "../app/ReportApp";

const companies=Array.from({length:5},(_,i)=>({id:`c${i}`,company_name:`Fixture Company ${i}`,ticker:`FC${i}`,country:i===0?"GB":"US",sector:"Technology",industry:"Technology",region:"Europe",exchange:"TEST",official_domain:"example.com",reports_downloaded:1,reports_indexed:1,pages_indexed:20,text_gaps:false,availability:"searchable",collection_status:"succeeded"}));
const report={id:"r1",company_id:"c0",company:"Fixture Company 0",title:"Fixture report",source_url:"https://example.com/report.pdf",sha256:"test",file_url:"/api/reports/r1/file",knowledge_status:"indexed",parse_status:"parsed",reporting_year:2025,detected_year:2025,document_role:"primary_report",retrieved_at:null,quality:null};
const observation={id:"o1",company_id:"c0",company_name:"Fixture Company 0",metric:"scope_1_emissions",report_title:"Fixture report",source_url:report.source_url,source_page:9,raw_value:"12500",raw_unit:"tCO2e",normalised_value:"12500",normalised_unit:"tCO2e",reporting_year:2024,supporting_excerpt:"Scope 1 emissions 2024: 12500 tCO2e.",validation_state:"needs_review",source_policy:"official"};
beforeEach(()=>{window.history.replaceState(null,"","/");vi.stubGlobal("fetch",vi.fn(async(url:string)=>{
 const body=url.includes("/knowledge/briefings")?{items:[]}:url.includes("/knowledge/companies")?{items:companies}:url.includes("/knowledge/status")?{companies_in_scope:5,companies_with_indexed_reports:5,reports_indexed:5,research:{configuration_error:null,model:"fixture-mini",monthly_budget_usd:5}}:url.includes("/knowledge/reports")?{items:[report]}:url.includes("/knowledge/answers")?{items:[]}:url.endsWith("/evidence")?{company_id:"c0",observations:[observation],reports:[{...report,local_url:report.file_url,pages:20}]}:null;
 if(body===null)throw Error("Unexpected route: "+url);
 return {ok:true,status:200,json:async()=>body};
}));});
it("retires the sample study without loading a hidden pharma dataset",async()=>{
 window.history.replaceState(null,"","/edition");render(<ReportApp/>);
 expect(await screen.findByRole("heading",{name:"Your reports."})).toBeInTheDocument();
 expect(vi.mocked(fetch).mock.calls.every(([url])=>!String(url).includes("/research/pharma"))).toBe(true);
 expect(screen.queryByText(/Reviewed pharma/)).not.toBeInTheDocument();
});
it("supports company search and country filters",async()=>{
 window.history.replaceState(null,"","/companies");const user=userEvent.setup();render(<ReportApp/>);await screen.findByRole("table");
 await user.type(screen.getByRole("searchbox",{name:"Search companies"}),"FC0");expect(within(screen.getByRole("table")).queryByText("Fixture Company 1")).not.toBeInTheDocument();
 await user.click(screen.getByRole("button",{name:"Clear filters"}));await user.selectOptions(screen.getByRole("combobox",{name:"Country"}),"GB");expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2);
});
it("opens a saved reported figure and restores source-button focus",async()=>{
 window.history.replaceState(null,"","/companies/c0");render(<ReportApp/>);const user=userEvent.setup();
 await user.click(await screen.findByRole("button",{name:"Figures"}));
 const button=await screen.findByRole("button",{name:/Fixture Company 0 Scope 1 emissions 2024 page 9/});
 await user.click(button);expect(screen.getByRole("dialog",{name:"Source evidence"})).toHaveTextContent(observation.supporting_excerpt);
 await user.keyboard("{Escape}");expect(button).toHaveFocus();
 expect(vi.mocked(fetch).mock.calls.every(([,opts])=>!opts?.method||opts.method==="GET")).toBe(true);
});
it("shows proposed pricing with working scope links and no checkout",async()=>{
 window.history.replaceState(null,"","/pricing");render(<ReportApp/>);
 expect(screen.getByRole("heading",{name:"Company benchmark"})).toBeInTheDocument();
 expect(screen.getByText("$5,000")).toBeInTheDocument();expect(screen.getByText("$10,000")).toBeInTheDocument();
 expect(screen.getByRole("link",{name:/Request company benchmark/})).toHaveAttribute("href","/contact?package=company");
 expect(screen.getByText(/checkout is not enabled/)).toBeInTheDocument();
 await waitFor(()=>expect(fetch).toHaveBeenCalled());
});
it("keeps source years independent of obsolete study query parameters",async()=>{
 window.history.replaceState(null,"","/companies?year=2024");render(<ReportApp/>);expect(await screen.findByRole("table")).toBeInTheDocument();
 expect(screen.queryByText(/No edition for/)).not.toBeInTheDocument();
});
it("shows unavailable data without substituting sample figures",async()=>{
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:false,status:503,json:async()=>({})}));render(<ReportApp/>);
 expect(await screen.findByRole("alert")).toBeInTheDocument();expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
it("retires the race route",async()=>{window.history.replaceState(null,"","/race");render(<ReportApp/>);expect(await screen.findByRole("heading",{name:"This page has been retired."})).toBeInTheDocument();});
it("preserves the globe landing and navigates through the existing wheel",async()=>{
 render(<ReportApp/>);expect(screen.getByRole("heading",{name:"Explore company sustainability."})).toBeInTheDocument();
 expect(await screen.findByRole("button",{name:"Europe"})).toBeInTheDocument();expect(screen.queryByRole("table")).not.toBeInTheDocument();
 await userEvent.setup().click(screen.getByRole("button",{name:"Open navigation"}));
 const nav=screen.getByRole("navigation",{name:"Main navigation"});
 expect(within(nav).getByRole("link",{name:"Pricing"})).toHaveAttribute("href","/pricing");
 expect(within(nav).getAllByRole("link").map(link=>link.textContent)).toEqual(["Home","Workspace","Pricing","How it works"]);
 expect(within(nav).queryByRole("link",{name:"Race"})).not.toBeInTheDocument();
});
it("groups companies and source reports under one library",async()=>{
 window.history.replaceState(null,"","/workspace/library");render(<ReportApp/>);const user=userEvent.setup();
 expect(await screen.findByRole("heading",{name:"Company library."})).toBeInTheDocument();
 await user.click(within(screen.getByRole("navigation",{name:"Library views"})).getByRole("link",{name:"Reports"}));
 expect(await screen.findByRole("heading",{name:"Report library."})).toBeInTheDocument();
 expect(screen.getByRole("link",{name:/Open PDF/})).toHaveAttribute("href",new URL(report.file_url,window.location.origin).href);
});
it("keeps methodology concise with technical detail on demand",async()=>{
 window.history.replaceState(null,"","/methodology");render(<ReportApp/>);
 expect(screen.getByRole("heading",{name:"From reports to a clearer picture."})).toBeInTheDocument();
 expect(screen.getByText("How are figures compared?").closest("details")).not.toHaveAttribute("open");
 await userEvent.setup().click(screen.getByText("How are figures compared?"));
 expect(screen.getByText(/Compatible units are converted automatically/)).toBeVisible();
});

it("opens the global assistant in the saved analysis, not an unrelated library search",async()=>{
 const original=vi.mocked(fetch).getMockImplementation()!;
 const briefing={id:'b1',title:'Saved comparison',primary_company_id:'c0',status:'ready',created_at:'2026-10-14',updated_at:'2026-10-14',sources_current:true,can_resume:false,completed_topics:0,findings_count:0,estimated_cost_usd:0,cost_note:'',definition:{company_ids:['c0','c1'],report_ids:['r1'],companies:companies.slice(0,2),focus:''},sections:[],matrix:[],review_opportunities:[]};
 vi.mocked(fetch).mockImplementation(async(...args)=>String(args[0]).endsWith('/briefings/b1')?{ok:true,status:200,json:async()=>briefing} as Response:original(...args));
 window.history.replaceState(null,'','/workspace/analysis?briefing=b1');
 render(<ReportApp/>);const user=userEvent.setup();await screen.findByRole('heading',{name:'Saved comparison'});
 await user.click(screen.getByRole('button',{name:'Explore findings'}));
 expect(await screen.findByText('Explaining this saved analysis · calculations and source evidence')).toBeInTheDocument();
 expect(screen.getByRole('dialog',{name:'Explore the findings'})).toHaveTextContent('Fixture Company 0');
 expect(vi.mocked(fetch).mock.calls.every(([,o])=>o?.method==='GET')).toBe(true);
});

it("does not silently open general research when the selected analysis cannot load",async()=>{
 const original=vi.mocked(fetch).getMockImplementation()!;
 vi.mocked(fetch).mockImplementation(async(...args)=>String(args[0]).endsWith('/briefings/missing')?{ok:false,status:404,json:async()=>({})} as Response:original(...args));
 window.history.replaceState(null,'','/workspace/analysis?briefing=missing');render(<ReportApp/>);
 await userEvent.setup().click(await screen.findByRole('button',{name:'Explore findings'}));
 await waitFor(()=>expect(screen.getAllByRole('alert').some(a=>a.textContent?.includes('no longer available'))).toBe(true));
 expect(screen.queryByRole('dialog',{name:'Explore the findings'})).not.toBeInTheDocument();
});
