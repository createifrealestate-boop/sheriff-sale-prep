import sys,os;sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from base import *
rows,by,sales=load()
per=collections.defaultdict(collections.Counter)
for c in rows:
    m=re.search(r'DEEDED TO\s+(.+?)(?:\.\s*\d|\s+\d{3}[-. ]\d{3}|\n|$)',(c['comments'] or '').upper())
    if m: per[c['sale_date']][re.sub(r'[.,]+$','',m.group(1).strip())]+=1
for s,C in per.items():
    n3=sum(1 for c in rows if c['sale_date']==s and c['outcome']=='sold_3p')
    print(s,'named',sum(C.values()),'of',n3,'3P; distinct buyers',len(C),'top',[(k if re.search(r'LLC|INC|CORP|\bCO\b|TRUST|ENTERPRISES',k) else 'an individual',v) for k,v in C.most_common(3)])
# named buyers: price vs type
nb=[c for c in rows if 'DEEDED TO' in (c['comments'] or '').upper()]
print(collections.Counter(c['grp'] for c in nb), med([c['price'] for c in nb if c['price']]))
pp=[c for c in nb if 'PENN PIONEER' in c['comments'].upper()]
print('Penn Pioneer:',[(c['municipality'],c['price'],c['grp'][:12]) for c in pp])
# stays by type share of cases
for T in ['Tax','Mortgage']:
    cs=[v for v in by.values() if v[0]['grp'].startswith(T)]
    print(T,len(cs),'final stayed',pct(sum(1 for v in cs if v[-1]['outcome']=='stayed'),len(cs)),'paid',pct(sum(1 for v in cs if v[-1]['outcome']=='paid'),len(cs)))
# residential count in S3
S3=[c for c in rows if c['outcome']=='sold_3p' and not c['forf']]
print('completed 3P',len(S3),'residential',sum(1 for c in S3 if c.get('residential')), 'all 3P rows',sum(1 for c in rows if c['outcome']=='sold_3p'))
# tax lien other: by opening relative - sells at opening or small over
