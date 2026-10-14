import {useEffect, useRef, useState, type FormEvent, type KeyboardEvent} from "react";
import {exportAnswer, knowledge, type Answer, type HistoryItem, type LibraryCompany, type Passage, type SavedAnswer} from "../lib/knowledge";
import {AnimatePresence} from "framer-motion";
import {Send, RotateCcw, SlidersHorizontal, X, ArrowUpRight} from "lucide-react";
import {ChatMessageBubble, ChatTypingIndicator} from "./ui/chat-messages";

const avatar="/brand/sustainobot-cyan.png";
interface Message {question:string;answer?:Answer;error?:string;stage?:string;historical?:boolean}
/** Collapse repeated page buttons, preserving every distinct supporting excerpt. */
export function citationGroups(citations:Passage[]):Passage[][] {
  const groups=new Map<string,Passage[]>();
  for(const citation of citations){
    const key=`${citation.report_id}:${citation.page}`;
    const group=groups.get(key)??[];
    if(!group.some(p=>p.evidence_id===citation.evidence_id&&(p.quote??p.text)===(citation.quote??citation.text)))group.push(citation);
    groups.set(key,group);
  }
  return [...groups.values()];
}
function CitationLinks({citations,openSource}:{citations:Passage[];openSource:(p:Passage,related?:Passage[])=>void}){
  const groups=citationGroups(citations);
  const sourceButton=(group:Passage[])=>{
    const p=group[0];
    return <button key={`${p.report_id}-${p.page}`} onClick={()=>group.length>1?openSource(p,group.slice(1)):openSource(p)} aria-label={`View source: ${p.company}, page ${p.page}`}>
      {p.company} <span>p. {p.page}{group.length>1?` · ${group.length} excerpts`:""} ↗</span>
    </button>;
  };
  return <div className="report-citations">{groups.slice(0,3).map(sourceButton)}{groups.length>3&&<details><summary>+ {groups.length-3} source pages</summary>{groups.slice(3).map(sourceButton)}</details>}</div>;
}
export function SustainobotLauncher({onOpen,compact=false}:{onOpen:()=>void;compact?:boolean}){
  return <button className={`sustainobot-launcher${compact?" compact":""}`} aria-label="Open Sustainobot" onClick={onOpen}><img src={avatar} alt=""/><span className="sustainobot-greeting"><strong>Hi, I’m Sustainobot <span aria-hidden="true">✧</span></strong>{!compact&&<span>Ask me about emissions,<br/>climate targets or company insights.</span>}<i aria-hidden="true">→</i></span></button>;
}

export function Sustainobot({open,onClose,companies,selected,onSelect,draft,setDraft,openSource,covered=false,configurationError,analysisId,onAnalysisChange,workspace=false}:{workspace?:boolean;open:boolean;onClose:()=>void;companies:LibraryCompany[];selected:string[];onSelect:(ids:string[])=>void;draft:string;setDraft:(q:string)=>void;openSource:(p:Passage,related?:Passage[])=>void;covered?:boolean;configurationError?:string|null;analysisId?:string|null;onAnalysisChange?:(id:string|null)=>void}){
  const [messages,setMessages]=useState<Message[]>([]);const [busy,setBusy]=useState(false);const [history,setHistory]=useState<HistoryItem[]>([]);const [historyError,setHistoryError]=useState("");const [search,setSearch]=useState("");const [scopeKey,setScopeKey]=useState("");const [savedOpen,setSavedOpen]=useState(false);
  const [optionsOpen,setOptionsOpen]=useState(false);
  const panel=useRef<HTMLElement>(null),input=useRef<HTMLTextAreaElement>(null),bottom=useRef<HTMLDivElement>(null);const alive=useRef(true);
  const key=[...selected].sort().join(",")+(analysisId?`:${analysisId}`:'');const selectedCompanies=companies.filter(c=>selected.includes(c.id));
  function refresh(){return knowledge<{items:HistoryItem[]}>("/knowledge/answers").then(r=>{if(alive.current){setHistory(r.items);setHistoryError("");}}).catch(e=>{if(alive.current)setHistoryError(e.message);});}
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  useEffect(()=>{if(!open)return;const previous=document.activeElement as HTMLElement|null;const overflow=document.body.style.overflow;document.body.style.overflow="hidden";input.current?.focus();void refresh();return()=>{document.body.style.overflow=overflow;if(previous?.isConnected)previous.focus();};},[open]);
  useEffect(()=>{if(open&&!covered)bottom.current?.scrollIntoView?.({block:"nearest",behavior:"smooth"});},[messages,open]);
  function keys(e:KeyboardEvent<HTMLElement>){if(covered)return;if(e.key==="Escape"){e.preventDefault();onClose();}if(e.key==="Tab"){const nodes=[...(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),textarea:not(:disabled),summary')??[])].filter(el=>el.getClientRects().length>0);const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}}
  async function restore(id:string){if(busy)return;setBusy(true);setHistoryError("");try{const chain:Message[]=[];let next:string|null=id;let ids:string[]=[];let restoredAnalysis:string|null=null;const seen=new Set<string>();while(next&&chain.length<12&&!seen.has(next)){seen.add(next);const saved:SavedAnswer=await knowledge(`/knowledge/answers/${next}`);if(saved.status!=="completed")throw new Error("This answer did not complete. Ask the question again.");if(!chain.length){ids=saved.result.request_scope?.company_ids??[];restoredAnalysis=saved.result.analysis_id??null;}chain.unshift({question:saved.question,answer:{...saved.result,answer_id:saved.answer_id,cached:true,model_called:false},historical:!saved.sources_current});next=saved.result.parent_answer_id??null;}onSelect(ids);onAnalysisChange?.(restoredAnalysis);setScopeKey([...ids].sort().join(",")+(restoredAnalysis?`:${restoredAnalysis}`:''));setMessages(chain);setDraft("");setSavedOpen(false);setOptionsOpen(false);input.current?.focus();}catch(e){setHistoryError((e as Error).message);}finally{setBusy(false);}}
  async function submit(e?:FormEvent){
    e?.preventDefault();const question=draft.trim();if(busy||question.length<5)return;
    const previous=key===scopeKey?messages:[];
    const parent=previous.some(m=>m.historical)?undefined:[...previous].reverse().find(m=>m.answer?.answer_id)?.answer?.answer_id;
    const index=previous.length;
    const update=(message:Message)=>{if(alive.current)setMessages(current=>[...current.slice(0,index),message]);};
    setScopeKey(key);setBusy(true);setDraft("");
    setMessages([...previous,{question,stage:analysisId?"Explaining the saved calculations and peer findings…":"Planning the question and researching report evidence…"}]);
    const request=analysisId?{question,previous_questions:previous.slice(-3).map(m=>m.question)}:{question,company_ids:[...selected].sort(),parent_answer_id:parent??null};
    try{const answer=await knowledge<Answer>(analysisId?`/knowledge/briefings/${analysisId}/explain`:"/knowledge/ask",request);update({question,answer});void refresh();}
    catch(error){update({question,error:(error as Error).message});if(alive.current)setDraft(question);}
    finally{if(alive.current)setBusy(false);}
  }
  return <div className="sustainobot-layer" hidden={!open} inert={covered?true:undefined}>
    <div className="sustainobot-scrim" onClick={onClose}/><aside ref={panel} className="sustainobot-panel" role="dialog" aria-modal="true" aria-labelledby="sustainobot-title" onKeyDown={keys}>
      <header className="sustainobot-header">{!workspace&&<img src={avatar} alt=""/>}<div><h2 id="sustainobot-title">{workspace?"Explore the findings":"Sustainobot"}</h2><p>Answers with sources</p></div><nav aria-label="Chat controls"><button title="New chat" aria-label="New chat" disabled={busy} onClick={()=>{setMessages([]);setScopeKey(key);setDraft("");setSavedOpen(false);setOptionsOpen(false);}}><RotateCcw size={15}/></button><button title="Peers and history" aria-label="Peers and history" aria-expanded={optionsOpen} onClick={()=>setOptionsOpen(!optionsOpen)}><SlidersHorizontal size={15}/></button><button aria-label={workspace?"Close explanation":"Close Sustainobot"} onClick={onClose}><X size={17}/></button></nav></header>
      {optionsOpen&&<div className="sustainobot-options"><div className="sustainobot-tools"><span>Conversation options</span><button disabled={busy} aria-expanded={savedOpen} onClick={()=>setSavedOpen(!savedOpen)}>Saved research {history.length?`(${history.length})`:""}</button></div>
      {savedOpen&&<section className="sustainobot-saved" aria-label="Saved research">{historyError&&<p role="alert">{historyError}</p>}{history.length?history.map(h=><button key={h.answer_id} disabled={busy} onClick={()=>void restore(h.answer_id)}>{h.question}<small>{new Date(h.created_at).toLocaleDateString("en-GB")}</small></button>):<p>Completed answers are saved automatically.</p>}</section>}
      <section className="sustainobot-scope" aria-label="Peer selection"><input type="search" aria-label="Chat company search" placeholder="Find a company or ticker" value={search} onChange={e=>setSearch(e.target.value)} disabled={busy}/><div>{companies.filter(c=>selected.includes(c.id)||(search.trim()&&`${c.company_name} ${c.ticker}`.toLowerCase().includes(search.toLowerCase()))).slice(0,10).map(c=><button key={c.id} disabled={busy||(!selected.includes(c.id)&&selected.length>=5)} aria-pressed={selected.includes(c.id)} onClick={()=>{onSelect(selected.includes(c.id)?selected.filter(id=>id!==c.id):[...selected,c.id]);setSearch("");}}>{c.company_name} {selected.includes(c.id)?"×":"＋"}</button>)}</div>{selected.length>0&&<button disabled={busy} onClick={()=>onSelect([])}>Search whole library</button>}</section></div>}
      {selectedCompanies.length>0&&!optionsOpen&&<button className="sustainobot-current-peers" onClick={()=>setOptionsOpen(true)}>{selectedCompanies.map(c=>c.company_name).join(" · ")}<SlidersHorizontal size={11}/></button>}
      {analysisId&&<p className="sustainobot-answer-label">Explaining this saved analysis · calculations and source evidence</p>}
      {messages.length>0&&key!==scopeKey&&<p className="sustainobot-notice">Your peer group changed. The next question starts a new conversation.</p>}
      {configurationError&&<p className="sustainobot-notice">AI configuration needs attention. Report search remains available; a submitted question will show the specific connection error.</p>}
      <div className="sustainobot-messages" role="log" aria-label="Chat messages" aria-live="polite" aria-busy={busy}>
        {!messages.length&&<section className="sustainobot-welcome"><ChatMessageBubble sender="assistant"><p>{workspace?"What would you like to understand about these findings?":"Hi, I’m Sustainobot. What would you like to know about your peers?"}</p></ChatMessageBubble><div>{[
          ["Explore insights","Summarise the reported climate commitments and progress in the selected reports. Cite the source evidence."],
          ["Compare disclosures","Compare the reported renewable electricity commitments for the selected peers, including their stated years and boundaries."],
          ["Find source evidence","What supplier emissions programmes are described in these reports?"],
        ].map(([label,q])=><button key={label} onClick={()=>{setDraft(q);input.current?.focus();}}>{label}<ArrowUpRight size={12}/></button>)}</div></section>}
        {messages.map((m,i)=><article className="sustainobot-message" key={`${i}-${m.question}`}><ChatMessageBubble sender="user"><p>{m.question}</p></ChatMessageBubble><AnimatePresence>{m.stage&&<ChatTypingIndicator label={m.stage}/>}</AnimatePresence>{m.error&&<div role="alert" className="sustainobot-notice"><p>{m.error}</p><button disabled={busy} onClick={()=>{setDraft(m.question);input.current?.focus();}}>Edit question</button></div>}{m.answer&&<ChatMessageBubble sender="assistant"><div className="sustainobot-answer">{m.answer.cached&&<span className="sustainobot-answer-label">Saved answer</span>}{m.historical&&<p className="sustainobot-notice">Historical answer: some source indexes have changed. Start a new chat to recheck.</p>}{m.answer.status==="partial"&&<span className="sustainobot-answer-label">Partial answer · source-backed findings</span>}{m.answer.notes?.slice(0,1).map(note=><p key={note}>{note}</p>)}{m.answer.status==="insufficient_evidence"&&!m.answer.notes?.length&&<p>This saved answer did not find enough evidence. Ask again to use the updated research workflow.</p>}{m.answer.calculations?.map(item=><p key={item.label}><strong>{item.value}</strong> {item.label}<small> · database count</small></p>)}{m.answer.claims.map((claim,j)=><section key={j}><p>{claim.text}</p><CitationLinks citations={claim.citations} openSource={openSource}/></section>)}{m.answer.follow_up_question&&<p>{m.answer.follow_up_question}</p>}<details><summary>Sources & analysis details</summary>{m.answer.notes?.slice(1).map(note=><p key={note}>{note}</p>)}{m.answer.research_plan&&<p>Research approach: {m.answer.research_plan.intent.replaceAll("_"," ")}. Searches: {m.answer.research_plan.queries.join(" · ")}</p>}<span className="sustainobot-answer-label">{m.answer.cached?"Saved answer · no new AI call":m.answer.model_called?"Live AI analysis":"No model call"}</span><p>{m.answer.model??"No model called"} · {m.answer.coverage.passages_supplied} passages · {m.answer.coverage.companies_supplied} companies supplied</p>{m.answer.usage&&<p>{((m.answer.usage.total_latency_ms??m.answer.usage.latency_ms)/1000).toFixed(1)} seconds · {m.answer.usage.input_tokens+m.answer.usage.output_tokens} tokens · original estimated cost ${Number(m.answer.estimated_cost_usd).toFixed(4)} before any promotional allowance.</p>}<p>Selected passages, not a complete audit. Citations are mechanically checked; interpretation can still be wrong.</p>{m.answer.coverage.companies.filter(c=>c.status!=="supplied").map(c=><p key={c.company_id}>{c.company??"Unknown company"}: {c.status.replaceAll("_"," ")}</p>)}{m.answer.claims.length>0&&<button className="sustainobot-export" onClick={()=>exportAnswer(m.question,m.answer!)}>Export briefing with sources ↓</button>}</details></div></ChatMessageBubble>}</article>)}<div ref={bottom}/>
      </div>
      <form className="sustainobot-composer" onSubmit={submit}><label className="sr-only" htmlFor="sustainobot-question">{workspace?"Ask about this analysis":"Ask Sustainobot"}</label><textarea id="sustainobot-question" ref={input} rows={1} maxLength={1200} placeholder={workspace?"Ask about a finding, calculation or difference…":"Ask Sustainobot…"} value={draft} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void submit();}}}/><button aria-label="Send question" disabled={busy||draft.trim().length<5}><Send size={16}/></button></form>
    </aside>
  </div>;
}
