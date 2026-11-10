import json,re,glob,collections
from datetime import datetime
rows=[]
for f in sorted(set(g for g in glob.glob('/tmp/claude-0/res/*Results*.json') if not g.endswith('.meta.json'))):
    if f.endswith('.meta.json'): continue
    meta=json.load(open(f.replace('.json','.meta.json')))
    sd=datetime.strptime(meta['date_of_sale'].split(', ',1)[1],'%B %d, %Y').date().isoformat()
    for c in json.load(open(f)):
        c['sale_date']=sd; rows.append(c)
print(len(rows), sorted(set(r['sale_date'] for r in rows)))
st=collections.Counter(re.sub(r'[\d/,\$\.]+','#',(c['status'] or ''))[:40] for c in rows)
for k,v in st.most_common(40): print(v,repr(k))
json.dump(rows,open('/tmp/claude-0/an/all_raw.json','w'))
