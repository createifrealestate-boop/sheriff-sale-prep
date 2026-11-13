import sys,os;sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from base import *
rows,by,sales=load()
S3=[c for c in rows if c['outcome']=='sold_3p' and not c['forf']]
TL=[c for c in rows if c['grp'].startswith('Tax lien')]
print("== TAX LIEN by plaintiff kind")
for k in set(c['pk'] for c in TL):
    g=[c for c in TL if c['pk']==k]; s=[c for c in g if c['outcome']=='sold_3p' and not c['forf']]
    r=[c['ratio'] for c in s if c['ratio']]
    print(f"{k:32} listings {len(g):4} completed3P {len(s):3} ({pct(len(s),len(g))}%) stayed {pct(sum(1 for c in g if c['outcome']=='stayed'),len(g))}% paid {pct(sum(1 for c in g if c['outcome']=='paid'),len(g))}% medprice {med([c['price'] for c in s]) or 0:,.0f} ratio {med(r) or 0:.2f} fcmin {sum(1 for c in s if c['minbid'])} decree {sum(1 for c in s if c['grp'].endswith('decree'))}")
print("== TAX LIEN by attorney")
P=collections.defaultdict(list)
for c in TL: P[(c['plaintiff_attorney'] or '')[:26]].append(c)
for k,g in sorted(P.items(),key=lambda kv:-len(kv[1]))[:14]:
    s=[c for c in g if c['outcome']=='sold_3p' and not c['forf']]; r=[c['ratio'] for c in s if c['ratio']]
    cases=len(set(c['case_no'] for c in g))
    print(f"{k:28} listings {len(g):4} cases {cases:4} 3P {len(s):3} ({pct(len(s),cases)}% of cases) medprice {med([c['price'] for c in s]) or 0:>8,.0f} ratio {med(r) or 0:.2f} at-open {pct(sum(1 for x in r if x<1.05),len(r))}% fcmin {sum(1 for c in s if c['minbid'])} decree {sum(1 for c in s if c['grp'].endswith('decree'))} forf {sum(1 for c in g if c['forf'])}")
print("== TAX LIEN top plaintiffs by completed 3P")
P=collections.defaultdict(list)
for c in TL: P[re.sub(r'\s+',' ',(c['plaintiff'] or '').upper().replace('BOROUGH OF WILKINSBURG','WILKINSBURG BOROUGH'))[:34]].append(c)
L=sorted(P.items(),key=lambda kv:-sum(1 for c in kv[1] if c['outcome']=='sold_3p' and not c['forf']))[:22]
for k,g in L:
    s=[c for c in g if c['outcome']=='sold_3p' and not c['forf']]; r=[c['ratio'] for c in s if c['ratio']]; cases=len(set(c['case_no'] for c in g))
    print(f"{k:36} cases {cases:4} 3P {len(s):3} ({pct(len(s),cases)}%) medprice {med([c['price'] for c in s]) or 0:>8,.0f} ratio {med(r) or 0:.2f} at-open {pct(sum(1 for x in r if x<1.05),len(r))}% fcmin {sum(1 for c in s if c['minbid'])} decree {sum(1 for c in s if c['grp'].endswith('decree'))} pl-took {sum(1 for c in g if c['outcome']=='plaintiff_costs')}")
print("== MUNICIPALITY (completed 3P >=10), residential")
M=collections.defaultdict(list)
for c in S3: M[c['municipality']].append(c)
allm=collections.Counter(c['municipality'] for c in rows if c['auctioned'])
f3=collections.Counter(c['municipality'] for c in rows if c['forf']); chk=collections.Counter(c['municipality'] for c in rows if c['forf_checkable'])
for k,g in sorted(M.items(),key=lambda kv:-len(kv[1])):
    if len(g)>=10:
        tl=[c for c in g if c['grp'].startswith('Tax') and not c['grp'].endswith('decree') and c['ratio']]; mf=[c for c in g if c['grp']=='Mortgage foreclosure']
        print(f"{k:22} 3P {len(g):3} of {allm[k]:3} auctioned ({pct(len(g),allm[k])}%) med {med([c['price'] for c in g]):>8,.0f} | taxlien n={len(tl):2} ratio {med([c['ratio'] for c in tl]) or 0:.2f} at-open {pct(sum(1 for c in tl if c['ratio']<1.05),len(tl))}% | MF n={len(mf):2} med {med([c['price'] for c in mf]) or 0:>8,.0f} | forfeit {f3[k]}/{chk[k]}")
print("== PITTSBURGH by zip (3P>=6)")
Z=collections.defaultdict(list)
for c in S3:
    if c['municipality']=='Pittsburgh': Z[c['zip']].append(c)
for k,g in sorted(Z.items(),key=lambda kv:-len(kv[1])):
    if len(g)>=6: print(k,len(g),'med',med([c['price'] for c in g]),'p25',q([c['price'] for c in g],.25),'p75',q([c['price'] for c in g],.75))
print("== CALENDAR MONTH (both years pooled)")
for m in range(1,13):
    g=[c for c in S3 if c['sd'].month==m]; a=[c for c in rows if c['sd'].month==m and c['auctioned']]; ns=len(set(c['sale_date'] for c in rows if c['sd'].month==m))
    tl=[c['ratio'] for c in g if c['grp'] in('Tax lien, other','Tax lien, free & clear min bid') and c['ratio']]
    mf=[c['price'] for c in g if c['grp']=='Mortgage foreclosure']
    print(m,'sales',ns,'3P/sale',round(len(g)/ns,1),'auct/sale',round(len(a)/ns,1),'TL ratio',round(med(tl),2),'n',len(tl),'MF med',med(mf),'at-open TL',pct(sum(1 for x in tl if x<1.05),len(tl)))
print("== OWNER TYPE (tax lien 3P)")
for o in set(c['owner_type'] for c in rows):
    g=[c for c in TL if c['owner_type']==o]; cases=len(set(c['case_no'] for c in g)); s=[c for c in g if c['outcome']=='sold_3p' and not c['forf']]
    r=[c['ratio'] for c in s if c['ratio'] and not c['grp'].endswith('decree')]
    print(o,'cases',cases,'3P',len(s),pct(len(s),cases),'med',med([c['price'] for c in s]),'ratio',round(med(r),2),'stayed',pct(sum(1 for c in g if c['outcome']=='stayed'),len(g)))
print("== multi-tract"); 
for t in (1,2,3):
    g=[c for c in S3 if (c['tracts'] or 1)==t or (t==3 and (c['tracts'] or 1)>=3)]; print(t,len(g),med([c['price'] for c in g]))
