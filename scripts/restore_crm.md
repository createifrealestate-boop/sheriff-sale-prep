# Getting CRM data back from a backup

Backups: `backups/crm-<UTC time>.json.gz`, every 3 hours (workflow "Back up CRM data").
Each holds `data.<Entity>` = every record of that table at that moment.

Find a record's earlier values, e.g. a sheriff property's checklist answers:

    python3 - <<'PY'
    import gzip, json, glob
    for f in sorted(glob.glob("backups/crm-*.json.gz")):
        snap = json.load(gzip.open(f))
        for p in snap["data"]["SheriffProperty"]:
            if p["address"] == "754 Linda Dr":
                print(f, p.get("checklist_state"))
    PY

Put values back with the Base44 tools (update the record's field), never by re-importing a whole
table. Before any entity schema change: read the live schema first, change only the fields meant
to change, and compare old vs new field lists (nested ones too) so nothing is dropped.
