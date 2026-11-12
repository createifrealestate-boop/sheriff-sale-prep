"""Merge compact Zillow lines into an/zillow_hist.json.
Line: idx; zest; lo; hi; sqft; beds; baths; year; flags; comps(comma); matched   (flags: R renovated, A a comp anchors, S subject's own sale/listing anchors)
      idx; -            (no Zestimate displayed)      idx = index in todo3p.json (or 'p<idx>' for the plaintiff list)
"""
import json,sys,datetime
S='/tmp/claude-0/an/'
Z=json.load(open(S+'zillow_hist.json')); T=json.load(open(S+'todo3p.json'))
try: P=json.load(open(S+'todoP.json'))
except FileNotFoundError: P=[]
n=0
num=lambda v: None if v.strip() in('','-') else float(v) if '.' in v else int(v)
for line in open(sys.argv[1]):
    line=line.strip()
    if not line or line.startswith('#'): continue
    f=[x.strip() for x in line.split(';')]
    t=(P[int(f[0][1:])] if f[0].startswith('p') else T[int(f[0])]); k=t['key']
    if f[1]=='-': rec={'zestimate':None}
    else:
        rec={'zestimate':num(f[1]),'range_lo':num(f[2]),'range_hi':num(f[3]),'sqft':num(f[4]),'beds':num(f[5]),'baths':num(f[6]),'year_built':num(f[7]),
             'renovated':'R' in f[8],'anchored':'A' in f[8],'subject_anchored':'S' in f[8],
             'comp_sold':[int(x) for x in f[9].split(',') if x.strip()],'matched_address':f[10] if len(f)>10 else None}
        rec={a:b for a,b in rec.items() if b is not None}
        if len(f)>11 and f[11]: rec['subject_anchor_kind']=f[11]
        if len(f)>12 and f[12]:
            rec['last_sold_price']=int(f[12]); rec['last_sold_ago']=f[13] if len(f)>13 else None
            if f[11]=='sale': rec['subject_anchor_price']=int(f[12]); rec['subject_anchor_date']=rec['last_sold_ago']
    rec['fetched']=datetime.date.today().isoformat(); Z[k]=rec; n+=1
json.dump(Z,open(S+'zillow_hist.json','w'),separators=(',',':'),sort_keys=True)
print(n,'merged;',len(Z),'records;', sum(1 for t in T if t['key'] not in Z),'third-party lookups left')
