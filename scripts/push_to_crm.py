"""Send the latest update (state/crm.json + the workbook) to the CRM's Sheriff Sale page.
Run by .github/workflows/email-workbook.yml. Usage: python3 scripts/push_to_crm.py [state/crm.json]
Env: CRM_API_KEY (matches the CRM's SHERIFF_INGEST_API_KEY secret), CRM_INGEST_URL (optional).
Missing key -> prints a notice and exits 0."""
import base64, json, os, sys, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = os.environ.get("CRM_INGEST_URL") or "https://create-if-crm.base44.app/api/apps/6a672f8ccee4376a8dfd5387/functions/ingestSheriffSale"
key = os.environ.get("CRM_API_KEY", "").strip()
if not key:
    print("::notice::CRM_API_KEY secret not set; skipping the CRM update.")
    sys.exit(0)

payload = json.load(open(sys.argv[1] if len(sys.argv) > 1 else ROOT / "state" / "crm.json"))
sale_date = payload["sale"]["sale_date"]
wb = ROOT / "state" / f"{sale_date}.xlsx"
if wb.exists():
    payload["workbook_b64"] = base64.b64encode(wb.read_bytes()).decode()
    payload["workbook_name"] = f"Sheriff Sale {sale_date} Prep.xlsx"

req = urllib.request.Request(URL, data=json.dumps(payload).encode(), method="POST",
                             headers={"content-type": "application/json", "x-api-key": key})
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.loads(r.read() or b"{}")
except urllib.error.HTTPError as e:
    sys.exit(f"CRM update failed: HTTP {e.code} {e.read()[:500]!r}")
print("CRM update:", json.dumps(res))
if not res.get("ok"):
    sys.exit(1)
if res.get("workbook_error"):
    print(f"::warning::workbook not stored: {res['workbook_error']}")
