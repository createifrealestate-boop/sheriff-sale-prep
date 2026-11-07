"""Preliminary deal score (0-100) from Zillow data. A rough screen to decide what to research first -
NOT an appraisal, NOT DealScore. All assumptions live in reference/scoring_config.json.

Usage: python3 -I score.py classified.json zillow_cache.json out.json
Adds to every OK-to-Sell / Almost-Ready case: prelim_score, arv, rehab_est, expected_bid, roi_expected,
max_bid_target, headroom, zestimate, rent_est, gross_yield, score_notes. Cases without Zillow data get prelim_score = None.
"""
import json, re, statistics, sys
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "reference"


def cache_key(c):
    addr = (c.get("address") or "").split(";")[0].strip().lower()
    return f"{addr}|{c.get('zip') or ''}"


def zillow_query(c):
    addr = (c.get("address") or "").split(";")[0].strip()
    return f"{addr}, {c.get('city') or c.get('municipality')}, PA {c.get('zip') or ''}".strip()


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def lerp(x, x0, x1):
    return clip((x - x0) / (x1 - x0), 0.0, 1.0)


def rehab_estimate(z, cfg):
    sqft = z.get("sqft") or cfg["default_sqft"]
    yb = z.get("year_built") or 1950
    per = next(p for lim, p in cfg["rehab_per_sqft_by_year_built"] if yb < lim)
    r = sqft * per
    if z.get("renovated"):
        r *= cfg["rehab_renovated_factor"]
    return max(cfg["min_rehab"], round(r, -2))


def score_case(c, z, cfg):
    if not z or not z.get("zestimate"):
        return None
    Z = float(z["zestimate"])
    comps = [float(x) for x in (z.get("comp_sold") or []) if x]
    arv = Z
    arv_src = "Zestimate"
    if len(comps) >= 2 and statistics.median(comps) < Z:
        arv, arv_src = statistics.median(comps), "median of comps' sale prices"
    rehab = rehab_estimate(z, cfg)
    bid = float(c.get("opening_bid") or 0)
    exp_bid = max(bid, cfg["win_pct_of_arv"] * arv)
    basis = exp_bid * (1 + cfg["buyer_cost_pct_of_bid"]) + rehab
    profit = arv * (1 - cfg["sell_hold_pct_of_arv"]) - basis
    roi = profit / basis if basis else 0
    max_all_in = arv * (1 - cfg["sell_hold_pct_of_arv"]) / (1 + cfg["target_roi"])
    max_bid = (max_all_in - rehab) / (1 + cfg["buyer_cost_pct_of_bid"])
    rent = float(z["rent"]) if z.get("rent") else None
    yld = (rent * 12 / basis) if rent and basis else None

    P = cfg["points"]
    profit_pts = P["profit"] * lerp(roi, cfg["roi_zero_points_at"], cfg["roi_full_points_at"])
    rent_pts = P["rent"] * lerp(yld, cfg["yield_zero_points_at"], cfg["yield_full_points_at"]) if yld is not None else 0
    lo, hi = z.get("range_lo"), z.get("range_hi")
    conf = 0.0
    if lo and hi:
        conf += 0.5 * (1 - lerp((hi - lo) / Z, 0.20, 0.50))
    if len(comps) >= 3:
        conf += 0.25
    if comps and abs(Z - statistics.median(comps)) / Z <= 0.15:
        conf += 0.25
    conf_pts = P["confidence"] * conf

    pen, notes = 0.0, []
    pc = cfg["penalties"]
    flags = " | ".join(c.get("flags") or []).lower()
    cat = c.get("sale_category", "")
    if cat.startswith("HOA"):
        pen += pc["hoa_condo_judgment"]; notes.append(f"-{pc['hoa_condo_judgment']} HOA/condo judgment")
    if "federal tax lien" in flags or "united states is a named" in flags:
        pen += pc["federal_tax_lien"]; notes.append(f"-{pc['federal_tax_lien']} federal lien/IRS")
    if "dhs lien" in flags or "redevelopment authority" in flags:
        pen += pc["other_gov_lien"]; notes.append(f"-{pc['other_gov_lien']} govt lien")
    if "entered an appearance" in flags:
        pen += pc["defense_attorney"]; notes.append(f"-{pc['defense_attorney']} defense attorney")
    if "bankruptcy history" in flags:
        pen += pc["bankruptcy_history"]; notes.append(f"-{pc['bankruptcy_history']} bankruptcy history")
    if str(c.get("bucket_reason", "")).startswith("VERIFY"):
        pen += pc["verify_case"]; notes.append(f"-{pc['verify_case']} verify status")
    elif c.get("bucket") == "almost":
        pen += pc["almost_ready"]; notes.append(f"-{pc['almost_ready']} not fully cleared")
    if z.get("anchored"):
        pen += pc["zestimate_anchored_to_price"]; notes.append(f"-{pc['zestimate_anchored_to_price']} Zestimate tied to a listing/sale price")
    bonus = 0.0
    if c.get("fc_min_bid"):
        bonus = cfg["bonuses"]["free_and_clear_order"]; notes.append(f"+{bonus:g} free & clear order")

    score = int(round(clip(profit_pts + rent_pts + conf_pts - pen + bonus, 0, 100)))
    return {
        "prelim_score": score, "zestimate": Z, "arv": round(arv), "arv_source": arv_src, "rehab_est": rehab,
        "expected_bid": round(exp_bid), "roi_expected": round(roi, 3), "max_bid_target": round(max_bid),
        "headroom": round(max_bid - bid), "rent_est": rent, "gross_yield": round(yld, 3) if yld is not None else None,
        "score_notes": f"ARV ${arv:,.0f} ({arv_src}); rehab ~${rehab:,.0f}; assumed winning bid ${exp_bid:,.0f}; "
                       f"ROI {roi*100:.0f}%" + (f"; rent ${rent:,.0f}/mo" if rent else "; no rent est.")
                       + ("; " + ", ".join(notes) if notes else ""),
    }


def main():
    classified, cache_path, out = sys.argv[1:4]
    cfg = json.load(open(REF / "scoring_config.json"))
    cases = json.load(open(classified))
    cache = json.load(open(cache_path)) if Path(cache_path).exists() else {}
    n = miss = 0
    for c in cases:
        if c["bucket"] == "excluded":
            continue
        n += 1
        r = score_case(c, cache.get(cache_key(c)), cfg)
        if r is None:
            miss += 1
            c["prelim_score"] = None
            c["score_notes"] = "No Zillow data"
        else:
            c.update(r)
    json.dump(cases, open(out, "w"), indent=1, default=str)
    print(f"scored {n - miss} of {n} OK/Almost cases ({miss} without Zillow data)")


if __name__ == "__main__":
    main()
