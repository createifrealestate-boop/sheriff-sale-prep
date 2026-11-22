"""Fetch county assessed values for the prep-list parcels from WPRDC (Allegheny County Property Assessments).

Run by the GitHub workflow (this workspace's network can't reach WPRDC). Reads state/crm.json, looks up parcels
not yet in state/assessed.json (or older than 120 days), and writes state/assessed.json:
  {PARID: {"fmv": FAIRMARKETTOTAL, "county": COUNTYTOTAL, "muni": MUNIDESC, "school": SCHOOLDESC, "fetched": date}}
Used for each property's real-estate tax in the cash flow (scripts/deal.py property_tax, reference/millage.json)
and, when switched on, the sheriff-deed transfer tax.

Usage: python3 scripts/fetch_assessed.py [--all]
"""
import datetime as dt, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = "65855e14-549e-4992-b5be-d629afc676fa"  # Property Assessments Parcel Data (API version)
API = "https://data.wprdc.org/api/3/action/datastore_search"


def parids(props):
    out = []
    for p in props:
        pp = (p.get("portal_parcel") or "").split(";")[0].strip()
        if pp and pp[0].isdigit():
            out.append(pp.replace("-", ""))
    return sorted(set(out))


def fetch(ids):
    """WPRDC's SQL endpoint now refuses requests, so this uses datastore_search with a PARID filter (via curl,
    which the site accepts where Python's own client gets a 403)."""
    got = {}
    for i in range(0, len(ids), 20):
        chunk = [x for x in ids[i:i + 20] if x.isalnum()]
        out = subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", "-G", API,
                              "--data-urlencode", "resource_id=" + RES, "--data-urlencode", "limit=1000",
                              "--data-urlencode", "filters=" + json.dumps({"PARID": chunk})],
                             capture_output=True, text=True, check=True).stdout
        for rec in json.loads(out)["result"]["records"]:
            got[rec["PARID"]] = {"fmv": rec["FAIRMARKETTOTAL"], "county": rec["COUNTYTOTAL"],
                                 "land": rec["FAIRMARKETLAND"], "bldg": rec["FAIRMARKETBUILDING"],
                                 "lot": rec.get("LOTAREA") or None, "cond": (rec.get("CONDITIONDESC") or "").strip() or None,
                                 "muni": (rec["MUNIDESC"] or "").strip(), "school": (rec["SCHOOLDESC"] or "").strip(),
                                 "fetched": dt.date.today().isoformat()}
    return got


def main():
    path = ROOT / "state" / "assessed.json"
    have = json.load(open(path)) if path.exists() else {}
    props = json.load(open(ROOT / "state" / "crm.json"))["properties"]
    today = dt.date.today()
    need = [x for x in parids(props) if "--all" in sys.argv or x not in have or "lot" not in have[x] or "cond" not in have[x]
            or (today - dt.date.fromisoformat(have[x].get("fetched", "2000-01-01"))).days > 120]
    if not need:
        print("assessed values: nothing to fetch"); return
    got = fetch(need)
    have.update(got)
    json.dump(dict(sorted(have.items())), open(path, "w"), indent=1)
    print(f"assessed values: fetched {len(got)} of {len(need)} parcels")


if __name__ == "__main__":
    main()
