# On-Market run (the daily Claude scheduled task follows this)

Pulls Zillow listings for the On-Market page in the CRM. Claude does only the Zillow part (the connector is only
reachable from a Claude session); GitHub Actions (`.github/workflows/onmarket.yml`) does the valuing, scoring,
CRM update and alert email. Nobody is watching: don't ask questions, make the reasonable call, say what you did.

## 0. Setup
- Repo: if `/home/claude/sheriff-sale-prep/scripts/onmarket_extract.py` is missing, `add_repo` (owner
  `createifrealestate-boop`, repo `sheriff-sale-prep`, access `push`) and clone once to `/home/claude/sheriff-sale-prep`.
- Note the start time: `T=$(date -u +%Y-%m-%dT%H:%M:%SZ)`. Every Zillow call after it is collected automatically
  from this session's transcript by `scripts/onmarket_extract.py`; there is no need to copy results anywhere.
- Kind of run: **sweep** if `state/onmarket/listings.json` has no `meta.last_sweep`, or it is 7+ days old;
  otherwise **daily**.

## 1. Zillow searches (`zillow_property_search`)
Base request for every for-sale search (the buy box):
```json
{"propertySearchRegionFiltersRequest": {"propertySearchRegions": [{"name": "Allegheny County, PA", "regionDisplayName": "Allegheny County"}]},
 "propertyFiltersRequest": {"salePrice": {"min": LO, "max": HI}, "homeTypes": ["singleFamily", "multiFamily"],
   "homeStatuses": ["fsba", "fsbo"], "forSaleListingStatuses": ["active"],
   "exclude": ["pending", "underContract", "contingent"], "daysOnZillow": {DOM}}}
```
Zillow returns at most 100 listings per search. When a result says `totalMatchingCount` > `displayResultsCount`,
split that price band in two (same days-on-Zillow band) and search both halves; repeat until none is capped.

**Daily**
1. New listings: `daysOnZillow {"max": 2}`, price bands 0-100000 and 100001-200000 (split if capped).
2. Recently sold (to move them to Gone): `homeStatuses ["recentlySold"]`, `daysOnZillow {"max": 7}`, price 0-250000,
   same region and home types, no `forSaleListingStatuses`/`exclude` (split if capped).

**Sweep** (also catches price changes, days on market and listings that went pending or were withdrawn)
- Every combination of days-on-Zillow band `{"max": 29}`, `{"min": 30, "max": 89}`, `{"min": 90, "max": 119}`,
  `{"min": 120, "max": 149}`, `{"min": 150, "max": 179}`, `{"min": 180}` and price band 0-50000, 50001-75000,
  75001-100000, 100001-125000, 125001-150000, 150001-175000, 175001-200000 (42 searches; split any that are capped).
- Plus the recently-sold search above.
- Send independent searches in parallel batches.

## 2. Save and push the pull
```bash
cd /home/claude/sheriff-sale-prep
python3 -I scripts/onmarket_extract.py --since "$T" --kind daily   # or --kind sweep
```
It prints the counts and any `capped_searches` still not covered by narrower ones; if there are any, run the
missing narrower searches and run the extract again (same `--since`; delete the earlier file first).
Then `git add state/onmarket/raw && git commit -m "On-Market pull <date> (<kind>)" && git push` (commit message ends
with the attribution lines the session gives). The push starts the workflow.

## 3. Rents
1. Wait for the "On-Market update" workflow run started by the push to finish (`gh run list --workflow onmarket.yml -L 1`,
   then `gh run watch <id>`; a cold county-data build takes ~5 minutes, otherwise ~1 minute), then `git pull`.
2. `T2=$(date -u +%Y-%m-%dT%H:%M:%SZ)`. For each entry in `state/onmarket/rent_todo.json` (up to 150), call
   `get_rent_zestimate` with its `query` exactly as written (parallel batches of ~15).
3. `python3 -I scripts/onmarket_extract.py --since "$T2" --kind daily`, commit and push as above. The workflow
   rescores with the rents (no new searches are in this file, so nothing else changes).

## 4. Report
Say: kind of run, listings found (new / sold / total active from the workflow's "Update listings" output), rents
added, and whether an alert email went out (the workflow's "Send alert" step). If the Zillow tool is missing or
fails, say so and stop; never push an empty sweep (it would mark every listing gone; the extract refuses a sweep
with no for-sale listings).
