import sys,os;sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from base import *
rows,by,sales=load()
si={s:i for i,s in enumerate(sales)}
PP=[c for c in rows if c['outcome']=='postponed']
print("== POSTPONEMENTS",len(PP))
# how far out
gap=collections.Counter()
for c in PP:
    if c['pp_date']:
        m=(c['pp_date'].year-c['sd'].year)*12+c['pp_date'].month-c['sd'].month; gap[min(m,7)]+=1
    else: gap['none/generally']+=1
print('months ahead:',sorted(gap.items(),key=lambda kv:str(kv[0])))
# does it show up at the promised sale
def at_promised(c):
    if not c['pp_date']: return None
    tgt=[s for s in sales if s[:7]==c['pp_date'].strftime('%Y-%m')]
    if not tgt: return 'beyond data'
    for d in by[c['case_no']]:
        if d['sale_date']==tgt[0]: return d['outcome']
    return 'not on list'
C=collections.Counter(at_promised(c) for c in PP); C.pop(None,None); C.pop('beyond data',None); n=sum(C.values())
print('outcome at promised date:',{k:f"{v} ({pct(v,n)}%)" for k,v in C.most_common()})
# next-appearance outcome by state at postponement
def nxt(c):
    r=at_promised(c)
    return r
def tab(name,g):
    C=collections.Counter(at_promised(c) for c in g); C.pop(None,None); C.pop('beyond data',None); n=sum(C.values())
    if n<15: return
    sold=C['sold_3p']+C['plaintiff_overbid']+C['plaintiff_costs']
    print(f"  {name:46} n={n:4} auctioned {pct(sold,n):5}% (3P {pct(C['sold_3p'],n):5}%) postponed again {pct(C['postponed'],n):5}% stayed {pct(C['stayed'],n):5}% paid {pct(C['paid'],n)}% off-list {pct(C['not on list'],n)}%")
for T,sel in [('TAX LIEN',lambda c:c['grp'].startswith('Tax')),('MORTGAGE',lambda c:c['grp']=='Mortgage foreclosure')]:
    g0=[c for c in PP if sel(c)]
    print(T); tab('all postponed',g0)
    tab('OK box checked',[c for c in g0 if c['box_ok']])
    tab('OK box not checked',[c for c in g0 if not c['box_ok']])
    tab('service+3129.2+3129.3 all checked',[c for c in g0 if c['box_service'] and c['box_3129_2'] and c['box_3129_3']])
    tab('service & 3129.2, no 3129.3',[c for c in g0 if c['box_service'] and c['box_3129_2'] and not c['box_3129_3']])
    tab('service not checked',[c for c in g0 if not c['box_service']])
    tab('3129.2 not checked',[c for c in g0 if not c['box_3129_2']])
    for k in (0,1,2,3,5):
        tab(f'postponed {k}{"+" if k==5 else ""} times before (in window)',[c for c in g0 if (c['app_i']==k if k<5 else c['app_i']>=5)])
    tab('1 month ahead',[c for c in g0 if c['pp_date'] and (c['pp_date'].year-c['sd'].year)*12+c['pp_date'].month-c['sd'].month==1])
    tab('2 months ahead',[c for c in g0 if c['pp_date'] and (c['pp_date'].year-c['sd'].year)*12+c['pp_date'].month-c['sd'].month==2])
    tab('3+ months ahead',[c for c in g0 if c['pp_date'] and (c['pp_date'].year-c['sd'].year)*12+c['pp_date'].month-c['sd'].month>=3])
    tab('status (Waived)',[c for c in g0 if 'Waived' in c['status_raw']])
    U=lambda c:(c['comments'] or '').upper()
    tab('notes: free & clear min bid stated',[c for c in g0 if c['minbid']])
    tab('notes: F/C mentioned, no min yet',[c for c in g0 if c['fc_token'] and not c['minbid']])
    tab('notes: NEED O/C',[c for c in g0 if re.search(r'NEED O/?C',U(c))])
    tab('notes: bankruptcy (BK)',[c for c in g0 if re.search(r'\bBK\b|BANKRUPT',U(c))])
    tab('notes: NEED BKD',[c for c in g0 if re.search(r'NEED BKD',U(c))])
    tab('notes: DECREE',[c for c in g0 if re.search(r'\bDECREE\b',U(c))])
    tab('notes: NEED DECREE',[c for c in g0 if re.search(r'NEED\s+(?:A\s+)?DECREE',U(c))])
    tab('notes: FORFEIT',[c for c in g0 if re.search(r'FORF',U(c))])
    tab('notes: OK TO SELL',[c for c in g0 if re.search(r'OK TO SELL',U(c))])
    tab('notes: handbill',[c for c in g0 if re.search(r'HANDBILL',U(c))])
    tab('notes: REASSESS DAMAGES',[c for c in g0 if re.search(r'REASSESS',U(c))])
    tab('notes: loss mit / forbear / SAVE YOUR HOME',[c for c in g0 if re.search(r'LOSS MIT|FORBEAR|SAVE YOUR HOME|SYH|PAYMENT PLAN|\bPP\b AGREE|AGREEMENT',U(c))])
    tab('notes empty',[c for c in g0 if not U(c).strip()])
    tab('estate/heirs',[c for c in g0 if c['owner_type'].startswith('Estate')])
    tab('entity owner',[c for c in g0 if c['owner_type'].startswith('Entity')])
    for pk in set(c['pk'] for c in g0): tab('plaintiff: '+pk,[c for c in g0 if c['pk']==pk])
print("== NEED lines vocabulary in postponed rows")
V=collections.Counter()
for c in PP:
    for l in (c['comments'] or '').upper().split('\n'):
        if l.startswith('NEED'): V[re.sub(r'[\d./-]+','#',l)[:30]]+=1
print(V.most_common(25))
