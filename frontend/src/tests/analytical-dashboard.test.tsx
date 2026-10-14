import {render,screen,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {expect,it,vi} from 'vitest';
import {ComparisonChart,DashboardStats,DisclosureCard,PeerAwards} from '../components/ui/research-dashboard';
import {ReportedData} from '../components/AnalysisDashboard';
import type {ReportAward,DisclosureScores,AnalyticalBadge} from '../lib/briefings';
import type {Passage} from '../lib/knowledge';

const source={evidence_id:'test',company_id:'a',company:'Fixture A',report_id:'r',report:'Fixture only',page:8,page_url:'/api/reports/r/file#page=8',source_url:'https://example.com/report.pdf',report_sha256:'hash',text:'Workforce disclosure',quote:'Workforce disclosure',kind:'text',reporting_year:2025,detected_year:2025} as Passage;
const metric:ReportAward={id:'parity',name:'Leadership representation',question:'Does representation reach leadership?',formula:'leaders / workforce × 100',criterion:'Representation in leadership relative to workforce.',operation:'formula',direction:'near_reference',reference_value:'100',caveat:'Reported seniority populations.',status:'calculated',winner_ids:[],sample_size:2,cohort_size:2,basis:'Calculated from saved inputs',excluded:[],unassessed_company_ids:[],rows:[{company_id:'a',company:'Fixture A',value:'50',unit:'parity index',year:2025,inputs:[{raw_value:'30',raw_unit:'%',value:'30',unit:'%',year:2025,source}]},{company_id:'b',company:'Fixture B',value:'75',unit:'parity index',year:2025,inputs:[{raw_value:'45',raw_unit:'%',value:'45',unit:'%',year:2025,source:{...source,company_id:'b',company:'Fixture B'}}]}]};
const scores:DisclosureScores={policy:'peer-common-equal-v1',meaning:'Common checklist',criteria:[{id:'scope3',definition:'Scope 3',disclosed_by:['a','b']}],rows:[{company_id:'a',company:'Fixture A',score:50,disclosed:1,total:2,deductions:[{criterion:'Training',points:50,peer_ids:['b','c'],reason:'Not identified after completed searches'}],pending:[]},{company_id:'b',company:'Fixture B',score:null,disclosed:1,total:2,deductions:[],pending:['Training']}]};

it('heads the dashboard with metric values and group median, not activity counts',async()=>{
 const onMetric=vi.fn();render(<DashboardStats metrics={[metric]} primaryId="a" onMetric={onMetric}/>);
 expect(screen.getByRole('button')).toHaveTextContent('50 parity index');
 expect(screen.getByText(/Peer-group median 62.5/)).toBeInTheDocument();
 expect(screen.queryByText('Reports')).not.toBeInTheDocument();
 await userEvent.setup().click(screen.getByRole('button'));expect(onMetric).toHaveBeenCalledWith(0);
});
it('charts calculated values, switches metrics, and opens their raw input sources',async()=>{
 const open=vi.fn(),change=vi.fn();const user=userEvent.setup();render(<ComparisonChart metrics={[metric,{...metric,id:'gap',name:'Training opportunity gap'}]} selection={0} setSelection={change} open={open}/>);
 expect(screen.queryByRole('option',{name:'Topic coverage'})).not.toBeInTheDocument();
 expect(screen.getByRole('region',{name:metric.name})).toBeInTheDocument();
 await user.selectOptions(screen.getByRole('combobox',{name:'Chart metric'}),'1');expect(change).toHaveBeenCalledWith(1);
 await user.click(screen.getByText('Calculation & source data'));
 await user.click(screen.getByRole('button',{name:'30 % · p. 8 ↗'}));expect(open).toHaveBeenCalledWith(source);
});
it('does not render absent metrics as zero or substitute a source-count chart',()=>{
 render(<ComparisonChart metrics={[]} selection={0} setSelection={vi.fn()} open={vi.fn()}/>);
 expect(screen.queryByRole('region')).not.toBeInTheDocument();
});
it('shows deductions and pending checks separately',async()=>{
 render(<DisclosureCard scores={scores}/>);const user=userEvent.setup();
 expect(screen.getAllByText('1 / 2 identified')).toHaveLength(2);expect(screen.queryByText('0 / 100')).not.toBeInTheDocument();
 await user.click(screen.getByText('1 checks to complete'));expect(screen.getByText('Final disclosure score: Pending')).toBeInTheDocument();
 await user.click(screen.getByText('1 disclosure deductions'));expect(screen.getByText(/−50 · Training/)).toBeInTheDocument();
});
it('supports tied awards and evidence without giving every company a badge',async()=>{
 const badge:AnalyticalBadge={id:'b',name:'Representation bridge',why_it_matters:'Similar leadership representation.',basis:'numeric',metric_id:'parity',winner_ids:['a','b'],status:'awarded',sample_size:2,rows:metric.rows.map(r=>({...r,sources:[r.inputs[0].source]})),rubric:[],assessments:[]};
 const open=vi.fn();render(<PeerAwards badges={[badge,{...badge,id:'pending',name:'Unestablished award',winner_ids:[],status:'pending'}]} open={open}/>);
 expect(screen.getByText('Fixture A & Fixture B')).toBeInTheDocument();expect(screen.queryByText('Unestablished award')).not.toBeInTheDocument();
 await userEvent.setup().click(screen.getByText('Why this award'));
 expect(screen.getByText(/shared distinction/)).toBeInTheDocument();
 await userEvent.setup().click(screen.getByRole('button',{name:'View evidence ↗'}));expect(open).toHaveBeenCalled();
 expect(within(screen.getByRole('heading',{name:'Peer distinctions'}).closest('section')!).queryByText('Research themes')).not.toBeInTheDocument();
});

it('uses the newly collected fact ledger for searchable source-linked figures',async()=>{
 const open=vi.fn(),user=userEvent.setup();
 render(<ReportedData open={open} facts={[
  {id:'1',company_id:'a',metric:'Employee training',value:'25',unit:'hours',year:2025,kind:'actual',population:'Employees',source},
  {id:'2',company_id:'b',metric:'Methane intensity',value:'0.08',unit:'%',year:2025,kind:'actual',population:'Upstream',source:{...source,company_id:'b',company:'Fixture B'}},
 ]}/>);
 expect(screen.getByText('25 hours')).toBeInTheDocument();
 await user.type(screen.getByRole('searchbox',{name:'Search reported data'}),'training');
 expect(screen.queryByText('Methane intensity')).not.toBeInTheDocument();
 await user.click(screen.getByRole('button',{name:'p. 8 ↗'}));expect(open).toHaveBeenCalledWith(source);
 await user.selectOptions(screen.getByRole('combobox',{name:'Reported data company'}),'b');
 expect(screen.getByText('No matching metric.')).toBeInTheDocument();
});
