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
