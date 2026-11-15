"""The current prep list by area, against each area's history (muni_stats.json from area.py)."""
import sys, os, json, collections
AH = os.path.dirname(os.path.abspath(__file__))
ST = {x["name"]: x for x in json.load(open(os.path.join(AH, "muni_stats.json")))}
props = json.load(open(os.path.join(AH, "..", "..", "state", "crm.json")))["properties"]
M = collections.defaultdict(list)
for p in props: M[p["municipality"]].append(p)
for k, g in sorted(M.items(), key=lambda kv: -len(kv[1])):
    s = ST.get(k, {})
    print(f"{k:18} on list {len(g):2} (OK {sum(1 for p in g if p['bucket']=='ok')}, tax {sum(1 for p in g if 'Tax' in p['sale_category'])}, High {sum(1 for p in g if p.get('sell_label')=='High')}, Med {sum(1 for p in g if p.get('sell_label')=='Medium')}) | history: {s.get('n')} purchases, median ${s.get('price') or 0:,.0f}, tl x{s.get('tl_ratio')}, cleared->auction {s.get('cleared_auct')}%, bank loses {s.get('mf_outside')}%, forf {s.get('forf')}, price/value {s.get('pv')}")
print(len(props), len(M))
