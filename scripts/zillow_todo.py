"""List the OK-to-Sell / Almost-Ready cases that still need a Zillow lookup (not in cache or older than 45 days).
Usage: python3 -I zillow_todo.py classified.json zillow_cache.json   -> JSON list of {sale_id, key, query}
"""
import datetime as dt, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import cache_key, zillow_query

cases = json.load(open(sys.argv[1]))
cache = json.load(open(sys.argv[2])) if Path(sys.argv[2]).exists() else {}
today = dt.date.today()
todo = []
for c in cases:
    if c["bucket"] == "excluded":
        continue
    k = cache_key(c)
    rec = cache.get(k)
    if rec and (today - dt.date.fromisoformat(rec.get("fetched", "2000-01-01"))).days <= 45:
        continue
    todo.append({"sale_id": c["sale_id"], "key": k, "query": zillow_query(c)})
print(json.dumps(todo))
