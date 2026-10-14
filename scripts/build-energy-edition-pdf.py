"""Render the editorial energy edition from the workbook's recalculated outputs."""
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT=Path(__file__).resolve().parents[1]
DATA=json.loads((ROOT/'data/editions/energy-2025/edition.json').read_text())
CALC=json.loads((ROOT/'tmp/energy-2025/calculated.json').read_text())
FACT={x['id']:x for x in DATA['facts']}
OUT=ROOT/'output/pdf/Vero_Energy_2025_Research_Report.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
FONTS=Path('/System/Library/Fonts/Supplemental')
for name,file in [('Body','Arial.ttf'),('Bold','Arial Bold.ttf'),('Display','Georgia.ttf'),('Italic','Georgia Italic.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(FONTS/file)))
pdfmetrics.registerFontFamily('Body',normal='Body',bold='Bold',italic='Italic',boldItalic='Bold')
W,H=595.28,841.89
INK='#17202F';MUTED='#667084';PURPLE='#6554C0';CYAN='#167DAB';PALE='#F1EFFA';LINE='#DDE1EA';WHITE='#FFFFFF'
c=canvas.Canvas(str(OUT),pagesize=(W,H))
c.setTitle('Vero | Energy, decoded | 2025 peer intelligence')
c.setAuthor('Vero')
PAGE=0
ABBR={'aramco':'Aramco SR','shell':'Shell AR','total':'TotalEnergies URD','total-climate':'TotalEnergies Climate 2026','equinor':'Equinor AR','eni':'Eni AR','eni-for':'Eni for 2025'}

def text(t,x,y,size=11,color=INK,font='Body'):
    c.setFillColor(HexColor(color));c.setFont(font,size);c.drawString(x,H-y-size*.78,str(t))

def para(t,x,y,w,size=11,color=INK,leading=None,font='Body'):
    style=ParagraphStyle('p',fontName=font,fontSize=size,leading=leading or size*1.4,textColor=HexColor(color))
    p=Paragraph(t,style);_,h=p.wrap(w,1000)
    p.drawOn(c,x,H-y-h);return y+h

def box(x,y,w,h,fill=PALE):
    c.setFillColor(HexColor(fill));c.rect(x,H-y-h,w,h,fill=1,stroke=0)

def line(x1,y1,x2,y2,color=LINE,width=.7):
    c.setStrokeColor(HexColor(color));c.setLineWidth(width);c.line(x1,H-y1,x2,H-y2)

def page(kicker,title,subtitle=''):
    global PAGE
    if PAGE:c.showPage()
    PAGE+=1
    box(0,0,W,H,WHITE)
    text('VERO',42,30,11,INK,'Bold');text('ENERGY / 2025',425,31,8,MUTED)
    line(42,52,W-42,52)
    text(kicker.upper(),42,75,9,PURPLE,'Bold')
    end=para(title,42,97,W-84,29,INK,34,'Display')
    if subtitle:para(subtitle,42,end+13,W-84,11,MUTED)
    line(42,798,W-42,798)
    text('Source-backed peer intelligence',42,812,8,MUTED)
    text(f'{PAGE:02d}',W-57,812,8,MUTED)

def sources(ids,y=748):
    refs=[];seen=set()
    for id in ids:
        f=FACT[id];key=(f['document'],f['printed_page'])
        if key in seen:continue
        seen.add(key)
        label=f"{ABBR[f['document']]} p. {f['printed_page']}"
        refs.append(f'<link href="{escape(f["url"], {chr(34):"&quot;"})}" color="{CYAN}">{escape(label)}</link>')
    para('Sources: '+' · '.join(refs),42,y,W-84,7.6,MUTED,11)

def bars(items,x,y,w,maxv,fmt,suffix='',step=46,color=PURPLE,labelw=120):
    plotw=w-labelw-50
    for i,(name,value) in enumerate(items):
        yy=y+i*step;text(name,x,yy+3,10)
        box(x+labelw,yy,plotw,20,'#F0F1F5');box(x+labelw,yy,plotw*value/maxv,20,color)
        text(fmt(value)+suffix,x+labelw+plotw+9,yy+3,10,INK,'Bold')
    return y+len(items)*step

def callout(number,heading,body,x,y,w):
    text(number,x,y,38,PURPLE,'Display');text(heading,x,y+50,11,INK,'Bold');para(body,x,y+70,w,10,MUTED)

# 1 / The cover is itself a one-minute briefing.
PAGE=1;box(0,0,W,H,'#10131D')
text('VERO',44,43,18,WHITE,'Bold');text('ENERGY INTELLIGENCE / 01',330,48,9,'#C0B9ED')
line(44,84,W-44,84,'#343345')
text('Energy,',44,131,58,WHITE,'Display');text('decoded.',44,201,58,'#BBB0FF','Italic')
para('What five energy companies reveal<br/>when you read beyond the headline KPI.',46,302,480,19,'#E0DFEB',27)
text('2025 DISCLOSURES',46,384,10,'#AAA4C6','Bold')
para('Aramco · Shell · TotalEnergies · Equinor · Eni',46,408,480,12,'#D7D7E3')
for yy in [471,558,645]:line(46,yy,549,yy,'#353343')
for yy,n,title,body in [
    (491,'10 / 10','THE SAFETY BLIND SPOT','All reported work-related injury fatalities were contractors or non-employees.'),
    (578,'2.75x','THE PORTFOLIO EFFECT','Shell’s net divestment effect versus its reported reduction activities.'),
    (665,'92.5%','THE OPPORTUNITY GAP','Female-to-male training hours at the strongest of three disclosing peers.'),
]:
    text(n,46,yy,31,'#BBB0FF','Display');text(title,206,yy,9,'#C4C0D4','Bold');para(body,206,yy+20,326,10,WHITE,14)
text('FIRST FIVE-COMPANY EDITION',46,781,8,'#C4C0D4');text('13 OCTOBER 2026',421,781,8,'#C4C0D4')

# 2 / Awards + scorecard.
page('Edition awards','Specific achievements.<br/>Visible criteria.','Awards are calculated from the disclosed peer subset, not an overall ESG league table.')
for i,(award,leader,value,criterion,n) in enumerate(CALC['awards']):
    y=214+i*85;line(42,y,553,y);text(f'0{i+1}',42,y+17,13,PURPLE,'Bold')
    text(award,80,y+15,12,INK,'Bold');text(leader,80,y+36,10,MUTED)
    result=f'{value:.1%}' if i<2 else f'${value:,.0f}'
    text(result,422,y+14,25,PURPLE,'Display')
    para(criterion+f' · {n} companies',80,y+55,450,9,MUTED)
text('DISCLOSURE DEPTH',42,495,10,PURPLE,'Bold')
para('TotalEnergies, Equinor and Eni share the lead on the seven-topic checklist.',42,516,490,15,INK,21,'Display')
scores=[('Aramco',5),('Shell',6),('TotalEnergies',7),('Equinor',7),('Eni',7)]
for i,(company,score) in enumerate(scores):
    x=42+i*103;text(company,x,580,9);text(f'{score}/7',x,604,27,PURPLE,'Display')
    for n in range(7):box(x+n*11,646,8,8,PURPLE if n<score else LINE)
para('One point each: separate Scope 1/2; quantified Scope 3; women in workforce; women in leadership; gender-split training; contractor fatalities; and credit quantity, timing and purpose.',42,679,510,9,MUTED,13)
sources(['a_women','s_women','t_women','q_women_n','e_women','t_train_f','q_train_f','e_train_f','a_social','s_social','e_social'],741)

# 3 / People.
page('People','More training is not the same<br/>as equal access.','The female-to-male hours ratio exposes a difference hidden by company-wide averages.')
text('TRAINING OPPORTUNITY / WOMEN’S HOURS AS A SHARE OF MEN’S',42,208,9,PURPLE,'Bold')
people=CALC['People'][1:]
training=[(r[0],r[6]*100) for r in people if isinstance(r[6],(int,float))]
bars(training,42,240,505,100,lambda v:f'{v:.1f}',suffix='%',step=52,labelw=116)
for i,(co,wh,mh) in enumerate([('TotalEnergies',24.6,26.6),('Equinor',22.6,28.7),('Eni',27.5,35.9)]):
    x=42+174*i;text(co,x,407,10,INK,'Bold');text(f'{mh-wh:.1f} hours',x,430,24,PURPLE,'Display');text('annual gap, men minus women',x,463,8,MUTED)
line(42,501,553,501)
text('REPRESENTATION / WOMEN IN THE WORKFORCE',42,525,9,PURPLE,'Bold')
ordered=sorted([(r[0],r[1]*100) for r in people],key=lambda x:-x[1])
bars(ordered,42,553,505,40,lambda v:f'{v:.1f}',suffix='%',step=31,labelw=116)
sources(['t_train_f','t_train_m','q_train_f','q_train_m','e_train_f','e_train_m','a_women','s_women','t_women','q_women_n','e_women'])

# 4 / Contractor safety.
page('Safety','The people missing from<br/>an employee-only comparison.','Across the reviewed 2025 disclosures, all ten work-related injury fatalities were contractors or non-employees.')
box(42,213,511,137,INK)
text('10',62,228,63,'#BBB0FF','Display');text('contractor / non-employee fatalities',178,244,13,WHITE,'Bold')
text('0',62,297,29,WHITE,'Display');text('own-employee fatalities',178,306,12,'#C0C5D1')
for i in range(10):box(405+(i%5)*24,300+(i//5)*17,10,10,'#BBB0FF')
headers=[('Company',42),('Own employees',245),('Contractors / others',397)]
for t,x in headers:text(t,x,380,10,MUTED,'Bold')
for i,(co,n) in enumerate([('Aramco',4),('Shell',4),('TotalEnergies',1),('Equinor',1),('Eni',0)]):
    y=413+i*43;line(42,y-10,553,y-10);text(co,42,y,12);text('0',286,y,12);text(n,454,y,12,PURPLE,'Bold')
box(42,657,511,65,PALE)
para('<b>The business question:</b> does contractor procurement receive the same board-level scrutiny as employee safety?',58,674,475,12,INK,17)
sources(['a_contractor_fatal','s_contractor_fatal','t_contractor_fatal','q_contractor_fatal','e_contractor_fatal'])

# 5 / Carbon movement, not arbitrary ranking.
page('Carbon progress','What actually moved<br/>the emissions line?','2025 change in each company’s reported gross Scope 1 + market-based Scope 2, using rounded source components.')
trajectory=CALC['Carbon and value'][1:]
origin=354;scale=10
for i,r in enumerate(trajectory):
    y=216+i*40;v=r[5]*100;text(r[0],42,y+2,11);text(f'{r[4]:.1f} → {r[3]:.1f} Mt',156,y+3,9,MUTED)
    line(origin,y-3,origin,y+27,'#BBC1CB')
    box(origin+min(v,0)*scale,y,abs(v)*scale,20,PURPLE if v<0 else CYAN)
    text(f'{v:+.1f}%',461,y+2,12,INK,'Bold')
para('Each company keeps its reported inventory perimeter. These are within-company movements, not a ranking of production efficiency.',42,423,500,8.5,MUTED,12)
line(42,463,553,463)
callout('2.75x','SHELL’S PORTFOLIO EFFECT','Net divestment effect: 4.8 minus 1.4 = 3.4 MtCO2e. Reduction activities, including purchased renewable electricity: 1.238 MtCO2e.',42,486,239)
callout('+5.1%','ARAMCO’S ABSOLUTE CHANGE','Scope 1+2 rose to 72.0 MtCO2e despite 1.57 MtCO2e of reported efficiency-related avoided emissions.',311,486,239)
para('<b>What to ask next:</b> how much of the change came from operating improvements, asset sales, output changes or measurement?',42,678,500,11,INK,16)
sources(['a_prior','a_avoided','a_s1','s_prior','s_acquire','s_divest','s_abate','t_prior','q_s1','e_s1'],743)

# 6 / Credit purpose.
page('Carbon credits','Same unit.<br/>Very different claims.','The interesting comparison is what credits are doing in the strategy, not who buys the most.')
credit_rows=[
    ('Aramco','0.513 Mt','Corporate Scope 1+2','2025 retirement; equivalent to 0.71% of reported gross Scope 1+2.'),
    ('Shell','5.5 Mt','Energy-product intensity','Credits in the NCI calculation fell 66.5% from 16.4 Mt in 2024.'),
    ('Equinor','0.041 Mt','Business flights','Flights outside Europe; 100% reduction credits under Verra VCS.'),
    ('Eni','7.0 Mt','Equity decarbonisation targets','2025 accounting; retired in February 2026. Reduction credits, not removals.'),
    ('TotalEnergies','5.0 Mt / year','Future residual emissions','Annual nature-based credit plan starting in 2030, not current retirement.'),
]
for i,(co,n,purpose,body) in enumerate(credit_rows):
    y=211+i*89;line(42,y,553,y);text(co,42,y+15,12,INK,'Bold');text(n,339,y+13,21,PURPLE,'Display')
    text(purpose,42,y+38,10,INK);para(body,42,y+57,502,9,MUTED,12)
box(42,676,511,49,PALE)
para('Retirement is not trading turnover. These disclosures do not establish what each company earned, spent or traded in carbon-credit markets.',56,688,483,10,INK,14)
sources(['a_credits','s_credit','s_credit_prior','q_credits','e_credits','t_credits'])

# 7 / AI without turning narratives into fictitious quantities.
page('AI and innovation','From AI activity<br/>to operating evidence.','A named deployment is more useful than an AI slogan. A measured operating effect is more useful still.')
box(42,211,511,116,INK);text('95%',61,227,52,'#BBB0FF','Display')
para('Aramco reports less manual effort in energy reporting, with forecasting across 27 assets.',237,235,287,13,WHITE,19)
text('A workflow benefit, not a 95% reduction in energy use.',62,303,9,'#C2C5D2')
rows=[
    ('Shell','Machine vision at Pearl GTL detects hazards and alerts supervisors; AI monitors equipment health.','Live operating application'),
    ('TotalEnergies','Close to 100 digital solutions created since 2020, about half integrating AI and progressively deployed.','Deployment portfolio'),
    ('Equinor','AI-assisted seismic interpretation is described as taking hours rather than months.','Reported time compression'),
    ('Eni','Safety Presence has generated about 800 alerts since deployment, prompting preventive actions.','Measured system activity'),
]
for i,(co,body,label) in enumerate(rows):
    y=359+i*80;line(42,y,553,y);text(co,42,y+16,12,INK,'Bold');text(label.upper(),42,y+40,7.6,PURPLE,'Bold');para(body,212,y+14,339,10,INK,14)
para('<b>Next-edition metric:</b> proportion of named AI deployments with a quantified operating outcome and a stated measurement period.',42,704,510,10,MUTED,14)
sources(['a_ai_admin','a_ai_assets','s_ai','t_ai_solutions','q_ai','e_ai_alerts'],759)

# 8 / Capital and business-scale lenses.
page('Capital allocation','Scale the investment.<br/>Then ask what it achieved.','Community spending per $1 million of sales creates a business-size lens on three disclosed budgets.')
social=sorted([(r[0],r[5]) for r in CALC['Social'][1:]],key=lambda x:-x[1])
bars(social,42,213,505,1400,lambda v:f'${v:,.0f}',step=55,labelw=100)
para('Aramco: $541m. Eni: €81m. Shell: $115m. Eni’s spending and sales share the same currency, so the ratio does not depend on an FX guess.',42,385,510,10,MUTED)
line(42,438,553,438)
text('A SECOND LENS / CARBON PER SALES DOLLAR',42,459,9,PURPLE,'Bold')
intensity=CALC['intensity'][1:]
for i,row in enumerate(intensity):
    x=42+i*269;callout(f'{row[3]:.0f}',row[0].upper(),'tCO2e per $1m sales, using the explicitly disclosed consolidated-group Scope 1+2 subset.',x,491,232)
para('The workbook converts Eni’s euro sales at its reported 2025 annual average of $1.13/€. These ratios capture business mix and prices as well as emissions; they are not oil-production efficiency measures.',42,643,505,9,MUTED,13)
sources(['a_social','a_revenue','s_social','s_sales','e_social','e_revenue','e_fx','t_consolidated_s1','t_consolidated_s2','t_revenue','e_consolidated_s1','e_consolidated_s2'],735)

# 9–11 / Company briefs: a buyer can recognise their own story.
def profile(co,y,headline,kpis,body,question):
    text(co.upper(),42,y,10,PURPLE,'Bold');para(headline,42,y+22,505,22,INK,27,'Display')
    for i,(n,label) in enumerate(kpis):
        x=42+i*171;text(n,x,y+91,28,PURPLE,'Display');para(label,x,y+128,150,9,MUTED,12)
    para(body,42,y+169,505,11,INK,16)
    para('<b>Question for management:</b> '+question,42,y+234,505,10,MUTED,14)

page('Company briefs','The story each company<br/>can take into the room.')
profile('Aramco',190,'Efficiency gains, growing scale.',[('3.17x','female hiring share / female workforce share'),('95','workforce nationalities'),('5/7','edition disclosure checklist')],
        'Strong examples of applied AI and significant social investment sit alongside rising absolute operational emissions. The recruitment pipeline is more female than the current workforce; leadership remains at 6.2% women.',
        'How will hiring translate into promotion, and which operating changes will outweigh production-driven emissions growth?')
line(42,484,553,484)
profile('Shell',505,'Explain the bridge, not just the drop.',[('2.75x','net portfolio effect / reduction activities'),('35%','women in workforce and senior leadership'),('6/7','edition disclosure checklist')],
        'Shell makes it possible to separate portfolio effects from operating measures. Its energy-product credit use fell sharply, while net carbon intensity stayed at a rounded 71 gCO2e/MJ.',
        'Which reductions remain after stripping out asset sales, and can training participation and hours be split by gender?')
sources(['a_hires','a_women','a_nationalities','a_lead','s_acquire','s_divest','s_abate','s_women','s_lead','s_nci'],771)

page('Company briefs','Current representation.<br/>Future leadership.')
profile('TotalEnergies',190,'A strong people-data benchmark.',[('36.7%','women in the workforce'),('92.5%','female / male training hours'),('7/7','edition disclosure checklist')],
        'TotalEnergies leads the five-company workforce measure and the three-company training-parity measure. Its annual report also separates operated emissions from the larger accounting perimeter.',
        'How will the 30.2% female senior-executive share catch up with workforce representation?')
line(42,484,553,484)
profile('Equinor',505,'Two carbon trajectories, one business.',[('46%','women in leadership level 2'),('+3.1%','Scope 3 significant-category emissions'),('7/7','edition disclosure checklist')],
        'Own-operations emissions fell while reported Scope 3 rose. Equinor explains divestments and US gas growth separately, and gives unusually granular leadership and training data.',
        'What would reduce the 6.1-hour female-to-male training gap, and what is the Scope 3 implication of gas growth?')
sources(['t_women','t_train_f','t_train_m','t_lead','t_s1','q_lead','q_scope3','q_scope3_prior','q_train_f','q_train_m'],771)

page('Company brief / SDGs','Follow the operating mechanism,<br/>not the SDG icon.')
profile('Eni',190,'A detailed transition narrative.',[('76.3%','LNG share of potentially avoided emissions'),('800','approximate AI safety alerts since deployment'),('7/7','edition disclosure checklist')],
        'Eni connects its transition story to LNG, credits, community access and innovation. Its detail enables better questions: broad management diversity is 30.8%, but senior managers alone are 19.8% women.',
        'How do the LNG counterfactual, credit retirements and gross inventory each contribute to the transition story?')
line(42,488,553,488)
text('SDG MAPPING → MECHANISM → OUTCOME',42,510,10,PURPLE,'Bold')
for i,(title,body) in enumerate([
    ('SDG 7 / energy access','Eni links gas to energy access; its community narrative reaches about 3 million people, including clean-cooking initiatives.'),
    ('SDG 4 / skills','Training totals become more decision-useful when translated into participation, gender gaps and promotion outcomes.'),
    ('SDG 13 / climate','Aramco maps climate action to efficiency and targets; the operating inventory still rose in 2025.'),
]):
    y=543+i*60;text(title,42,y,11,INK,'Bold');para(body,228,y,323,9.5,MUTED,13)
sources(['e_avoided','e_lng_avoided','e_ai_alerts','e_lead','e_senior','e_sdg','e_beneficiaries','a_sdg','a_avoided'],758)

# 12 / Source bundle and a short, usable method.
page('Sources and calculation notes','One company.<br/>A bundle of evidence.','Annual accounts provide the denominators. Sustainability and climate reports provide additional operating detail.')
doc_order=['aramco','shell','total','total-climate','equinor','eni','eni-for']
documents={d['key']:d for d in DATA['documents']}
for i,key in enumerate(doc_order):
    d=documents[key];y=205+i*49
    text(f'{i+1:02d}',42,y,11,PURPLE,'Bold')
    link=f'<link href="{escape(d["source_url"], {chr(34):"&quot;"})}" color="{CYAN}">{escape(d["title"])}</link>'
    para(link,75,y,473,10,INK,13)
    text('2025 performance' if key!='total-climate' else 'Published 2026; reports 2025 performance',75,y+27,8,MUTED)
line(42,567,553,567)
text('HOW THE EDITION IS BUILT',42,586,10,PURPLE,'Bold')
para('111 selected facts feed editable workbook calculations and ten editorial findings. Unit conversions use arithmetic; the euro-dollar conversion uses Eni’s stated annual average. Awards use the stated peer sample and criterion, with equal treatment of ties.',42,609,511,10,INK,15)
para('The disclosure checklist is seven equally weighted topics across the downloaded bundle. A missing item earns no disclosure point, but is not treated as zero operating performance. Scores describe this edition, not an external ESG rating.',42,675,511,9.5,MUTED,14)
para('Aramco’s separate annual report was requested but timed out; its sustainability report contains the revenue used here. Printed pages and PDF-viewer pages, source excerpts and document hashes are retained in the workbook/data. AI-assisted research and editorial synthesis; no paid API inference was used for this edition.',42,734,511,8.5,MUTED,12)
c.save()
print(f'{PAGE} pages: {OUT}')
