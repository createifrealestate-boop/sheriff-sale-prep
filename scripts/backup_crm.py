"""Off-site backup of the CRM's data (Base44 app create-if-crm).

Calls the CRM's backupData function (same x-api-key as the sheriff ingest) and writes
backups/crm-YYYY-MM-DDTHH-MMZ.json.gz. Keeps every backup from the last 14 days and one a day
for 90 days; older ones are deleted. Started 2026-11-20 after a schema change wiped the sheriff
checklist answers, because Base44's own data history isn't on for this workspace.

Restore: scripts/restore_crm.md explains how to find a record's earlier values.
Env: CRM_API_KEY. Exit 1 on failure so the workflow run shows red.
"""
import datetime as dt, gzip, json, os, sys, urllib.request
from pathlib import Path

URL = "https://create-if-crm.base44.app/api/apps/6a672f8ccee4376a8dfd5387/functions/backupData"
ROOT = Path(__file__).resolve().parent.parent / "backups"


def main():
    key = os.environ.get("CRM_API_KEY", "").strip()
    if not key:
        print("::error::CRM_API_KEY not set"); sys.exit(1)
    req = urllib.request.Request(URL, data=b"{}", method="POST",
                                 headers={"content-type": "application/json", "x-api-key": key})
    with urllib.request.urlopen(req, timeout=300) as r:
        snap = json.load(r)
    bad = {k: v for k, v in snap.get("counts", {}).items() if not isinstance(v, int)}
    ROOT.mkdir(exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    path = ROOT / f"crm-{now:%Y-%m-%dT%H-%MZ}.json.gz"
    with gzip.open(path, "wt") as f:
        json.dump(snap, f, separators=(",", ":"), default=str)
    total = sum(v for v in snap["counts"].values() if isinstance(v, int))
    print(f"backup: {path.name}, {total} records in {len(snap['counts'])} tables, {path.stat().st_size/1e6:.1f} MB")
    if bad:
        print(f"::warning::tables that could not be read: {bad}")
    # retention
    keep_day = set()
    for p in sorted(ROOT.glob("crm-*.json.gz"), reverse=True):
        try:
            t = dt.datetime.strptime(p.name[4:21], "%Y-%m-%dT%H-%M").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        age = (now - t).days
        if age <= 14:
            continue
        if age <= 90 and t.date() not in keep_day:
            keep_day.add(t.date()); continue
        p.unlink(); print("pruned", p.name)


if __name__ == "__main__":
    main()
