import {useState} from "react";
import {render, screen, within, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {beforeEach, expect, it, vi} from "vitest";
import {LibraryDirectory, LibraryCompanyPage, LibraryPeerComparison, LibrarySources, ReportSearch, passageSelection} from "../components/ReportLibrary";
import {Sustainobot, citationGroups} from "../components/Sustainobot";
import {SourceDrawer} from "../components/SourceDrawer";
import {NavigationProvider} from "../lib/navigation";
import {knowledge, loadReportLibrary, reportTitle, safeUrl, type Answer, type LibraryCompany, type Passage, type ReportLibrary} from "../lib/knowledge";

// Synthetic fixtures stay inside tests. Nothing here seeds the application database.
const companies:LibraryCompany[]=Array.from({length:30},(_,i)=>({id:`c${i}`,company_name:`Test Company ${i}`,ticker:`T${i}`,country:i===0?"GB":"US",region:"Test",sector:i===0?"Energy":"Technology",industry:"Test",official_domain:"example.com",exchange:"TEST",reports_downloaded:i===29?0:1,reports_indexed:i===29?0:1,pages_indexed:i===29?0:40,text_gaps:false,availability:i===29?"not_collected":"searchable",collection_status:i===29?"unavailable":"succeeded"}));
const passage:Passage={evidence_id:"e1",company_id:"c0",company:"Test Company 0",report_id:"r0",report:"Test report",page:12,page_url:"/api/reports/r0/file#page=12",source_url:"https://example.com/report.pdf",text:"Test evidence: suppliers receive training.",quote:"suppliers receive training",report_sha256:"abc",reporting_year:2025,detected_year:2025,kind:"page"};
const library:ReportLibrary={companies,status:{companies_in_scope:30,official_reports_downloaded:29,reports_indexed:29,companies_with_indexed_reports:29,pages_indexed:1160,reports_with_text_gaps:0,research:{provider:"openai",model:"test-model",enabled:true,configuration_error:null,monthly_budget_usd:5}},reports:[{id:"r0",company_id:"c0",company:"Test Company 0",title:"Test report",document_role:"primary_report_candidate",reporting_year:2025,detected_year:2025,source_url:"https://example.com/report.pdf",sha256:"abc",file_url:"/api/reports/r0/file",knowledge_status:"indexed",parse_status:"parsed",retrieved_at:"2026-10-01T00:00:00Z",quality:{coverage:"complete_extracted_text"}}]};
const answer:Answer={answer_id:"a1",status:"answered",claims:[{text:"The company describes supplier training.",citations:[passage]}],coverage:{companies_supplied:1,passages_supplied:1,exhaustive:false,companies:[{company_id:"c0",company:"Test Company 0",status:"supplied",matching_passages:1}]},model:"test-model",cached:false,model_called:true,estimated_cost_usd:"0.001",usage:{latency_ms:200,input_tokens:100,output_tokens:20},request_scope:{company_ids:["c0"]}};
const reply=(body:unknown,status=200)=>({ok:status>=200&&status<300,status,json:async()=>body});
it("does not turn a report label year into a metric observation year",()=>{
 const evidence=passageSelection({...passage,reporting_year:null,detected_year:2025}).evidence![0];
 expect(evidence.report_year).toBe(2025);
 expect(evidence.reporting_year).toBeUndefined();
 expect(evidence.kind).toBe("report_passage");
});
it("shows passage provenance without suggesting unextracted values are missing metrics",()=>{
 const file="/api/reports/01900000-0000-4000-8000-000000000005/file";
 render(<SourceDrawer selection={passageSelection({...passage,page_url:file+"#page=12"})} onClose={vi.fn()}/>);
 expect(screen.getByText("Report label year")).toBeInTheDocument();
 expect(screen.queryByText("Reporting year")).not.toBeInTheDocument();
 expect(screen.queryByText("Raw value")).not.toBeInTheDocument();
 expect(screen.getByText("suppliers receive training")).toBeInTheDocument();
 expect(screen.getByRole("link",{name:/Open saved PDF/})).toHaveAttribute("href",file+"#page=12&view=FitH");
});
const calls=()=>vi.mocked(fetch).mock.calls.map(([url,options])=>({url:String(url),body:options?.body?JSON.parse(String(options.body)):undefined}));
it("groups repeated page citations without dropping distinct excerpts or reports",()=>{
 const second={...passage,evidence_id:"e2",quote:"Another exact excerpt"};
 const otherReport={...passage,report_id:"r2"};
 const otherPage={...passage,page:13};
 expect(citationGroups([passage,passage,second,otherReport,otherPage])).toEqual([[passage,second],[otherReport],[otherPage]]);
});
beforeEach(()=>{window.history.replaceState(null,"","/");vi.stubGlobal("fetch",vi.fn(async(url)=>{
 const path=String(url);
 if(path.endsWith("/knowledge/companies"))return reply({items:companies});
 if(path.endsWith("/knowledge/status"))return reply(library.status);
 if(path.includes("/knowledge/reports"))return reply({items:library.reports});
 if(path.endsWith("/knowledge/answers"))return reply({items:[]});
 if(path.endsWith("/knowledge/search"))return reply({items:[passage],total:1});
 if(path.endsWith("/knowledge/preview"))return reply({coverage:answer.coverage});
 if(path.endsWith("/knowledge/ask"))return reply(answer);
 throw new Error(`Unexpected test request ${path}`);
}));});
const wrap=(element:React.ReactNode)=>render(<NavigationProvider>{element}</NavigationProvider>);
function Directory(){const [ids,setIds]=useState<string[]>([]);return <LibraryDirectory library={library} selected={ids} setSelected={setIds}/>;}
function Chat({source=vi.fn(),analysisId}: {source?:(p:Passage)=>void;analysisId?:string}){const [ids,setIds]=useState(["c0"]),[draft,setDraft]=useState("");return <Sustainobot open onClose={vi.fn()} companies={companies} selected={ids} onSelect={setIds} draft={draft} setDraft={setDraft} openSource={source} analysisId={analysisId}/>;}

it('explains saved calculations and keeps follow-ups in the same analysis',async()=>{
 const original=vi.mocked(fetch).getMockImplementation()!;
 vi.mocked(fetch).mockImplementation((url,init)=>String(url).endsWith('/briefings/b1/explain')?Promise.resolve(reply({...answer,analysis_id:'b1'}) as Response):original(url,init));
 render(<Chat analysisId="b1"/>);const user=userEvent.setup();
 await user.type(screen.getByRole('textbox',{name:'Ask Sustainobot'}),'Explain the training comparison');
 await user.click(screen.getByRole('button',{name:'Send question'}));
 await screen.findByText('The company describes supplier training.');
 await user.type(screen.getByRole('textbox',{name:'Ask Sustainobot'}),'How is that calculated?');
 await user.click(screen.getByRole('button',{name:'Send question'}));
 await waitFor(()=>expect(calls().filter(c=>c.url.endsWith('/explain'))).toHaveLength(2));
 expect(calls().filter(c=>c.url.endsWith('/explain'))[1].body).toEqual({question:'How is that calculated?',previous_questions:['Explain the training comparison']});
 expect(calls().filter(c=>c.url.endsWith('/ask'))).toHaveLength(0);
});

it("loads the real library contract without substituting research fixtures",async()=>{expect(await loadReportLibrary()).toEqual(library);expect(calls().every(c=>!c.url.includes("/ask"))).toBe(true);});
it("fails closed on an invalid directory response",async()=>{vi.mocked(fetch).mockResolvedValue(reply({}) as Response);await expect(loadReportLibrary()).rejects.toThrow("No replacement data");});
it("paginates and filters the company roster independently of metric availability",async()=>{wrap(<Directory/>);const user=userEvent.setup();expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(26);await user.click(screen.getByRole("button",{name:"Next →"}));expect(screen.getByText("26–30 of 30")).toBeInTheDocument();await user.selectOptions(screen.getByRole("combobox",{name:"Sector"}),"Energy");expect(await screen.findByText("1–1 of 1")).toBeInTheDocument();expect(within(screen.getByRole("table")).getByText("Test Company 0")).toBeInTheDocument();});
it("limits selected peers to five and can clear them",async()=>{wrap(<Directory/>);const user=userEvent.setup();for(let i=0;i<5;i++)await user.click(screen.getByRole("checkbox",{name:`Select Test Company ${i}`}));expect(screen.getByRole("checkbox",{name:"Select Test Company 5"})).toBeDisabled();await user.click(screen.getByRole("button",{name:"Clear selection"}));expect(screen.getByRole("checkbox",{name:"Select Test Company 5"})).toBeEnabled();});
it("does not present uncollected company reports as analysed",()=>{wrap(<LibraryCompanyPage company={companies[29]} reports={[]} selected={[]} setSelected={vi.fn()} open={vi.fn()} ask={vi.fn()}/>);expect(screen.getByText(/not counted as analysed/)).toBeInTheDocument();expect(screen.getByRole("button",{name:"Explore company insights ↗"})).toBeDisabled();expect(screen.queryByText("0 tCO2e")).not.toBeInTheDocument();});
it("searches actual passages and passes page provenance into source viewing",async()=>{const open=vi.fn();wrap(<ReportSearch companyIds={["c0"]} open={open} ask={vi.fn()}/>);const user=userEvent.setup();await user.type(screen.getByRole("searchbox",{name:"Search report text"}),"supplier training");await user.click(screen.getByRole("button",{name:"Search report text"}));await user.click(await screen.findByRole("button",{name:"View source · page 12 ↗"}));expect(open).toHaveBeenCalledWith(passage);expect(calls()[0].body.company_ids).toEqual(["c0"]);expect(passageSelection(passage).evidence?.[0]).toMatchObject({source_page:12,supporting_excerpt:passage.quote,report_sha256:"abc",validation_state:"source_text_not_metric_validation"});});
it("does not turn empty retrieval into a finding of nondisclosure",async()=>{vi.mocked(fetch).mockResolvedValue(reply({items:[],total:0}) as Response);wrap(<ReportSearch initial="missing disclosure" open={vi.fn()} ask={vi.fn()}/>);expect(await screen.findByText(/does not prove the topic is absent/)).toBeInTheDocument();expect(calls().some(c=>c.url.endsWith("/ask"))).toBe(false);});
it("retains source title, hash and report URL in the source library",()=>{wrap(<LibrarySources library={library} open={vi.fn()} ask={vi.fn()}/>);expect(screen.getByRole("link",{name:"Open PDF ↗"})).toHaveAttribute("href",expect.stringContaining("/api/reports/r0/file"));expect(screen.getByText("abc")).toBeInTheDocument();expect(screen.getByRole("heading",{name:"Test report"})).toBeInTheDocument();});
it("prepares scoped comparison questions without an automatic model call",async()=>{const ask=vi.fn();wrap(<LibraryPeerComparison library={library} selected={["c0","c1"]} setSelected={vi.fn()} open={vi.fn()} ask={ask}/>);const user=userEvent.setup();await user.selectOptions(screen.getByRole("combobox",{name:"Comparison topic"}),"Renewable electricity");await user.click(screen.getByRole("button",{name:"Explain this comparison ↗"}));expect(ask).toHaveBeenCalledWith(expect.stringContaining("renewable electricity"),["c0","c1"]);expect(fetch).not.toHaveBeenCalled();});
it("retrieves each selected peer separately",async()=>{wrap(<LibraryPeerComparison library={library} selected={["c0","c1"]} setSelected={vi.fn()} open={vi.fn()} ask={vi.fn()}/>);await userEvent.setup().click(screen.getByRole("button",{name:"Find source passages"}));await screen.findAllByText("Test evidence: suppliers receive training.");expect(calls().map(c=>c.body.company_ids)).toEqual([["c0"],["c1"]]);});
it("uses the cyan robot, waits for explicit send, and opens a citation",async()=>{const source=vi.fn();render(<Chat source={source}/>);const user=userEvent.setup();expect(document.querySelector(".sustainobot-header img")).toHaveAttribute("src","/brand/sustainobot-cyan.png");await user.click(screen.getByRole("button",{name:"Find source evidence"}));expect(calls().filter(c=>c.url.endsWith("/ask"))).toHaveLength(0);await user.click(screen.getByRole("button",{name:"Send question"}));await user.click(await screen.findByRole("button",{name:"View source: Test Company 0, page 12"}));expect(source).toHaveBeenCalledWith(passage);expect(screen.getByText("Live AI analysis")).toBeInTheDocument();});
it("follows up using a saved answer id and the same peer scope",async()=>{render(<Chat/>);const user=userEvent.setup();const input=screen.getByRole("textbox",{name:"Ask Sustainobot"});await user.type(input,"Describe supplier programmes");await user.click(screen.getByRole("button",{name:"Send question"}));await screen.findByText("The company describes supplier training.");await user.type(input,"Which actions are explicitly stated?");await user.click(screen.getByRole("button",{name:"Send question"}));await waitFor(()=>expect(calls().filter(c=>c.url.endsWith("/ask"))).toHaveLength(2));expect(calls().filter(c=>c.url.endsWith("/ask"))[1].body).toMatchObject({company_ids:["c0"],parent_answer_id:"a1"});});
it("starts a fresh conversation when the selected scope changes",async()=>{render(<Chat/>);const user=userEvent.setup();await user.type(screen.getByRole("textbox",{name:"Ask Sustainobot"}),"Describe supplier programmes");await user.click(screen.getByRole("button",{name:"Send question"}));await screen.findByText("The company describes supplier training.");await user.click(screen.getByRole("button",{name:"Peers and history"}));await user.click(screen.getByRole("button",{name:"Search whole library"}));await user.type(screen.getByRole("textbox",{name:"Ask Sustainobot"}),"What biodiversity programmes are described?");await user.click(screen.getByRole("button",{name:"Send question"}));await waitFor(()=>expect(calls().filter(c=>c.url.endsWith("/ask"))).toHaveLength(2));expect(calls().filter(c=>c.url.endsWith("/ask"))[1].body).toMatchObject({company_ids:[],parent_answer_id:null});});
it("preserves a failed question and never silently switches providers",async()=>{const original=vi.mocked(fetch).getMockImplementation()!;vi.mocked(fetch).mockImplementation((url,init)=>String(url).endsWith("/ask")?Promise.resolve(reply({detail:{code:"openai_rate_limit"}},429) as Response):original(url,init));render(<Chat/>);const user=userEvent.setup();await user.type(screen.getByRole("textbox",{name:"Ask Sustainobot"}),"Describe supplier programmes");await user.click(screen.getByRole("button",{name:"Send question"}));expect(await screen.findByRole("alert")).toHaveTextContent("rate-limiting");expect(screen.getByRole("textbox",{name:"Ask Sustainobot"})).toHaveValue("Describe supplier programmes");expect(calls().filter(c=>c.url.endsWith("/ask"))).toHaveLength(1);});
it("reopens saved research without repeating inference",async()=>{const original=vi.mocked(fetch).getMockImplementation()!;vi.mocked(fetch).mockImplementation((url,init)=>String(url).endsWith("/answers")?Promise.resolve(reply({items:[{answer_id:"a1",question:"Earlier question",created_at:"2026-10-01",model:"test-model",request_scope:{company_ids:["c0"]}}]}) as Response):String(url).endsWith("/answers/a1")?Promise.resolve(reply({answer_id:"a1",question:"Earlier question",status:"completed",sources_current:true,result:answer}) as Response):original(url,init));render(<Chat/>);const user=userEvent.setup();await user.click(screen.getByRole("button",{name:"Peers and history"}));await user.click(await screen.findByRole("button",{name:"Saved research (1)"}));await user.click(screen.getByRole("button",{name:/Earlier question/}));expect(await screen.findByText("Saved answer · no new AI call")).toBeInTheDocument();expect(calls().filter(c=>c.url.endsWith("/ask"))).toHaveLength(0);});
it("keeps strict error messages and safe source URLs",async()=>{vi.mocked(fetch).mockResolvedValue(reply({detail:{code:"unsupported_number"}},422) as Response);await expect(knowledge("/knowledge/ask",{})).rejects.toThrow("no replacement figures");expect(safeUrl("javascript:alert(1)")).toBeUndefined();expect(reportTitle("Download PDF","https://example.com/annual_report_2025.pdf")).toBe("annual report 2025");});

it("shows useful partial findings with citations instead of the old dead-end response",async()=>{
 const original=vi.mocked(fetch).getMockImplementation()!;
 vi.mocked(fetch).mockImplementation((url,init)=>String(url).endsWith("/ask")?Promise.resolve(reply({...answer,status:"partial",notes:["These are reported examples, not an overall ranking."],research_plan:{intent:"comparison",queries:["supplier training","emissions programmes"],company_names:[],comparison_basis:null}}) as Response):original(url,init));
 const source=vi.fn();render(<Chat source={source}/>);const user=userEvent.setup();
 await user.type(screen.getByRole("textbox",{name:"Ask Sustainobot"}),"Compare the companies");await user.click(screen.getByRole("button",{name:"Send question"}));
 expect(await screen.findByText("Partial answer · source-backed findings")).toBeInTheDocument();
 expect(screen.getByText("These are reported examples, not an overall ranking.")).toBeInTheDocument();
 expect(screen.getByText("The company describes supplier training.")).toBeInTheDocument();
 await user.click(screen.getByRole("button",{name:"View source: Test Company 0, page 12"}));expect(source).toHaveBeenCalledWith(passage);
 expect(screen.queryByText(/Try a narrower company or topic/)).not.toBeInTheDocument();
 expect(calls().some(c=>c.url.endsWith("/preview"))).toBe(false);
});

it("renders database counts without presenting them as report-extracted facts",async()=>{
 const original=vi.mocked(fetch).getMockImplementation()!;
 vi.mocked(fetch).mockImplementation((url,init)=>String(url).endsWith("/ask")?Promise.resolve(reply({...answer,claims:[],calculations:[{label:"Companies in the selected library scope",value:30,source:"/api/knowledge/status"}]}) as Response):original(url,init));
 render(<Chat/>);const user=userEvent.setup();await user.type(screen.getByRole("textbox",{name:"Ask Sustainobot"}),"How many companies are in the database?");await user.click(screen.getByRole("button",{name:"Send question"}));
 expect(await screen.findByText("30",{selector:"strong"})).toBeInTheDocument();
 expect(screen.getByText(/database count/)).toBeInTheDocument();
 expect(screen.queryByRole("button",{name:/View source:/})).not.toBeInTheDocument();
});
