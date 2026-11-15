# Sheriff-data-only analysis (added 2026-11-13)

Uses nothing but the Sheriff's results PDFs (Jan 2025 - Nov 2026): outcomes, prices, opening bids,
boxes, notes, parties, dates. No Zillow values or rehab estimates.
Write-up: Claude Doc "Sheriff Sale Results: What the Sheriff's Own Data Shows".

- `cases.json.gz` - one row per case per sale (8,394), from `../scripts/prep.py`.
- `base.py` - derived fields: group (free & clear min bid / decree / plain tax lien / mortgage),
  effective opening bid, forfeits, months on the list, "cleared for this sale" dates in the notes.
- `a1.py` funnel, monthly, lifecycle, cohort. `a2.py` prices and multiples. `a3.py` mortgage plaintiffs,
  bank bids vs reassessed damages. `a4.py` tax-lien plaintiffs, municipalities, months, owner type.
  `a5.py` postponements and what predicts the next date. `a6.py` forfeits, free & clear, buyers named on deeds.
  `a7.py` position, sale size, 3129.3. `a8.py`/`a10.py` Nov 2 prep list vs result. `a9.py` cleared listings.
  `a11.py` named buyers per sale.
- `output.txt` - full output of all scripts. Run: `python3 -I a1.py` etc. from this folder.

## Sell odds model (added 2026-11-15)

- `fit_sell.py` fits the chance an outside buyer wins a cleared residential listing (logistic model on sale
  type, free & clear minimum bid, decree, owner type, FORF/FHA/bankruptcy/reassessed damages in the notes,
  months on the list, law firm, plaintiff) and writes `reference/sell_model.json`. Refit after adding new
  months of results: `python3 -I fit_sell.py`.
- `check_sell.py` prints the out-of-sample checks (later months, and the Nov 2, 2026 prep list).
- The live pipeline applies it with `scripts/sell_chance.py` (same feature code), adding sell_chance,
  sell_label (High 60%+ / Medium 30-60% / Low) and sell_reasons to the workbook, email and CRM.
