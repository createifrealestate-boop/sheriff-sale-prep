"""Chance an outside buyer wins each OK to Sell / Almost Ready property at the sale.

Uses only what the Sheriff's list shows (sale type, free & clear minimum bid, decree, owner type, notes,
months on the list, law firm, plaintiff) and the model in reference/sell_model.json, which is fit on 23 months
of the Sheriff's results by analysis/sheriff_only/fit_sell.py. Adds to each case: sell_chance (0-1),
sell_label (High / Medium / Low), sell_reasons.

Usage: python3 -I sell_chance.py scored.json --sale-date YYYY-MM-DD   (updates the file in place)
"""
import json, math, re, sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fcmin import fc_min  # noqa: E402

REF = Path(__file__).resolve().parent.parent / "reference"
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def group(c):
    cat = (c.get("sale_category") or "").lower()
    com = (c.get("comments") or "").upper()
    if cat.startswith("tax lien"):
        _, mn = fc_min(c.get("comments"))
        ct = c.get("cost_tax_bid")
        if mn is not None and ct and mn >= ct - 1:
            mn = None
        if mn is None and c.get("fc_min_bid"):
            mn = c["fc_min_bid"]
        if mn:
            return "fc"
        if re.search(r"\bDECREE\b|UPSET", com):
            return "decree"
        return "tax"
    if cat.startswith("mortgage"):
        return "mortgage"
    if cat.startswith("hoa"):
        return "hoa"
    return "other"


def months_on_list(c, sale_date):
    m = re.search(r"(\d+)([A-Z]{3})(\d{2})$", c.get("sale_id") or "")
    if not m or m.group(2) not in MON or not sale_date:
        return None
    sd = date.fromisoformat(str(sale_date)[:10])
    return (sd.year - 2000 - int(m.group(3))) * 12 + sd.month - (MON.index(m.group(2)) + 1)


def firm_key(c):
    u = re.sub(r"[^A-Z& ]", "", (c.get("plaintiff_attorney") or "").upper())
    return " ".join(u.split()[:3])


def plaintiff_key(c):
    u = re.sub(r"[^A-Z ]", " ", (c.get("plaintiff") or "").upper())
    u = re.sub(r"\bBOROUGH OF WILKINSBURG\b", "WILKINSBURG BOROUGH", " ".join(u.split()))
    u = re.sub(r"\bALLEGHENY COUNTY\b", "COUNTY OF ALLEGHENY", u)
    u = re.sub(r"\b(N ?A|LLC|INC|CORP|CORPORATION|COMPANY|CO|FSB|DBA|D B A|F K A|FKA|AS|NOT|TRUSTEE|THE)\b.*", "", u).strip()
    return " ".join(u.split()[:3])


def features(c, firms, plfs, sale_date=None):
    g = group(c)
    kind = "tax" if g in ("fc", "decree", "tax") else "mortgage" if g == "mortgage" else "other"
    com = (c.get("comments") or "").upper()
    own = c.get("owner_type") or ""
    f = {"grp_" + g: 1.0}
    if own.startswith("Estate"):
        f["estate_" + kind] = 1.0
    elif own.startswith("Entity"):
        f["entity_" + kind] = 1.0
    if re.search(r"FORF", com):
        f["forf"] = 1.0
    if kind == "mortgage" and re.search(r"\bFHA\b", com):
        f["fha"] = 1.0
    if kind == "mortgage" and (c.get("reassessed_damages") or c.get("dmg")):
        f["damages"] = 1.0
    if re.search(r"\bBK\b|BANKRUPT|\bCH(?:AP(?:TER)?)?\.?\s*\d+\b", com):
        f["bankruptcy_" + kind] = 1.0
    dm = months_on_list(c, sale_date or c.get("sale_date"))
    if dm is not None:
        b = "new" if dm <= 0 else "1to3" if dm <= 3 else "4to12" if dm <= 12 else "over12"
        f[f"months_{b}_{kind}"] = 1.0
    fk, pk = firm_key(c), plaintiff_key(c)
    if fk in firms:
        f["firm:" + fk] = 1.0
    if pk in plfs:
        f["plaintiff:" + pk] = 1.0
    return f


LABELS = {
    "grp_fc": "free & clear minimum bid", "grp_decree": "decree (sells at the upset price)",
    "grp_tax": "plain tax lien (often postponed)", "grp_mortgage": "mortgage (bank usually bids)",
    "grp_hoa": "HOA judgment", "estate_tax": "owner is an estate / heirs", "estate_mortgage": "owner is an estate / heirs",
    "entity_mortgage": "owner is a company (lender usually takes it back)", "entity_tax": "owner is a company",
    "forf": "earlier winning bid forfeited (FORF)", "fha": "FHA loan", "damages": "judgment reassessed",
    "bankruptcy_tax": "bankruptcy in the notes", "bankruptcy_mortgage": "bankruptcy in the notes",
}


def nice(name):
    t = re.sub(r"\s+", " ", (name or "").strip()).title()
    for a, b in ((" Llp", " LLP"), (" Llc", " LLC"), (" Pllc", " PLLC"), (" P.C.", " PC"), (" Esq", ""), (" N.A.", ""), (" Na", "")):
        t = t.replace(a, b)
    return t[:34].rstrip(" ,&")


def label(name, c=None):
    if name in LABELS:
        return LABELS[name]
    if name.startswith("firm:"):
        return "law firm " + (nice(c.get("plaintiff_attorney")) if c else name[5:].title())
    if name.startswith("plaintiff:"):
        return "plaintiff " + (nice(c.get("plaintiff")) if c else name[10:].title())
    if name.startswith("months_"):
        b = name.split("_")[1]
        return {"new": "first time on the list", "1to3": "on the list 1-3 months", "4to12": "on the list 4-12 months",
                "over12": "on the list over a year"}[b]
    return name


def chance(c, model, sale_date=None):
    f = features(c, set(model["firms"]), set(model["plaintiffs"]), sale_date)
    W = model["coef"]
    z = model["intercept"] + sum(W.get(k, 0.0) * v for k, v in f.items())
    p = 1 / (1 + math.exp(-z))
    b = model["bands"]
    lab = "High" if p >= b["High"] else "Medium" if p >= b["Medium"] else "Low"
    contrib = sorted(((W.get(k, 0.0), k) for k in f if abs(W.get(k, 0.0)) >= 0.25), key=lambda t: -abs(t[0]))[:3]
    reasons = "; ".join(("+ " if w > 0 else "- ") + label(k, c) for w, k in contrib)
    if c.get("bucket") == "almost":  # the model is fit on cleared listings
        reasons = "If the Sheriff clears it: " + reasons
    return round(p, 3), lab, reasons


def bank_bid(c, model):
    """Bank's likely winning bid on a mortgage foreclosure: share of the reassessed judgment in the Sheriff's
    notes (by judgment size), else share of the Zestimate. Returns (est, lo, hi, note) or None."""
    if group(c) != "mortgage" or "bank_bid" not in model:
        return None
    bb = model["bank_bid"]
    r100 = lambda x: int(round(x, -2))
    d = c.get("reassessed_damages")
    if d:
        b = next(x for x in bb["judgment_bands"] if d >= x["judgment_from"] and (x["judgment_to"] is None or d < x["judgment_to"]))
        note = (f"{b['median']:.0%} of the ${d:,.0f} judgment in the Sheriff's notes; banks bid {b['p25']:.0%}-{b['p75']:.0%} "
                f"of judgments this size in half their wins (n={b['n']})")
        if b.get("outside_winners_median"):
            note += f". Outside buyers who won these paid a median {b['outside_winners_median']:.0%} of the judgment"
        return r100(b["median"] * d), r100(b["p25"] * d), r100(b["p75"] * d), note
    v = c.get("zestimate")
    if v:
        z = bb["zestimate"]
        note = (f"No judgment in the notes, so {z['median']:.0%} of the ${v:,.0f} Zestimate; banks bid {z['p25']:.0%}-{z['p75']:.0%} "
                f"of the Zestimate in half their wins (n={z['n']}). Less reliable than a judgment")
        return r100(z["median"] * v), r100(z["p25"] * v), r100(z["p75"] * v), note
    return None


def main():
    path = sys.argv[1]
    sale_date = sys.argv[sys.argv.index("--sale-date") + 1] if "--sale-date" in sys.argv else None
    model = json.load(open(REF / "sell_model.json"))
    cases = json.load(open(path))
    n = nb = 0
    for c in cases:
        if c.get("bucket") not in ("ok", "almost"):
            continue
        c["sell_chance"], c["sell_label"], c["sell_reasons"] = chance(c, model, sale_date)
        c["sell_group"] = group(c)
        b = bank_bid(c, model)
        if b:
            c["bank_bid_est"], c["bank_bid_lo"], c["bank_bid_hi"], c["bank_bid_note"] = b
            nb += 1
        n += 1
    json.dump(cases, open(path, "w"), indent=1, default=str)
    from collections import Counter
    print(f"sell chance for {n} cases:", dict(Counter(c.get('sell_label') for c in cases if c.get('sell_label'))),
          f"| bank's likely bid for {nb} mortgage cases")


if __name__ == "__main__":
    main()
