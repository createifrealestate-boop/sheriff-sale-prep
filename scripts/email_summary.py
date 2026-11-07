"""Build the update email from a run. Usage: email_summary.py scored.json run_summary.json out.json [--top 15]
run_summary.json = the JSON line printed last by run_update.py. Writes {subject, html, text}."""
import html, json, sys
sc = json.load(open(sys.argv[1])); rs = json.load(open(sys.argv[2])); out = sys.argv[3]
top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 15
rows = [c for c in sc if c["bucket"] in ("ok", "almost")]
rows.sort(key=lambda c: -(c["prelim_score"] if c.get("prelim_score") is not None else -1))
m = lambda v: "" if v is None else f"${v:,.0f}"
d = rs["sale_date"]
subj = f"Sheriff sale {d} prep: {rs['ok_to_sell']} OK to sell, {rs['almost_ready']} almost ready" + (f" ({len(rs['changes'])} changes)" if rs.get("changes") else "")
ch = "".join(f"<li>{html.escape(x)}</li>" for x in rs.get("changes", [])[:40]) or "<li>No changes since the last update.</li>"
scored_rows = [r for r in rows if r.get("prelim_score") is not None][:top]
tr = "".join(
    f"<tr><td>{c['prelim_score']}</td><td>{html.escape(c['address'])}, {html.escape(c.get('municipality') or '')}</td>"
    f"<td>{'OK' if c['bucket']=='ok' else 'Almost'}</td><td>{m(c.get('opening_bid'))}</td><td>{m(c.get('arv'))}</td>"
    f"<td>{'' if c.get('roi_expected') is None else format(c['roi_expected'],'.0%')}</td><td>{m(c.get('max_bid_target'))}</td></tr>"
    for c in scored_rows)
unscored = sum(1 for c in rows if c.get("prelim_score") is None)
body = f"""<div style="font-family:Arial,sans-serif;font-size:14px">
<h2>Sheriff sale {d}</h2>
<p><b>{rs['ok_to_sell']}</b> OK to sell · <b>{rs['almost_ready']}</b> almost ready · list printed {html.escape(str(rs.get('list_printed')))}</p>
<h3>What changed</h3><ul>{ch}</ul>
<h3>Top {top} by preliminary score</h3>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:13px">
<tr style="background:#1F3A5F;color:#fff"><th>Score</th><th>Property</th><th>Status</th><th>Opening bid</th><th>ARV</th><th>Est. ROI</th><th>Max bid @ target</th></tr>{tr}</table>
<p style="color:#666">Score is a rough Zillow-based screen, not an appraisal or DealScore. {unscored} properties have no Zestimate and need manual research. The full workbook (all columns, Transfer Tax, Glossary) is in the Claude session for this run and in the repo state file.</p></div>"""
text = subj + "\n" + "\n".join(x for x in rs.get("changes", [])[:40])
json.dump({"subject": subj, "html": body, "text": text}, open(out, "w"))
print(subj)
