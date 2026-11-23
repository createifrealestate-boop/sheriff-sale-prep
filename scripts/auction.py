"""Sheriff sale history for On-Market listings.

Reads every Sheriff results file in analysis/results/ (the Sheriff's results PDFs parsed with
scripts/parse_listing.py, one <name>.json + <name>.meta.json per sale; new months are added as they come out,
and everything there is used, no cutoff) and finds, per parcel, the most recent sale where it actually sold:

  third_party  "Third Party - $X" (an outside buyer won it; 7-digit prices can wrap and read "Party - $X")
  plaintiff    "Overbid - $X", "Cost & Tax - $X", "PLTF Cost - $X" (the plaintiff took it back: bank, lender or
               taxing body)

Postponed, stayed, waived, paid ("Money Made") and unsold cases are not sales and are skipped.

Used by scripts/onmarket_update.py, which adds these fields to each active listing with a county parcel id:
auction_date, auction_outcome, auction_price, auction_plaintiff, auction_category, auction_case,
auction_parcels (parcels sold together in that case: the price covers all of them), auction_count.

Usage: python3 -I scripts/auction.py   # summary: parcels with an outcome, and active listings matched
"""
import datetime as dt
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "analysis" / "results"
FIELDS = ["auction_date", "auction_outcome", "auction_price", "auction_plaintiff", "auction_category", "auction_case",
          "auction_parcels", "auction_count"]


def parid(p):
    """Sheriff parcel '702-G-94' (or '702-G-94-0000-00') -> county PARID '0702G00094000000'."""
    m = re.fullmatch(r"(\d{1,4})-([A-Z])-(\d{1,5})(?:-(\d{4})-(\d{2}))?", (p or "").strip().upper())
    if not m:
        return None
    return f"{int(m.group(1)):04d}{m.group(2)}{int(m.group(3)):05d}{m.group(4) or '0000'}{m.group(5) or '00'}"


def outcome(status):
    s = status or ""
    m = re.match(r"(.*?)\s*-\s*\$([\d,]+(?:\.\d+)?)", s)
    price = float(m.group(2).replace(",", "")) if m else None
    k = (m.group(1) if m else s).strip()
    if k.startswith("Third Party") or k == "Party":
        return "third_party", price
    if k.startswith("Overbid") or k.startswith("Cost & Tax") or k.startswith("PLTF Cost"):
        return "plaintiff", price
    return None, None


def sale_date(meta, path):
    raw = (meta or {}).get("date_of_sale") or ""
    for fmt in ("%A, %B %d, %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            pass
    # fall back to the file name, e.g. "August-2026-Results.json" -> first Monday isn't known; use the 1st
    m = re.match(r"([A-Za-z]+)-(\d{4})", Path(path).name)
    return dt.datetime.strptime(f"{m.group(1)} 1 {m.group(2)}", "%B %d %Y").date() if m else None


def load(results_dir=RESULTS):
    """{parid: {fields...}} for every parcel that sold at a Sheriff sale in the results files."""
    events = {}
    for f in sorted(glob.glob(str(results_dir / "*.json"))):
        if f.endswith(".meta.json"):
            continue
        meta_p = Path(f[:-5] + ".meta.json")
        meta = json.load(open(meta_p)) if meta_p.exists() else {}
        d = sale_date(meta, f)
        if not d:
            continue
        for c in json.load(open(f)):
            kind, price = outcome(c.get("status"))
            if not kind:
                continue
            pids = [q for q in (parid(p) for p in re.split(r"\s*;\s*", c.get("parcels") or "")) if q]
            for q in pids:
                events.setdefault(q, {})[(d, c.get("case_no"))] = {
                    "auction_date": d.isoformat(), "auction_outcome": kind, "auction_price": price,
                    "auction_plaintiff": c.get("plaintiff"), "auction_category": c.get("sale_category"),
                    "auction_case": c.get("case_no"), "auction_parcels": len(pids),
                }
    out = {}
    for q, ev in events.items():
        latest = ev[max(ev)]  # the same case can show up in more than one results file; dedup on (date, case)
        out[q] = {**latest, "auction_count": len(ev)}
    return out


def annotate(listing, history):
    """Fields to set on a listing (all None when the parcel never sold at Sheriff sale)."""
    h = history.get(listing.get("parid") or "")
    return {k: (h.get(k) if h else None) for k in FIELDS}


if __name__ == "__main__":
    H = load()
    L = json.load(open(ROOT / "state" / "onmarket" / "listings.json"))["listings"]
    act = [r for r in L.values() if r.get("status") == "active"]
    hits = [r for r in act if r.get("parid") in H]
    print(json.dumps({"results_files": len([f for f in glob.glob(str(RESULTS / "*.json")) if not f.endswith(".meta.json")]),
                      "parcels_sold": len(H), "active_listings": len(act), "matched": len(hits),
                      "third_party": sum(1 for r in hits if H[r["parid"]]["auction_outcome"] == "third_party"),
                      "plaintiff": sum(1 for r in hits if H[r["parid"]]["auction_outcome"] == "plaintiff")}))
