"""Get HUD's Small Area Fair Market Rents (SAFMR: rent by ZIP code and bedroom count) for the Pittsburgh metro and save
them to state/onmarket/hud_safmr.json, used by scripts/onmarket_update.py for each listing's HUD rent.

The CRM holds the HUD User API key (secret HUD_API_KEY), so this asks the CRM's backend function hudSafmrTable for the
table (auth: CRM_API_KEY, the key push_onmarket.py uses). SAFMR = HUD's 40th-percentile gross rent (rent + utilities)
for standard units, by ZIP; the Section 8 payment standard is 90-110% of it. HUD publishes once a year (FY starts Oct 1).
Run by .github/workflows/onmarket.yml; refreshes when the file is missing or 30+ days old.
Usage: python3 scripts/hud_safmr.py [--force]
"""
import datetime as dt, json, os, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "state" / "onmarket" / "hud_safmr.json"
URL = os.environ.get("CRM_HUD_URL") or "https://create-if-crm.base44.app/api/apps/6a672f8ccee4376a8dfd5387/functions/hudSafmrTable"


def main():
    today = dt.date.today()
    have = json.load(open(OUT)) if OUT.exists() else {}
    if have.get("built") and (today - dt.date.fromisoformat(have["built"])).days < 30 and "--force" not in sys.argv:
        print(f"HUD SAFMR FY{have.get('fy')} checked {have['built']}; next check after 30 days")
        return
    key = os.environ.get("CRM_API_KEY", "").strip()
    if not key:
        print("::warning::CRM_API_KEY not set; cannot get HUD rents")
        return
    req = urllib.request.Request(URL, data=b"{}", method="POST", headers={"content-type": "application/json", "x-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        msg = getattr(e, "read", lambda: b"")()[:300]
        print(f"::warning::HUD rents not refreshed: {e} {msg!r}; keeping FY{have.get('fy', 'none')}")
        return
    zips = {z: v for z, v in (d.get("zips") or {}).items() if len(v) == 5 and all(v)}
    if len(zips) < 50:
        print(f"::warning::HUD returned {len(zips)} ZIP rents (smallarea_status {d.get('smallarea_status')}, metro {d.get('metro')}); "
              f"keeping FY{have.get('fy', 'none')}")
        return
    json.dump({"fy": d.get("year"), "built": today.isoformat(), "source": "HUD User API via CRM hudSafmrTable",
               "area": d.get("area_name"), "cbsa": d.get("cbsa"), "metro": d.get("metro"),
               "note": "HUD Small Area Fair Market Rents: gross rent (incl. utilities) by ZIP for 0-4 bedrooms.",
               "zips": dict(sorted(zips.items()))}, open(OUT, "w"), indent=0)
    print(f"HUD SAFMR FY{d.get('year')}: {len(zips)} ZIPs in {d.get('area_name')}")


if __name__ == "__main__":
    main()
