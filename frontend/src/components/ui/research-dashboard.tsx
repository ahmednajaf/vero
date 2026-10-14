// Efferd's Dashboard 4 composition, adapted to Vero's existing night/glass palette.
// https://21st.dev/@efferd/components/dashboard-4 (MIT). No fixture business data.
import {useState, type ReactNode} from 'react';
import {Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import {ArrowDownToLine, ArrowUpRight, FileSpreadsheet, FileText, Sparkles} from 'lucide-react';
import {ReportFolder} from './report-folder';
import {exportLink, type Briefing, type ReportAward, type AnalyticalBadge, type DisclosureScores} from '../../lib/briefings';
import type {AskReport, OpenPassage} from '../ReportLibrary';

export const metricNumber=(value:number|string)=>new Intl.NumberFormat('en-GB',{maximumFractionDigits:2}).format(Number(typeof value==='string'?value.replaceAll(',', '').replace(/%$/, '').trim():value));
export function ResearchCard({title,description,action,children,className=''}:{title:string;description?:string;action?:ReactNode;children:ReactNode;className?:string}) {
  return <section className={`research-card ${className}`}><header><div><h2>{title}</h2>{description&&<p>{description}</p>}</div>{action}</header>{children}</section>;
}
export function DashboardStats({metrics,primaryId,onMetric}:{metrics:ReportAward[];primaryId:string;onMetric:(index:number)=>void}) {
  if(!metrics.length)return null;
  return <div className="research-stat-strip" style={{gridTemplateColumns:`repeat(${Math.min(metrics.length,4)},minmax(0,1fr))`}}>{metrics.slice(0,4).map((metric,index)=>{
    const row=metric.rows.find(r=>r.company_id===primaryId)??metric.rows[0];
    if(!row)return null;
    const sorted=metric.rows.map(r=>Number(r.value)).sort((a,b)=>a-b);
    const middle=Math.floor(sorted.length/2),median=sorted.length%2?sorted[middle]:(sorted[middle-1]+sorted[middle])/2;
    return <button className="research-card research-stat" key={metric.id??index} onClick={()=>onMetric(index)}><span>{metric.name}</span><strong>{metricNumber(row.value)} <em>{row.unit}</em></strong><small>{row.company}{row.year?` · ${row.year}`:''}</small><small>{metric.contextual?'Company-specific reporting bases':sorted.length>1?`Peer-group median ${metricNumber(median)} · n=${sorted.length}`:'One reported result'}</small></button>;
  })}</div>;
}
const palette=['#afa2e8','#88c7e6','#7675ba','#d0b4d9','#597ca2','#d6d4e4'];
const tooltip={background:'#16151d',border:'1px solid #ffffff20',borderRadius:10,color:'#efecf7',fontSize:12};
export function ComparisonChart({metrics,selection,setSelection,open}:{metrics:ReportAward[];selection:number;setSelection:(i:number)=>void;open:OpenPassage}) {
  const [narrow,setNarrow]=useState(false);
  const metric=metrics[selection]??metrics[0];
  if(!metric)return null;
  const data=metric.rows.map(row=>({name:row.company,value:Number(row.value)}));
  return <ResearchCard title="Peer comparison" className="research-chart-card" action={<select aria-label="Chart metric" value={selection} onChange={e=>setSelection(Number(e.target.value))}>{metrics.map((m,i)=><option key={m.id??i} value={i}>{m.name}</option>)}</select>}>
    <div className="research-chart-heading"><strong>{metric.name}</strong><span>{metric.rows[0]?.unit} · {metric.sample_size} companies</span></div>
    {metric.contextual&&<p className="report-caption">Different company reporting bases · no peer ranking</p>}
    <div className="research-plot" style={narrow?{height:Math.max(240,data.length*38+35)}:undefined} role="region" aria-label={metric.name}><ResponsiveContainer width="100%" height="100%" onResize={width=>setNarrow(width<560)}><BarChart data={data} layout={narrow?'vertical':'horizontal'} margin={{top:10,right:15,bottom:0,left:4}} accessibilityLayer><CartesianGrid vertical={narrow} horizontal={!narrow} stroke="#ffffff0c"/>{narrow?<><XAxis type="number" tick={{fill:'#a3a0b2',fontSize:10}} axisLine={false} tickLine={false}/><YAxis type="category" dataKey="name" width={115} tick={{fill:'#a3a0b2',fontSize:10}} axisLine={false} tickLine={false} tickFormatter={name=>name.length>20?name.slice(0,18)+'…':name}/></>:<><XAxis dataKey="name" tick={{fill:'#a3a0b2',fontSize:10}} axisLine={false} tickLine={false} interval={0} height={50} tickFormatter={name=>name.length>22?name.slice(0,20)+'…':name}/><YAxis tick={{fill:'#858393',fontSize:10}} axisLine={false} tickLine={false} width={55}/></>}<ReferenceLine {...(narrow?{x:0}:{y:0})} stroke="#ffffff25"/><Tooltip formatter={v=>[metricNumber(Number(v)),metric.rows[0]?.unit??'Result']} contentStyle={tooltip} itemStyle={{color:"#eee9f7"}} labelStyle={{color:"#c3b5dd"}} cursor={{fill:'#ffffff04'}}/><Bar dataKey="value" radius={narrow?[0,4,4,0]:[4,4,0,0]} maxBarSize={48}>{data.map((row,i)=><Cell key={row.name} fill={palette[i%palette.length]}/>)}</Bar></BarChart></ResponsiveContainer></div>
    <details className="metric-calculation"><summary>Calculation & source data</summary><p>{metric.question??metric.criterion}</p><p>{metric.formula??metric.operation.replaceAll('_',' ')}</p><table><thead><tr><th>Company</th><th>Result</th><th>Inputs</th></tr></thead><tbody>{metric.rows.map(row=><tr key={row.company_id}><th>{row.company}</th><td>{metricNumber(row.value)} {row.unit}</td><td>{row.inputs.map((input,i)=><button key={i} className="workspace-text-button" onClick={()=>open(input.source)}>{metricNumber(input.raw_value)} {input.raw_unit} · p. {input.source.page} ↗</button>)}</td></tr>)}</tbody></table>{metric.caveat&&<p>{metric.caveat}</p>}</details>
  </ResearchCard>;
}
export function PeerAwards({badges,open}:{badges:AnalyticalBadge[];open:OpenPassage}) {
  const awarded=badges.filter(b=>b.winner_ids.length);
  return <ResearchCard title="Peer distinctions" className="research-awards-card">{awarded.length?awarded.map(badge=><article className="peer-distinction" key={badge.id}>
    <img className="award-object" src={`/awards/${/training|innovation|learning/i.test(badge.name)?'innovation':/people|parity|women|leadership/i.test(badge.name)?'people':'clarity'}.png`} alt="" width={120} height={120}/><div><h3>{badge.name}</h3><strong>{badge.rows.filter(r=>badge.winner_ids.includes(r.company_id)).map(r=>r.company).join(' & ')}</strong>
      <details><summary>Why this award</summary><p>{badge.why_it_matters}</p><p>{badge.sample_size} assessed companies{badge.winner_ids.length>1?' · shared distinction':''}</p>
        {badge.basis==='qualitative'&&<>{badge.rubric.map(r=><p key={r.id}>{r.criterion} · {r.max_points} points</p>)}{badge.assessments.map((r,i)=><p key={i}>{badge.rows.find(c=>c.company_id===r.company_id)?.company}: {r.points} · {r.explanation}</p>)}</>}
        {badge.rows.some(r=>r.sources.length>0)&&<button className="workspace-text-button" onClick={()=>{const sources=badge.rows.flatMap(r=>r.sources);open(sources[0],sources.slice(1));}}>View evidence ↗</button>}
      </details>
    </div></article>):<p className="research-empty">No award has been established in this analysis.</p>}</ResearchCard>;
}
export function DisclosureCard({scores,detail=false}:{scores:DisclosureScores;detail?:boolean}) {
  if(!scores.criteria.length)return detail?<ResearchCard title="Disclosure comparison" className="research-wide"><p className="research-empty">This analysis has not established a common disclosure checklist.</p></ResearchCard>:null;
  return <ResearchCard title="Disclosure coverage" description="Common checklist items identified in the reports" className={detail?'research-wide':'research-half'}><div className="disclosure-score-list">{scores.rows.map(row=><div className="disclosure-score-row" key={row.company_id}><div><strong>{row.company}</strong><span>{row.disclosed} / {row.total} identified</span></div><div className="disclosure-track" aria-hidden="true"><i style={{width:`${row.total?100*row.disclosed/row.total:0}%`}}/></div><details><summary>{row.score===null?`${row.pending.length||'Checklist'} checks to complete`:row.deductions.length?`${row.deductions.length} disclosure deductions`:'Common items disclosed'}</summary><p>Final disclosure score: {row.score===null?'Pending':`${metricNumber(row.score)} / 100`}</p>{row.deductions.map(d=><p key={d.criterion}>−{metricNumber(d.points)} · {d.criterion}<small>{d.peer_ids.length} peers disclose this · {d.reason}</small></p>)}{row.pending.map(p=><p key={p}>{p} · search incomplete</p>)}</details></div>)}</div><details className="metric-calculation"><summary>Scoring method</summary><p>Equal weight for items disclosed by at least two companies and at least half this group. Completed searches with no disclosure receive a deduction.</p><p>{scores.meaning}</p>{scores.criteria.map(c=><p key={c.id}>{c.definition} · {c.disclosed_by.length}/{scores.rows.length}</p>)}</details></ResearchCard>;
}
export function QuickActions({brief,ask}:{brief:Briefing;ask:AskReport}) {
  return <ResearchCard title="Your deliverables" className="research-half research-deliverables"><div className="deliverable-layout"><ReportFolder id={brief.id}/><div className="research-downloads">
    <a href={exportLink(brief.id,'pdf')}><FileText/><div><strong>Client report</strong><span>PDF · findings, calculations & peer distinctions</span></div><ArrowDownToLine/></a>
    <a href={exportLink(brief.id,'xlsx')}><FileSpreadsheet/><div><strong>Analysis workbook</strong><span>Excel · working formulas & source links</span></div><ArrowDownToLine/></a>
    <button onClick={()=>ask('Explain the most significant differences in this peer group, with report sources.',brief.definition.company_ids)}><Sparkles/><div><strong>Explain this analysis</strong><span>Ask a question about these findings</span></div><ArrowUpRight/></button>
  </div></div><details className="research-export-details"><summary>Supporting files</summary><a href={exportLink(brief.id,'csv')}>Evidence CSV</a><a href={exportLink(brief.id,'json')}>Analysis JSON</a><a href={exportLink(brief.id,'html')}>Report HTML</a></details></ResearchCard>;
}
