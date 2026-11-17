"""Build the update email from a run. Usage: email_summary.py scored.json run_summary.json out.json [--top 15] [--attached]
run_summary.json = the JSON line printed last by run_update.py. Writes {subject, html, text}."""
import html, json, sys
sc = json.load(open(sys.argv[1])); rs = json.load(open(sys.argv[2])); out = sys.argv[3]
top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 15
rows = [c for c in sc if c["bucket"] in ("ok", "almost")]
rows.sort(key=lambda c: -(c["prelim_score"] if c.get("prelim_score") is not None else -1))
m = lambda v: "" if v is None else f"${v:,.0f}"
d = rs["sale_date"]
hot = rs.get("new_hot") or []
subj = (f"NEW likely-to-sell: {len(hot)} | " if hot else "") + f"Sheriff sale {d} prep: {rs['ok_to_sell']} OK to sell, {rs['almost_ready']} almost ready" + (f" ({len(rs['changes'])} changes)" if rs.get("changes") else "")
ch = "".join(f"<li>{html.escape(x)}</li>" for x in rs.get("changes", [])[:40]) or "<li>No changes since the last update.</li>"
mao = lambda v: "" if v is None else ("none" if v <= 0 else f"${v:,.0f}")
scored_rows = [r for r in rows if r.get("prelim_score") is not None][:top]
tr = "".join(
    f"<tr><td>{c['prelim_score']}</td><td>{html.escape(c['address'])}, {html.escape(c.get('municipality') or '')}</td>"
    f"<td>{c.get('sell_label') or ''}{'' if c.get('sell_chance') is None else ' ' + format(c['sell_chance'], '.0%')}</td>"
    f"<td>{'OK' if c['bucket']=='ok' else 'Almost'}</td><td>{m(c.get('opening_bid'))}</td><td>{m(c.get('arv'))}</td>"
    f"<td>{c.get('brrrr_score', '')} / {c.get('flip_score', '')}</td>"
    f"<td>{mao(c.get('mao_brrrr_0k'))}</td><td>{mao(c.get('mao_flip_30k'))}</td></tr>"
    for c in scored_rows)
unscored = sum(1 for c in rows if c.get("prelim_score") is None)
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from hot import rows_html, TABLE_HEAD  # noqa: E402
hot_html = (f"<h3 style='color:#1d6b38'>New free &amp; clear / decree / High sell odds since the last update ({len(hot)})</h3>"
            f"{TABLE_HEAD}{rows_html(hot)}</table>") if hot else ""
body = f"""<div style="font-family:Arial,sans-serif;font-size:14px">
<h2>Sheriff sale {d}</h2>
<p><b>{rs['ok_to_sell']}</b> OK to sell · <b>{rs['almost_ready']}</b> almost ready · list printed {html.escape(str(rs.get('list_printed')))}</p>
{hot_html}<h3>What changed</h3><ul>{ch}</ul>
<h3>Top {top} by preliminary score</h3>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:13px">
<tr style="background:#1F3A5F;color:#fff"><th>Score</th><th>Property</th><th>Sell odds</th><th>Status</th><th>Opening bid</th><th>ARV</th><th>BRRRR / flip score</th><th>MAO BRRRR ($0 left)</th><th>MAO flip ($30k profit)</th></tr>{tr}</table>
<p><b>OK to Sell with High sell odds</b> (chance an outside buyer wins, from the Sheriff's past results): {", ".join(html.escape(c['address']) for c in sorted([r for r in rows if r.get('sell_label') == 'High' and r['bucket'] == 'ok'], key=lambda r: -r['sell_chance'])) or "none"}.</p>
<p style="color:#666">Sell odds come from 23 months of the Sheriff's results: High = 60%+, Medium = 30-60%, Low = under 30%; for Almost Ready properties they assume the Sheriff clears them. Score = BRRRR (45) + flip (35) + data confidence (20) at the assumed winning bid, using your underwriting numbers; MAOs are the highest price that still leaves $0 in the deal (BRRRR) or $30k profit (flip). Zillow-based, not an appraisal. {unscored} properties have no Zestimate and need manual research. {"The full workbook (all columns, Transfer Tax, Glossary) is attached." if "--attached" in sys.argv else "The full workbook (all columns, Transfer Tax, Glossary) is in the Claude session for this run and in the repo state file."}</p></div>"""
text = subj + "\n" + "".join(f"NEW: {h['address']}, {h['municipality']}: {h['why']}\n" for h in hot) + "\n".join(x for x in rs.get("changes", [])[:40])
json.dump({"sale_date": d, "subject": subj, "html": body, "text": text}, open(out, "w"))
print(subj)
