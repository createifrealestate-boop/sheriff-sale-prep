"""Fit the "bank's likely bid" ratios for mortgage foreclosures and store them in reference/sell_model.json.

From the Sheriff's results (Jan 2025 - Nov 2026): when the plaintiff (bank) won with an overbid, what it bid
  * as a share of the reassessed judgment shown in the Sheriff's notes, by judgment size, and
  * as a share of the Zestimate (fallback when no judgment is shown; Zillow values from ../zillow_hist.json,
    leaving out homes whose Zestimate is just the sheriff price).
Usage: python3 -I fit_bank.py
"""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from base import *  # noqa
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from score import cache_key  # noqa: E402

rows, by, sales = load()
ob = [c for c in rows if c["grp"] == "Mortgage foreclosure" and c["outcome"] == "plaintiff_overbid"]
won3 = [c for c in rows if c["grp"] == "Mortgage foreclosure" and c["outcome"] == "sold_3p" and not c["forf"]]
r3 = lambda x: round(x, 3)
bands = []
for lo_, hi_ in [(0, 60000), (60000, 200000), (200000, None)]:
    x = [c["price"] / c["dmg"] for c in ob if c["dmg"] and c["dmg"] >= lo_ and (hi_ is None or c["dmg"] < hi_)]
    y = [c["price"] / c["dmg"] for c in won3 if c["dmg"] and c["dmg"] >= lo_ and (hi_ is None or c["dmg"] < hi_)]
    bands.append({"judgment_from": lo_, "judgment_to": hi_, "n": len(x), "median": r3(med(x)), "p25": r3(q(x, .25)),
                  "p75": r3(q(x, .75)), "outside_winners_median": r3(med(y)) if y else None, "outside_n": len(y)})
Z = json.load(open(os.path.join(REPO, "analysis", "zillow_hist.json")))
Z0 = json.load(open(os.path.join(REPO, "state", "zillow_cache.json")))
zr = []
for c in ob:
    z = Z.get(cache_key(c)) or Z0.get(cache_key(c)) or {}
    v = z.get("zestimate")
    if v and abs(v - c["price"]) / c["price"] > 0.03:
        zr.append(c["price"] / v)
bank = {"_readme": "Bank's likely winning bid on a mortgage foreclosure: share of the reassessed judgment in the Sheriff's notes "
                   "(by judgment size), else share of the Zestimate. Fit by analysis/sheriff_only/fit_bank.py.",
        "judgment_bands": bands,
        "zestimate": {"n": len(zr), "median": r3(med(zr)), "p25": r3(q(zr, .25)), "p75": r3(q(zr, .75))}}
p = os.path.join(REPO, "reference", "sell_model.json")
m = json.load(open(p)); m["bank_bid"] = bank
json.dump(m, open(p, "w"), indent=1)
print(json.dumps(bank, indent=1))
