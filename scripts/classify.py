"""Decode Sheriff comments and sort each case into OK to Sell / Almost Ready / excluded.

Input:  cases.json  (list of case dicts, schema in reference/schema.md)
Output: classified.json (same dicts + derived fields)

Usage: python3 -I classify.py cases.json classified.json --sale-date 2026-11-02
"""
import argparse, json, re, sys, datetime as dt
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "reference"

NON_RESIDENTIAL = re.compile(r"commercial|industrial|vacant|agricultur|land", re.I)
RESIDENTIAL_HINT = re.compile(r"residential|condo|dwelling|house|apartment|single|duplex", re.I)

DATE = r"\d{1,2}[-./]\d{1,2}[-./]\d{2,4}"
MONEY = r"\$?\s?([\d,]+\.\d{2})"
FC_RE = r"\bF/C\b[^\n$\d]*\$?\s?([\d,]+\.\d{2})"  # free & clear order with a minimum bid


def norm_date(s):
    m = re.match(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})", s)
    if not m:
        return None
    mo, d, y = map(int, m.groups())
    if y < 100:
        y += 2000
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def fmt(d):
    return f"{d.month}/{d.day}/{str(d.year)[2:]}" if d else ""


def money(s):
    return float(s.replace(",", ""))


# ---------------------------------------------------------------- requirements
def decode_requirements(comments, sale_date):
    """Return list of (kind, text). kind in:
    3129.3, 3129.2, oc, bk, service, mailing, handbill, postpone, replenish, other
    Only lines that state something still NEEDED / rejected count."""
    out = []
    for raw in (comments or "").split("\n"):
        line = raw.strip().lstrip("-").strip()
        u = line.upper()
        if not u:
            continue
        # resolved / informational lines
        if re.match(r"^(RCVD|O/C TO RE-?ASSESS|OK TO SELL|F/C|DECREE|FHA|FORFEIT)", u) and not re.search(
            r"NOT ACCEPTED|NO ACCEPTED|INCORRECT|NEED", u
        ):
            continue
        hit = False
        if re.search(r"HANDBILL", u) and re.search(r"INCORRECT|NO INFORMATION|NEEDS? PP|POSTPONE", u):
            out.append(("handbill", "Handbill / short-description defect – Sheriff says sale must be postponed"))
            hit = True
        if re.search(r"NEEDS? (TO BE )?PP FROM|MUST BE (PP|POSTPONED)|NEEDS? POSTPONE", u) and not hit:
            out.append(("postpone", "Sheriff notes sale must be postponed"))
            hit = True
        if re.search(r"NEED\s+BKD|NEED\s+BKDR|NEED\s+(BK\s+)?DISMISSAL|NEED RELIEF", u):
            bk = re.search(r"(\d{2}-\d{5})", u)
            out.append(("bk", "Bankruptcy dismissal / relief-from-stay docs" + (f" (BK {bk.group(1)})" if bk else "")))
            hit = True
        if re.search(r"NSM ON DEF|NO SERVICE|SERVICE RETURN IS|NEED (SIGNED )?AFFIDAVIT OF SERVICE", u):
            who = re.search(r"NSM ON (DEFS?)\b", u)
            out.append(("service", "Proof of service on " + ("defendants" if who and who.group(1) == "DEFS" else "defendant")))
            hit = True
        m3 = re.search(r"3129\.3", u)
        if m3 and re.search(r"NEED|NOT ACCEPTED|NO ACCEPTED|INCORRECT|REJECT", u):
            d = re.search(r"3129\.3\s*(?:FOR\s*)?(" + DATE + ")", u)
            txt = "Rule 3129.3 notice of postponed sale date" + (f" (for {fmt(norm_date(d.group(1)))})" if d else "")
            if re.search(r"NOT ACCEPTED|NO ACCEPTED|INCORRECT|REJECT", u):
                txt += " – filed copy rejected, must be re-filed"
            out.append(("3129.3", txt))
            hit = True
        if re.search(r"3129\.2|NEED\s+3129(?![.\d])", u) and re.search(r"NEED|INCOMPLETE|NOT ACCEPTED|NO ACCEPTED|REJECT", u):
            miss = re.search(r"MISSING[:\s-]+(.+)", u)
            if "INCOMPLETE" in u:
                txt = "Complete Rule 3129.2 notice/affidavit" + (f" – missing: {miss.group(1).strip().lower()}" if miss else "")
            elif re.search(r"NOT ACCEPTED|REJECT", u):
                txt = "Rule 3129.2 notice rejected – must be re-served"
            else:
                txt = "Rule 3129.2 notice of sale / affidavit of service"
            out.append(("3129.2", txt))
            hit = True
        if re.search(r"O/C", u) and re.search(r"NEED|NOT ACCEPTED|NO ACCEPTED|INCORRECT", u) and not re.search(
            r"NEED O/C FOR POSTING", u
        ):
            dates = [norm_date(x) for x in re.findall(DATE, u.split("(")[0])]
            dates = [d for d in dates if d]
            txt = "Court order (O/C) approving postponements"
            if dates:
                txt += f" covering {len(dates)} sale date(s): " + ", ".join(fmt(d) for d in dates)
            out.append(("oc", txt))
            hit = True
        elif re.search(r"NEED O/C FOR POSTING|O/C PERMITTING", u):
            out.append(("oc", "Court order permitting service by posting"))
            hit = True
        if re.search(r"NEED (PROOF OF )?MAILING|NEED CERT|PROOF OF MAILING", u):
            out.append(("mailing", "Proof of mailing/posting: " + re.sub(r"^.*?(NEED|PROOF)", r"\1", line).lower()[:120]))
            hit = True
        if re.search(r"REPLENISH", u):
            out.append(("replenish", "Replenishment invoice must be paid"))
            hit = True
        if not hit and re.search(r"\bNEEDS?\b|\bINCOMPLETE\b|NOT ACCEPTED", u):
            out.append(("other", line[:160]))
    # de-duplicate, keep order
    # one entry per kind (keep the most detailed text); 'other' and 'mailing' may repeat
    res, pos = [], {}
    for k, t in out:
        if k in ("other", "mailing"):
            if (k, t) not in res:
                res.append((k, t))
        elif k in pos:
            if len(t) > len(res[pos[k]][1]):
                res[pos[k]] = (k, t)
        else:
            pos[k] = len(res)
            res.append((k, t))
    return res


# ---------------------------------------------------------------- risk flags
def decode_flags(c, sale_date=None):
    u = (c.get("comments") or "").upper()
    f = []
    mins = re.findall(FC_RE, u)
    if mins:
        f.append(f"Free & clear court order, min bid ${money(mins[0]):,.2f}" + (
            f" (earlier orders: {', '.join('$%s' % format(money(x), ',.2f') for x in mins[1:])})" if len(mins) > 1 else ""))
    if "UPSET PRICE" in u:
        f.append('Free & clear order at "upset price"')
    m = re.search(r"FEDERAL TAX LIEN[^\n$]*" + MONEY, u)
    if m:
        f.append(f"Federal tax lien ${money(m.group(1)):,.2f}")
    elif re.search(r"FEDERAL TAX LIEN|IRS LIEN|\bIRS\b", u):
        f.append("Federal tax lien / IRS")
    if re.search(r"UNITED STA", u) or re.search(r"UNITED STATES", (c.get("defendant") or "").upper()):
        f.append("United States is a named defendant (IRS right of redemption possible)")
    m = re.search(r"(?:DHS|DEPT\.? OF HUMAN SERVICES?) LIEN[^\n$]*" + MONEY, u)
    if m:
        f.append(f"PA DHS lien ${money(m.group(1)):,.2f}")
    m = re.search(r"REDEVELOPMENT AUTHORITY[^\n$]*" + MONEY, u)
    if m:
        f.append(f"Redevelopment Authority mortgage ${money(m.group(1)):,.2f}")
    if re.search(r"LAND BANK", u + " " + (c.get("plaintiff") or "").upper() + " " + (c.get("plaintiff_attorney") or "").upper()):
        f.append("Land bank involvement")
    elif re.search(r"\bDECREE\b", u):
        f.append("Court decree on file")
    if re.search(r"\bFHA\b", u):
        f.append("FHA-insured loan")
    if re.search(r"FORFEIT", u):
        f.append("Prior winning bidder forfeited (property re-offered)")
    if re.search(r"SAVE YOUR HOME|\bSYH\b", u):
        f.append("Save Your Home program involvement")
    rc = recalc_ct(c.get("comments"))
    if rc:
        f.append(f"Opening bid recalculated – new C+T bid ${rc:,.2f}")
    if sale_date:
        oks = [norm_date(d) for d in re.findall(r"OK TO SELL\s*(?:FOR\s*)?(" + DATE + ")", u)]
        oks = [d for d in oks if d]
        if oks and sale_date not in oks:
            f.append(f"OK-to-sell note dated {fmt(max(oks))}, not this sale – verify")
    bks = set(re.findall(r"(\d{2}-\d{5})", u))
    if re.search(r"\bBK\b|BANKRUPT|CHP?\s*\d+", u):
        f.append(f"Bankruptcy history: {max(len(bks),1)} filing(s)")
    if c.get("sale_category", "").startswith("HOA"):
        f.append("HOA/condo judgment sale — a first mortgage may survive the sale")
    if re.search(r"ENTRY OF APPEARANCE", u):
        f.append("Defense attorney has entered an appearance")
    return f


def reassessed_damages(comments):
    u = (comments or "").upper()
    m = re.search(r"RE-?ASSESS DAMAGES[^\n$\d]*" + MONEY, u)
    return money(m.group(1)) if m else None


def recalc_ct(comments):
    u = (comments or "").upper()
    m = re.search(r"NEW C\+T BID[^\n$\d]*" + MONEY, u) or re.search(r"CALCULATED COST \+ TAX BID[^\n$]*" + MONEY, u)
    return money(m.group(1)) if m else None


def fc_min_bid(comments):
    mins = re.findall(FC_RE, (comments or "").upper())
    return money(mins[0]) if mins else None


def ok_in_comments(comments, sale_date):
    for d in re.findall(r"OK TO SELL\s*(?:FOR\s*)?(" + DATE + ")", (comments or "").upper()):
        if norm_date(d) == sale_date:
            return True
    return False


def is_residential(ptype):
    p = ptype or ""
    parts = [x.strip() for x in re.split(r";", p) if x.strip()] or ["Residential / unspecified"]
    # keep if any tract is residential/unspecified/condo; drop if every tract is commercial/industrial/land
    return any(not NON_RESIDENTIAL.search(x) or RESIDENTIAL_HINT.search(x) for x in parts)


def portal_parcel(pid):
    out = []
    for p in re.split(r"\s*;\s*", pid or ""):
        p = p.strip().upper()
        m = re.fullmatch(r"(\d{1,4})-([A-Z])-(\d{1,5})(?:-(\d{4})-(\d{2}))?", p)
        if m:
            out.append(f"{int(m.group(1)):04d}-{m.group(2)}-{int(m.group(3)):05d}-{m.group(4) or '0000'}-{m.group(5) or '00'}")
        elif p:
            out.append("search by address")
    return " ; ".join(out)


def tax_muni(muni, mapping, names):
    if muni in mapping:
        return mapping[muni]
    key = re.sub(r"\b(boro(ugh)?|twp|township|city|municipality|of|the)\b", "", (muni or "").lower()).replace("mt.", "mount").strip()
    key = re.sub(r"\s+", " ", key)
    for n in names:
        nk = re.sub(r"\b(boro|twp|city|municipality)\b", "", n.lower()).strip()
        if nk == key:
            return n
    return ""


# ---------------------------------------------------------------- bucket
def classify(c, sale_date, mapping, names):
    reqs = decode_requirements(c.get("comments"), sale_date)
    kinds = {k for k, _ in reqs}
    c["outstanding"] = [t for _, t in reqs]
    c["n_outstanding"] = len(reqs)
    c["flags"] = decode_flags(c, sale_date)
    c["reassessed_damages"] = c.get("reassessed_damages") or reassessed_damages(c.get("comments"))
    c["recalc_ct_bid"] = c.get("recalc_ct_bid") or recalc_ct(c.get("comments"))
    c["fc_min_bid"] = c.get("fc_min_bid") or fc_min_bid(c.get("comments"))
    c["opening_bid"] = c["fc_min_bid"] or c["recalc_ct_bid"] or c.get("cost_tax_bid")
    c["portal_parcel"] = portal_parcel(c.get("parcels"))
    c["tax_municipality"] = tax_muni(c.get("municipality"), mapping, names)
    c["ok_in_comments"] = ok_in_comments(c.get("comments"), sale_date)
    c["residential"] = is_residential(c.get("property_type"))

    status = (c.get("status") or "").lower()
    svs, n2, n3, ok = (bool(c.get(k)) for k in ("box_service", "box_3129_2", "box_3129_3", "box_ok"))
    blockers = kinds & {"bk", "postpone", "handbill"}
    non_3129_3 = kinds - {"3129.3"}

    if not status.startswith("active"):
        bucket, why = "excluded", c.get("status") or "Not active"
    elif not c["residential"]:
        bucket, why = "excluded", f"Non-residential ({c.get('property_type')})"
    elif blockers:
        bucket, why = "excluded", "; ".join(t for k, t in reqs if k in blockers)
    elif ok and not non_3129_3:
        bucket, why = "ok", "Sheriff OK box checked" + (" (3129.3 still open – usually filed last minute)" if "3129.3" in kinds else "")
    elif ok and non_3129_3:
        bucket, why = "almost", "VERIFY – OK box checked but notes still list: " + "; ".join(t for k, t in reqs if k != "3129.3")
    elif svs and n2 and kinds and kinds <= {"3129.3"}:
        bucket, why = "almost", "Only Rule 3129.3 outstanding"
    elif c["ok_in_comments"] and not non_3129_3:
        bucket, why = "almost", "VERIFY – notes say OK TO SELL but OK box unchecked"
    elif svs and n2 and not ok and not kinds and n3:
        bucket, why = "almost", "VERIFY – Service/3129.2/3129.3 checked, OK not yet checked, no items listed"
    else:
        bucket, why = "excluded", "Docs outstanding: " + ("; ".join(c["outstanding"]) or "boxes incomplete")
    c["bucket"], c["bucket_reason"] = bucket, why
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("out")
    ap.add_argument("--sale-date", required=True)
    a = ap.parse_args()
    sale_date = dt.date.fromisoformat(a.sale_date)
    mapping = json.load(open(REF / "muni_map.json"))
    names = [m["municipality"] for m in json.load(open(REF / "transfer_tax.json"))["municipalities"]]
    cases = json.load(open(a.cases))
    res = [classify(c, sale_date, mapping, names) for c in cases]
    json.dump(res, open(a.out, "w"), indent=1, default=str)
    from collections import Counter
    print(Counter(c["bucket"] for c in res))
    miss = sorted({c["municipality"] for c in res if c["bucket"] != "excluded" and not c["tax_municipality"]})
    if miss:
        print("WARNING: no transfer-tax match for:", miss, file=sys.stderr)


if __name__ == "__main__":
    main()
