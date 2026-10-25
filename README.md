# sheriff-sale-prep
Scripts and state for the Allegheny County sheriff-sale prep skill.
- scripts/find_listing.py  download the current Sale Listings PDF
- scripts/parse_listing.py PDF -> cases.json
- scripts/classify.py      decode notes, sort OK to Sell / Almost Ready
- scripts/build_workbook.py build the workbook (+ "what changed" vs previous)
- reference/               transfer-tax table, municipality map, glossary, schema
- state/                   latest workbook per auction (used for the changes view)
