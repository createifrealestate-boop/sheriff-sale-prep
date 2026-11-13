import sys,os;sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from base import *
rows,by,sales=load()
S3all=[c for c in rows if c['outcome']=='sold_3p']; S3=[c for c in S3all if not c['forf']]
print("== OK-TO-SELL lead time (days before sale of the latest OK/ALL DOCS date <= sale date)")
for name,g in [('3P sold',S3all),('plaintiff took',[c for c in rows if c['outcome'] in('plaintiff_overbid','plaintiff_costs')])]:
    for T in ['Tax','Mortgage']:
        L=[]
        gg=[c for c in g if c['grp'].startswith(T)]
        for c in gg:
            ds=[d for d in c['ok_dates'] if d<=c['sd'] and (c['sd']-d).days<200]
            if ds: L.append((c['sd']-max(ds)).days)
        if L: print(name,T,'n with date',len(L),'of',len(gg),'median',med(L),'p25',q(L,.25),'p75',q(L,.75),'<=3d',pct(sum(1 for x in L if x<=3),len(L)),'<=7d',pct(sum(1 for x in L if x<=7),len(L)),'<=14d',pct(sum(1 for x in L if x<=14),len(L)),'>30d',pct(sum(1 for x in L if x>30),len(L)))
# weekday/time distribution of leads
L=[]
for c in S3all:
    ds=[d for d in c['ok_dates'] if d<=c['sd'] and (c['sd']-d).days<200]
    if ds: L.append((c['sd']-max(ds)).days)
print('lead histogram (days):',sorted(collections.Counter(min(x,40) for x in L).items()))
print("== boxes on 3P-sold rows:",collections.Counter((c['box_service'],c['box_3129_2'],c['box_3129_3'],c['box_ok']) for c in S3all).most_common(6))
print("== FORFEITS")
chk=[c for c in S3all if c['forf_checkable']]; F=[c for c in chk if c['forf']]
print('checkable',len(chk),'forfeit',len(F),pct(len(F),len(chk)))
for g in ['Tax lien, free & clear min bid','Tax lien, other','Tax lien, decree','Mortgage foreclosure']:
    a=[c for c in chk if c['grp']==g]; print(' ',g,len(a),pct(sum(1 for c in a if c['forf']),len(a)))
B=[0,10e3,25e3,50e3,100e3,1e9]
for a,b in zip(B,B[1:]):
    x=[c for c in chk if a<=c['price']<b]; print(f'  price {a/1000:.0f}-{b/1000:.0f}k',len(x),pct(sum(1 for c in x if c['forf']),len(x)))
for lo,hi in [(0,1.05),(1.05,2),(2,5),(5,10),(10,999)]:
    x=[c for c in chk if c['ratio'] and lo<=c['ratio']<hi]; print(f'  ratio {lo}-{hi}',len(x),pct(sum(1 for c in x if c['forf']),len(x)))
for h in sorted(set(c['half'] for c in chk)):
    x=[c for c in chk if c['half']==h]; print(' ',h,len(x),pct(sum(1 for c in x if c['forf']),len(x)))
# what happens next
nx=collections.Counter(); gaps=[]; rel=[]; nf=collections.Counter()
for c in F:
    chain=[d for d in by[c['case_no']] if d['sale_date']>c['sale_date']]
    n=c['next']; nx[n['outcome']]+=1; gaps.append(si:=sales.index(n['sale_date'])-sales.index(c['sale_date']))
    fin=None
    for d in chain:
        if d['outcome'] in('sold_3p','plaintiff_overbid','plaintiff_costs','stayed','paid'): fin=d
        if d['outcome']=='sold_3p' and not d['forf']: break
    last=chain[-1]
    nf['resold 3P (completed)' if any(d['outcome']=='sold_3p' and not d['forf'] for d in chain) else 'plaintiff' if any(d['outcome'].startswith('plaintiff') for d in chain) else 'stayed' if last['outcome']=='stayed' else 'still re-listing/forfeited again']+=1
    r=[d for d in chain if d['outcome']=='sold_3p' and not d['forf']]
    if r: rel.append((r[0]['price']/c['price'], r[0]['price']-c['price'], sales.index(r[0]['sale_date'])-sales.index(c['sale_date']), c['grp']))
print(' next appearance:',nx.most_common(),' months to next appearance',sorted(collections.Counter(gaps).items()))
print(' eventual:',nf.most_common())
print(' completed re-sale vs forfeited bid: n',len(rel),'median ratio',round(med([x[0] for x in rel]),2),'p25',round(q([x[0] for x in rel],.25),2),'p75',round(q([x[0] for x in rel],.75),2),'lower',pct(sum(1 for x in rel if x[0]<0.98),len(rel)),'same',pct(sum(1 for x in rel if .98<=x[0]<=1.02),len(rel)),'higher',pct(sum(1 for x in rel if x[0]>1.02),len(rel)),'median $ change',med([x[1] for x in rel]),'months',med([x[2] for x in rel]))
for g in ['Tax lien, free & clear min bid','Tax lien, other','Tax lien, decree','Mortgage foreclosure']:
    x=[r for r in rel if r[3]==g]
    if x: print('   ',g,len(x),round(med([r[0] for r in x]),2))
multi=collections.Counter(sum(1 for d in cs if d['forf']) for cs in by.values()); print(' cases by # forfeits',sorted(multi.items()))
# forfeit notes on re-listed rows: FORFEITED date
print("== at re-auction, was FORF in the notes?")
n=m=0
for c in F:
    d=c['next']; n+=1; m+=bool(re.search(r'FORF',(d['comments'] or '').upper()))
print(m,'of',n)
print("== FREE & CLEAR: how much lien is wiped")
fc=[c for c in S3 if c['minbid'] and c.get('cost_tax_bid')]
print(len(fc),'min bid med',med([c['minbid'] for c in fc]),'cost&tax med',med([c['cost_tax_bid'] for c in fc]),'min/C&T med',round(med([c['minbid']/c['cost_tax_bid'] for c in fc]),2),'price/C&T med',round(med([c['price']/c['cost_tax_bid'] for c in fc]),2),'price<C&T',pct(sum(1 for c in fc if c['price']<c['cost_tax_bid']),len(fc)))
print(' min bid common values',collections.Counter(c['minbid'] for c in fc).most_common(10))
print("== BUYERS named in notes (deeded)")
B=collections.Counter(); ent=0; tot=0
for c in rows:
    m=re.search(r'DEEDED TO\s+(.+?)(?:\.\s*\d|\s+\d{3}[-. ]\d{3}|\n|$)',(c['comments'] or '').upper())
    if m:
        nm=re.sub(r'[.,]+$','',m.group(1).strip()); B[nm]+=1; tot+=1; ent+=bool(re.search(r'LLC|INC|CORP|\bLP\b|TRUST|PROPERTIES|INVEST|DEVELOP|HOLDINGS|CAPITAL|GROUP|COMPANY|\bCO\b|RENTAL|REALTY|HOMES',nm))
print(tot,'entity-like',ent,'repeat buyers',[(k if re.search(r'LLC|INC|CORP|CO\b|TRUST',k) else 'individual',v) for k,v in B.items() if v>1])
extra=collections.Counter()
for c in rows:
    m=re.search(r'PAID IN \$?[\d,. ]+?(?:AND|&|PLUS)\s*\$([\d,.]+\d)',(c['comments'] or '').upper())
    if m: extra[m.group(1)]+=1
print(' extra fee amounts',extra.most_common(5))
print("== STAYED / PAID"); 
st_=[c for c in rows if c['outcome']=='stayed']; print('stayed rows',len(st_),'cases',len(set(c['case_no'] for c in st_)),'reappear later',sum(1 for c in st_ if c['next'] is not None))
print(' after stay next outcomes',collections.Counter(c['next']['outcome'] for c in st_ if c['next']).most_common())
