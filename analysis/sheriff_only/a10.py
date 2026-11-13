import sys,os;sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from base import *
import openpyxl
rows,by,sales=load()
wb=openpyxl.load_workbook(os.environ.get('PREP_XLSX',os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','state','2026-11-02.xlsx')),read_only=True)
D=list(wb['_Data'].iter_rows(values_only=True)); H=D[0]; D=[dict(zip(H,r)) for r in D[1:]]
res={c['case_no']:c for c in rows if c['sale_date']=='2026-11-02'}
ok=[d for d in D if d['bucket']=='ok' and d['case_no'] in res]
print(collections.Counter(d['bucket_reason'] for d in ok))
def tab(name,g):
    C=collections.Counter(res[d['case_no']]['outcome'] for d in g); n=len(g)
    if n: print(f"  {name:40} n={n:3}",C.most_common())
tab('3129.3 open on Oct 30 list',[d for d in ok if '3129.3' in (d['bucket_reason'] or '')])
tab('3129.3 done on Oct 30 list',[d for d in ok if '3129.3' not in (d['bucket_reason'] or '')])
for T in ['Tax','Mortgage']:
    for lab,f in [('3129.3 open',lambda d:'3129.3' in (d['bucket_reason'] or '')),('3129.3 done',lambda d:'3129.3' not in (d['bucket_reason'] or ''))]:
        tab(T+' '+lab,[d for d in ok if f(d) and res[d['case_no']]['grp'].startswith(T)])
for g in ['Tax lien, free & clear min bid','Tax lien, decree','Tax lien, other']:
    tab(g,[d for d in ok if res[d['case_no']]['grp']==g])
tab('estate',[d for d in ok if res[d['case_no']]['owner_type'].startswith('Estate')])
tab('flag forfeited',[d for d in ok if 'forfeit' in (d['flags'] or '').lower()])
