// Generic Vero workbook renderer. Input is the saved publication, never a model call.
import fs from 'node:fs/promises';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';
const [input, output, previewDir] = process.argv.slice(2);
const data = JSON.parse(await fs.readFile(input, 'utf8'));
const book = Workbook.create();
const sheetNumbers=new Map();
function sheet(name){const result=book.worksheets.add(name);sheetNumbers.set(name,sheetNumbers.size+1);return result;}
const sheetNumber=s=>sheetNumbers.get(s.name);
const cover=sheet('Cover');
const findings = sheet('Findings');
const hasCalculations = data.awards.some(a=>a.rows.length);
const comparisons = hasCalculations ? sheet('Comparisons') : null;
if(data.disclosure_scores || data.badges?.length)sheet('Scorecard');
if(data.promises?.length)sheet('Promises');
const inputs = hasCalculations ? sheet('Inputs') : null;
if(data.reported_facts?.length)sheet('Reported data');
const references = sheet('Sources');
const links=[];
const comparisonPreviews=[];
const ink = '#171924', accent = '#6855A2', light = '#F6F5F9', muted='#626879';
const literal = value => typeof value==='string' && /^[=+@-]/.test(value.trimStart()) ? `'${value}` : value ?? '';
const write = (sheet, range, rows) => {sheet.getRange(range).values = rows.map(r=>r.map(literal));};
function base(sheet, title, widths, rows) {
  sheet.showGridLines = false;
  sheet.tabColor = accent;
  const area = sheet.getRangeByIndexes(0,0,Math.max(rows,15),widths.length);
  area.format.font = {name:'Arial',size:10,color:ink};
  area.format.rowHeight = 24;
  area.format.verticalAlignment = 'center';
  area.format.fill='#FFFFFF';
  widths.forEach((width,i)=>sheet.getRangeByIndexes(0,i,Math.max(rows,15),1).format.columnWidth=width);
  write(sheet,'A2',[[title]]);
  sheet.getRange('A2').format.font = {name:'Arial',size:16,bold:true,color:ink};
  sheet.getRangeByIndexes(2,0,1,widths.length).format.borders = {bottom:{style:'thin',color:'#DEDCE7'}};
  if(data.brand?.logo) sheet.images.add({dataUrl:data.brand.logo,anchor:{from:{row:0,col:widths.length-1,colOffsetPx:Math.max(0,widths.at(-1)*7-95),rowOffsetPx:7},extent:{widthPx:90,heightPx:35}}});
  sheet.freezePanes.freezeRows(5);
}
function header(sheet, row, values) {
  write(sheet,`A${row}`,[values]);
  const range=sheet.getRangeByIndexes(row-1,0,1,values.length);
  range.format.fill=ink;
  range.format.font={name:'Arial',size:10,color:'#FFFFFF',bold:true};
  range.format.horizontalAlignment='center';
  range.format.rowHeight=30;
  range.format.borders={insideVertical:{style:'hair',color:'#FFFFFF'}};
}
const paragraphs=data.chapters.flatMap(c=>c.paragraphs.map(p=>({...p,topic:c.title})));
base(findings,'Research findings',[7,29,86,18],paragraphs.length+10);
write(findings,'A4',[[`${data.package}${data.incomplete?' · Working draft — analysis incomplete':''}`]]);
findings.getRange('A4:C4').merge();
header(findings,5,['No.','Topic','Finding','Source pages']);
function sentence(text, limit=250) {
  // Legacy results lack editorial takeaways. A marked preview avoids treating
  // company abbreviations (e.g. Co. Ltd.) as complete sentences.
  return text.length<=limit?text:text.slice(0,limit-1).replace(/\s+\S*$/,'')+'…';
}
paragraphs.forEach((p,i)=>{
  const row=i+6;
  write(findings,`A${row}`,[[i+1,p.topic,p.takeaway||p.heading||sentence(p.text,200),p.references.map(n=>`[${n}]`).join(', ')]]);
  if(p.references.length)links.push({sheet:sheetNumber(findings),cell:`D${row}`,location:`'Sources'!A${p.references[0]+5}`});
  const area=findings.getRange(`A${row}:D${row}`);
  area.format.wrapText=true;
  area.format.rowHeight=Math.max(44,Math.ceil((p.takeaway||p.heading||sentence(p.text,200)).length/84)*14+12);
  area.format.fill=i%2?'#FFFFFF':light;
  findings.getRange(`A${row}`).format.horizontalAlignment='center';
  findings.getRange(`D${row}`).format.font={name:'Arial',size:10,color:accent,underline:'single'};
});
if(paragraphs.length) {
  findings.tables.add(`A5:D${paragraphs.length+5}`,true,'PeerFindings').style='TableStyleMedium1';
  findings.getRange(`A5:D${paragraphs.length+5}`).format.borders={insideHorizontal:{style:'hair',color:'#E4DFED'}};
}
// Each unique raw operand appears once. Comparisons link to converted inputs.
const operandRows = new Map();
const comparisonCells = new Map();
if(hasCalculations){
base(inputs,'Reported inputs & source links',[28,36,17,20,19,23,12,10,19,19],Math.max(15,data.awards.reduce((n,a)=>n+a.rows.length*2,0)+8));
header(inputs,5,['Company','Input','Raw value','Raw unit','Common-unit value','Common unit','Year','Page','Official report','Conversion factor']);
let inputRow=6;
const urlFor=s=>/^https?:\/\//.test(s.source_url||'')?s.source_url.split('#')[0]+`#page=${s.page}`:'';
function addInput(entry,operand,label) {
  const key=JSON.stringify([operand.source.company_id||entry.company_id,label,operand.raw_value,operand.raw_unit,operand.unit,operand.year,operand.source.report_id,operand.source.page]);
  if(operandRows.has(key))return operandRows.get(key);
  const row=inputRow++;
  const factor=operand.conversion_factor!==undefined?Number(operand.conversion_factor):Number(operand.raw_value)!==0?Number(operand.value)/Number(operand.raw_value):null;
  write(inputs,`A${row}`,[[operand.source.company||entry.company,label,Number(operand.raw_numeric_value??operand.raw_value),operand.raw_unit,Number(operand.value),operand.unit,operand.year,operand.source.page,'',factor]]);
  if(factor!==null)inputs.getRange(`E${row}`).formulas=[[`=IF(AND(ISNUMBER(C${row}),ISNUMBER(J${row})),C${row}*J${row},"")`]];
  const url=urlFor(operand.source);
  if(url){write(inputs,`I${row}`,[['Open report']]);links.push({sheet:sheetNumber(inputs),cell:`I${row}`,url});}
  inputs.getRange(`C${row}`).setNumberFormat(Number.isInteger(Number(operand.raw_numeric_value??operand.raw_value))?'#,##0':'#,##0.000');
  inputs.getRange(`E${row}`).setNumberFormat(Number.isInteger(Number(operand.value))?'#,##0':'#,##0.000');
  inputs.getRange(`A${row}:J${row}`).format.fill=row%2?light:'#FFFFFF';
  inputs.getRange(`A${row}:J${row}`).format.wrapText=true;
  inputs.getRange(`A${row}:J${row}`).format.rowHeight=Math.max(38,Math.ceil(label.length/35)*13+10);
  inputs.getRange(`C${row}`).format.font={name:'Arial',size:10,color:'#365A89'};
  for(const col of ['D','F','G','H']) inputs.getRange(`${col}${row}`).format.horizontalAlignment='center';
  inputs.getRange(`I${row}`).format.font={name:'Arial',size:10,color:accent,underline:'single'};
  operandRows.set(key,row);return row;
}
function formulaResult(entry,metric) {
  const cells=new Map();
  const resultFactor=Number(entry.result_conversion_factor??1);
  for(const operand of entry.inputs)cells.set(operand.id,`E${addInput(entry,operand,operand.metric||operand.id)}`);
  for(const [stepIndex,step] of metric.steps.entries()){
    const args=step.operands.map(operand=>{
      if(cells.has(operand))return cells.get(operand);
      if(!/^-?\d+(?:\.\d+)?$/.test(operand))throw Error('Unknown calculation operand');
      return operand;
    });
    if(entry.step_conversions?.[step.id]&&Number(entry.step_conversions[step.id])!==1){
      args[1]=`(${args[1]}*${Number(entry.step_conversions[step.id])})`;
    }
    const [a,b]=args;
    const expression={add:args.join('+'),subtract:`${a}-${b}`,multiply:`${a}*${b}`,divide:`${a}/${b}`,power:`${a}^${b}`,absolute:`ABS(${a})`}[step.operation];
    if(!expression)throw Error('Unknown calculation operation');
    const r=inputRow++;
    write(inputs,`A${r}`,[[entry.company,`${metric.name} / ${step.id===metric.result_step_id&&resultFactor===1?'Result':`Step ${stepIndex+1}: ${step.operation}`}`,null,'',null,step.id===metric.result_step_id&&resultFactor===1?entry.unit:'step',null,null,'','']]);
    const checks=args.map(a=>`NOT(ISNUMBER(${a}))`);
    if(step.operation==='divide')checks.push(`${b}=0`);
    inputs.getRange(`E${r}`).formulas=[[`=IF(OR(${checks.join(',')}),"Unavailable",${expression})`]];
    inputs.getRange(`E${r}`).setNumberFormat('#,##0.000');
    inputs.getRange(`F${r}`).format.horizontalAlignment='center';
    inputs.getRange(`A${r}:J${r}`).format.wrapText=true;
    inputs.getRange(`A${r}:J${r}`).format.rowHeight=42;
    inputs.getRange(`A${r}:J${r}`).format.fill='#EEEAF6';
    cells.set(step.id,`E${r}`);
  }
  if(!cells.has(metric.result_step_id))throw Error('Missing result step');
  if(resultFactor!==1){
    const r=inputRow++, previous=cells.get(metric.result_step_id);
    write(inputs,`A${r}`,[[entry.company,`${metric.name} / Result unit conversion`,null,'',null,entry.unit,null,null,'',resultFactor]]);
    inputs.getRange(`E${r}`).formulas=[[`=IF(AND(ISNUMBER(${previous}),ISNUMBER(J${r})),${previous}*J${r},"Unavailable")`]];
    inputs.getRange(`E${r}`).setNumberFormat('#,##0.000');
    inputs.getRange(`A${r}:J${r}`).format.wrapText=true;
    inputs.getRange(`A${r}:J${r}`).format.rowHeight=42;
    inputs.getRange(`A${r}:J${r}`).format.fill='#EEEAF6';
    cells.set(metric.result_step_id,`E${r}`);
  }
  return `='Inputs'!${cells.get(metric.result_step_id)}`;
}
base(comparisons,'Calculated comparisons',[32,16,19,10,18,21,3,14,14,14,14,14,14],Math.max(25,data.awards.reduce((n,a)=>n+a.rows.length+23,0)));
let row=5;
for(const award of data.awards){
  const sectionStart=row;
  write(comparisons,`A${row}`,[[award.name]]);
  comparisons.getRange(`A${row}:F${row}`).merge();
  comparisons.getRange(`A${row}:F${row}`).format.wrapText=true;
  comparisons.getRange(`A${row}:F${row}`).format.rowHeight=32;
  comparisons.getRange(`A${row}`).format.font={name:'Arial',size:12,bold:true,color:accent};
  write(comparisons,`A${row+1}`,[[award.criterion]]);
  comparisons.getRange(`A${row+1}:F${row+1}`).merge();
  comparisons.getRange(`A${row+1}:F${row+1}`).format.wrapText=true;
  comparisons.getRange(`A${row+1}:F${row+1}`).format.rowHeight=40;
  row+=2;
  header(comparisons,row,['Company','Result','Unit','Year','Position','Calculation']);
  const start=++row,end=start+award.rows.length-1;
  for(const entry of award.rows){
    let formula;
    if(award.operation==='formula')formula=formulaResult(entry,award);
    else {
    const n=addInput(entry,entry.inputs[0],`${award.name} / numerator`);
    const d=entry.inputs[1]?addInput(entry,entry.inputs[1],`${award.name} / denominator`):null;
    const a=`'Inputs'!E${n}`, b=d?`'Inputs'!E${d}`:null;
    const calculation=award.operation==='ratio'?`${a}/${b}`:award.operation==='difference'?`${a}-${b}`:award.operation==='percent_change'?`100*(${a}/${b}-1)`:a;
    const checks=[`NOT(ISNUMBER(${a}))`,...(b?[`NOT(ISNUMBER(${b}))`]:[]),...(['ratio','percent_change'].includes(award.operation)?[`${b}=0`]:[])];
    formula=`=IF(OR(${checks.join(',')}),"Unavailable",${calculation})`;
    }
    write(comparisons,`A${row}`,[[entry.company,null,entry.unit,entry.year,'',({value:'Common-unit value',ratio:'Ratio',difference:'Difference',percent_change:'Year-on-year change'})[award.operation]||'See Inputs steps']]);
    comparisons.getRange(`B${row}`).formulas=[[formula]];
    comparisonCells.set(`${award.id}:${entry.company_id}`,`'Comparisons'!B${row}`);
    comparisons.getRange(`B${row}`).setNumberFormat(Math.abs(Number(entry.value))>0&&Math.abs(Number(entry.value))<1?'0.000':'#,##0.0');
    comparisons.getRange(`B${row}`).format.font={name:'Arial',size:12,bold:true,color:ink};
    if(award.status==='awarded') comparisons.getRange(`E${row}`).formulas=[[`=IF(ISNUMBER(B${row}),IF(B${row}=${award.direction==='higher'?'MAX':'MIN'}($B$${start}:$B$${end}),"Leading value",""),"")`]];
    comparisons.getRange(`A${row}:F${row}`).format.fill=row%2?light:'#FFFFFF';
    comparisons.getRange(`A${row}:F${row}`).format.wrapText=true;
    comparisons.getRange(`A${row}:F${row}`).format.rowHeight=38;
    comparisons.getRange(`C${row}:E${row}`).format.horizontalAlignment='center';
    row++;
  }
  if(award.rows.length){
    const chart=comparisons.charts.add('bar',[comparisons.getRange(`A${start-1}:A${end}`),comparisons.getRange(`B${start-1}:B${end}`)]);
    chart.title=`Results (${award.rows[0].unit})`;chart.titleTextStyle.fontSize=12;chart.titleTextStyle.typeface='Arial';
    chart.hasLegend=false;chart.series.items[0].fill=accent;
    chart.barOptions.direction='column';chart.barOptions.grouping='clustered';chart.barOptions.gapWidth=100;
    chart.xAxis={axisType:'textAxis',tickLabelPosition:'low',majorGridlines:null,minorGridlines:null,textStyle:{typeface:'Arial',fontSize:11}};
    const magnitude=Math.max(...award.rows.map(r=>Math.abs(Number(r.value))));
    const axisFormat=magnitude<1?'0.000':magnitude<10?'0.00':award.rows.every(r=>Number.isInteger(Number(r.value)))?'#,##0':'#,##0.0';
    chart.yAxis={numberFormatCode:axisFormat,numberFormatSourceLinked:false,majorGridlines:{fill:'#E2DFE9',style:'solid',width:.5},textStyle:{typeface:'Arial',fontSize:11}};
    chart.setPosition(`H${sectionStart}`,`M${Math.max(row+4,sectionStart+14)}`);
  }
  write(comparisons,`A${row+1}`,[[`${award.sample_size} assessed / ${award.cohort_size} selected${award.contextual?' · Contextual comparison':''}`]]);
  comparisons.getRange(`A${row+1}:F${row+1}`).merge();
  comparisons.getRange(`A${row+1}:F${row+1}`).format.font={name:'Arial',size:10,color:muted};
  write(comparisons,`A${row+3}`,[[award.caveat||'']]);
  comparisons.getRange(`A${row+3}:F${row+4}`).merge();
  comparisons.getRange(`A${row+3}:F${row+4}`).format.wrapText=true;
  comparisons.getRange(`A${row+3}:F${row+4}`).format.font={name:'Arial',size:10,color:muted};
  row=Math.max(row+7,sectionStart+17);
  comparisonPreviews.push(`A${sectionStart}:M${row-1}`);
}
}
// Source references without raw quotations. Useful even when no numeric awards exist.
const urlFor=s=>/^https?:\/\//.test(s.source_url||'')?s.source_url.split('#')[0]+`#page=${s.page}`:'';
base(references,'Source page index',[8,30,57,10,19],data.references.length+8);
header(references,5,['Ref','Company','Report','Page','Official report']);
data.references.forEach((s,i)=>{
  const r=6+i;
  write(references,`A${r}`,[[s.reference,s.company,s.report,s.page,'Open report']]);
  const url=urlFor(s);
  if(url)links.push({sheet:sheetNumber(references),cell:`E${r}`,url});
  references.getRange(`A${r}:E${r}`).format.wrapText=true;
  references.getRange(`A${r}:E${r}`).format.rowHeight=Math.max(32,Math.ceil(s.report.length/55)*13+10);
  references.getRange(`A${r}`).format.horizontalAlignment='center';
  references.getRange(`D${r}:E${r}`).format.horizontalAlignment='center';
  references.getRange(`E${r}`).format.font={name:'Arial',size:10,color:accent,underline:'single'};
});
// Scores and awards are concise results, not pasted source excerpts.
if(data.disclosure_scores || data.badges?.length){
  const scores=book.worksheets.getItem('Scorecard');
  const rows=data.disclosure_scores?.criteria?.length?data.disclosure_scores.rows:[];
  base(scores,'Disclosure & peer distinctions',[36,15,15,15,18,42],rows.length+data.badges.length*12+15);
  if(rows.length)header(scores,5,['Company','Disclosed','Common items','Pending','Score / 100','Deductions']);
  rows.forEach((entry,i)=>{
    const row=i+6;
    write(scores,`A${row}`,[[entry.company,entry.disclosed,entry.total,entry.pending.length,null,entry.deductions.map(d=>d.criterion).join('; ')]]);
    scores.getRange(`E${row}`).formulas=[[`=IF(OR(C${row}=0,D${row}>0),"Pending",100*B${row}/C${row})`]];
    scores.getRange(`E${row}`).setNumberFormat('0.0');
    scores.getRange(`A${row}:F${row}`).format.wrapText=true;
    scores.getRange(`A${row}:F${row}`).format.rowHeight=Math.max(36,Math.ceil(entry.deductions.map(d=>d.criterion).join('; ').length/40)*13+10);
    scores.getRange(`A${row}:F${row}`).format.borders={bottom:{style:'hair',color:'#DEDCE7'}};
    scores.getRange(`B${row}:E${row}`).format.horizontalAlignment='center';
    comparisonCells.set(`disclosure:${entry.company_id}`,`'Scorecard'!E${row}`);
  });
  let row=rows.length+9;
  for(const badge of data.badges??[]){
    write(scores,`A${row}`,[[badge.name]]);scores.getRange(`A${row}:E${row}`).merge();
    scores.getRange(`A${row}:E${row}`).format.wrapText=true;scores.getRange(`A${row}:E${row}`).format.rowHeight=34;
    scores.getRange(`A${row}`).format.font={bold:true,size:12,color:accent};
    const label=badge.name.toLowerCase(),art=/people|training|inclusion|diversity|women/.test(label)?'people':/innovation|ai |digital|execution stack/.test(label)?'innovation':'clarity';
    if(data.brand?.[art])scores.images.add({dataUrl:data.brand[art],anchor:{from:{row:row-1,col:5,colOffsetPx:14,rowOffsetPx:2},extent:{widthPx:58,heightPx:58}}});
    row+=2;
    header(scores,row,['Company','Result','Position','', '','']);row++;
    const first=row,last=row+badge.rows.length-1;
    const metric=data.awards.find(m=>m.id===badge.metric_id||m.equivalent_ids?.includes(badge.metric_id));
    const direction=metric?.direction??'higher';
    for(const entry of badge.rows){
      write(scores,`A${row}`,[[entry.company,Number(entry.value),'',null,null,null]]);
      const cell=comparisonCells.get(`${badge.basis==='disclosure'?'disclosure':badge.metric_id}:${entry.company_id}`);
      if(cell)scores.getRange(`B${row}`).formulas=[[`=${cell}`]];
      // Reference-distance ranking uses a visible distance column, not an
      // incorrect MIN/MAX of the raw measure. Qualitative points are saved inputs.
      if(direction==='near_reference'&&metric?.reference_value!=null){
        write(scores,`D${first-1}`,[['Distance']]);
        scores.getRange(`D${row}`).formulas=[[`=IF(ISNUMBER(B${row}),ABS(B${row}-${Number(metric.reference_value)}),"")`]];
      }
      const col=direction==='near_reference'?'D':'B',fn=direction==='higher'?'MAX':'MIN';
      if(badge.status==='awarded')scores.getRange(`C${row}`).formulas=[[`=IF(AND(COUNT($B$${first}:$B$${last})>=2,ISNUMBER(B${row})),IF(${col}${row}=${fn}($${col}$${first}:$${col}$${last}),"Leading value",""),"Pending")`]];
      scores.getRange(`A${row}:F${row}`).format.rowHeight=30;
      scores.getRange(`C${row}`).format.horizontalAlignment='center';
      scores.getRange(`B${row}`).setNumberFormat('0.00');row++;
    }
    write(scores,`A${row+1}`,[[sentence(badge.why_it_matters,160)]]);
    scores.getRange(`A${row+1}:F${row+1}`).merge();scores.getRange(`A${row+1}:F${row+1}`).format.wrapText=true;scores.getRange(`A${row+1}:F${row+1}`).format.rowHeight=42;
    row+=4;
  }
}
// A searchable evidence ledger, not an excerpt dump. Keep numeric values numeric;
// longer commitments stay in the promise register and PDF narrative.
if(data.reported_facts?.length){
  const reported=book.worksheets.getItem('Reported data');
  base(reported,'Reported data',[27,48,22,24,11,14,48,10,18],data.reported_facts.length+6);
  header(reported,5,['Company','Metric','Reported value','Unit','Year','Kind','Reporting population','Page','Report']);
  data.reported_facts.forEach((fact,i)=>{
    const row=i+6,raw=String(fact.value),numeric=raw.replace(/,/g,'').replace(/%$/,'').trim();
    const value=/^-?\d+(?:\.\d+)?$/.test(numeric)?Number(numeric):raw;
    const s=fact.source;
    const display=typeof value==='string'?sentence(value,180):value;
    write(reported,`A${row}`,[[s.company,fact.metric,display,fact.unit,fact.year,fact.kind,fact.population,s.page,'Open report']]);
    const area=reported.getRange(`A${row}:I${row}`);
    area.format.wrapText=true;
    area.format.rowHeight=Math.max(44,Math.ceil(Math.max(fact.metric.length/46,String(display).length/24,(fact.population||'').length/46))*13+12);
    area.format.fill=i%2?'#FFFFFF':light;
    const places=typeof value==='number'&&!Number.isInteger(value)?Math.min(6,(String(value).split('.')[1]||'').length):0;
    reported.getRange(`C${row}`).setNumberFormat('#,##0'+(places?'.'+'0'.repeat(places):''));
    for(const col of ['D','E','F','H'])reported.getRange(`${col}${row}`).format.horizontalAlignment='center';
    reported.getRange(`I${row}`).format.font={name:'Arial',size:10,color:accent,underline:'single'};
    const url=urlFor(s);if(url)links.push({sheet:sheetNumber(reported),cell:`I${row}`,url});
  });
  reported.tables.add(`A5:I${data.reported_facts.length+5}`,true,'ReportedFacts').style='TableStyleMedium1';
  reported.getRange(`A6:I${data.reported_facts.length+5}`).format.borders={insideHorizontal:{style:'hair',color:'#E4DFED'}};
}
if(data.promises?.length){
  const promises=book.worksheets.getItem('Promises');
  base(promises,'Promises & delivery',[28,52,14,68,18],data.promises.length+6);
  header(promises,5,['Company','Commitment','Deadline','Reported delivery','Source pages']);
  data.promises.forEach((p,i)=>{
    const row=i+6;
    write(promises,`A${row}`,[[p.company,p.commitment,p.deadline,p.assessment,[...new Set(p.citations.map(s=>`p. ${s.page}`))].join(', ')]]);
    promises.getRange(`A${row}:E${row}`).format.wrapText=true;
    promises.getRange(`A${row}:E${row}`).format.rowHeight=Math.max(54,Math.ceil(Math.max(p.commitment.length/50,p.assessment.length/64))*13+12);
    promises.getRange(`A${row}:E${row}`).format.fill=i%2?'#FFFFFF':light;
    promises.getRange(`E${row}`).format.font={name:'Arial',size:10,color:accent,underline:'single'};
    const url=p.citations[0]?urlFor(p.citations[0]):'';if(url)links.push({sheet:sheetNumber(promises),cell:`E${row}`,url});
  });
  promises.tables.add(`A5:E${data.promises.length+5}`,true,'PromiseRegister').style='TableStyleMedium1';
  promises.getRange(`A6:E${data.promises.length+5}`).format.borders={insideHorizontal:{style:'hair',color:'#E4DFED'}};
}
// A quiet front cover and direct navigation. Analysis remains in the working tabs.
cover.showGridLines=false;cover.tabColor=ink;
cover.getRange('A1:J36').format.fill='#FFFFFF';
cover.getRange('A1:J36').format.font={name:'Arial',size:10,color:ink};
cover.getRange('A1:J36').format.rowHeight=24;
cover.getRange('A1:A36').format.columnWidth=4;
cover.getRange('B1:I36').format.columnWidth=14;
cover.getRange('J1:J36').format.columnWidth=4;
if(data.brand?.logo)cover.images.add({dataUrl:data.brand.logo,anchor:{from:{row:1,col:1},extent:{widthPx:185,heightPx:72}}});
write(cover,'B6',[[data.package.toUpperCase()]]);
cover.getRange('B6:I6').merge();cover.getRange('B6').format.font={name:'Arial',size:10,bold:true,color:accent};
write(cover,'B8',[[data.title]]);cover.getRange('B8:I11').merge();
cover.getRange('B8:I11').format.font={name:'Arial',size:24,color:ink};
cover.getRange('B8:I11').format.wrapText=true;cover.getRange('B8:I11').format.verticalAlignment='center';
write(cover,'B13',[[(data.edition?.companies||[]).map(c=>c.company_name).join(' / ')]]);
cover.getRange('B13:I15').merge();cover.getRange('B13:I15').format.wrapText=true;
write(cover,'B17',[[data.incomplete?'Working draft - analysis incomplete':`Prepared ${(data.edition?.created_at||'').slice(0,10)}`]]);
cover.getRange('B17:I17').merge();cover.getRange('B17').format.font={name:'Arial',size:10,color:muted};
cover.getRange('B19:I19').format.borders={bottom:{style:'thin',color:'#DEDCE7'}};
write(cover,'B21',[['RESEARCH & RESULTS']]);write(cover,'G21',[['SUPPORTING DATA']]);
cover.getRange('B21:E21').merge();cover.getRange('G21:I21').merge();
for(const cell of ['B21','G21'])cover.getRange(cell).format.font={name:'Arial',size:10,bold:true,color:accent};
for(const [names,start,last] of [[['Findings','Comparisons','Scorecard','Promises'],'B','E'],[['Inputs','Reported data','Sources'],'G','I']]){
  let r=23;
  for(const name of names.filter(n=>sheetNumbers.has(n))){
    write(cover,`${start}${r}`,[[name]]);cover.getRange(`${start}${r}:${last}${r+1}`).merge();
    cover.getRange(`${start}${r}:${last}${r+1}`).format.font={name:'Arial',size:12,color:ink};
    cover.getRange(`${start}${r}:${last}${r+1}`).format.borders={bottom:{style:'hair',color:'#DEDCE7'}};
    links.push({sheet:sheetNumber(cover),cell:`${start}${r}`,location:`'${name}'!A1`});r+=3;
  }
}
// Freeze just the useful table headings and identifiers. Outputs stay first;
// technical inputs have quieter tabs, without hiding the calculation trail.
for(const name of sheetNumbers.keys()){
  if(name==='Cover')continue;
  const tab=book.worksheets.getItem(name);
  tab.tabColor=['Findings','Comparisons','Scorecard'].includes(name)?accent:'#C5C2CE';
  if(['Inputs','Reported data','Sources','Promises'].includes(name))tab.freezePanes.freezeColumns(1);
  const column=name==='Comparisons'?'M':name==='Findings'?'D':name==='Inputs'?'J':name==='Reported data'?'I':name==='Scorecard'?'F':'E';
  const cell=`${column}4`;
  write(tab,cell,[['Cover']]);tab.getRange(cell).format.font={name:'Arial',size:10,color:accent,underline:'single'};
  links.push({sheet:sheetNumber(tab),cell,location:"'Cover'!B8"});
}
book.recalculate();
const errors=await book.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!',options:{useRegex:true,maxResults:20},maxChars:2000});
if(/#REF!|#DIV\/0!|#VALUE!|#NAME\?|#NUM!|#SPILL!/.test(errors.ndjson)) throw Error('Workbook formula validation failed');
if(previewDir){
  await fs.mkdir(previewDir,{recursive:true});
  for(const [sheet,range] of [['Cover','A1:J36'],['Findings','A1:D12'],...(hasCalculations?[['Comparisons','A1:M21'],['Inputs','A1:J12']]:[]),['Sources','A1:E12'],...(data.disclosure_scores||data.badges?.length?[['Scorecard','A1:F18']]:[]),...(data.reported_facts?.length?[['Reported data','A1:I12']]:[]),...(data.promises?.length?[['Promises','A1:E12']]:[])]){
    const blob=await book.render({sheetName:sheet,range,scale:1.5});
    await fs.writeFile(`${previewDir}/${sheet}.png`,new Uint8Array(await blob.arrayBuffer()));
  }
  if(hasCalculations)console.log((await book.inspect({kind:'table',range:'Comparisons!A5:F13',include:'values,formulas',tableMaxRows:9,tableMaxCols:6,maxChars:2000})).ndjson);
  for(const [i,range] of comparisonPreviews.entries()){
    const blob=await book.render({sheetName:'Comparisons',range,scale:1});
    await fs.writeFile(`${previewDir}/Comparison-${i+1}.png`,new Uint8Array(await blob.arrayBuffer()));
  }
}
await (await SpreadsheetFile.exportXlsx(book)).save(output);
await fs.writeFile(output+'.links.json',JSON.stringify(links));
