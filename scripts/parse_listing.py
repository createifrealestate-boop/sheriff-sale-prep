"""Parse the Allegheny County Sheriff's Sale Property Listing PDF (CountySuite print) into cases.json.

Usage: python3 -I parse_listing.py listing.pdf cases.json

Layout facts this relies on (checked against the 10/22/2026 print, 94 pages / 430 cases):
  * every case starts with a header row "Sale  Case Number ... Svs 3129.2 3129.3 OK"
  * the line under it holds sale id, case #, sale type, status, tracts, cost & tax bid
  * checkbox marks are an "X" printed under the Svs / 3129.2 / 3129.3 / OK header columns,
    so they are read by x-position, never by text order
  * a "Plaintiff(s): Attorney... Defendant(s): Property Municipality Parcel/Tax ID:" row,
    then one data row per tract (property lines + municipality + parcel)
  * "Comments:" and its lines run until the next case header or the page footer
  * the last page has "Summary Count: Active Postponed Cancelled Bankruptcy Total"
"""
import json, re, sys
from collections import Counter, defaultdict
import pdfplumber

# x boundaries (points, page width 792) — recalibrated per page from the header row when found
COL = {"sale": 0, "case": 80, "type": 165, "status": 355, "tracts": 480, "bid": 560}
PARTY = {"plaintiff": 0, "attorney": 165, "defendant": 305, "property": 453, "muni": 585, "parcel": 668}
BOX_X = {"box_service": 672, "box_3129_2": 702, "box_3129_3": 732, "box_ok": 762}

SALE_ID = re.compile(r"^\d{1,4}[A-Z]{3}\d{2}$")
FOOTER = re.compile(r"^(Printed:|\(c\)|Page \d+ of \d+|Summary Count)")


def lines_of(words, tol=2.5):
    """group words into visual lines by 'top'"""
    rows = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(rows[-1][0] - w["top"]) <= tol:
            rows[-1][1].append(w)
        else:
            rows.append([w["top"], [w]])
    return [(t, sorted(ws, key=lambda w: w["x0"])) for t, ws in rows]


def col_text(words, lo, hi):
    return " ".join(w["text"] for w in sorted(words, key=lambda w: w["x0"]) if lo <= w["x0"] < hi)


def col_lines(words, lo, hi):
    """text of a column, lines in top-to-bottom order (a wrapped cell reads correctly)"""
    ws = [w for w in words if lo <= w["x0"] < hi]
    return clean(" ".join(" ".join(w["text"] for w in l) for _, l in lines_of(ws)))


def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("&amp;", "&")).strip()


def classify_type(text):
    """tract descriptors printed in the Property cell"""
    u = text.upper()
    t = []
    if re.search(r"VACANT\s+COMMERCIAL", u):
        t.append("Vacant Commercial")
    elif re.search(r"VACANT\s+AGRICULT", u):
        t.append("Vacant Agricultural")
    elif re.search(r"VACANT|\bLAND\b|\bLOT\b", u) and not re.search(r"\b(RESIDENTIAL|HOUSE)\b", u):
        t.append("Vacant Land")
    elif re.search(r"INDUSTRIAL", u) and re.search(r"COMMERCIAL", u):
        t.append("Industrial ; Commercial")
    elif re.search(r"INDUSTRIAL", u):
        t.append("Industrial")
    elif re.search(r"COMMERCIAL", u):
        t.append("Commercial")
    elif re.search(r"AGRICULT", u):
        t.append("Vacant Agricultural")
    elif re.search(r"CONDOMIN", u):
        t.append("Condominium")
    return t[0] if t else "Residential / unspecified"


def smart_title(s):
    def fix(w):
        if re.fullmatch(r"\d+(ST|ND|RD|TH)", w, re.I):
            return w.lower()
        if re.fullmatch(r"(PA|NE|NW|SE|SW|II|III|IV)", w, re.I):
            return w.upper()
        if "'" in w or "-" in w:
            return "-".join(x[:1].upper() + x[1:].lower() for x in w.split("-"))
        return w[:1].upper() + w[1:].lower()
    return " ".join(fix(w) for w in s.split())


DESCR = r"(VACANT( LAND| COMMERCIAL| AGRICULTURAL)?|COMMERCIAL|INDUSTRIAL|CONDOMINIUM|AGRICULTURAL)"


def split_property(plines):
    """Property cell lines -> (street address, city, zip, property type)"""
    full = clean(" ".join(plines))
    ptype = classify_type(full)
    city_i = next((i for i, l in enumerate(plines) if re.search(r",\s*PA\s+\d{5}", l, re.I)), None)
    city = zp = ""
    street_lines = list(plines)
    if city_i is not None:
        m = re.match(r"^(.*?),\s*PA\s+(\d{5})(?:-\d{4})?\s*(.*)$", plines[city_i], re.I)
        city, zp, tail = clean(m.group(1)), m.group(2), clean(m.group(3))
        street_lines = plines[:city_i] + ([tail] if tail else []) + plines[city_i + 1:]
    street = clean(" ".join(street_lines))
    street = re.sub(r"\s*[-–]?\s*\b\d+\s*(ST|ND|RD|TH)?\s+WARD\b", "", street, flags=re.I)
    street = re.sub(r"\s*[-–]?\s*\bWARD\s*\d*\b\s*$", "", street, flags=re.I)
    street = re.sub(r"\s*[-–]\s*" + DESCR + r"\s*$", "", street, flags=re.I)
    street = re.sub(r"\s+[-–]\s+(RES|RESIDENTIAL|COMMERCIAL|VACANT|AUX|INDUSTRIAL|CONDO|GARAGE|REAR|APT)\b.*$", "", street, flags=re.I)
    street = re.sub(r"\s*[-–]\s*$", "", re.sub(r"\s+" + DESCR + r"\s*$", "", street, flags=re.I)).strip()
    return smart_title(street), smart_title(city), zp, ptype


def category_of(sale_type, plaintiff, comments):
    s = (sale_type or "").lower()
    if "tax lien" in s:
        return "Tax lien (Sci Fa sur tax lien)"
    if "mortgage" in s:
        return "Mortgage foreclosure"
    if "municipal" in s:
        return "Municipal lien"
    if re.search(r"assoc|condominium|homeowner|community|hoa|owners", (plaintiff or "").lower()) or "ar-" in s:
        return "HOA / condo assessment judgment"
    return "Other judgment execution"


def owner_type(defendant):
    d = (defendant or "")
    if re.search(r"\b(LLC|L\.L\.C|LP|L\.P\.|INC|CORP|CO\.|COMPANY|LTD|TRUST CO|PARTNERS|ASSOC|ENTERPRISES|PROPERTIES|HOLDINGS|INVESTORS|BANK)\b", d, re.I):
        return "Entity (LLC/LP/Inc)"
    if re.search(r"\b(ESTATE|HEIRS|UNKNOWN|DECEASED|TRUSTEE|TRUST|SUCCESSOR|ADMINISTRAT|EXECUTOR)\b", d, re.I):
        return "Estate / heirs / trust"
    return "Individual"


def parse_page(page, pageno, carry):
    words = page.extract_words(x_tolerance=2, keep_blank_chars=False)
    rows = lines_of(words)
    # header rows: line containing 'Sale' and 'Case' and 'Number'
    heads = [i for i, (t, ws) in enumerate(rows) if [w["text"] for w in ws[:3]] == ["Sale", "Case", "Number"]]
    if not heads:
        return []
    out = []
    # continuation of previous case's comments (text above first header, below page title)
    if carry is not None:
        for t, ws in rows[: heads[0]]:
            txt = clean(" ".join(w["text"] for w in ws))
            if txt and not FOOTER.match(txt) and not txt.startswith(("Date of Sale", "SHERIFF'S SALE")):
                carry["comment_lines"].append(txt)
    bounds = heads + [len(rows)]
    for hi, (a, b) in enumerate(zip(bounds[:-1], bounds[1:])):
        block = rows[a:b]
        top_hdr = block[0][0]
        # header word positions -> per-case column calibration (box columns)
        hdr_words = {w["text"]: w for w in block[0][1]}
        box_x = dict(BOX_X)
        if all(k in hdr_words for k in ("Svs", "3129.2", "3129.3", "OK")):
            box_x = {
                "box_service": (hdr_words["Svs"]["x0"] + hdr_words["Svs"]["x1"]) / 2,
                "box_3129_2": (hdr_words["3129.2"]["x0"] + hdr_words["3129.2"]["x1"]) / 2,
                "box_3129_3": (hdr_words["3129.3"]["x0"] + hdr_words["3129.3"]["x1"]) / 2,
                "box_ok": (hdr_words["OK"]["x0"] + hdr_words["OK"]["x1"]) / 2,
            }
        # locate structural rows
        idx_party = next((i for i, (t, ws) in enumerate(block) if ws[0]["text"].startswith("Plaintiff")), None)
        idx_comm = next((i for i, (t, ws) in enumerate(block) if ws[0]["text"] == "Comments:"), None)
        if idx_party is None:
            continue
        rec_rows = block[1:idx_party]
        rec_words = [w for t, ws in rec_rows for w in ws]
        rec1 = [w for w in rec_words if abs(w["top"] - rec_rows[0][0]) <= 3] if rec_rows else []
        sale_id = col_text(rec1, COL["sale"], COL["case"])
        mid = " ".join(w["text"] for w in sorted(rec1, key=lambda w: w["x0"]) if COL["case"] <= w["x0"] < COL["status"])
        mc = re.match(r"\s*([A-Z]{2}-\d{2}-\d{4,7})\s*(.*)$", mid)
        case_no, sale_type = (mc.group(1), mc.group(2)) if mc else (mid, "")
        status = col_lines(rec_words, COL["status"], COL["tracts"])
        tracts = col_text(rec1, COL["tracts"], COL["bid"])
        bid = col_text(rec1, COL["bid"], COL["bid"] + 100)
        boxes = {k: False for k in BOX_X}
        for w in rec_words:
            if w["text"] == "X":
                cx = (w["x0"] + w["x1"]) / 2
                k = min(box_x, key=lambda k: abs(box_x[k] - cx))
                if abs(box_x[k] - cx) <= 14:
                    boxes[k] = True
        # parties / tracts
        end_party = idx_comm if idx_comm is not None else len(block)
        data_rows = block[idx_party + 1 : end_party]
        dw = [w for t, ws in data_rows for w in ws if not FOOTER.match(w["text"])]
        dw = [w for w in dw if w["top"] < (page.height - 45)]
        plaintiff = col_lines(dw, PARTY["plaintiff"], PARTY["attorney"])
        attorney = col_lines(dw, PARTY["attorney"], PARTY["defendant"])
        defendant = col_lines(dw, PARTY["defendant"], PARTY["property"])
        parcel_words = sorted([w for w in dw if w["x0"] >= PARTY["parcel"]], key=lambda w: w["top"])
        tops = []
        for w in parcel_words:
            if not tops or w["top"] - tops[-1] > 5:
                tops.append(w["top"])
        if not tops:
            tops = [data_rows[0][0]] if data_rows else [0]
        tract_list = []
        for i, t0 in enumerate(tops):
            lo = t0 - 3
            hi_ = (tops[i + 1] - 3) if i + 1 < len(tops) else 1e9
            seg = [w for w in dw if lo <= w["top"] < hi_] if i else [w for w in dw if w["top"] < hi_]
            plines = [clean(" ".join(x["text"] for x in ws))
                      for t, ws in lines_of([w for w in seg if PARTY["property"] <= w["x0"] < PARTY["muni"]])]
            prop = plines
            muni = col_lines(seg, PARTY["muni"], PARTY["parcel"])
            parcel = col_lines([w for w in seg if w["x0"] >= PARTY["parcel"]], PARTY["parcel"], 1e9)
            tract_list.append((prop, muni, parcel))
        addrs, parcels, ptypes, munis, cities, zips = [], [], [], [], [], []
        for plines, muni, parcel in tract_list:
            addr, city, zp, ptype = split_property(plines)
            if addr not in addrs:
                addrs.append(addr)
            ptypes.append(ptype)
            parcels.append(parcel)
            munis.append(muni)
            cities.append(city)
            zips.append(zp)
        # comments
        comment_lines = []
        if idx_comm is not None:
            for j in range(idx_comm, len(block)):
                t, ws = block[j]
                txt_words = [w for w in ws if not (j == idx_comm and w["text"] == "Comments:")]
                txt = clean(" ".join(w["text"] for w in txt_words))
                if not txt or FOOTER.match(txt) or t > page.height - 50:
                    continue
                comment_lines.append(txt)
        case = {
            "sale_id": sale_id, "case_no": case_no, "sale_type_listed": sale_type,
            "sale_category": category_of(sale_type, plaintiff, comment_lines),
            "status": clean(status),
            "postponed_to": (re.search(r"to\s+(\d{1,2}/\d{1,2}/\d{4})", status) or [None, None])[1],
            "address": " ; ".join(addrs),
            "city": cities[0] if cities else "", "zip": zips[0] if zips else "",
            "municipality": munis[0] if munis else "",
            "parcels": " ; ".join(parcels),
            "tracts": int(tracts) if tracts.isdigit() else len(tract_list),
            "property_type": " ; ".join(dict.fromkeys(ptypes)) if len(set(ptypes)) > 1 else (ptypes[0] if ptypes else ""),
            "cost_tax_bid": float(bid.replace("$", "").replace(",", "")) if re.match(r"^\$?[\d,]+\.\d{2}$", bid) else None,
            "plaintiff": plaintiff, "plaintiff_attorney": attorney, "defendant": defendant,
            "owner_type": owner_type(defendant),
            **boxes,
            "comment_lines": comment_lines, "pdf_page": pageno,
        }
        out.append(case)
        carry = case
    return out


def main():
    pdf_path, out_path = sys.argv[1], sys.argv[2]
    cases, carry = [], None
    summary = None
    with pdfplumber.open(pdf_path) as pdf:
        header_date = None
        for i, page in enumerate(pdf.pages, 1):
            txt = page.extract_text() or ""
            m = re.search(r"Date of Sale:\s*(.+)", txt)
            if m and not header_date:
                header_date = m.group(1).strip()
            sm = re.search(r"Summary Count:.*?\n\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", txt, re.S)
            if sm:
                summary = dict(zip(["active", "postponed", "cancelled", "bankruptcy", "total"], map(int, sm.groups())))
            got = parse_page(page, i, cases[-1] if cases else None)
            cases.extend(got)
        printed = None
        t0 = pdf.pages[0].extract_text() or ""
        tl = pdf.pages[-1].extract_text() or ""
        m = re.search(r"Printed:\s*([\d/]+\s*[\d:]+\s*[AP]M)", tl)
        printed = m.group(1) if m else None
    for c in cases:
        c["comments"] = "\n".join(re.sub(r"^[-–]\s*", "", l) for l in c.pop("comment_lines"))
    meta = {"date_of_sale": header_date, "printed": printed, "summary_count": summary, "cases_parsed": len(cases)}
    json.dump(cases, open(out_path, "w"), indent=1)
    json.dump(meta, open(out_path.replace(".json", ".meta.json"), "w"), indent=1)
    # self-checks
    st = Counter()
    for c in cases:
        s = c["status"].lower()
        st["active" if s.startswith("active") else "postponed" if s.startswith("postponed") else "cancelled" if s.startswith(("stayed", "money")) else "other"] += 1
    print(json.dumps(meta))
    print("parsed status counts:", dict(st))
    problems = []
    if summary and summary["total"] != len(cases):
        problems.append(f"case count {len(cases)} != Sheriff summary total {summary['total']}")
    if summary and summary["active"] != st["active"]:
        problems.append(f"active {st['active']} != summary {summary['active']}")
    for c in cases:
        if not SALE_ID.match(c["sale_id"] or ""):
            problems.append(f"bad sale id {c['sale_id']!r} p{c['pdf_page']}")
        if not c["parcels"]:
            problems.append(f"{c['sale_id']}: no parcel")
        if not c["address"]:
            problems.append(f"{c['sale_id']}: no address")
        if c["cost_tax_bid"] is None:
            problems.append(f"{c['sale_id']}: no bid")
    ids = [c["sale_id"] for c in cases]
    for k, v in Counter(ids).items():
        if v > 1:
            problems.append(f"duplicate sale id {k}")
    print("PROBLEMS:" if problems else "no parse problems", *problems[:40], sep="\n  " if problems else "")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
