"""On-Market pipeline: fold new Zillow pulls into the tracked listings, value and score them, and write the CRM
payload, the rent to-do list for the next Claude run, and an alert email. Runs in GitHub Actions
(.github/workflows/onmarket.yml) because it needs the county data (scripts/county.py).

State (state/onmarket/):
  raw/*.json        Zillow pulls written by scripts/onmarket_extract.py in a Claude session (deleted after 14 days)
  listings.json     every tracked listing: {meta, listings: {zpid: {...}}}
  rents.json        Rent Zestimates by zpid
  rent_todo.json    listings worth a Rent Zestimate (read by the next Claude run)
  crm.json          payload for the CRM's On-Market page (scripts/push_onmarket.py)
  alert_email.json  alert email (only when something new reaches the threshold)

Settings: reference/onmarket_config.json; underwriting: reference/deal_model.json (on_market) and scripts/deal.py.
Usage: python3 scripts/onmarket_update.py
"""
import datetime as dt, glob, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deal import underwrite, property_tax, market_costs, M as DM  # noqa: E402
from county import County  # noqa: E402
from risk import danger  # noqa: E402
from rehab_level import level as rehab_level  # noqa: E402
import auction  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ST = ROOT / "state" / "onmarket"
CFG = json.load(open(ROOT / "reference" / "onmarket_config.json"))
TODAY = dt.date.today()
HUD = json.load(open(ST / "hud_safmr.json")) if (ST / "hud_safmr.json").exists() else {}


def load(p, default):
    return json.load(open(p)) if Path(p).exists() else default


def dom_today(r):
    if r.get("dom_floor") is None or not r.get("dom_floor_date"):
        return None
    return r["dom_floor"] + (TODAY - dt.date.fromisoformat(r["dom_floor_date"])).days


def query_addr(r):
    return f"{r['line1']}, {r['city']}, PA {r['zip']}"


def hud_rent(r, p):
    """HUD Small Area FMR for the listing's ZIP and bedroom count (per unit, times the units for a 2-4 unit)."""
    if not HUD:
        return None, "No HUD rent file yet (scripts/hud_safmr.py)."
    t = HUD["zips"].get(str(r.get("zip") or "").zfill(5))
    if not t:
        return None, f"ZIP {r.get('zip')} is not in HUD's Pittsburgh-area Small Area FMR list."
    units = (p or {}).get("units") or 0
    guessed = False
    if units < 1:
        units, guessed = (2, True) if r.get("home_type") == "multiFamily" else (1, False)
    units = min(units, CFG["buy_box"]["max_units"])
    beds = r.get("beds") or (p or {}).get("beds")
    if not beds:
        return None, "No bedroom count, so no HUD rent."
    b = max(0, round(beds / units))
    per = t[b] if b <= 4 else round(t[4] * (1 + 0.15 * (b - 4)))  # HUD: +15% of the 4BR rent per bedroom over 4
    note = (f"HUD FY{HUD['fy']} Small Area FMR, ZIP {str(r.get('zip')).zfill(5)}, {b}BR ${per:,}"
            + (f" x {units} units ({beds:g} beds total{', 2 units assumed' if guessed else ''})" if units > 1 else "")
            + ". Gross rent (incl. utilities); the Section 8 payment standard is 90-110% of it.")
    return per * units, note


def in_box(x):
    B = CFG["buy_box"]
    return (x.get("price") or 0) <= B["max_price"] and x.get("home_type") in B["home_types"]


def apply_raw(L, meta):
    done = set(meta.get("processed", []))
    files = sorted(glob.glob(str(ST / "raw" / "*.json")))
    rents = load(ST / "rents.json", {})
    todo = {t["query"]: t["zpid"] for t in load(ST / "rent_todo.json", [])}
    events = []
    for f in files:
        name = os.path.basename(f)
        if name in done:
            continue
        raw = json.load(open(f))
        day = raw["taken_at"][:10]
        seen = set()
        for x in raw["listings"]:
            z = x["zpid"]
            r = L.get(z)
            if x.get("sold"):
                if r and r.get("status") == "active":
                    r.update(status="gone", gone_date=day, gone_reason="sold", sold_price=x.get("price"))
                continue
            if not in_box(x):
                continue
            seen.add(z)
            if r is None:
                r = L[z] = {"zpid": z, "first_seen": day, "price_history": [], "status": "active"}
                events.append(("new", z))
            elif r.get("status") == "gone":
                r.update(status="active", gone_date=None, gone_reason=None, sold_price=None)
                r["back_on_market"] = day
                events.append(("back", z))
            for k in ("line1", "city", "zip", "lat", "lng", "beds", "baths", "sqft", "lot_sqft", "home_type", "url"):
                if x.get(k) is not None:
                    r[k] = x[k]
            old = r.get("price")
            if old != x["price"]:
                r["price_history"].append({"date": day, "price": x["price"]})
                if old and x["price"] < old:
                    events.append(("drop", z))
                r["price"] = x["price"]
            r["last_seen"] = day
            if x.get("words"):  # listing-word searches (kept for good: descriptions rarely change)
                r["listing_words"] = sorted(set(r.get("listing_words") or []) | set(x["words"]))
            # days on market: a lower bound from the search's days-on-Zillow band (word searches carry none)
            lo = x.get("dom_min")
            if lo is not None and (r.get("dom_floor") is None or lo > dom_today(r)):
                r["dom_floor"], r["dom_floor_date"] = lo, day
        n_active = sum(1 for r in L.values() if r.get("status") == "active")
        if raw.get("kind") == "sweep" and raw.get("complete") and len(seen) < 0.5 * n_active:
            print(f"::warning::sweep {name} saw only {len(seen)} of {n_active} active listings; not marking any gone")
        elif raw.get("kind") == "sweep" and raw.get("complete"):
            for z, r in L.items():
                if r.get("status") == "active" and z not in seen and (r.get("last_seen") or "") < day:
                    r.update(status="gone", gone_date=day, gone_reason="left the market (pending, sold or withdrawn)")
            meta["last_sweep"] = day
        if any(s.get("kw") and not s.get("dom") for s in raw.get("searches") or []):
            meta["words_backfill"] = day  # listing-word searches over the whole buy box
        by_q = {query_addr(r): z for z, r in L.items() if r.get("line1")}
        for q, v in (raw.get("rents") or {}).items():
            z = todo.get(q) or by_q.get(q)
            if z:
                rents[z] = v
        done.add(name)
        meta.setdefault("pulls", []).append({"file": name, "kind": raw.get("kind"), "complete": raw.get("complete"),
                                             "listings": len(raw["listings"]), "rents": len(raw.get("rents") or {})})
    meta["processed"] = sorted(done)[-200:]
    meta["pulls"] = meta.get("pulls", [])[-60:]
    json.dump(rents, open(ST / "rents.json", "w"), indent=0)
    # old raw files
    for f in files:
        if (TODAY - dt.date.fromisoformat(os.path.basename(f)[:10])).days > 14:
            os.remove(f)
    return rents, events


def score_listing(r, C, rents):
    S, A = CFG["score"], CFG["arv"]
    out = {"ideal_box": bool(r.get("beds") in CFG["buy_box"]["ideal_beds"] and (r.get("sqft") or 9e9) <= CFG["buy_box"]["ideal_max_sqft"])}
    pid = r.get("parid") or C.match(r.get("line1"), r.get("zip"))
    p = C.P.get(pid) if pid else None
    if p:
        r["parid"] = pid
        out.update({"parid": pid, "municipality": p["muni"], "neighborhood": p["nbname"], "units": p["units"], "year_built": p["yr"],
                    "county_sqft": p["sqft"], "county_beds": p["beds"], "condition": p["cond"], "assessed_value": p["fmv"],
                    "last_sale_date": p["last_sale"] or None, "last_sale_price": p["last_price"], "homestead": p["homestead"]})
        if p["units"] > CFG["buy_box"]["max_units"]:
            out["out_of_box"] = "more than 4 units"
    sqft = r.get("sqft") or (p or {}).get("sqft")
    out["sqft_used"] = sqft
    rv = rents.get(r["zpid"]) or {}
    out["rent_zestimate"], out["rent_comp"] = rv.get("rent"), rv.get("comp_rent")
    out["hud_rent"], out["hud_rent_note"] = hud_rent(r, p)
    # rent used for the BRRRR math: Rent Zestimate, else Zillow's nearby-rentals figure, else HUD's
    rent, out["rent_source"] = next(((v, s) for v, s in ((out["rent_zestimate"], "Rent Zestimate"),
                                                        (out["rent_comp"], "Zillow nearby rentals (no Rent Zestimate)"),
                                                        (out["hud_rent"], "HUD Small Area FMR (no Zillow rent)")) if v), (None, None))
    out["rent_est"] = rent
    if not p:
        out.update({"score_notes": "No county parcel matched this address, so no county ARV: needs your ARV.", "needs_arv": True,
                    "priority_score": None})
        return out
    a = C.arv(pid, sqft=sqft)
    out.update(a)
    dpts, dwhy = danger(C.assessed_rec(pid), C.area, price=r["price"], arv=a.get("county_arv"))
    out.update({"danger_points": dpts, "danger_reasons": dwhy, "area_flip_rate": (C.area.get(p["muni"]) or {}).get("rate")})
    fl = C.flips_like(pid, beds=r.get("beds"), sqft=sqft, months=S["flip_area_months"])
    out["flips_nearby"] = fl[:6]
    out["flips_nearby_count"] = len(fl)
    out["flips_work"] = len(fl) >= S["flip_area_min_flips"]
    tax, tax_note = property_tax(C.assessed_rec(pid))
    if not a.get("county_arv"):
        out.update({"score_notes": f"No county ARV ({a.get('county_arv_note')}): needs your ARV.", "needs_arv": True,
                    "priority_score": None, "property_tax": tax, "property_tax_note": tax_note})
        return out
    hi = a["county_arv_conf"] == "high"
    arv = a["county_arv"] if hi else round(a["county_arv"] * A["low_conf_factor"], -2)
    out.update({"arv": arv, "arv_source": "county sales (high confidence)" if hi else f"county sales x {A['low_conf_factor']:.0%} (low confidence)",
                "needs_arv": not hi})
    offer = round(r["price"] * DM["on_market"]["offer_pct_of_list"], -2)
    costs = market_costs(p["muni"])
    lvl, _, lvl_why = rehab_level(p["cond"], r.get("listing_words"), r["price"], a.get("county_arv"), p["yr"],
                                  p["last_sale"], p["last_price"], TODAY)
    out.update({"rehab_level": lvl, "rehab_level_why": lvl_why})
    uw = underwrite(offer, arv, sqft, rent, p["fmv"], None, tax, tax_note, costs=costs, level=lvl)
    W = DM["scores"]["total_weights"]
    cp = S["confidence_points"]
    conf_pts = (cp["high_10_comps"] if a["county_arv_comps"] >= 10 else cp["high"]) if hi else cp["low"]
    flip_pts, brrrr_pts = W["flip"] * uw["flip_score"] / 100, W["brrrr"] * uw["brrrr_score"] / 100
    dom = dom_today(r)
    dom_pts = max([b for d, b in S["dom_bonus"] if dom is not None and dom >= d] or [0])
    fa_pts = S["flip_area_bonus"] if out["flips_work"] else 0
    pri = int(round(max(0, min(100, flip_pts + brrrr_pts + conf_pts + fa_pts + dom_pts + dpts))))
    fm = lambda k: "n/a" if uw.get(k) is None else f"${uw[k]:,.0f}"
    notes = (f"ARV ${arv:,.0f} ({out['arv_source']}; {a['county_arv_note']}). Offer ${offer:,.0f} (90% of ${r['price']:,.0f} list); "
             f"rehab ${uw['rehab_est']:,.0f} ({lvl}, ${uw['rehab_rate']}/sqft: {'; '.join(lvl_why)}) + ${uw['contingency']:,.0f} contingency; closing ${costs['closing']:,} + transfer tax ${uw['transfer_tax']:,.0f} "
             f"(buyer's half of {(costs['tt_rate'] or DM['on_market']['transfer_rate_default']):.1%}). At the offer: flip profit ${uw['flip_profit']:,.0f} (flip score {uw['flip_score']}); "
             + (f"BRRRR {uw['refi_terms']}, ${uw['refi_cash_flow']:,.0f}/mo, ${uw['brrrr_cash_left']:,.0f} left (BRRRR score {uw['brrrr_score']})"
                if uw.get("refi_ok") else f"BRRRR: {uw['refi_terms']} (BRRRR score 0)")
             + f". MAO flip {fm('mao_flip_30k')} / {fm('mao_flip_45k')} / {fm('mao_flip_60k')}; MAO BRRRR {fm('mao_brrrr_0k')} / {fm('mao_brrrr_15k')} / {fm('mao_brrrr_30k')}. "
             f"Points: BRRRR {brrrr_pts:.0f}/{W['brrrr']}, flip {flip_pts:.0f}/{W['flip']}, confidence {conf_pts}/20"
             + (f", flips work here +{fa_pts} ({len(fl)} similar flips nearby)" if fa_pts else "")
             + (f", {dom}+ days on market +{dom_pts}" if dom_pts else "")
             + (f", danger {dpts:+d}: {'; '.join(dwhy)}" if dwhy else "") + ".")
    if rent:
        notes += f" Rent used ${rent:,.0f}/mo: {out['rent_source']}."
    out.update(uw)
    out.update({"offer_price": offer, "priority_score": pri, "dom_bonus": dom_pts, "flip_area_bonus": fa_pts,
                "score_points": {"brrrr": round(brrrr_pts, 1), "flip": round(flip_pts, 1), "confidence": conf_pts,
                                 "flips_work": fa_pts, "days_on_market": dom_pts, "danger": dpts},
                "score_notes": notes})
    return out


def main():
    ST.mkdir(parents=True, exist_ok=True)
    state = load(ST / "listings.json", {"meta": {}, "listings": {}})
    L, meta = state["listings"], state["meta"]
    before = {z: r.get("priority_score") for z, r in L.items()}
    rents, events = apply_raw(L, meta)
    C = County()
    AH = auction.load()  # Sheriff sale history by parcel (every results file in analysis/results)
    json.dump(dict(sorted(C.area.items())), open(ROOT / "state" / "area_flip_rates.json", "w"), indent=0)
    for z, r in list(L.items()):
        if r.get("status") == "gone" and r.get("gone_date") and (TODAY - dt.date.fromisoformat(r["gone_date"])).days > CFG["gone"]["keep_days"]:
            del L[z]
            continue
        if r.get("status") != "active":
            continue
        for k in [k for k in r if k not in ("zpid", "first_seen", "price_history", "status", "line1", "city", "zip", "lat", "lng", "beds",
                                             "baths", "sqft", "lot_sqft", "home_type", "url", "price", "last_seen", "dom_floor",
                                             "dom_floor_date", "parid", "back_on_market", "gone_date", "gone_reason", "sold_price",
                                             "listing_words")]:
            r.pop(k)
        r.update(score_listing(r, C, rents))
        r.update(auction.annotate(r, AH))
        r["dom"] = dom_today(r)
    meta.update({"updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "county_data": C.built})
    json.dump(state, open(ST / "listings.json", "w"), indent=0, default=str)

    # rent to-do for the next Claude run
    R = CFG["rent"]
    todo = []
    for z, r in L.items():
        if r.get("status") != "active" or r.get("flip_profit") is None or r["flip_profit"] < R["todo_min_flip_profit"]:
            continue
        have = rents.get(z)
        if have and have.get("date") and (TODAY - dt.date.fromisoformat(have["date"])).days < R["refresh_days"]:
            continue
        todo.append({"zpid": z, "query": query_addr(r), "flip_profit": r["flip_profit"]})
    todo.sort(key=lambda t: -t["flip_profit"])
    json.dump(todo[:R["todo_max_per_run"]], open(ST / "rent_todo.json", "w"), indent=0)

    # CRM payload: active + recently gone
    show = []
    for z, r in L.items():
        if r.get("status") == "gone" and (TODAY - dt.date.fromisoformat(r["gone_date"])).days > CFG["gone"]["show_days"]:
            continue
        p = {k: v for k, v in r.items() if v is not None and k != "dom"}  # the page works out days on market from dom_floor
        p["address"] = r.get("line1")
        p["list_price"] = r.get("price")
        drops = [h["price"] for h in r.get("price_history", [])]
        p["price_drop_total"] = (max(drops) - r["price"]) if drops and r.get("price") else 0
        show.append(p)
    active = [p for p in show if p["status"] == "active"]
    payload = {"run": {"updated_at": meta["updated_at"], "last_sweep": meta.get("last_sweep"), "county_data": C.built,
                       "active": len(active), "gone": len(show) - len(active),
                       "scored": sum(1 for p in active if p.get("priority_score") is not None),
                       "new_today": sum(1 for e in events if e[0] == "new")},
               "listings": show}
    json.dump(payload, open(ST / "crm.json", "w"), indent=0, default=str)

    # alerts
    A = CFG["alerts"]
    hits = []
    for kind, z in dict.fromkeys(events):
        r = L.get(z)
        if not r or r.get("status") != "active":
            continue
        if (r.get("price") or 0) < CFG["buy_box"].get("hide_under", 0):
            continue
        if not (r.get("sqft") or 0) > 0 and not (r.get("county_sqft") or 0) > 0 and not (r.get("beds") or 0) > 0:
            continue  # land (no living area, no bedrooms): hidden on the page by default
        good = (r.get("priority_score") or 0) >= A["min_priority"] or (r.get("brrrr_cash_left") is not None and r["brrrr_cash_left"] <= 0) \
            or (r.get("flip_profit") or 0) >= 30000
        if good and not (kind == "drop" and (before.get(z) or 0) >= A["min_priority"]):
            hits.append((kind, r))
    if hits:
        label = {"new": "New", "drop": "Price drop", "back": "Back on market"}
        rows = "".join(
            f"<tr><td>{label[k]}</td><td><b>{r.get('priority_score') if r.get('priority_score') is not None else '-'}</b></td>"
            f"<td><a href=\"{r.get('url')}\">{r.get('line1')}, {r.get('city')}</a></td><td>${r['price']:,.0f}</td>"
            f"<td>{r.get('beds') or '?'} bd / {r.get('sqft') or '?'} sqft</td><td>${r.get('arv') or 0:,.0f}{'' if not r.get('needs_arv') else ' (check)'}</td>"
            f"<td>${r.get('flip_profit') or 0:,.0f}</td><td>{'' if r.get('brrrr_cash_left') is None else '$' + format(r['brrrr_cash_left'], ',.0f')}</td>"
            f"<td>{'Yes' if r.get('flips_work') else ''}</td><td>{r.get('dom') if r.get('dom') is not None else ''}</td></tr>"
            for k, r in sorted(hits, key=lambda h: -(h[1].get("priority_score") or 0)))
        html = (f"<div style=\"font-family:Arial,sans-serif;font-size:14px\"><h2>On-market: {len(hits)} listing{'s' if len(hits) != 1 else ''} worth a look</h2>"
                "<p>Scored at 90% of list with the county ARV. Open the CRM's On-Market page for the numbers.</p>"
                "<table border=\"1\" cellpadding=\"4\" cellspacing=\"0\" style=\"border-collapse:collapse;font-size:13px\">"
                "<tr style=\"background:#1F3A5F;color:#fff\"><th>Why</th><th>Priority</th><th>Listing</th><th>List</th><th>Size</th><th>ARV</th>"
                "<th>Flip profit</th><th>BRRRR left</th><th>Flips work</th><th>Days on market</th></tr>" + rows + "</table>"
                "<p><a href=\"https://create-if-crm.base44.app/on-market\">Open the On-Market page</a></p></div>")
        json.dump({"subject": f"On-market: {len(hits)} listing{'s' if len(hits) != 1 else ''} worth a look ({TODAY:%b %-d})", "html": html,
                   "text": f"{len(hits)} on-market listings reached the alert threshold. See the CRM On-Market page.", "attach": False,
                   "to": A["to"], "made_at": meta["updated_at"]}, open(ST / "alert_email.json", "w"), indent=1)
    print(json.dumps({**payload["run"], "events": {k: sum(1 for e in events if e[0] == k) for k in ("new", "drop", "back")},
                      "alerts": len(hits), "rent_todo": len(todo)}))


if __name__ == "__main__":
    main()
