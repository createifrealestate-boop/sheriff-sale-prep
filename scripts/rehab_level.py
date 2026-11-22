"""Guess a house's rehab level (Cosmetic / Medium / Heavy / Gut) before anyone has looked at it.

Rates per level are in reference/deal_model.json rehab.levels (the user's, 2026-11-22: $25 / $45 / $65 / $95 per
sqft; calibrated from their own jobs: a cosmetic rehab at ~$25/sqft and a near-gut at ~$65/sqft). The score uses the
guessed level as is; the team can pick the level in the CRM popup, which then wins.

Signals (settings and points in reference/rehab_levels.json), added to a 0-3 scale and rounded:
- county condition rating (stale, but the only house-specific record for most homes)
- words in the Zillow listing ("as-is", "cash only", "fire" push heavier; "renovated", "updated" lighter)
- list price vs the county ARV (a house listed at 30% of ARV is priced for a big rehab)
- age (pre-1940 houses lean heavier)
- recent resale: bought within 2 years and now listed at 1.4x+ (likely already redone, lighter)

level(signals) -> (name, rate, reasons)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = json.load(open(ROOT / "reference" / "rehab_levels.json"))
RATES = json.load(open(ROOT / "reference" / "deal_model.json"))["rehab"]["levels"]
NAMES = ["Cosmetic", "Medium", "Heavy", "Gut"]


def level(cond=None, words=None, price=None, arv=None, year_built=None, last_sale_date=None, last_sale_price=None, today=None):
    why = []
    cond = (cond or "").strip().upper()
    s = C["condition"].get(cond, C["condition_unknown"])
    why.append(f"county condition {cond.lower()}" if cond else "no county condition rating")
    up = down = 0.0
    words = [w.lower() for w in words or [] if w.lower() in C["words"]]
    heavy = [w for w in words if C["words"][w] > 0]
    cheap = bool(price and arv and price / arv < C["light_words_ignored_below"])
    # Zillow's word search is loose ("renovated" also catches "could be renovated"): a heavy word, or a price far
    # under the ARV, overrules the light words.
    if heavy or cheap:
        words = heavy
    for w in words:
        p = C["words"][w]
        if p > 0:
            up += p
        else:
            down += p
        why.append(f"listing says \"{w}\"")
    s += min(up, C["words_max_up"]) + max(down, -C["words_max_down"])
    if price and arv:
        r = price / arv
        for lo, hi, p in C["price_vs_arv"]:
            if lo <= r < hi:
                if p:
                    s += p
                    why.append(f"listed at {r:.0%} of the ARV")
                break
    if year_built and year_built < C["old_before"]:
        s += C["old_points"]
        why.append(f"built {int(year_built)}")
    if price and last_sale_price and last_sale_date and today:
        try:
            import datetime as dt
            days = (today - dt.date.fromisoformat(str(last_sale_date)[:10])).days
        except ValueError:
            days = None
        if days is not None and 60 <= days <= 730 and price >= C["resold_factor"] * last_sale_price:
            s += C["resold_points"]
            why.append(f"bought for ${last_sale_price:,.0f} {days // 30} months ago, now listed at ${price:,.0f} (probably redone)")
    i = max(0, min(3, int(round(s))))
    return NAMES[i], RATES[NAMES[i]], why
