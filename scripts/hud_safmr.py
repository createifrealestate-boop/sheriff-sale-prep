"""Download HUD's Small Area Fair Market Rents (SAFMR, rent by ZIP code and bedroom count) for the Pittsburgh metro
and save them to state/onmarket/hud_safmr.json, used by scripts/onmarket_update.py for each listing's HUD rent.

SAFMR = HUD's 40th-percentile gross rent (rent + utilities) for standard units, by ZIP. Housing authorities set the
voucher payment standard at 90-110% of it. Published once a year (fiscal year starts Oct 1).
Run by .github/workflows/onmarket.yml; refreshes when the file is missing, 30+ days old, or a newer year is out.
Needs openpyxl. Usage: python3 scripts/hud_safmr.py [--force]
"""
import datetime as dt, io, json, re, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "state" / "onmarket" / "hud_safmr.json"
AREA = "Pittsburgh, PA"  # HUD Metro FMR Area name starts with this
URL = "https://www.huduser.gov/portal/datasets/fmr/fmr{fy}/fy{fy}_safmrs.xlsx"


def norm(v):
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


def money(v):
    if v is None or v == "":
        return None
    try:
        return int(round(float(str(v).replace("$", "").replace(",", ""))))
    except ValueError:
        return None


def parse(data):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    cols = None
    for row in rows:
        h = [norm(c) for c in row]
        if any("zip" in c for c in h) and any(re.fullmatch(r"safmr ?0 ?br", c) for c in h):
            zc = next(i for i, c in enumerate(h) if "zip" in c)
            ac = next((i for i, c in enumerate(h) if "area name" in c), None)
            br = {int(m.group(1)): i for i, c in enumerate(h) if (m := re.fullmatch(r"safmr ?(\d) ?br", c))}
            cols = (zc, ac, br)
            break
    if not cols or sorted(cols[2]) != [0, 1, 2, 3, 4]:
        raise ValueError(f"could not find the ZIP / SAFMR 0-4BR columns (found {cols})")
    zc, ac, br = cols
    zips, area = {}, None
    for row in rows:
        name = str(row[ac] or "") if ac is not None else ""
        if not name.startswith(AREA):
            continue
        z = str(row[zc] or "").strip()
        if z.isdigit():
            z = z.zfill(5)
            vals = [money(row[br[b]]) for b in range(5)]
            if all(vals):
                zips[z] = vals
                area = name
    if len(zips) < 50:
        raise ValueError(f"only {len(zips)} Pittsburgh-area ZIPs found")
    return area, zips


def main():
    today = dt.date.today()
    fy_now = today.year + 1 if today.month >= 10 else today.year
    have = json.load(open(OUT)) if OUT.exists() else {}
    fresh = have.get("built") and (today - dt.date.fromisoformat(have["built"])).days < 30
    if fresh and have.get("fy", 0) >= fy_now and "--force" not in sys.argv:
        print(f"HUD SAFMR FY{have['fy']} from {have['built']}: up to date")
        return
    if fresh and "--force" not in sys.argv:
        print(f"HUD SAFMR FY{have.get('fy')} checked {have['built']}; next check after 30 days")
        return
    for fy in (fy_now, fy_now - 1, fy_now - 2):
        if have.get("fy", 0) > fy:
            break
        url = URL.format(fy=fy)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sheriff-sale-prep on-market pipeline (GitHub Actions)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            area, zips = parse(data)
        except Exception as e:  # noqa: BLE001
            print(f"FY{fy}: {e}")
            continue
        OUT.parent.mkdir(parents=True, exist_ok=True)
        json.dump({"fy": fy, "built": today.isoformat(), "source": url, "area": area,
                   "note": "HUD Small Area Fair Market Rents: gross rent (incl. utilities) by ZIP for 0-4 bedrooms.",
                   "zips": dict(sorted(zips.items()))}, open(OUT, "w"), indent=0)
        print(f"HUD SAFMR FY{fy}: {len(zips)} ZIPs in {area}")
        return
    if have:
        have["built"] = today.isoformat()  # keep the old year; try again in 30 days
        json.dump(have, open(OUT, "w"), indent=0)
    print(f"::warning::could not download a newer HUD SAFMR file; keeping FY{have.get('fy', 'none')}")


if __name__ == "__main__":
    main()
