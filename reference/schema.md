# cases.json — contract between the PDF parser and the classifier

One object per case on the Sheriff's Sale Listings PDF (all statuses, all property types).

| key | type | example | notes |
|---|---|---|---|
| sale_id | str | "37JUL19" | Sheriff sale number; the key used to keep the user's entries |
| case_no | str | "GD-17-006258" | |
| sale_type_listed | str | "Real Estate Sale - Sci Fa Sur Tax Lien" | verbatim |
| sale_category | str | "Tax lien (Sci Fa sur tax lien)" | one of: Tax lien (Sci Fa sur tax lien) · Mortgage foreclosure · HOA / condo assessment judgment · Other judgment execution · Municipal lien |
| status | str | "Active" / "Postponed to 4/5/2027" / "Stayed" / "Money Made" | verbatim-ish; only `Active…` can be on the sheet |
| postponed_to | str\|null | "4/5/2027" | |
| address, city, zip | str | "516 High St", "Elizabeth", "15037" | |
| municipality | str | "Elizabeth Twp" | as printed; mapped to the Transfer Tax table via reference/muni_map.json, then fuzzy |
| parcels | str | "1269-D-75 ; 1269-D-76" | `;`-joined for multi-tract |
| tracts | int | 1 | |
| property_type | str | "Residential / unspecified ; Vacant Land" | `;`-joined per tract. Non-residential = Commercial, Industrial, Vacant Land/Commercial/Agricultural |
| cost_tax_bid | float | 84642.45 | |
| plaintiff, plaintiff_attorney, defendant | str | | |
| owner_type | str | "Individual" / "Estate / heirs / trust" / "Entity (LLC/LP/Inc)" | |
| box_service, box_3129_2, box_3129_3, box_ok | bool | | read from checkbox positions in the PDF layout, never guessed from text order |
| comments | str | "NEED O/C FOR 1-5-26 ...\nNEED 3129.3 FOR 10-5-26" | verbatim, one Sheriff note per line, newest first as printed |
| pdf_page | int | 2 | |

The classifier derives everything else (outstanding items, flags, F&C min bid, recalculated C+T,
reassessed damages, opening bid, portal parcel ID, transfer-tax municipality, bucket).
