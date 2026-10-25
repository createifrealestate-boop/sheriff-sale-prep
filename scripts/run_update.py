"""One-command update: download -> parse -> classify -> build workbook (with 'what changed').

Usage (from the repo root):
  python3 -I scripts/run_update.py --work /tmp/sheriff_run [--pdf local.pdf] [--no-state]

Reads/writes state/<sale-date>.xlsx in the repo (the previous version, used for the Changes view).
Prints a JSON summary on the last line; writes the workbook to <work>/Sheriff Sale <date> Prep.xlsx.
Exit codes: 0 ok · 2 Sheriff site unreachable · 3 listing link/PDF problem · 4 parse self-check failed
"""
import argparse, datetime as dt, json, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
S = ROOT / "scripts"


def run(args, **kw):
    return subprocess.run([sys.executable, "-I", *map(str, args)], capture_output=True, text=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--pdf", help="use this PDF instead of downloading (testing / manual attach)")
    ap.add_argument("--no-state", action="store_true", help="ignore previous state (treat as first run)")
    a = ap.parse_args()
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)

    if a.pdf:
        pdf, url = Path(a.pdf), "(local file)"
    else:
        r = run([S / "find_listing.py", work / "dl"])
        print(r.stdout.strip())
        if r.returncode:
            print(json.dumps({"ok": False, "stage": "download", "code": r.returncode, "detail": r.stdout.strip() or r.stderr.strip()}))
            sys.exit(r.returncode)
        info = json.loads(r.stdout.strip().splitlines()[-1])
        pdf, url = Path(info["file"]), info["url"]

    cases = work / "cases.json"
    r = run([S / "parse_listing.py", pdf, cases])
    print(r.stdout.strip(), r.stderr.strip()[-500:], sep="\n")
    meta = json.load(open(work / "cases.meta.json")) if (work / "cases.meta.json").exists() else {}
    if r.returncode:
        print(json.dumps({"ok": False, "stage": "parse", "detail": r.stdout.strip()[-800:]}))
        sys.exit(4)

    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", meta.get("date_of_sale") or "")
    if not m:
        print(json.dumps({"ok": False, "stage": "parse", "detail": "no Date of Sale found in the PDF"}))
        sys.exit(4)
    sale_date = dt.datetime.strptime(" ".join(m.groups()), "%B %d %Y").date()

    cls = work / "classified.json"
    r = run([S / "classify.py", cases, cls, "--sale-date", sale_date.isoformat()])
    print(r.stdout.strip(), r.stderr.strip())
    if r.returncode:
        print(json.dumps({"ok": False, "stage": "classify", "detail": r.stderr.strip()[-800:]}))
        sys.exit(4)

    state = ROOT / "state" / f"{sale_date.isoformat()}.xlsx"
    out = work / f"Sheriff Sale {sale_date.isoformat()} Prep.xlsx"
    source = f"{Path(url).name or 'Sale Listings PDF'} (printed {meta.get('printed')})"
    cmd = [S / "build_workbook.py", cls, out, "--sale-date", sale_date.isoformat(), "--source", source]
    if state.exists() and not a.no_state:
        cmd += ["--previous", state]
    r = run(cmd)
    print(r.stdout.strip(), r.stderr.strip())
    if r.returncode:
        print(json.dumps({"ok": False, "stage": "build", "detail": r.stderr.strip()[-800:]}))
        sys.exit(4)

    state.parent.mkdir(exist_ok=True)
    shutil.copy(out, state)  # caller commits state/ so the next run can diff against it

    # summary + changes for the notification text
    import openpyxl
    wb = openpyxl.load_workbook(out, data_only=True)
    ov = wb["Overview"]
    counts = {"ok_to_sell": ov["B4"].value, "almost_ready": ov["B5"].value}
    changes, grab = [], False
    for row in ov.iter_rows(min_row=9, max_row=200, values_only=True):
        if row[0] and str(row[0]).startswith("Changes since"):
            grab = True
            continue
        if grab:
            if not row[0] or str(row[0]).startswith(("Off the sheet", "Update log")):
                break
            if row[0] != "Change" and row[1]:
                changes.append(f"{row[0]}: {row[2]} ({row[3]})" + (f" – {row[5]}" if row[5] else ""))
    print(json.dumps({"ok": True, "sale_date": sale_date.isoformat(), "workbook": str(out), "state_file": str(state),
                      "source": source, "list_printed": meta.get("printed"), **counts,
                      "total_cases": meta.get("cases_parsed"), "changes": changes}))


if __name__ == "__main__":
    main()
