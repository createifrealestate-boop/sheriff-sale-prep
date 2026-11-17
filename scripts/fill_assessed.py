"""Fill county assessed value and transfer tax into state/crm.json for properties that don't have them yet
(new parcels fetched by fetch_assessed.py after the run that scored them). Used by the GitHub workflow right
before it sends crm.json to the CRM; the next scheduled run folds them into the score and MAOs too."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from deal import transfer_rate, transfer_tax  # noqa: E402

p = ROOT / "state" / "crm.json"
crm = json.load(open(p))
have = json.load(open(ROOT / "state" / "assessed.json")) if (ROOT / "state" / "assessed.json").exists() else {}
n = 0
for x in crm["properties"]:
    if x.get("assessed_value"):
        continue
    pid = (x.get("portal_parcel") or "").split(";")[0].strip().replace("-", "")
    rec = have.get(pid)
    if rec and rec.get("fmv"):
        x["assessed_value"] = rec["fmv"]
        x["transfer_rate"] = x.get("transfer_rate") or transfer_rate(x.get("tax_municipality"))
        x["transfer_tax"] = transfer_tax(rec["fmv"], x["transfer_rate"])
        n += 1
json.dump(crm, open(p, "w"), indent=1, default=str)
print(f"filled assessed value for {n} properties")
