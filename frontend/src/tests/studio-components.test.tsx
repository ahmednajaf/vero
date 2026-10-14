import {render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {expect,it,vi} from 'vitest';
import {ReportFolder} from '../components/ui/report-folder';
import GlassFolder from '../components/ui/glass-folder';
import {PressDepth} from '../components/ui/press-depth';
import {PromiseRegister} from '../components/AnalysisDashboard';
import type {PromiseRecord} from '../lib/briefings';

it('puts only the saved edition’s real downloads in its folder',async()=>{
  render(<ReportFolder id="saved-edition"/>);const user=userEvent.setup();
  const folder=screen.getByRole('button',{name:'Open Report & workbook, 3 items'});
  expect(folder).toHaveAttribute('aria-expanded','false');
  await user.click(folder);expect(folder).toHaveAttribute('aria-expanded','true');
  expect(document.querySelector('.gf-files')).toHaveAttribute('inert');
  expect(document.querySelector('.gf-files')).toHaveAttribute('aria-hidden','true');
  const list=screen.getByRole('list',{name:'Report & workbook contents'});
  expect(within(list).getAllByRole('link')).toHaveLength(3);
  expect(within(list).getByRole('link',{name:'Client report PDF'})).toHaveAttribute('href','/api/knowledge/briefings/saved-edition/export?format=pdf');
  expect(within(list).getByRole('link',{name:'Analysis workbook XLSX'})).toHaveAttribute('href','/api/knowledge/briefings/saved-edition/export?format=xlsx');
  await user.keyboard('{Escape}');expect(folder).toHaveAttribute('aria-expanded','false');
});

it('does not introduce sample files or add-file controls by default',()=>{
  render(<GlassFolder art="none" appear={false}/>);
  expect(screen.queryByText('Moodboard')).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Open My Files, 0 items'})).toBeInTheDocument();
  expect(screen.getAllByRole('button')).toHaveLength(1);
});

it('keeps the tactile control a native keyboard-accessible button',async()=>{
  const action=vi.fn(),user=userEvent.setup();render(<PressDepth onClick={action}>Generate report</PressDepth>);
  await user.tab();expect(screen.getByRole('button',{name:'Generate report'})).toHaveFocus();
  await user.keyboard('{Enter}');expect(action).toHaveBeenCalledTimes(1);
});

it('preserves form submission and disabled state for tactile controls',async()=>{
  const submit=vi.fn(e=>e.preventDefault()),user=userEvent.setup();
  const view=render(<form onSubmit={submit}><PressDepth type="submit">Prepare</PressDepth></form>);
  await user.click(screen.getByRole('button'));expect(submit).toHaveBeenCalledTimes(1);
  view.rerender(<PressDepth disabled onClick={submit}>Prepare</PressDepth>);
  await user.click(screen.getByRole('button'));expect(submit).toHaveBeenCalledTimes(1);
});

it('filters and pages commitments without losing their supporting sources',async()=>{
  const source={company:'Fixture',report_id:'r',page:8} as PromiseRecord['citations'][number];
  const promises=Array.from({length:8},(_,i)=>({company_id:i<7?'a':'b',company:i<7?'Fixture A':'Fixture B',commitment:`Commitment ${i+1}`,deadline:'2030',assessment:`Reported progress ${i+1}`,citations:[source]}));
  const open=vi.fn(),user=userEvent.setup();render(<PromiseRegister promises={promises} open={open}/>);
  expect(screen.getAllByRole('article')).toHaveLength(6);expect(screen.queryByText('Commitment 7')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Next'}));expect(screen.getByText('Commitment 7')).toBeInTheDocument();
  await user.selectOptions(screen.getByRole('combobox',{name:'Commitment company'}),'b');
  expect(screen.getAllByRole('article')).toHaveLength(1);expect(screen.getByText('1–1 of 1')).toBeInTheDocument();
  await user.click(screen.getByText('Reported progress'));expect(screen.getByText('Reported progress 8')).toBeVisible();
  await user.click(screen.getByRole('button',{name:'View source ↗'}));expect(open).toHaveBeenCalledWith(source,[]);
  await user.type(screen.getByRole('searchbox',{name:'Search commitments'}),'no match');expect(screen.getByText('No matching commitments.')).toBeInTheDocument();
});
