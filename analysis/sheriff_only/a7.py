import sys,os;sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from base import *
rows,by,sales=load()
# order check
x=[c for c in rows if c['sale_date']=='2026-10-05']
print([c['sale_id'] for c in x[:12]],[c['sale_id'] for c in x[-8:]], [c['pdf_page'] for c in x[:5]],x[-1]['pdf_page'])
for c in rows: c['_i']=None
for sd in sales:
    cs=[c for c in rows if c['sale_date']==sd]
    for i,c in enumerate(cs): c['pos']=i/len(cs)
    au=[c for c in cs if c['auctioned']]
    for i,c in enumerate(au): c['apos']=i/len(au); c['arank']=i
print("== POSITION IN SALE (auctioned order tercile) ")
for T,sel in [('FC min bid',lambda c:c['grp']=='Tax lien, free & clear min bid'),('Tax lien other',lambda c:c['grp']=='Tax lien, other'),('MF',lambda c:c['grp']=='Mortgage foreclosure')]:
    for a,b in [(0,.25),(.25,.5),(.5,.75),(.75,1.01)]:
        g=[c for c in rows if c['auctioned'] and sel(c) and a<=c['apos']<b]
        s=[c for c in g if c['outcome']=='sold_3p' and not c['forf']]; r=[c['ratio'] for c in s if c['ratio']]
        print(f"  {T:15} quartile {a:.2f}-{b:.2f} auctioned {len(g):3} 3P {len(s):3} ({pct(len(s),len(g))}%) price med {med([c['price'] for c in s]) or 0:>8,.0f} ratio {med(r) or 0:.2f} at-open {pct(sum(1 for x in r if x<1.05),len(r))}% forf {pct(sum(1 for c in g if c['forf']),sum(1 for c in g if c['forf_checkable']))}")
print("== SALE SIZE vs competition")
pts=[]
for sd in sales:
    cs=[c for c in rows if c['sale_date']==sd]; au=[c for c in cs if c['auctioned']]
    s=[c for c in au if c['outcome']=='sold_3p' and not c['forf']]
    tl=[c['ratio'] for c in s if c['grp'] in('Tax lien, free & clear min bid','Tax lien, other') and c['ratio']]
    fc=[c['ratio'] for c in s if c['grp']=='Tax lien, free & clear min bid' and c['ratio']]
    mf=[c for c in au if c['grp']=='Mortgage foreclosure']
    pts.append((sd,len(au),len(s),len(tl),round(med(tl),2) if tl else None,round(med(fc),2) if fc else None,pct(sum(1 for x in tl if x<1.05),len(tl)),pct(sum(1 for c in mf if c['outcome']=='sold_3p'),len(mf)),sum(1 for c in au if c['forf'])))
for p in pts: print(p)
def corr(a,b):
    ab=[(x,y) for x,y in zip(a,b) if x is not None and y is not None]; n=len(ab); mx=sum(x for x,_ in ab)/n; my=sum(y for _,y in ab)/n
    sx=math.sqrt(sum((x-mx)**2 for x,_ in ab)); sy=math.sqrt(sum((y-my)**2 for _,y in ab)); return round(sum((x-mx)*(y-my) for x,y in ab)/(sx*sy),2)
print('corr(#auctioned, TL ratio)',corr([p[1] for p in pts],[p[4] for p in pts]),'corr(#TL sold, TL ratio)',corr([p[3] for p in pts],[p[4] for p in pts]),'corr(#auct, at-open%)',corr([p[1] for p in pts],[p[6] for p in pts]),'corr(#auct, MF 3P share)',corr([p[1] for p in pts],[p[7] for p in pts]))
print("== 3129.3 unchecked among 3P-sold, by type")
for g in ['Tax lien, free & clear min bid','Tax lien, other','Tax lien, decree','Mortgage foreclosure']:
    s=[c for c in rows if c['outcome']=='sold_3p' and c['grp']==g]; print(g,len(s),pct(sum(1 for c in s if not c['box_3129_3']),len(s)))
print("== FORFEIT re-sale, alt definition (next 3P sale of any kind)")
r=[]
for c in rows:
    if c['forf']:
        nx=[d for d in by[c['case_no']] if d['sale_date']>c['sale_date'] and d['outcome']=='sold_3p']
        if nx: r.append(nx[0]['price']/c['price'])
print(len(r),round(med(r),2), 'mean',round(sum(r)/len(r),2))
print("== given competition (ratio>=1.05), ratio")
for g in ['Tax lien, free & clear min bid','Tax lien, other']:
    r=[c['ratio'] for c in rows if c['outcome']=='sold_3p' and not c['forf'] and c['grp']==g and c['ratio'] and c['ratio']>=1.05]
    print(g,len(r),round(med(r),2),round(q(r,.25),2),round(q(r,.75),2),'over$ med',med([c['price']-c['open'] for c in rows if c['outcome']=='sold_3p' and not c['forf'] and c['grp']==g and c['ratio'] and c['ratio']>=1.05]))
print("== MF bank overbid/damages by half; MF 3P counts")
for h in sorted(set(c['half'] for c in rows)):
    ob=[c['price']/c['dmg'] for c in rows if c['half']==h and c['outcome']=='plaintiff_overbid' and c['dmg']]
    o2=[c['price'] for c in rows if c['half']==h and c['outcome']=='plaintiff_overbid']
    t=[c['price'] for c in rows if c['half']==h and c['outcome']=='sold_3p' and not c['forf'] and c['grp']=='Mortgage foreclosure']
    print(h,'overbid/dmg',round(med(ob),2) if ob else None,len(ob),'overbid med',med(o2),len(o2),'3P med',med(t),len(t))
print("== DECREE: 3P vs plaintiff took, by plaintiff")
D=[c for c in rows if c['grp']=='Tax lien, decree' and c['auctioned']]
print(len(D),collections.Counter(c['outcome'] for c in D)); print(collections.Counter((c['plaintiff'][:22],c['outcome']) for c in D).most_common(12))
print('decree below opening:',sum(1 for c in D if c['outcome']=='sold_3p' and c['ratio'] and c['ratio']<0.95), [ (c['price'],c['open'],c['comments'][:80].replace('\n','/')) for c in D if c['outcome']=='sold_3p' and c['ratio'] and c['ratio']<0.6][:5])
print("== total volume"); s=[c for c in rows if c['outcome']=='sold_3p' and not c['forf']]; print(len(s),round(sum(c['price'] for c in s)/1e6,1),'M; per sale',round(sum(c['price'] for c in s)/23/1e6,2))
print("== first-appearance 3P share by type"); 
for g in ['Tax lien, free & clear min bid','Tax lien, other','Tax lien, decree','Mortgage foreclosure']:
    n=[c for c in rows if c['docket_m']==0 and c['grp']==g]; print(g,len(n),pct(sum(1 for c in n if c['outcome']=='sold_3p'),len(n)))
