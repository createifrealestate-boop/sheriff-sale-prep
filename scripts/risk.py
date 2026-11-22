"""Danger points for a house, shared by the Sheriff and On-Market scores (settings: reference/risk_config.json).

Why (county sales 2023-25, every market buy followed 18 months; tools/flip_arv/cheap_buys.py in the CRM app):
- Under $50k, houses the county rates POOR / VERY POOR were never flipped (0 of 211); FAIR 1%; AVERAGE 5%.
- Buys under 25% of the county ARV flipped less (5%) than those at 25-55% (8-9%) and were passed along more.
- Some areas almost never see a cheap buy flipped (Wilkinsburg, Clairton, North Braddock); others often do.
- Mostly-land assessments (building under half the value) flipped least (1%).
Condition also raises the rehab rate (reference/deal_model.json rehab.per_sqft_by_condition).

danger(rec, area, price=None, arv=None) -> (points, reasons): points <= 0 are penalties, > 0 a bonus.
rec: {"cond", "bldg", "land", "muni"} (county assessment); area: {muni: {"n", "flipped", "rate"}}.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = json.load(open(ROOT / "reference" / "risk_config.json"))


def cond_key(cond):
    return (cond or "").strip().upper()


def danger(rec, area=None, price=None, arv=None):
    rec = rec or {}
    pts, why = 0, []
    cond = cond_key(rec.get("cond"))
    if cond in C["condition_points"]:
        p = C["condition_points"][cond]
        pts += p
        why.append(f"county rates it {cond.lower()} ({p:+d})")
    b, l = rec.get("bldg"), rec.get("land")
    if b is not None and l and (b + l) > 0 and b / (b + l) < C["shell"]["building_share_below"]:
        p = C["shell"]["points"]
        pts += p
        why.append(f"building only {b / (b + l):.0%} of the assessed value ({p:+d})")
    if price is not None and arv and price < C["too_cheap"]["below_share_of_arv"] * arv:
        p = C["too_cheap"]["points"]
        pts += p
        why.append(f"price under {C['too_cheap']['below_share_of_arv']:.0%} of the ARV ({p:+d})")
    a = (area or {}).get(rec.get("muni") or "")
    A = C["area"]
    if a and a["n"] >= A["min_buys"]:
        if a["rate"] <= A["rare_rate"]:
            pts += A["rare_points"]
            why.append(f"similar buys here rarely got flipped ({a['flipped']} of {a['n']}) ({A['rare_points']:+d})")
        elif a["rate"] >= A["good_rate"]:
            pts += A["good_points"]
            why.append(f"similar buys here often got flipped ({a['flipped']} of {a['n']}) ({A['good_points']:+d})")
    return pts, why
