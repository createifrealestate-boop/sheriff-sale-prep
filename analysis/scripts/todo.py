import json,sys
sys.path.insert(0,'/home/claude/sheriff-sale-prep/scripts')
from score import cache_key, zillow_query
cases=json.load(open('/tmp/claude-0/an/cases.json'))
cache=json.load(open('/home/claude/sheriff-sale-prep/state/zillow_cache.json'))
try: acache=json.load(open('/tmp/claude-0/an/zillow_hist.json'))
except FileNotFoundError: acache={}
want=[c for c in cases if c['outcome'] in('sold_3p','plaintiff_overbid','plaintiff_costs') and c.get('residential')]
seen={};
for c in want:
    k=cache_key(c)
    if k in cache or k in acache or k in seen: continue
    seen[k]={'key':k,'query':zillow_query(c),'outcome':c['outcome']}
todo=sorted(seen.values(),key=lambda t:(t['outcome']!='sold_3p',t['key']))
print(len(want),'auctioned residential;',len(todo),'need lookups;', sum(1 for t in todo if t['outcome']=='sold_3p'),'are 3rd-party sales')
json.dump(todo,open('/tmp/claude-0/an/todo.json','w'),indent=0)
for i in range(0,len(todo),45):
    json.dump(todo[i:i+45],open(f'/tmp/claude-0/an/todo_{i//45}.json','w'),indent=0)
print([t['query'] for t in todo[:5]])
