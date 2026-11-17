"""Fetch county assessed values for the prep-list parcels from WPRDC (Allegheny County Property Assessments).

Run by the GitHub workflow (this workspace's network can't reach WPRDC). Reads state/crm.json, looks up parcels
not yet in state/assessed.json (or older than 120 days), and writes state/assessed.json:
  {PARID: {"fmv": FAIRMARKETTOTAL, "county": COUNTYTOTAL, "muni": MUNIDESC, "school": SCHOOLDESC, "fetched": date}}
The transfer tax on a sheriff deed uses the full assessed value (fmv) x CLR x rates (scripts/deal.py).

Usage: python3 scripts/fetch_assessed.py [--all]
"""
import datetime as dt, json, sys, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = "65855e14-549e-4992-b5be-d629afc676fa"  # Property Assessments Parcel Data (API version)
API = "https://data.wprdc.org/api/3/action/datastore_search_sql?sql="


def parids(props):
    out = []
    for p in props:
        pp = (p.get("portal_parcel") or "").split(";")[0].strip()
        if pp and pp[0].isdigit():
            out.append(pp.replace("-", ""))
    return sorted(set(out))


def fetch(ids):
    got = {}
    for i in range(0, len(ids), 50):
        chunk = [x for x in ids[i:i + 50] if x.isalnum()]
        sql = (f'SELECT "PARID","FAIRMARKETTOTAL","COUNTYTOTAL","MUNIDESC","SCHOOLDESC" FROM "{RES}" '
               f'WHERE "PARID" IN ({",".join(repr(x) for x in chunk)})')
        with urllib.request.urlopen(API + urllib.parse.quote(sql), timeout=60) as r:
            for rec in json.load(r)["result"]["records"]:
                got[rec["PARID"]] = {"fmv": rec["FAIRMARKETTOTAL"], "county": rec["COUNTYTOTAL"],
                                     "muni": rec["MUNIDESC"], "school": rec["SCHOOLDESC"],
                                     "fetched": dt.date.today().isoformat()}
    return got


def main():
    path = ROOT / "state" / "assessed.json"
    have = json.load(open(path)) if path.exists() else {}
    props = json.load(open(ROOT / "state" / "crm.json"))["properties"]
    today = dt.date.today()
    need = [x for x in parids(props) if "--all" in sys.argv or x not in have
            or (today - dt.date.fromisoformat(have[x].get("fetched", "2000-01-01"))).days > 120]
    if not need:
        print("assessed values: nothing to fetch"); return
    got = fetch(need)
    have.update(got)
    json.dump(dict(sorted(have.items())), open(path, "w"), indent=1)
    print(f"assessed values: fetched {len(got)} of {len(need)} parcels")


if __name__ == "__main__":
    if not json.load(open(ROOT / "reference" / "deal_model.json")).get("include_transfer_tax", True):
        print("transfer tax is off in reference/deal_model.json; skipping"); sys.exit(0)
    main()
