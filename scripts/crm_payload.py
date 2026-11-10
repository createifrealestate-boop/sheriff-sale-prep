"""Build state/crm.json: the OK to Sell / Almost Ready properties plus the run summary, for the CRM's
Sheriff Sale page (sent by .github/workflows/email-workbook.yml via scripts/push_to_crm.py).
Usage: python3 -I crm_payload.py scored.json run_summary.json zillow_cache.json out.json"""
import json, re, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import cache_key  # noqa: E402

KEEP = ["sale_id", "case_no", "address", "city", "zip", "municipality", "parcels", "portal_parcel", "tracts",
        "property_type", "sale_category", "bucket", "bucket_reason", "opening_bid", "fc_min_bid", "plaintiff",
        "plaintiff_attorney", "defendant", "owner_type", "outstanding", "flags", "comments", "prelim_score",
        "zestimate", "arv", "arv_source", "rehab_est", "expected_bid", "roi_expected", "max_bid_target", "headroom",
        "rent_est", "gross_yield", "score_notes"]
ZKEEP = ["sqft", "beds", "baths", "year_built", "range_lo", "range_hi", "renovated", "anchored"]


FREE_CLEAR = re.compile(r"\bF\s*[&/]\s*C\b|FREE\s*(AND|&)\s*CLEAR", re.I)


def deal_type(c):
    """Label used by the CRM's Priority weights. Free & clear = any free-and-clear order mentioned in the
    Sheriff's notes (granted, pending or needed) or a free & clear minimum bid."""
    cat = (c.get("sale_category") or "").lower()
    fc = bool(c.get("fc_min_bid")) or bool(FREE_CLEAR.search(c.get("comments") or ""))
    if cat.startswith("tax lien"):
        t = "Free & clear tax lien" if fc else "Tax lien"
    elif cat.startswith("mortgage"):
        t = "Mortgage foreclosure"
    elif cat.startswith("hoa"):
        t = "HOA/condo judgment"
    else:
        t = "Other"
    return t, fc


def main():
    scored, summ, cache_p, out = sys.argv[1:5]
    cases = json.load(open(scored))
    rs = json.loads(summ) if summ.lstrip().startswith("{") else json.load(open(summ))
    cache = json.load(open(cache_p)) if Path(cache_p).exists() else {}
    changes = rs.get("changes") or []
    props = []
    for c in cases:
        if c.get("bucket") not in ("ok", "almost"):
            continue
        p = {k: c.get(k) for k in KEEP if c.get(k) is not None}
        z = cache.get(cache_key(c)) or {}
        p.update({k: z[k] for k in ZKEEP if z.get(k) is not None})
        p["deal_type"], p["free_clear"] = deal_type(c)
        notes = [x for x in changes if c["sale_id"] in x]
        if notes:
            p["change_note"] = "; ".join(notes)
        props.append(p)
    payload = {
        "sale": {
            "sale_date": rs["sale_date"], "list_printed": rs.get("list_printed"), "source": rs.get("source"),
            "ok_to_sell": rs.get("ok_to_sell"), "almost_ready": rs.get("almost_ready"),
            "total_cases": rs.get("total_cases"), "changes": changes,
            "unscored": sum(1 for p in props if p.get("prelim_score") is None),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "properties": props,
    }
    json.dump(payload, open(out, "w"), indent=1, default=str)
    print(f"crm payload: {len(props)} properties -> {out}")


if __name__ == "__main__":
    main()
