import sys,os;sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from base import *
import openpyxl
rows,by,sales=load()
wb=openpyxl.load_workbook(os.environ.get('PREP_XLSX',os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','state','2026-11-02.xlsx')),read_only=True)
D=list(wb['_Data'].iter_rows(values_only=True)); H=D[0]; D=[dict(zip(H,r)) for r in D[1:]]
print('meta',list(wb['_Meta'].iter_rows(values_only=True))[:8])
res={c['case_no']:c for c in rows if c['sale_date']=='2026-11-02'}
print("== NOV 2 PREP LIST (built Nov 1) vs RESULT")
for b in ['ok','almost','excluded']:
    g=[d for d in D if d['bucket']==b]
    C=collections.Counter((res[d['case_no']]['outcome'] if d['case_no'] in res else 'not in results') for d in g)
    print(b,len(g),C.most_common())
    if b!='excluded':
        for T in ['Tax','Mortgage']:
            gg=[d for d in g if d['case_no'] in res and res[d['case_no']]['grp'].startswith(T)]
            print('   ',T,len(gg),collections.Counter(res[d['case_no']]['outcome'] for d in gg).most_common())
ex=[d for d in D if d['bucket']=='excluded' and d['case_no'] in res and res[d['case_no']]['auctioned']]
print('excluded but auctioned:',[(d['bucket_reason'][:50],res[d['case_no']]['outcome'],res[d['case_no']]['property_type'][:12]) for d in ex])
print("== FC MIN BID: lead time before the sale")
L1=[];L2=[]
for c in rows:
    if c['outcome']=='sold_3p' and c['grp']=='Tax lien, free & clear min bid':
        prev=[d for d in by[c['case_no']] if d['sale_date']<c['sale_date']]
        a=[d for d in prev if d['fc_token']]; b=[d for d in prev if d['minbid']]
        i=sales.index(c['sale_date'])
        L1.append(i-sales.index(a[0]['sale_date']) if a else 0); L2.append(i-sales.index(b[0]['sale_date']) if b else 0)
        c['_prevn']=len(prev)
print(len(L1),'F/C mentioned at an earlier sale: ',pct(sum(1 for x in L1 if x>0),len(L1)),'% ; months before (if any) median',med([x for x in L1 if x>0]))
print('min bid already stated at an earlier sale:',pct(sum(1 for x in L2 if x>0),len(L2)),'%', sorted(collections.Counter(L2).items()))
print('on the list at an earlier sale in window:',pct(sum(1 for c in rows if c.get('_prevn')),len(L1)))
# state of the row one sale before an FC 3P sale
C=collections.Counter()
for c in rows:
    if c['outcome']=='sold_3p' and c['grp']=='Tax lien, free & clear min bid' and c['prev']:
        p=c['prev']; U=(p['comments'] or '').upper()
        C['prev: '+('min bid stated' if p['minbid'] else 'F/C mentioned' if p['fc_token'] else 'NEED O/C' if 'NEED O/C' in U else 'no F/C hint')+(' | forfeited' if p['outcome']=='sold_3p' else '')]+=1
print(C.most_common())
print("== competitive wins: bid endings")
E=collections.Counter()
for c in rows:
    if c['outcome']=='sold_3p' and not c['forf'] and c['ratio'] and c['ratio']>=1.05:
        p=c['price']; E['x,000' if p%1000==0 else 'x,500' if p%500==0 else 'x,100' if p%1000==100 else 'other hundreds' if p%100==0 else 'odd']+=1
n=sum(E.values()); print(n,{k:pct(v,n) for k,v in E.most_common()})
print("== NEW LISTINGS per sale by half (docket_m==0)")
for h in sorted(set(c['half'] for c in rows)):
    ns=len(set(c['sale_date'] for c in rows if c['half']==h))
    print(h,'tax',round(sum(1 for c in rows if c['half']==h and c['docket_m']==0 and c['grp'].startswith('Tax'))/ns,1),'mortgage',round(sum(1 for c in rows if c['half']==h and c['docket_m']==0 and c['grp']=='Mortgage foreclosure')/ns,1),'3P per sale',round(sum(1 for c in rows if c['half']==h and c['outcome']=='sold_3p' and not c['forf'])/ns,1),'auctioned/sale',round(sum(1 for c in rows if c['half']==h and c['auctioned'])/ns,1))
print("== ESTATE check: defendants sample"); print([c['defendant'][:40] for c in rows if c['owner_type'].startswith('Estate') and c['outcome']=='sold_3p'][:8])
print("== tax-lien cases outcome by owner type & plaintiff County vs others (cases)")
for o in ['Individual','Estate / heirs / trust','Entity (LLC/LP/Inc)']:
    for pk in ['Allegheny County','School district','Borough / township / authority']:
        cs=[v for v in by.values() if v[0]['grp'].startswith('Tax') and v[0]['owner_type']==o and v[0]['pk']==pk]
        s=sum(1 for v in cs if any(c['outcome']=='sold_3p' and not c['forf'] for c in v))
        print(o,'|',pk,len(cs),pct(s,len(cs)))
