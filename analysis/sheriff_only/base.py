"""Sheriff-data-only base table: one row per case per sale (Jan 2025 - Nov 2026). No outside values."""
import json, re, sys, math, collections, statistics as st, datetime as dt, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fcmin import fc_min
SRC = os.environ.get("SHERIFF_CASES", os.path.join(HERE, "cases.json.gz"))

med = lambda xs: st.median(xs) if xs else None
def q(xs, p):
    xs = sorted(xs)
    if not xs: return None
    i = (len(xs) - 1) * p; lo = math.floor(i); hi = math.ceil(i)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)
pct = lambda a, b: round(100 * a / b, 1) if b else None
MON = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']

def pdate(s, ref):
    """Parse m/d/yy, m-d-yy, m.d.yy near a reference date."""
    m = re.match(r"(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,4})", s)
    if not m: return None
    mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100: y += 2000
    try: return dt.date(y, mo, d)
    except ValueError: return None

def plaintiff_kind(p, cat):
    u = (p or "").upper()
    if cat.startswith("mortgage"): return "Lender / servicer"
    if re.search(r"SCHOOL", u): return "School district"
    if re.search(r"CITY OF PITTSBURGH|PITTSBURGH WATER|PWSA", u): return "City of Pittsburgh / PWSA"
    if re.search(r"COUNTY OF ALLEGHENY|ALLEGHENY COUNTY", u): return "Allegheny County"
    if re.search(r"BOROUGH|TOWNSHIP|MUNICIPALITY|\bCITY OF\b|\bTWP\b|\bBORO\b|AUTHORITY|SANITARY|WATER|SEWER", u): return "Borough / township / authority"
    if re.search(r"ASSOC|CONDOMINIUM|HOMEOWNER|\bHOA\b", u): return "HOA / condo"
    return "Other"

def load():
    import gzip
    rows = json.load(gzip.open(SRC, "rt") if SRC.endswith(".gz") else open(SRC))
    by = collections.defaultdict(list)
    for c in rows: by[c["case_no"]].append(c)
    sales = sorted(set(c["sale_date"] for c in rows))
    for cs in by.values():
        cs.sort(key=lambda c: c["sale_date"])
        for i, c in enumerate(cs):
            c["app_i"] = i; c["app_n"] = len(cs)
            c["next"] = cs[i + 1] if i + 1 < len(cs) else None
            c["prev"] = cs[i - 1] if i else None
    for c in rows:
        sd = dt.date.fromisoformat(c["sale_date"]); c["sd"] = sd
        cat = (c.get("sale_category") or "").lower(); istax = cat.startswith("tax lien")
        com = c.get("comments") or ""; U = com.upper()
        has, mn = fc_min(com)
        paid = "PAID IN" in U
        ct = c.get("cost_tax_bid")
        minbid = mn if (istax and mn) else None
        if minbid is not None and not paid and ct and minbid >= ct - 1: minbid = None
        c["minbid"] = minbid; c["ct"] = None if paid else (c.get("recalc_ct_bid") or ct)
        c["open"] = minbid or c["ct"]
        decree = minbid is None and istax and bool(re.search(r"\bDECREE\b|UPSET", U))
        c["grp"] = ("Tax lien, decree" if decree else "Tax lien, free & clear min bid" if minbid else "Tax lien, other") if istax else \
                   "Mortgage foreclosure" if cat.startswith("mortgage") else "HOA / condo" if cat.startswith("hoa") else "Other"
        c["fc_token"] = has
        c["pk"] = plaintiff_kind(c.get("plaintiff"), cat)
        m = re.search(r"-(\d{2})-", c.get("case_no") or ""); c["case_year"] = 2000 + int(m.group(1)) if m else None
        m = re.search(r"(\d+)([A-Z]{3})(\d{2})$", c.get("sale_id") or "")
        c["first_listed"] = dt.date(2000 + int(m.group(3)), MON.index(m.group(2)) + 1, 1) if m and m.group(2) in MON else None
        c["docket_m"] = (sd.year - c["first_listed"].year) * 12 + sd.month - c["first_listed"].month if c["first_listed"] else None
        c["forf"] = c["outcome"] == "sold_3p" and c["next"] is not None
        c["forf_checkable"] = c["outcome"] == "sold_3p" and c["sale_date"] != sales[-1]
        c["auctioned"] = c["outcome"] in ("sold_3p", "plaintiff_overbid", "plaintiff_costs", "unsold")
        # dates in the notes
        oks = [pdate(x, sd) for x in re.findall(r"OK TO SELL\s*(?:FOR|ON)?\s*(\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4})", U)]
        oks += [pdate(x, sd) for x in re.findall(r"ALL DOCS? RE?CV?D\s*(?:FOR(?: THE)?)?\s*(\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4})", U)]
        c["ok_dates"] = sorted(d for d in oks if d)
        pp = c.get("postponed_to"); c["pp_date"] = pdate(pp, sd) if pp else None
        c["dmg"] = c.get("reassessed_damages")
        c["half"] = f"{sd.year} H{1 if sd.month <= 6 else 2}"
        c["ratio"] = c["price"] / c["open"] if (c.get("price") and c["open"]) else None
    return rows, by, sales

if __name__ == "__main__":
    rows, by, sales = load()
    print(len(rows), len(by), len(sales))
    print(collections.Counter(c["grp"] for c in rows if c["outcome"] == "sold_3p"))
    print(collections.Counter(c["pk"] for c in rows))
    print(sum(1 for c in rows if c["dmg"]), sum(1 for c in rows if c["ok_dates"]), sum(1 for c in rows if c["pp_date"]))
