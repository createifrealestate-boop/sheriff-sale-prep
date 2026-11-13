import sys,os;sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from base import *
rows,by,sales=load()
print("== 1. FUNNEL BY TYPE (row = one case at one sale)")
T=collections.defaultdict(collections.Counter)
for c in rows:
    g='Tax lien' if c['grp'].startswith('Tax') else c['grp']
    T[g][c['outcome']]+=1; T['ALL'][c['outcome']]+=1
for g,C in T.items():
    n=sum(C.values()); a=C['sold_3p']+C['plaintiff_overbid']+C['plaintiff_costs']+C['unsold']
    print(f"{g:22} n={n:5} postponed {pct(C['postponed'],n)}% stayed {pct(C['stayed'],n)}% paid {pct(C['paid'],n)}% auctioned {pct(a,n)}% | of auctioned: 3P {pct(C['sold_3p'],a)}% plaintiff-overbid {pct(C['plaintiff_overbid'],a)}% plaintiff-costs {pct(C['plaintiff_costs'],a)}% unsold {C['unsold']}")
print("== 2. MONTHLY")
for sd in sales:
    cs=[c for c in rows if c['sale_date']==sd]; s3=[c for c in cs if c['outcome']=='sold_3p']
    a=[c for c in cs if c['auctioned']]
    print(sd,len(cs),'auct',len(a),'3P',len(s3),'pl',len(a)-len(s3),'med3P',round(med([c['price'] for c in s3])),'vol$k',round(sum(c['price'] for c in s3)/1000),'stayed',sum(1 for c in cs if c['outcome']=='stayed'),'paid',sum(1 for c in cs if c['outcome']=='paid'),'new',sum(1 for c in cs if c['docket_m']==0))
print("== 3. LIFECYCLE of distinct cases")
fin=collections.Counter(); apps=collections.Counter()
for k,cs in by.items():
    last=cs[-1]; o=last['outcome']
    if o=='postponed' and last['sale_date']!=sales[-1]: o='dropped off after postponement'
    elif o=='postponed': o='still pending (Nov 2026)'
    fin[o]+=1; apps[min(len(cs),10)]+=1
n=len(by)
for k,v in fin.most_common(): print(f"  {k:35} {v:5} {pct(v,n)}%")
print(' appearances:',sorted(apps.items()))
# ever sold to 3P (completed) / ever plaintiff
ever3=sum(1 for cs in by.values() if any(c['outcome']=='sold_3p' and not c['forf'] for c in cs))
everp=sum(1 for cs in by.values() if any(c['outcome'] in('plaintiff_overbid','plaintiff_costs') for c in cs))
print('distinct cases',n,'ever completed 3P',ever3,pct(ever3,n),'ever plaintiff',everp,pct(everp,n))
# cohort: cases whose first listing is inside window with >=12 months follow-up
print("== 3b. COHORT first listed Jan-Nov 2025 (>=12 months follow-up)")
for g in ['Mortgage foreclosure','Tax lien','ALL']:
    co=[cs for cs in by.values() if cs[0]['docket_m']==0 and cs[0]['sale_date']<'2025-12-01' and (g=='ALL' or cs[0]['grp'].startswith(g))]
    C=collections.Counter(); tt=[]
    for cs in co:
        res=None
        for c in cs:
            if c['outcome']=='sold_3p' and not c['forf']: res='3P'; tt.append(c['app_i']); break
            if c['outcome'] in('plaintiff_overbid','plaintiff_costs'): res='plaintiff'; break
            if c['outcome']=='stayed': res='stayed'; break
            if c['outcome']=='paid': res='paid'; break
        if res is None: res='still postponed' if cs[-1]['sale_date']==sales[-1] else 'dropped off list'
        C[res]+=1
    print(g,len(co),{k:f"{v} ({pct(v,len(co))}%)" for k,v in C.most_common()})
print("== 3c. First appearance outcome for new listings (docket_m==0)")
C=collections.Counter(c['outcome'] for c in rows if c['docket_m']==0); n=sum(C.values()); print(n,{k:pct(v,n) for k,v in C.most_common()})
print("== 3d. How old is the listing when it sells to 3P (months since first listed, from sale number)")
for g in ['Mortgage foreclosure','Tax lien, free & clear min bid','Tax lien, other','Tax lien, decree']:
    d=[c['docket_m'] for c in rows if c['outcome']=='sold_3p' and not c['forf'] and c['grp']==g and c['docket_m'] is not None]
    print(g,len(d),'median',med(d),'p25',q(d,.25),'p75',q(d,.75),'first-time',pct(sum(1 for x in d if x==0),len(d)),'<=3m',pct(sum(1 for x in d if x<=3),len(d)),'>12m',pct(sum(1 for x in d if x>12),len(d)),'>36m',pct(sum(1 for x in d if x>36),len(d)))
