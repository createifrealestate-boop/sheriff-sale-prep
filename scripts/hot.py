"""Track the "hot" properties for a sale and report which ones are new since the last check.

Hot = on OK to Sell or Almost Ready AND (free & clear minimum bid, decree, or High sell odds). These sell to
outside buyers about 9 times in 10, and most free & clear orders show up in the final weeks. The set already
reported is kept in state/hot_<sale_date>.json (key = sale_id|bucket, so a property moving from Almost Ready
to OK to Sell is reported again).

Library: new_hot(cases, sale_date, state_dir, save=True) -> list of dicts.
CLI (final-week alert days; no Zillow needed):
  python3 -I hot.py --work /tmp/sheriff_run --sale-date YYYY-MM-DD [--days-until N]
  Reads <work>/classified.json (from run_update.py --todo-only), computes sell odds, and when something is new
  writes state/alert_email.json (picked up by the Email workbook workflow). Prints {"new": n, ...}.
"""
import argparse, html, json, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sell_chance import chance, group, REF  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def why(c):
    g = c.get("sell_group") or group(c)
    if g == "fc":
        from fcmin import fc_min
        mn = fc_min(c.get("comments"))[1] or c.get("fc_min_bid")
        return f"free & clear minimum bid{f' ${mn:,.0f}' if mn else ''}"
    if g == "decree":
        return "decree (sells at the upset price)"
    return f"High sell odds ({c['sell_chance']:.0%})"


def is_hot(c):
    return c.get("bucket") in ("ok", "almost") and ((c.get("sell_group") or group(c)) in ("fc", "decree") or c.get("sell_label") == "High")


def new_hot(cases, sale_date, state_dir=ROOT / "state", save=True):
    p = Path(state_dir) / f"hot_{sale_date}.json"
    seen = set(json.load(open(p))["seen"]) if p.exists() else set()
    out = []
    for c in cases:
        if not is_hot(c):
            continue
        k = f"{c['sale_id']}|{c['bucket']}"
        if k in seen:
            continue
        seen.add(k)
        out.append({"sale_id": c["sale_id"], "address": c.get("address"), "municipality": c.get("municipality"),
                    "bucket": c["bucket"], "why": why(c), "sell_chance": c.get("sell_chance"),
                    "opening_bid": c.get("opening_bid"), "plaintiff": c.get("plaintiff")})
    if save:
        p.parent.mkdir(exist_ok=True)
        json.dump({"sale_date": sale_date, "seen": sorted(seen),
                   "updated": datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M")}, open(p, "w"), indent=1)
    out.sort(key=lambda h: -(h["sell_chance"] or 0))
    return out


def rows_html(hot):
    m = lambda v: "" if v is None else f"${v:,.0f}"
    return "".join(f"<tr><td>{html.escape(h['address'] or '')}, {html.escape(h['municipality'] or '')}</td>"
                   f"<td>{'OK to Sell' if h['bucket'] == 'ok' else 'Almost Ready'}</td><td>{html.escape(h['why'])}</td>"
                   f"<td>{'' if h['sell_chance'] is None else format(h['sell_chance'], '.0%')}</td><td>{m(h['opening_bid'])}</td></tr>"
                   for h in hot)


TABLE_HEAD = ('<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:13px">'
              '<tr style="background:#1F3A5F;color:#fff"><th>Property</th><th>List</th><th>Why</th><th>Sell odds</th>'
              '<th>Opening bid</th></tr>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--sale-date", required=True)
    ap.add_argument("--days-until")
    a = ap.parse_args()
    work = Path(a.work)
    cases = json.load(open(work / "classified.json"))
    model = json.load(open(REF / "sell_model.json"))
    for c in cases:
        if c.get("bucket") in ("ok", "almost"):
            c["sell_chance"], c["sell_label"], c["sell_reasons"] = chance(c, model, a.sale_date)
            c["sell_group"] = group(c)
    hot = new_hot(cases, a.sale_date)
    meta = json.load(open(work / "cases.meta.json")) if (work / "cases.meta.json").exists() else {}
    res = {"new": len(hot), "sale_date": a.sale_date, "list_printed": meta.get("printed"), "hot": hot}
    if hot:
        now = datetime.now(ZoneInfo("America/New_York"))
        subj = (f"Sheriff sale {a.sale_date}: {len(hot)} new likely-to-sell propert{'y' if len(hot) == 1 else 'ies'} "
                f"({', '.join(h['address'] for h in hot[:3])}{'...' if len(hot) > 3 else ''})")
        body = (f'<div style="font-family:Arial,sans-serif;font-size:14px"><h2>New since the last check</h2>'
                f"<p>The Sheriff's list printed {html.escape(str(meta.get('printed')))} has {len(hot)} new propert"
                f"{'y' if len(hot) == 1 else 'ies'} with a free &amp; clear minimum bid, a decree, or High sell odds. "
                f"Over the last 23 months, cleared properties like these sold to outside buyers 7 to 9 times in 10.</p>{TABLE_HEAD}{rows_html(hot)}</table>"
                f'<p style="color:#666">Final-week alert{f" ({a.days_until} days to the sale)" if a.days_until else ""}, checked '
                f"{now:%a %b %-d %-I:%M %p} ET. The full workbook and CRM update come with the next regular update. "
                f"Sell odds are from the Sheriff's past results, not a guarantee; the Sheriff finalizes the list the morning of the sale.</p></div>")
        text = subj + "\n" + "\n".join(f"- {h['address']}, {h['municipality']}: {h['why']}" for h in hot)
        json.dump({"sale_date": a.sale_date, "subject": subj, "html": body, "text": text, "attach": False,
                   "checked": now.isoformat()}, open(ROOT / "state" / "alert_email.json", "w"))
        res["email"] = "state/alert_email.json"
    print(json.dumps(res, default=str))


if __name__ == "__main__":
    main()
