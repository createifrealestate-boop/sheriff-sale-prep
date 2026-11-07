"""Merge Zillow records into the cache. Usage: zcache_add.py cache.json records.json  (records: {key: {...}})"""
import datetime as dt, json, sys
from pathlib import Path
p = Path(sys.argv[1]); cache = json.load(open(p)) if p.exists() else {}
new = json.load(open(sys.argv[2]))
for k, v in new.items():
    v.setdefault("fetched", dt.date.today().isoformat()); cache[k] = v
json.dump(cache, open(p, "w"), separators=(",", ":"), sort_keys=True)
print(len(cache), "records")
