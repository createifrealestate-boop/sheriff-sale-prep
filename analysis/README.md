# Sheriff sale results analysis

Batch 1: the six sales June 1 – November 2, 2026 (results PDFs from
https://sheriffalleghenycounty.com/sheriff-sale-results/). Write-up: the Claude Doc
"Allegheny County Sheriff Sale Results Analysis".

- `results/*.json` — each results PDF parsed with `scripts/parse_listing.py` (+ `.meta.json`).
- `zillow_hist.json` — Zestimates looked up Nov 10, 2026 for every residential property that went
  to auction (key = `address|zip`, same as `state/zillow_cache.json`; extra fields `subject_anchored`
  etc. say whether Zillow values the home off its own recent sale/listing).
- `findings_2026-06_to_2026-11.json` — the headline numbers used in the doc.
- `scripts/` — the working scripts (they read/write /tmp/claude-0/an and /tmp/claude-0/res; copy the
  JSON there to rerun): build.py (merge months) → prep.py (classify as of each sale date, outcome,
  deal type) → todo.py (Zillow lookups needed) → analyze.py → refine.py (effective opening bid,
  decree split, per-type winning-bid fit, score vs outcome).

Next batch: December 2025 – May 2026.
