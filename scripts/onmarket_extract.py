"""Collect this Claude session's Zillow results into a file for the On-Market pipeline.

The Zillow connector is only reachable from a Claude session, and its results land in the session's transcript
(~/.claude/projects/*/*.jsonl). Rather than retyping hundreds of listings, this reads them back from there.

Every zillow_property_search call made after --since is parsed together with the filters it was called with
(the days-on-Zillow range tells how long each listing has been up; recentlySold searches mark sales). Every
get_rent_zestimate call after --since becomes a rent for the matching listing (by address, via
state/onmarket/rent_todo.json or the listings already known).

Usage: python3 -I scripts/onmarket_extract.py --since 2026-11-20T20:00:00Z --kind daily|sweep [--out state/onmarket/raw]
  --kind sweep : a full pass over the buy box. Listings missing from a complete sweep are marked gone by the update.
  --complete   : with sweep, after any capped search was redone in narrower price bands.
Prints a summary, including any search that hit Zillow's 100-result cap (those need a narrower price band).
"""
import argparse, datetime as dt, glob, json, os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def transcripts():
    files = glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl"))
    return sorted(files, key=os.path.getmtime, reverse=True)[:3]


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict))


def lot_sqft(lot):
    if not lot or lot.get("size") is None:
        return None
    return round(lot["size"] * 43560) if (lot.get("sizeUnits") or "").lower().startswith("acre") else round(lot["size"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--kind", choices=["daily", "sweep"], required=True)
    ap.add_argument("--complete", action="store_true",
                    help="sweep only: every capped search was re-run in narrower bands, so the sweep covers the whole buy box")
    ap.add_argument("--out", default=str(ROOT / "state" / "onmarket" / "raw"))
    a = ap.parse_args()
    since = a.since.replace("Z", "+00:00")
    uses, results = {}, {}
    for f in transcripts():
        for line in open(f, encoding="utf-8", errors="replace"):
            try:
                m = json.loads(line)
            except ValueError:
                continue
            ts = (m.get("timestamp") or "").replace("Z", "+00:00")
            c = (m.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            for b in c:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use" and ts >= since and (
                        b.get("name", "").endswith("zillow_property_search") or b.get("name", "").endswith("get_rent_zestimate")):
                    uses[b["id"]] = (b["name"].rsplit("__", 1)[-1], b.get("input") or {}, ts)
                elif b.get("type") == "tool_result" and b.get("tool_use_id"):
                    results[b["tool_use_id"]] = text_of(b.get("content"))

    listings, searches, rents, capped = {}, [], {}, []
    for uid, (name, inp, ts) in sorted(uses.items(), key=lambda kv: kv[1][2]):
        res = results.get(uid)
        if res is None:
            continue
        if name == "get_rent_zestimate":
            mm = re.search(r"Rent Zestimate for the given address: (.+?) is \$([\d,]+)", res)
            addr = inp.get("address", "")
            rents[addr] = {"rent": int(mm.group(2).replace(",", "")) if mm else None, "date": ts[:10],
                           "note": None if mm else res.strip()[:200]}
            continue
        req = inp.get("request") or {}
        pf = req.get("propertyFiltersRequest") or {}
        sold = "recentlySold" in (pf.get("homeStatuses") or [])
        doz = pf.get("daysOnZillow") or {}
        jm = re.search(r"\{.*\}\s*$", res, re.S)
        if not jm:
            continue
        try:
            data = json.loads(jm.group(0))
        except ValueError:
            continue
        cnt = data.get("resultCounts") or {}
        total, shown = cnt.get("totalMatchingCount"), cnt.get("displayResultsCount")
        searches.append({"at": ts, "sold": sold, "price": pf.get("salePrice"), "dom": doz, "total": total, "shown": shown,
                         "home_types": pf.get("homeTypes"), "statuses": pf.get("homeStatuses")})
        if total is not None and shown is not None and total > shown:
            capped.append(searches[-1])
        for r in data.get("results") or []:
            x = r.get("result") or {}
            url = x.get("homeDetailsPageUrl") or ""
            zm = re.search(r"/(\d+)_zpid", url)
            if not zm:
                continue
            fa, ll = x.get("formattedAddress") or {}, (x.get("geoRegion") or {}).get("latLong") or {}
            rec = {"zpid": zm.group(1), "line1": fa.get("line1"), "city": fa.get("city"), "zip": fa.get("postalCode"),
                   "lat": ll.get("latitude"), "lng": ll.get("longitude"), "beds": x.get("bedroomCount"), "baths": x.get("bathroomCount"),
                   "sqft": x.get("livingAreaSquareFeet"), "lot_sqft": lot_sqft(x.get("lotArea")), "home_type": x.get("homeType"),
                   "price": (x.get("price") or {}).get("filteredPrice"), "url": url.split("?")[0], "seen_at": ts,
                   "sold": sold, "dom_min": doz.get("min", 0) if not sold else None, "dom_max": doz.get("max") if not sold else None}
            old = listings.get((rec["zpid"], sold))
            if old and not sold:  # seen in two DOM bands (edge of a band): keep the tighter, higher floor
                rec["dom_min"] = max(old["dom_min"] or 0, rec["dom_min"] or 0)
            listings[(rec["zpid"], sold)] = rec

    now = dt.datetime.now(dt.timezone.utc)
    out = {"kind": a.kind, "taken_at": now.isoformat(timespec="seconds"), "since": a.since,
           "complete": a.kind == "sweep" and (not capped or a.complete), "searches": searches,
           "listings": list(listings.values()), "rents": rents}
    Path(a.out).mkdir(parents=True, exist_ok=True)
    path = Path(a.out) / f"{now:%Y-%m-%dT%H%MZ}-{a.kind}.json"
    json.dump(out, open(path, "w"), indent=0)
    n_sale = sum(1 for k in listings if not k[1])
    print(json.dumps({"file": str(path), "searches": len(searches), "for_sale": n_sale, "sold": len(listings) - n_sale,
                      "rents": len(rents), "capped_searches": [{"price": c["price"], "dom": c["dom"], "total": c["total"]} for c in capped]}))


if __name__ == "__main__":
    main()
