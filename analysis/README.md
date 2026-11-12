# Sheriff sale results analysis

Batches 1–2: the twelve sales December 1, 2025 – November 2, 2026 (results PDFs from
https://sheriffalleghenycounty.com/sheriff-sale-results/). Write-up: the Claude Doc
"Allegheny County Sheriff Sale Results Analysis".

- `results/*.json` — each results PDF parsed with `scripts/parse_listing.py` (+ `.meta.json`).
- `zillow_hist.json` — Zestimates looked up Nov 10, 2026 for every residential property that went
  to auction (key = `address|zip`, same as `state/zillow_cache.json`; extra fields `subject_anchored`
  etc. say whether Zillow values the home off its own recent sale/listing).
- `findings_2026-06_to_2026-11.json` — batch 1 headline numbers (first write-up; grouping since refined).
- `findings_2025-12_to_2026-11.json` — 12-month numbers by batch (b1 = Jun–Nov 2026, b2 = Dec 2025–May 2026, all),
  the out-of-sample winning-bid test and the score tests, as used in the doc.
- `scripts/` — the working scripts (they read/write /tmp/claude-0/an and /tmp/claude-0/res; copy the
  JSON there to rerun): build.py (merge months) → prep.py (classify as of each sale date, outcome,
  deal type) → todo.py (Zillow lookups needed) → analyze.py → refine.py (effective opening bid,
  decree/upset-price split, per-type winning-bid fit, score vs outcome) → compare.py (batch comparison,
  out-of-sample test).

Groups: "Free & clear tax lien" = notes state a court minimum bid below the Cost & Tax bid; "Tax lien (decree)"
= DECREE or UPSET PRICE in the notes with no lower minimum (incl. free-and-clear-for-upset-price).

Next batch: June – November 2025, then January – May 2025.


## Batches 3 and 4 (January-November 2025), added 2026-11-12

-  now holds all 23 months the Sheriff has posted (January 2025 - November 2026).
-  has 943 records. The 301 added for 2025 cover homes bought by outside buyers only;
  the 258 homes the plaintiff took in 2025 were not looked up.
-  is the 23-month result set (, ).
- Method changes from batches 1-2, applied to all 23 months:
  - A winning bid whose case shows up again at a later sale is treated as not completed (forfeited or set
    aside) and left out of the price figures. 101 of 755 checkable third-party sales.
  -  reads every free-and-clear minimum-bid wording seen in the 23 months
    ("O/C F/C MIN BID $8000", "O/C FC MIN BID 15,000.00", "O/C F/C RCVD 3/19/25 $20,000", ...). The live
    classifier's reader ( FC_RE) still needs "F/C" and cents and misses these.
  - Results PDFs printed after deeds issued ("PAID IN ... DEEDED TO ...") show the amount paid in the
    Cost & Tax column, so the opening bid is unknown for those 52 rows.
  - Zillow often shows a later sale ("This home sold for ..."). When that sale is after the sheriff sale and
    at a different price it is recorded as the resale (, ).
- Run order for a new month: build.py, prep.py, todo.py, Zillow lookups merged with zadd.py, analyze.py,
  refine.py, deep.py, extra.py.
