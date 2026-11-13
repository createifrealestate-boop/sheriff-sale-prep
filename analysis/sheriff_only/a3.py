import sys,os;sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from base import *
rows,by,sales=load()
MF=[c for c in rows if c['grp']=='Mortgage foreclosure']
A=[c for c in MF if c['auctioned']]
print("== MORTGAGE: auctioned",len(A),collections.Counter(c['outcome'] for c in A))
ob=[c for c in A if c['outcome']=='plaintiff_overbid']; s3=[c for c in A if c['outcome']=='sold_3p' and not c['forf']]
print('overbid amount: med',med([c['price'] for c in ob]),'p25',q([c['price'] for c in ob],.25),'p75',q([c['price'] for c in ob],.75))
print('3P amount: med',med([c['price'] for c in s3]))
print('overbid ratio to opening: med',med([c['price']/c['open'] for c in ob if c['open']]))
# damages
for name,g in [('3P',s3),('plaintiff overbid',ob)]:
    d=[c for c in g if c['dmg']]
    r=[c['price']/c['dmg'] for c in d]
    print(name,'with reassessed damages',len(d),'of',len(g),'price/damages med',round(med(r),2),'p25',round(q(r,.25),2),'p75',round(q(r,.75),2),'damages med',med([c['dmg'] for c in d]), 'share price<damages',pct(sum(1 for x in r if x<1),len(r)),'share <0.5',pct(sum(1 for x in r if x<.5),len(r)))
# does reassessed damages predict 3P vs plaintiff?
for lab,cond in [('has reassessed damages',lambda c:bool(c['dmg'])),('no reassessed',lambda c:not c['dmg'])]:
    g=[c for c in A if cond(c)]; print(lab,len(g),'3P share',pct(sum(1 for c in g if c['outcome']=='sold_3p'),len(g)))
# FHA
for lab,pat in [('FHA',r'\bFHA\b'),('VA',r'\bVA\b'),('HUD',r'\bHUD\b'),('REVERSE',r'REVERSE')]:
    g=[c for c in A if re.search(pat,(c['comments'] or '').upper()+' '+(c['plaintiff'] or '').upper())]
    if g: print(lab,len(g),'3P share',pct(sum(1 for c in g if c['outcome']=='sold_3p'),len(g)),'med 3P price',med([c['price'] for c in g if c['outcome']=='sold_3p']))
# overbid amounts round? distribution of overbid vs damages bins
print('overbid price/damages distribution',collections.Counter(min(int((c['price']/c['dmg'])*10)/10,1.5) for c in ob if c['dmg']).most_common(20))
print('3P price/damages distribution',sorted(collections.Counter(min(int((c['price']/c['dmg'])*10)/10,1.5) for c in s3 if c['dmg']).items()))
# By plaintiff
def norm(p):
    u=re.sub(r'[^A-Z ]','',(p or '').upper()); u=re.sub(r'\b(NA|N A|LLC|INC|CORP|CORPORATION|COMPANY|CO|FSB|AS TRUSTEE.*|NOT IN ITS.*|TRUSTEE.*|SUCCESSOR.*|DBA.*|FKA.*|ET AL)\b.*','',u).strip()
    return ' '.join(u.split()[:3])
print("== MF by plaintiff (auctioned >=10)")
P=collections.defaultdict(list)
for c in A: P[norm(c['plaintiff'])].append(c)
L=[]
for k,g in P.items():
    if len(g)>=10:
        t=[c for c in g if c['outcome']=='sold_3p']; o=[c for c in g if c['outcome']=='plaintiff_overbid']
        L.append((pct(len(t),len(g)),k,len(g),len(t),med([c['price'] for c in t]) if t else None,med([c['price'] for c in o]) if o else None))
for x in sorted(L,reverse=True): print(x)
print("== MF by attorney (auctioned >=15)")
P=collections.defaultdict(list)
for c in A: P[(c['plaintiff_attorney'] or '')[:28]].append(c)
alln=collections.Counter((c['plaintiff_attorney'] or '')[:28] for c in MF)
for k,g in sorted(P.items(),key=lambda kv:-len(kv[1])):
    if len(g)>=15:
        t=[c for c in g if c['outcome']=='sold_3p']
        print(f"{k:30} listings {alln[k]:4} auctioned {len(g):3} ({pct(len(g),alln[k])}% of listings) 3P {len(t):3} ({pct(len(t),len(g))}%) med3P {med([c['price'] for c in t]) if t else 0:,.0f}")
print("== MF 3P share by half and by opening band, by owner type, by docket age")
for h in sorted(set(c['half'] for c in A)):
    g=[c for c in A if c['half']==h]; print(h,len(g),pct(sum(1 for c in g if c['outcome']=='sold_3p'),len(g)))
for o in set(c['owner_type'] for c in A):
    g=[c for c in A if c['owner_type']==o]; print(o,len(g),pct(sum(1 for c in g if c['outcome']=='sold_3p'),len(g)))
for a,b in [(0,1),(1,3),(3,6),(6,12),(12,999)]:
    g=[c for c in A if c['docket_m'] is not None and a<=c['docket_m']<b]; print('docket',a,b,len(g),pct(sum(1 for c in g if c['outcome']=='sold_3p'),len(g)))
# by municipality 3P share in MF
print("== plaintiff_costs cases: what are they"); pc=[c for c in rows if c['outcome']=='plaintiff_costs']; print(collections.Counter(c['grp'] for c in pc), collections.Counter(c['plaintiff'][:30] for c in pc).most_common(8))
