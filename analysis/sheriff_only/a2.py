import sys,os;sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from base import *
rows,by,sales=load()
S3=[c for c in rows if c['outcome']=='sold_3p' and not c['forf']]
G=['Tax lien, free & clear min bid','Tax lien, other','Tax lien, decree','Mortgage foreclosure','HOA / condo']
def line(name,g):
    go=[c for c in g if c['ratio']]
    pr=[c['price'] for c in g]
    r=[c['ratio'] for c in go]
    if not g: return
    print(f"{name:32} n={len(g):4} price med {med(pr):>9,.0f} p25 {q(pr,.25):>8,.0f} p75 {q(pr,.75):>9,.0f} | open med {med([c['open'] for c in go]) or 0:>8,.0f} | ratio med {med(r) or 0:5.2f} p25 {q(r,.25) or 0:5.2f} p75 {q(r,.75) or 0:5.2f} | at-open(<1.05) {pct(sum(1 for x in r if x<1.05),len(r))}% >2x {pct(sum(1 for x in r if x>2),len(r))}% >5x {pct(sum(1 for x in r if x>5),len(r))}% | over-open med ${med([c['price']-c['open'] for c in go]) or 0:,.0f}")
print("== PRICES BY TYPE (completed 3P sales)"); 
for g in G: line(g,[c for c in S3 if c['grp']==g])
line('ALL',S3)
print("== residential only")
for g in G: line(g,[c for c in S3 if c['grp']==g and c.get('residential')])
print("== by property type"); 
for t,n in collections.Counter(c['property_type'] for c in S3).most_common(8): line(t[:32],[c for c in S3 if c['property_type']==t])
print("== price bands (all completed 3P)")
B=[0,10e3,25e3,50e3,75e3,100e3,150e3,250e3,1e9]
for a,b in zip(B,B[1:]):
    g=[c for c in S3 if a<=c['price']<b]; print(f"  ${a/1000:.0f}k-{b/1000:.0f}k: {len(g)} ({pct(len(g),len(S3))}%)", collections.Counter(c['grp'][:14] for c in g).most_common(4))
print("== BY OPENING-BID BAND: what price wins")
OB=[0,3e3,6e3,10e3,20e3,40e3,80e3,1e9]
for g in ['Tax lien, free & clear min bid','Tax lien, other','Mortgage foreclosure']:
    print(g)
    for a,b in zip(OB,OB[1:]):
        x=[c for c in S3 if c['grp']==g and c['open'] and a<=c['open']<b]
        if len(x)>=5: line(f"  open ${a/1000:.0f}k-{b/1000:.0f}k",x)
print("== HALF-YEAR TREND")
for h in sorted(set(c['half'] for c in rows)):
    print(h, 'sales',len(set(c['sale_date'] for c in rows if c['half']==h)))
    for g in G[:4]+['ALL']:
        line('  '+g,[c for c in S3 if c['half']==h and (g=='ALL' or c['grp']==g)])
print("== bid endings")
E=collections.Counter()
for c in S3:
    p=c['price']; 
    k='cents' if p!=int(p) else 'x,000' if p%1000==0 else 'x,500' if p%500==0 else 'x,100' if p%100==0 else 'ends 1 (e.g. 50,001)' if p%100==1 else 'other odd'
    E[k]+=1
print(E.most_common())
print('min increments: differences within small ratios?')
# cents cases = likely exactly opening bid
print('cents & at-open:',sum(1 for c in S3 if c['price']!=int(c['price']) and c['ratio'] and c['ratio']<1.05), 'cents total',E['cents'])
print("== CASH NEEDED percentiles (residential 3P)"); pr=[c['price'] for c in S3 if c.get('residential')]
print(len(pr),[round(q(pr,p)) for p in(.1,.25,.5,.75,.9)], 'under 25k',pct(sum(1 for x in pr if x<25e3),len(pr)),'under 50k',pct(sum(1 for x in pr if x<50e3),len(pr)),'under 100k',pct(sum(1 for x in pr if x<100e3),len(pr)))
