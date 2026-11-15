"""Area patterns in the sheriff sale results (Jan 2025 - Nov 2026): municipality, ZIP, street, area tiers.
values.json = price / Zillow value and later resale for outside purchases (from the 23-month value analysis)."""
import sys, os, json, re
AH = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(AH, "..", "sheriff_only"))
from base import *  # noqa
rows, by, sales = load()
V = json.load(open(os.path.join(AH, "values.json")))
for c in rows:
    v = V.get(f"{c['case_no']}|{c['sale_date']}") or {}
    c["pv"] = v.get("pv") if not c["forf"] else None; c["resale"] = v.get("resale") if not c["forf"] else None
    c["cleared"] = c["sd"] in c["ok_dates"]
    c["kind"] = "tax" if c["grp"].startswith("Tax") else "mortgage" if c["grp"] == "Mortgage foreclosure" else "other"
R = [c for c in rows if c.get("residential")]
S3 = [c for c in R if c["outcome"] == "sold_3p" and not c["forf"]]

def stats(g_all, name, minn=0):
    s = [c for c in g_all if c["outcome"] == "sold_3p" and not c["forf"]]
    if len(s) < minn: return None
    au = [c for c in g_all if c["auctioned"]]
    mfa = [c for c in au if c["kind"] == "mortgage"]
    tl = [c for c in s if c["grp"] in ("Tax lien, other", "Tax lien, free & clear min bid") and c["ratio"]]
    cl = [c for c in g_all if c["cleared"]]
    chk = [c for c in g_all if c["forf_checkable"]]
    pv = [c["pv"] for c in s if c["pv"]]
    cases = len(set(c["case_no"] for c in g_all))
    y = lambda yr: [c for c in s if c["sale_date"][:4] == yr]
    rs = [c for c in s if c["resale"]]
    return {"name": name, "cases": cases, "listings": len(g_all), "n": len(s), "per_100_cases": pct(len(s), cases),
            "price": med([c["price"] for c in s]), "p25": q([c["price"] for c in s], .25), "p75": q([c["price"] for c in s], .75),
            "tax_share": pct(sum(1 for c in s if c["kind"] == "tax"), len(s)),
            "fc": sum(1 for c in s if c["grp"].endswith("min bid")), "decree": sum(1 for c in s if c["grp"].endswith("decree")),
            "plain": sum(1 for c in s if c["grp"] == "Tax lien, other"), "mf": sum(1 for c in s if c["kind"] == "mortgage"),
            "mf_price": med([c["price"] for c in s if c["kind"] == "mortgage"]), "tl_price": med([c["price"] for c in s if c["kind"] == "tax"]),
            "tl_ratio": round(med([c["ratio"] for c in tl]), 2) if tl else None, "tl_n": len(tl),
            "tl_at_open": pct(sum(1 for c in tl if c["ratio"] < 1.05), len(tl)),
            "mf_auct": len(mfa), "mf_outside": pct(sum(1 for c in mfa if c["outcome"] == "sold_3p"), len(mfa)),
            "cleared": len(cl), "cleared_auct": pct(sum(1 for c in cl if c["auctioned"]), len(cl)),
            "stayed": pct(sum(1 for c in g_all if c["outcome"] == "stayed"), len(g_all)),
            "forf": f"{sum(1 for c in chk if c['forf'])}/{len(chk)}", "forf_pct": pct(sum(1 for c in chk if c["forf"]), len(chk)),
            "pv": round(med(pv), 2) if pv else None, "pv_n": len(pv),
            "n25": len(y("2025")), "n26": len(y("2026")), "price25": med([c["price"] for c in y("2025")]), "price26": med([c["price"] for c in y("2026")]),
            "resales": len(rs), "resale_gain": med([c["resale"] - c["price"] for c in rs]) if rs else None,
            "estate": pct(sum(1 for c in s if c["owner_type"].startswith("Estate")), len(s))}

def show(st, keys):
    print(" | ".join(f"{k}={st[k]:,.0f}" if isinstance(st[k], float) and abs(st[k]) > 500 else f"{k}={st[k]}" for k in keys))

if __name__ == "__main__":
    M = collections.defaultdict(list)
    for c in R: M[c["municipality"]].append(c)
    ST = [x for x in (stats(g, k) for k, g in M.items()) if x]
    ST.sort(key=lambda x: -x["n"])
    tot = stats(R, "ALL")
    print("municipalities with listings", len(M), "with a completed outside purchase", sum(1 for x in ST if x["n"]), "residential completed", tot["n"])
    cum = 0
    for i, x in enumerate(ST[:30]):
        cum += x["n"]
        if i in (2, 4, 9, 19): print(f"top {i+1} = {pct(cum, tot['n'])}%")
    K1 = ["name", "cases", "n", "per_100_cases", "price", "p25", "p75", "fc", "decree", "plain", "mf", "tl_price", "mf_price"]
    K2 = ["name", "tl_ratio", "tl_n", "tl_at_open", "mf_auct", "mf_outside", "cleared", "cleared_auct", "stayed", "forf", "pv", "pv_n", "n25", "n26", "price25", "price26", "resales", "resale_gain", "estate"]
    print("== TOP 25 (A)"); [show(x, K1) for x in ST[:25]]
    print("== TOP 25 (B)"); [show(x, K2) for x in ST[:25]]
    show(tot, K1); show(tot, K2)
    json.dump(ST, open(os.path.join(AH, "muni_stats.json"), "w"), indent=0, default=str)
    print("== TIERS by median outside price (munis with >=5 purchases); others pooled")
    tier = {}
    for x in ST:
        if x["n"] >= 5: tier[x["name"]] = "A under $35k" if x["price"] < 35000 else "B $35k-$70k" if x["price"] < 70000 else "C over $70k"
    for t in sorted(set(tier.values())) + ["D few purchases"]:
        g = [c for c in R if tier.get(c["municipality"], "D few purchases") == t]
        x = stats(g, t); print(t, "munis:", sorted(k for k, v in tier.items() if v == t)[:40] if t[0] != "D" else len(set(c["municipality"] for c in g)))
        show(x, K1[1:]); show(x, K2[1:])
        for gname in ["Tax lien, free & clear min bid", "Tax lien, other", "Mortgage foreclosure"]:
            s = [c for c in g if c["outcome"] == "sold_3p" and not c["forf"] and c["grp"] == gname]
            pv = [c["pv"] for c in s if c["pv"]]; r = [c["ratio"] for c in s if c["ratio"]]
            if s: print(f"    {gname[:22]:22} n={len(s):3} price {med([c['price'] for c in s]):>9,.0f} ratio {med(r) if r else 0:.2f} price/value {round(med(pv),2) if pv else None} (n={len(pv)})")
    print("== ZIP (>=8 purchases)")
    Zp = collections.defaultdict(list)
    for c in R: Zp[c["zip"]].append(c)
    Zs = sorted([x for x in (stats(g, k, 8) for k, g in Zp.items()) if x], key=lambda x: -x["n"])
    for x in Zs:
        munis = collections.Counter(c["municipality"] for c in Zp[x["name"]] if c["outcome"] == "sold_3p").most_common(2)
        print(x["name"], munis, f"n={x['n']} price {x['price']:,.0f} tax_share {x['tax_share']} tl_ratio {x['tl_ratio']} at_open {x['tl_at_open']} mf_outside {x['mf_outside']} forf {x['forf']} pv {x['pv']}({x['pv_n']}) 25/26 {x['n25']}/{x['n26']}")
    print("== STREETS with 3+ completed outside purchases")
    def street(a):
        a = re.sub(r"\s+;.*", "", (a or "").upper()); a = re.sub(r"^[\d\-\s/&A-Z]{0,3}?\d[\d\-/]*\s*[A-Z]?\s+", "", a)
        a = re.sub(r"\b(STREET|ST|AVENUE|AVE|ROAD|RD|DRIVE|DR|WAY|LANE|LN|BOULEVARD|BLVD|PLACE|PL|COURT|CT|EXT|EXTENSION)\b\.?.*$", "", a).strip()
        return a
    SC = collections.defaultdict(list)
    for c in S3: SC[(street(c["address"]), c["municipality"])].append(c)
    for (s_, m_), g in sorted(SC.items(), key=lambda kv: -len(kv[1])):
        if len(g) >= 3 and s_: print(f"  {s_}, {m_}: {len(g)} purchases, prices {sorted(int(c['price']) for c in g)}, types {dict(collections.Counter(c['kind'] for c in g))}")
    rep = collections.Counter()
    for (s_, m_), g in SC.items():
        if s_: rep["1" if len(g) == 1 else "2" if len(g) == 2 else "3+"] += len(g)
    print("purchases by street repeat count", dict(rep))
    print("== PIPELINE: cases still pending at the Nov 2026 sale (postponed), by municipality, top 15")
    pend = [c for c in R if c["sale_date"] == sales[-1] and c["outcome"] == "postponed"]
    P = collections.Counter(c["municipality"] for c in pend)
    for k, v in P.most_common(15):
        g = [c for c in pend if c["municipality"] == k]
        print(f"  {k}: {v} pending (tax {sum(1 for c in g if c['kind']=='tax')}, mortgage {sum(1 for c in g if c['kind']=='mortgage')})")
    print("total pending", len(pend))
