import sys,os;sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from base import *
rows,by,sales=load()
CL=[c for c in rows if c['sd'] in c['ok_dates']]
print("== CLEARED FOR THIS SALE (notes say OK TO SELL / ALL DOCS for this sale date)",len(CL),'of',len(rows))
print(' share of auctioned rows that carry the note:',pct(sum(1 for c in rows if c['auctioned'] and c['sd'] in c['ok_dates']),sum(1 for c in rows if c['auctioned'])))
print(' by sale: ',[(s[2:7],sum(1 for c in CL if c['sale_date']==s)) for s in sales])
def tab(name,g,minn=20):
    n=len(g)
    if n<minn: return
    C=collections.Counter(c['outcome'] for c in g); a=C['sold_3p']+C['plaintiff_overbid']+C['plaintiff_costs']+C['unsold']
    print(f"  {name:44} n={n:4} auctioned {pct(a,n):5}% | 3P {pct(C['sold_3p'],n):5}% plaintiff {pct(C['plaintiff_overbid']+C['plaintiff_costs'],n):5}% | postponed {pct(C['postponed'],n):5}% stayed {pct(C['stayed'],n):5}% paid {pct(C['paid'],n)}%")
tab('ALL cleared',CL)
for T,sel in [('TAX LIEN',lambda c:c['grp'].startswith('Tax')),('MORTGAGE',lambda c:c['grp']=='Mortgage foreclosure')]:
    g0=[c for c in CL if sel(c)]; print(T); tab('all',g0)
    for h in sorted(set(c['half'] for c in g0)): tab(h,[c for c in g0 if c['half']==h])
    for g in sorted(set(c['grp'] for c in g0)): tab(g,[c for c in g0 if c['grp']==g])
    for o in sorted(set(c['owner_type'] for c in g0)): tab('owner: '+o,[c for c in g0 if c['owner_type']==o])
    for pk in sorted(set(c['pk'] for c in g0)): tab('plaintiff: '+pk,[c for c in g0 if c['pk']==pk])
    A=collections.Counter((c['plaintiff_attorney'] or '')[:26] for c in g0)
    for k,_ in A.most_common(14): tab('atty: '+k,[c for c in g0 if (c['plaintiff_attorney'] or '')[:26]==k])
    tab('first time on list',[c for c in g0 if c['docket_m']==0])
    tab('on list 1-3 months',[c for c in g0 if c['docket_m'] and 1<=c['docket_m']<=3])
    tab('on list 4-12 months',[c for c in g0 if c['docket_m'] and 4<=c['docket_m']<=12])
    tab('on list >12 months',[c for c in g0 if c['docket_m'] and c['docket_m']>12])
    tab('3129.3 box checked',[c for c in g0 if c['box_3129_3']])
    tab('3129.3 box not checked',[c for c in g0 if not c['box_3129_3']])
    U=lambda c:(c['comments'] or '').upper()
    tab('notes: bankruptcy history',[c for c in g0 if re.search(r'\bBK|BANKRUPT',U(c))])
    tab('notes: forfeited before',[c for c in g0 if re.search(r'FORF',U(c))])
    tab('notes: FHA',[c for c in g0 if re.search(r'\bFHA\b',U(c))])
    tab('notes: reassessed damages',[c for c in g0 if c['dmg']])
    tab('cleared for an earlier sale too (pulled before)',[c for c in g0 if any(d<c['sd'] for d in c['ok_dates'])])
    if T=='MORTGAGE':
        def norm(p):
            u=re.sub(r'[^A-Z ]','',(p or '').upper()); return ' '.join(u.split()[:2])
        P=collections.Counter(norm(c['plaintiff']) for c in g0)
        for k,_ in P.most_common(16): tab('plf: '+k,[c for c in g0 if norm(c['plaintiff'])==k],15)
    B=[0,5e3,10e3,20e3,40e3,80e3,1e9]
    for a,b in zip(B,B[1:]): tab(f'opening ${a/1000:.0f}k-{b/1000:.0f}k',[c for c in g0 if c['open'] and a<=c['open']<b])
    M=collections.Counter(c['municipality'] for c in g0)
    for k,_ in M.most_common(12): tab('muni: '+k,[c for c in g0 if c['municipality']==k])
# cleared & postponed: what happens next
P=[c for c in CL if c['outcome']=='postponed']
C=collections.Counter()
for c in P:
    ch=[d for d in by[c['case_no']] if d['sale_date']>c['sale_date']]
    r='no later appearance'
    for d in ch:
        if d['outcome']!='postponed': r=d['outcome']; break
    else:
        if ch: r='still postponed'
    C[r]+=1
print('cleared-then-postponed, eventual:',C.most_common(), 'n',len(P))
print(' postponed how far:',sorted(collections.Counter(((c['pp_date'].year-c['sd'].year)*12+c['pp_date'].month-c['sd'].month) if c['pp_date'] else -1 for c in P).items()))
