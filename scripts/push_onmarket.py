"""Send state/onmarket/crm.json to the CRM's On-Market page (Base44 function ingestMarketListings).
Only listings that changed since the last successful push are sent (state/onmarket/pushed.json keeps a hash per
listing), in chunks of 120 a minute apart (Base44 allows 140 record updates a minute), plus the full list of listing ids so the CRM can retire ones that dropped off.
Run by .github/workflows/onmarket.yml. Env: CRM_API_KEY. Usage: python3 scripts/push_onmarket.py [--all]"""
import hashlib, json, os, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ST = ROOT / "state" / "onmarket"
URL = os.environ.get("CRM_ONMARKET_URL") or "https://create-if-crm.base44.app/api/apps/6a672f8ccee4376a8dfd5387/functions/ingestMarketListings"
key = os.environ.get("CRM_API_KEY", "").strip()
if not key:
    print("::notice::CRM_API_KEY secret not set; skipping the CRM update.")
    sys.exit(0)

payload = json.load(open(ST / "crm.json"))
pushed = {} if "--all" in sys.argv else (json.load(open(ST / "pushed.json")) if (ST / "pushed.json").exists() else {})
h = lambda p: hashlib.sha1(json.dumps(p, sort_keys=True, default=str).encode()).hexdigest()[:16]
changed = [p for p in payload["listings"] if pushed.get(p["zpid"]) != h(p)]
keep = [p["zpid"] for p in payload["listings"]]


def post(body):
    req = urllib.request.Request(URL, data=json.dumps(body, default=str).encode(), method="POST",
                                 headers={"content-type": "application/json", "x-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"CRM update failed: HTTP {e.code} {e.read()[:500]!r}")


tot = {"created": 0, "updated": 0, "retired": 0}
chunks = [changed[i:i + 120] for i in range(0, len(changed), 120)] or [[]]
for i, ch in enumerate(chunks):
    last = i == len(chunks) - 1
    if i:
        time.sleep(62)
    res = post({"run": payload["run"], "listings": ch, **({"keep_zpids": keep} if last else {})})
    if not res.get("ok"):
        sys.exit(f"CRM update failed: {res}")
    for k in tot:
        tot[k] += res.get(k) or 0
    for p in ch:
        pushed[p["zpid"]] = h(p)
    json.dump({z: pushed[z] for z in keep if z in pushed}, open(ST / "pushed.json", "w"), indent=0)
print("CRM On-Market update:", json.dumps({"sent": len(changed), **tot}))
