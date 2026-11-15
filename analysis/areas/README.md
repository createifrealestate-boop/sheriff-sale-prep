# Area analysis (added 2026-11-14)

Write-up: Claude Doc "Sheriff Sale Areas: Where Properties Sell and How".
- `area.py` - municipality, price-tier, ZIP, street and pending-case tables (residential, Jan 2025 - Nov 2026);
  writes `muni_stats.json`. Uses `../sheriff_only/base.py` and `values.json` (price / Zillow value and later
  resale per outside purchase, from the 23-month value analysis).
- `dec7.py` - the current prep list (`state/crm.json`) against each municipality's history.
- `output.txt`, `dec7_output.txt` - full output.
