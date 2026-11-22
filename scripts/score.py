"""Preliminary deal score (0-100) from Zillow data. A rough screen to decide what to research first -
NOT an appraisal, NOT DealScore. All assumptions live in reference/scoring_config.json.

Usage: python3 -I score.py classified.json zillow_cache.json out.json
Adds to every OK-to-Sell / Almost-Ready case: prelim_score (BRRRR 45 + flip 35 + data confidence 20 - penalties),
flip_score, brrrr_score, arv, rehab_est (rehab level x sqft, scripts/rehab_level.py), expected_bid, flip/BRRRR MAOs (scripts/deal.py), best refi,
transfer tax, zestimate, rent_est, score_notes. Cases without Zillow data get prelim_score = None.
"""
import json, re, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deal import underwrite, property_tax, M as DM  # noqa: E402
from risk import danger  # noqa: E402
from rehab_level import level as rehab_level  # noqa: E402

AREA_PATH = Path(__file__).resolve().parent.parent / "state" / "area_flip_rates.json"
AREA = json.load(open(AREA_PATH)) if AREA_PATH.exists() else {}

REF = Path(__file__).resolve().parent.parent / "reference"
ASSESSED_PATH = Path(__file__).resolve().parent.parent / "state" / "assessed.json"
_ASSESSED = None


def parid(c):
    """WPRDC parcel id (e.g. 0188B00264000000) of the first parcel on the listing."""
    p = (c.get("portal_parcel") or "").split(";")[0].strip()
    return p.replace("-", "") if p and p[0].isdigit() else None


def assessed_for(c):
    """County assessed value (WPRDC FAIRMARKETTOTAL) from state/assessed.json, kept by the GitHub workflow."""
    global _ASSESSED
    if _ASSESSED is None:
        _ASSESSED = json.load(open(ASSESSED_PATH)) if ASSESSED_PATH.exists() else {}
    rec = _ASSESSED.get(parid(c) or "")
    return rec.get("fmv") if rec else None


def assessed_rec(c):
    global _ASSESSED
    if _ASSESSED is None:
        _ASSESSED = json.load(open(ASSESSED_PATH)) if ASSESSED_PATH.exists() else {}
    return _ASSESSED.get(parid(c) or "")


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


def score_case(c, z, cfg):
    if not z or not z.get("zestimate"):
        return None
    Z = float(z["zestimate"])
    comps = [float(x) for x in (z.get("comp_sold") or []) if x]
    arv = Z
    arv_src = "Zestimate"
    if len(comps) >= 2 and statistics.median(comps) < Z:
        arv, arv_src = statistics.median(comps), "median of comps' sale prices"
    bid = float(c.get("opening_bid") or 0)
    flags_l = " | ".join(c.get("flags") or []).lower()
    cat_l = (c.get("sale_category") or "").lower()
    byt = cfg.get("win_pct_by_type")
    if byt:
        if c.get("fc_min_bid"):
            grp, pct = "free & clear", byt["free_and_clear"]
        elif cat_l.startswith("tax lien") and "court decree" in flags_l:
            grp, pct = "tax-lien decree", byt["tax_lien_decree"]
        elif cat_l.startswith("tax lien"):
            grp, pct = "tax lien", byt["tax_lien"]
        elif cat_l.startswith("mortgage"):
            grp, pct = "mortgage", byt["mortgage"]
        elif cat_l.startswith("hoa"):
            grp, pct = "HOA/condo", byt["hoa"]
        else:
            grp, pct = "other", byt["other"]
    else:
        grp, pct = "all", cfg["win_pct_of_arv"]
    exp_bid = max(bid, pct * arv)
    rent = float(z["rent"]) if z.get("rent") else None
    rec = assessed_rec(c)
    assessed = rec.get("fmv") if rec else None
    ptax, ptax_note = property_tax(rec)
    cond = (rec or {}).get("cond")
    # Sheriff bids are low by nature, so price vs ARV says nothing about condition here; no listing text either.
    lvl, _, lvl_why = rehab_level(cond, None, None, None, z.get("year_built"))
    uw = underwrite(exp_bid, arv, z.get("sqft"), rent, assessed, c.get("tax_municipality"), ptax, ptax_note, level=lvl)
    dpts, dwhy = danger(rec, AREA)  # sheriff bids are low by nature, so no price-vs-ARV check here
    rehab = uw["rehab_est"]
    yld = (rent * 12 / (exp_bid + rehab)) if rent and (exp_bid + rehab) else None
    W = DM["scores"]["total_weights"]
    lo, hi = z.get("range_lo"), z.get("range_hi")
    conf = 0.0
    if lo and hi:
        conf += 0.5 * (1 - lerp((hi - lo) / Z, 0.20, 0.50))
    if len(comps) >= 3:
        conf += 0.25
    if comps and abs(Z - statistics.median(comps)) / Z <= 0.15:
        conf += 0.25

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
    if "forfeited" in flags_l:
        notes.append("FORF: re-auction, prior winner walked away")
    bonus = 0.0
    if c.get("fc_min_bid"):
        bonus = cfg["bonuses"]["free_and_clear_order"]; notes.append(f"+{bonus:g} free & clear order")

    flip_pts = W["flip"] * uw["flip_score"] / 100
    brrrr_pts = W["brrrr"] * uw["brrrr_score"] / 100
    conf_pts = W["confidence"] * conf
    score = int(round(clip(flip_pts + brrrr_pts + conf_pts - pen + bonus + dpts, 0, 100)))
    if dwhy:
        notes.append(f"danger {dpts:+d}: " + "; ".join(dwhy))
    tt_note = (f"transfer tax ${uw['transfer_tax']:,.0f}" if uw["transfer_tax"] is not None
               else f"closing ${DM['buy_closing_flat']:,} + sheriff fee ${DM['sheriff_closing_fee']:,}, no transfer tax")
    fm = lambda k: "n/a" if uw.get(k) is None else f"${uw[k]:,.0f}"
    return {
        "prelim_score": score, "zestimate": Z, "arv": round(arv), "arv_source": arv_src, "expected_bid": round(exp_bid),
        "rent_est": rent, "gross_yield": round(yld, 3) if yld is not None else None,
        "condition": cond, "danger_points": dpts, "danger_reasons": dwhy, "rehab_level": lvl, "rehab_level_why": lvl_why,
        **uw,
        "headroom": round(uw["mao_flip_30k"] - bid),
        "score_points": {"brrrr": round(brrrr_pts, 1), "flip": round(flip_pts, 1), "confidence": round(conf_pts, 1), "penalties": -pen, "bonus": bonus, "danger": dpts},
        "score_notes": (f"ARV ${arv:,.0f} ({arv_src}); rehab ${rehab:,.0f} ({lvl}, ${uw['rehab_rate']}/sqft: {'; '.join(lvl_why)}) + ${uw['contingency']:,.0f} contingency; {tt_note}; "
                        f"assumed winning bid ${exp_bid:,.0f} ({grp}, {pct*100:.0f}% of ARV or opening bid if higher). "
                        f"At that bid: flip profit ${uw['flip_profit']:,.0f} (flip score {uw['flip_score']}); "
                        + (f"BRRRR {uw['refi_terms']}, ${uw['refi_cash_flow']:,.0f}/mo, ${uw['brrrr_cash_left']:,.0f} left in the deal (BRRRR score {uw['brrrr_score']})"
                           if uw.get("refi_ok") else f"BRRRR: {uw['refi_terms']} (BRRRR score 0)")
                        + f". MAO flip {fm('mao_flip_30k')} ($30k profit), {fm('mao_flip_45k')} ($45k), {fm('mao_flip_60k')} ($60k); "
                        + f"MAO BRRRR {fm('mao_brrrr_0k')} ($0 left), {fm('mao_brrrr_15k')} ($15k), {fm('mao_brrrr_30k')} ($30k). "
                        + f"Points: BRRRR {brrrr_pts:.0f}/{W['brrrr']}, flip {flip_pts:.0f}/{W['flip']}, confidence {conf_pts:.0f}/{W['confidence']}"
                        + ("; " + ", ".join(notes) if notes else "")),
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
        c["lot_sqft"] = (assessed_rec(c) or {}).get("lot")  # county lot area, square feet
        r = score_case(c, cache.get(cache_key(c)), cfg)
        if r is None:
            miss += 1
            c["prelim_score"] = None
            c["score_notes"] = "No Zillow data"
            rec = assessed_rec(c)
            c["condition"] = (rec or {}).get("cond")
            c["danger_points"], c["danger_reasons"] = danger(rec, AREA)
        else:
            c.update(r)
    json.dump(cases, open(out, "w"), indent=1, default=str)
    print(f"scored {n - miss} of {n} OK/Almost cases ({miss} without Zillow data)")


if __name__ == "__main__":
    main()
