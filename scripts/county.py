"""Allegheny County's own records (WPRDC) for after-repair value (ARV), proven flips and parcel lookup.

Used by the On-Market pipeline (scripts/onmarket_update.py) and, for a second-opinion ARV, by the Sheriff
Sale push (scripts/county.py sheriff). Runs in GitHub Actions (this workspace cannot reach WPRDC).

Data: Property Assessments (residential parcels, card 1) + Property Sale Transactions 2023-now. `build` downloads
them (about 330 MB) and writes a compact cache (cache/county.pkl.gz, kept by the workflow's actions/cache, not
committed). Everything else loads that cache.

ARV method (backtested on 483 flip resales from 2025-26: median miss 12%, 70% within 20%, bias -3%; reads high
under $100k): the average of
  (a) price per sqft of renovated comps x the subject's sqft, and
  (b) price / county assessed value of renovated comps x the subject's assessed value,
where renovated comps = flip resales nearby if there are 2+, else the top quarter of similar sales.
Comps: same assessor neighborhood (else municipality), last 18 months, same number of units, size within
+-30% (+-35% for b). Confidence is "high" when (a) and (b) agree within 25% and the ARV is $100k+.

A flip = a buy (real price, not a family/corrective/multi-parcel/quit-claim deed) resold as a market sale
60-548 days later for 1.4x+, $25k+ more and $50k+.

Usage:
  python3 scripts/county.py build [workdir]          # download + build the cache (workflow, weekly)
  python3 scripts/county.py sheriff state/crm.json   # add county_arv* fields to the Sheriff payload in place
"""
import csv, datetime as dt, gzip, json, os, pickle, re, statistics as st, subprocess, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("COUNTY_CACHE") or ROOT / "cache" / "county.pkl.gz")
ASSESS_DUMP = "https://data.wprdc.org/datastore/dump/9a1c60bd-f9f7-4aba-aeb7-af8c3aaa44e5"
SALES = {2023: "9fbceb58-5bc1-4ad6-b93f-8147a9b34c5c", 2024: "9366b400-e4a2-403f-ab14-64cf708ec2f7",
         2025: "57b84145-f9eb-493b-a78f-9bc803413d99", 2026: "0bd13902-f2ee-4340-b7c8-c54ebd0f6bd0"}
RES_USES = {"SINGLE FAMILY": 1, "TWO FAMILY": 2, "THREE FAMILY": 3, "FOUR FAMILY": 4, "TOWNHOUSE": 1, "ROWHOUSE": 1}
MARKET = {"VALID SALE", "TIME ON MARKET (INSUFF/EXCESS)"}
NOT_A_BUY = {"LOVE AND AFFECTION SALE", "CORRECTIVE DEED / DUPLICATE SALE", "MULTI-PARCEL SALE", "QUIT CLAIM", "NOT APPLICABLE"}

# ---------------------------------------------------------------- addresses
_SUF = {"STREET": "ST", "AVENUE": "AVE", "AV": "AVE", "DRIVE": "DR", "ROAD": "RD", "LANE": "LN", "COURT": "CT", "PLACE": "PL",
        "BOULEVARD": "BLVD", "TERRACE": "TER", "TERR": "TER", "CIRCLE": "CIR", "HIGHWAY": "HWY", "EXTENSION": "EXT", "EXTN": "EXT",
        "PARKWAY": "PKWY", "SQUARE": "SQ", "TRAIL": "TRL", "ALLEY": "ALY", "HEIGHTS": "HTS", "MOUNT": "MT", "SAINT": "ST",
        "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "PIKE": "PIKE", "WAY": "WAY", "RUN": "RUN", "HOLLOW": "HOLW",
        "CROSSING": "XING", "POINT": "PT", "RIDGE": "RDG", "VIEW": "VW", "MANOR": "MNR"}
_SUFX = re.compile(r"\s(ST|AVE|DR|RD|LN|CT|PL|BLVD|TER|CIR|WAY|HWY|EXT|PKWY|TRL|ALY)$")
_UNIT = re.compile(r"\s+(APT|UNIT|STE|SUITE|FL|FLOOR|#)\s*\S*$|\s+#\S+$", re.I)


def norm_street(s):
    s = _UNIT.sub("", (s or "").upper().replace(".", "").replace(",", " "))
    words = [_SUF.get(w, w) for w in re.split(r"\s+", s.strip()) if w]
    return " ".join(words)


def split_line1(line1):
    """'720-722 Center St Apt 2' -> ('720', 'CENTER ST')"""
    m = re.match(r"\s*(\d+)[A-Z]?(?:\s*-\s*\d+[A-Z]?)?\s+(.*)$", (line1 or "").upper())
    return (m.group(1), norm_street(m.group(2))) if m else (None, None)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _hn(x):
    v = _num(x)
    return str(int(v)) if v is not None else None


# ---------------------------------------------------------------- build
def _download(url, dest):
    if dest.exists() and dest.stat().st_size > 1000:
        return
    subprocess.run(["curl", "-sSL", "-f", "--retry", "3", "-m", "1800", "-A", "Mozilla/5.0", "-o", str(dest), url], check=True)


def build(work):
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    _download(ASSESS_DUMP, work / "assess.csv")
    for y, rid in SALES.items():
        _download(f"https://data.wprdc.org/datastore/dump/{rid}", work / f"sales_{y}.csv")
    P, ADDR = {}, defaultdict(list)
    for r in csv.DictReader(open(work / "assess.csv", newline="", encoding="utf-8", errors="replace")):
        units = RES_USES.get(r["USEDESC"])
        if not units or r.get("CARDNUMBER") not in (None, "", "1", "1.0"):
            continue
        hn, street, z = _hn(r["PROPERTYHOUSENUM"]), norm_street(r["PROPERTYADDRESS"]), (_hn(r["PROPERTYZIP"]) or "")[:5]
        P[r["PARID"]] = {
            "units": units, "use": r["USEDESC"], "nb": r["NEIGHCODE"], "nbname": (r["NEIGHDESC"] or "").strip(),
            "muni": (r["MUNIDESC"] or "").strip(), "school": (r["SCHOOLDESC"] or "").strip(), "zip": z,
            "sqft": _num(r["FINISHEDLIVINGAREA"]), "beds": _num(r["BEDROOMS"]),
            "baths": (_num(r["FULLBATHS"]) or 0) + 0.5 * (_num(r["HALFBATHS"]) or 0), "yr": _num(r["YEARBLT"]),
            "cond": (r["CONDITIONDESC"] or "").strip(), "grade": (r["GRADEDESC"] or "").strip(),
            "addr": f"{hn or ''} {street}".strip(), "fmv": _num(r["FAIRMARKETTOTAL"]), "land": _num(r["FAIRMARKETLAND"]),
            "bldg": _num(r["FAIRMARKETBUILDING"]), "county": _num(r["COUNTYTOTAL"]), "lot": _num(r["LOTAREA"]),
            "homestead": (r["HOMESTEADFLAG"] or "").strip() == "HOM", "last_sale": (r["SALEDATE"] or "")[:10],
            "last_price": _num(r["SALEPRICE"]),
        }
        if hn and street:
            ADDR[f"{hn}|{street}|{z}"].append(r["PARID"])
            ADDR[f"{hn}|{street}"].append(r["PARID"])
    S, seen = [], set()
    for y in SALES:
        for r in csv.DictReader(open(work / f"sales_{y}.csv", newline="", encoding="utf-8", errors="replace")):
            pid = r["PARID"]
            price, d = _num(r["PRICE"]), r["SALEDATE"][:10]
            if pid not in P or not price or not d:
                continue
            k = (pid, d, r["PRICE"], r["DEEDBOOK"], r["DEEDPAGE"])
            if k in seen:
                continue
            seen.add(k)
            S.append((pid, dt.date.fromisoformat(d), price, r["SALEDESC"]))
    S.sort()
    by = defaultdict(list)
    for s in S:
        by[s[0]].append(s)
    flips = []
    for pid, ss in by.items():
        for i, b in enumerate(ss):
            if b[3] in NOT_A_BUY or b[2] < 3000:
                continue
            for r in ss[i + 1:]:
                days = (r[1] - b[1]).days
                if days < 60:
                    continue
                if days > 548:
                    break
                if r[3] in MARKET and r[2] >= 1.4 * b[2] and r[2] - b[2] >= 25000 and r[2] >= 50000:
                    flips.append({"pid": pid, "buy_d": b[1], "buy": b[2], "buy_type": b[3], "sale_d": r[1], "sale": r[2], "days": days})
                    break
                if r[3] not in NOT_A_BUY:
                    break
    data = {"built": dt.date.today().isoformat(), "P": P, "ADDR": dict(ADDR), "S": S, "flips": flips}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(CACHE, "wb", compresslevel=5) as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"county cache: {len(P)} residential parcels, {len(S)} sales, {len(flips)} flips -> {CACHE} ({CACHE.stat().st_size / 1e6:.1f} MB)")


# ---------------------------------------------------------------- queries
class County:
    def __init__(self, path=CACHE):
        with gzip.open(path, "rb") as f:
            d = pickle.load(f)
        self.built, self.P, self.ADDR, self.flips = d["built"], d["P"], d["ADDR"], d["flips"]
        fk = {(f["pid"], f["sale_d"]) for f in self.flips}
        self.C, self.CM = defaultdict(list), defaultdict(list)
        for pid, d_, price, desc in d["S"]:
            p = self.P[pid]
            if desc in MARKET and p["sqft"] and p["sqft"] >= 400 and price >= 20000 and p["fmv"]:
                c = {"pid": pid, "d": d_, "price": price, "sqft": p["sqft"], "beds": p["beds"], "units": p["units"],
                     "ppsf": price / p["sqft"], "ratio": price / p["fmv"], "flip": (pid, d_) in fk}
                self.C[p["nb"]].append(c)
                self.CM[p["muni"]].append(c)
        self.HZ = None
        self.FN = defaultdict(list)
        for f in self.flips:
            self.FN[self.P[f["pid"]]["nb"]].append(f)

    # parcel lookup ---------------------------------------------------
    def match(self, line1, zip5=None):
        """Zillow address line -> PARID (or None). Exact house number + street (+ ZIP when it settles a tie)."""
        hn, street = split_line1(line1)
        if not hn:
            return None
        for key in ([f"{hn}|{street}|{zip5}"] if zip5 else []) + [f"{hn}|{street}"]:
            ids = self.ADDR.get(key) or []
            if len(set(ids)) == 1:
                return ids[0]
            if ids and zip5:
                z = [i for i in set(ids) if self.P[i]["zip"] == zip5]
                if len(z) == 1:
                    return z[0]
        # street written without its suffix on one side ("Jenny Lind" vs "JENNY LIND ST")
        if not zip5:
            return None
        if self.HZ is None:
            self.HZ = defaultdict(list)
            for k, ids in self.ADDR.items():
                parts = k.split("|")
                if len(parts) == 3:
                    self.HZ[f"{parts[0]}|{parts[2]}"].append((_SUFX.sub("", parts[1]), ids))
        base = _SUFX.sub("", street)
        cands = {i for b, ids in self.HZ.get(f"{hn}|{zip5}", []) if b == base for i in ids}
        return cands.pop() if len(cands) == 1 else None

    # ARV -------------------------------------------------------------
    def _cands(self, p, pid, when, months, tol, scope, sqft):
        lo = when - dt.timedelta(days=int(months * 30.5))
        pool = self.C[p["nb"]] if scope == "nb" else self.CM[p["muni"]]
        return [c for c in pool if lo <= c["d"] < when and c["pid"] != pid and c["units"] == p["units"]
                and (1 - tol) * sqft <= c["sqft"] <= (1 + tol) * sqft]

    @staticmethod
    def _q(xs, f):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(f * len(xs)))]

    def _method(self, p, pid, when, sqft, tol, key, base):
        for scope in ("nb", "muni"):
            cs = self._cands(p, pid, when, 18, tol, scope, sqft)
            fl = [c[key] for c in cs if c["flip"]]
            if len(fl) >= 2:
                return st.median(fl) * base, f"{len(fl)} flip resales ({'neighborhood' if scope == 'nb' else 'municipality'})", cs
            if len(cs) >= 5:
                return self._q([c[key] for c in cs], 0.75) * base, f"top quarter of {len(cs)} sales ({'neighborhood' if scope == 'nb' else 'municipality'})", cs
        return None, None, []

    def arv(self, pid, when=None, sqft=None):
        """County ARV for a parcel as of `when` (default today). sqft overrides the county's living area."""
        when = when or dt.date.today()
        p = self.P.get(pid)
        if not p:
            return {"county_arv": None, "county_arv_note": "not a residential parcel in county records"}
        sqft = sqft or p["sqft"]
        if not sqft or not p["fmv"]:
            return {"county_arv": None, "county_arv_note": "county record has no living area or assessment"}
        a, ma, ca = self._method(p, pid, when, sqft, 0.30, "ppsf", sqft)
        b, mb, cb = self._method(p, pid, when, sqft, 0.35, "ratio", p["fmv"])
        est = (a + b) / 2 if a and b else (a or b)
        if not est:
            return {"county_arv": None, "county_arv_note": "too few comparable sales nearby"}
        agree = abs(a - b) / est if a and b else None
        conf = "high" if agree is not None and agree < 0.25 and est >= 100000 else "low"
        why = [] if conf == "high" else (["only one method had comps"] if agree is None else
                                         [f"the two methods differ by {agree:.0%}"] if agree >= 0.25 else []) + (["under $100k, where it tends to read high"] if est < 100000 else [])
        comps = {(c["pid"], c["d"]): c for c in ca + cb}.values()
        top = sorted(comps, key=lambda c: (not c["flip"], -c["d"].toordinal()))[:8]
        return {
            "county_arv": round(est, -2), "county_arv_conf": conf, "county_arv_comps": len(comps),
            "county_arv_flips": sum(1 for c in comps if c["flip"]),
            "county_arv_note": (f"${a:,.0f} by $/sqft ({ma}); ${b:,.0f} by price/assessed ({mb})" if a and b else
                                f"${est:,.0f} by {'$/sqft' if a else 'price/assessed'} ({ma or mb})")
                               + f"; {conf} confidence" + (f": {', '.join(why)}" if why else ""),
            "county_arv_top": [{"addr": self.P[c["pid"]]["addr"], "date": c["d"].isoformat(), "price": c["price"],
                                "sqft": c["sqft"], "beds": c["beds"], "flip": c["flip"]} for c in top],
        }

    def flips_like(self, pid, beds=None, sqft=None, months=24, when=None):
        """Flips resold in the same assessor neighborhood in the last `months` with beds within 1 and size within 25%."""
        when = when or dt.date.today()
        p = self.P.get(pid)
        if not p:
            return []
        beds = beds if beds is not None else p["beds"]
        sqft = sqft or p["sqft"]
        lo = when - dt.timedelta(days=int(months * 30.5))
        out = []
        for f in self.FN[p["nb"]]:
            q = self.P[f["pid"]]
            if f["pid"] == pid or not (lo <= f["sale_d"] <= when):
                continue
            if beds is not None and q["beds"] is not None and abs(q["beds"] - beds) > 1:
                continue
            if sqft and q["sqft"] and not (0.75 * sqft <= q["sqft"] <= 1.25 * sqft):
                continue
            out.append({"addr": q["addr"], "buy": f["buy"], "buy_date": f["buy_d"].isoformat(), "sale": f["sale"],
                        "sale_date": f["sale_d"].isoformat(), "days": f["days"], "beds": q["beds"], "sqft": q["sqft"]})
        return sorted(out, key=lambda x: x["sale_date"], reverse=True)

    def assessed_rec(self, pid):
        """Same shape as state/assessed.json entries, for deal.property_tax."""
        p = self.P.get(pid) or {}
        return {"fmv": p.get("fmv"), "county": p.get("county"), "land": p.get("land"), "bldg": p.get("bldg"),
                "lot": p.get("lot"), "muni": p.get("muni"), "school": p.get("school")} if p else None


# ---------------------------------------------------------------- sheriff
def sheriff(payload_path):
    """Second-opinion county ARV on every Sheriff Sale property (added to the CRM payload, not committed)."""
    C = County()
    payload = json.load(open(payload_path))
    n = 0
    for p in payload["properties"]:
        pid = (p.get("portal_parcel") or "").split(";")[0].strip().replace("-", "")
        if not pid:
            continue
        r = C.arv(pid)
        r.pop("county_arv_top", None)
        p.update({k: v for k, v in r.items()})
        n += bool(r.get("county_arv"))
    json.dump(payload, open(payload_path, "w"), indent=1, default=str)
    print(f"county ARV on {n} of {len(payload['properties'])} sheriff properties (county data as of {C.built})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        build(sys.argv[2] if len(sys.argv) > 2 else "/tmp/county")
    elif cmd == "sheriff":
        sheriff(sys.argv[2])
    else:
        sys.exit(__doc__)
