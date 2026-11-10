"""One-command update: download -> parse -> classify -> build workbook (with 'what changed').

Usage (from the repo root):
  python3 -I scripts/run_update.py --work /tmp/sheriff_run [--pdf local.pdf] [--no-state] [--todo-only | --reuse]

Two-pass flow (Zillow lookups happen between the passes, done by the calling session through the Zillow connector):
  pass 1: --todo-only  download+parse+classify, write <work>/zillow_todo.json (properties missing from
                       state/zillow_cache.json or older than 45 days), no workbook, no state written
  (session looks each up, merges with scripts/zcache_add.py into state/zillow_cache.json)
  pass 2: --reuse      reuse <work>/cases.json etc. from pass 1, score, build workbook, write state
Without either flag it does everything in one go using whatever is already cached.

Reads/writes state/<sale-date>.xlsx in the repo (the previous version, used for the Changes view).
Prints a JSON summary on the last line; writes the workbook to <work>/Sheriff Sale <date> Prep.xlsx.
Exit codes: 0 ok · 2 Sheriff site unreachable · 3 listing link/PDF problem · 4 parse self-check failed · 5 Sheriff still shows a past sale's list
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
    ap.add_argument("--todo-only", action="store_true", help="stop after classify and write zillow_todo.json")
    ap.add_argument("--reuse", action="store_true", help="skip download/parse/classify; reuse files from a --todo-only pass")
    a = ap.parse_args()
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)

    cls = work / "classified.json"
    if a.reuse:
        info = json.load(open(work / "run_info.json"))
        url, sale_date = info["url"], dt.date.fromisoformat(info["sale_date"])
        meta = json.load(open(work / "cases.meta.json"))
    else:
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

        today_et = dt.datetime.now(__import__("zoneinfo").ZoneInfo("America/New_York")).date()
        if sale_date < today_et:
            print(json.dumps({"ok": False, "stage": "stale-list", "code": 5,
                              "detail": f"The Sheriff's page still shows the list for the {sale_date} sale, which has already happened. The next list has not been posted yet; nothing was built."}))
            sys.exit(5)

        r = run([S / "classify.py", cases, cls, "--sale-date", sale_date.isoformat()])
        print(r.stdout.strip(), r.stderr.strip())
        if r.returncode:
            print(json.dumps({"ok": False, "stage": "classify", "detail": r.stderr.strip()[-800:]}))
            sys.exit(4)

        json.dump({"url": url, "sale_date": sale_date.isoformat()}, open(work / "run_info.json", "w"))

    cache = ROOT / "state" / "zillow_cache.json"
    if a.todo_only:
        r = run([S / "zillow_todo.py", cls, cache])
        (work / "zillow_todo.json").write_text(r.stdout)
        todo = json.loads(r.stdout or "[]")
        print(json.dumps({"ok": True, "stage": "todo", "sale_date": sale_date.isoformat(), "zillow_todo": len(todo),
                          "todo_file": str(work / "zillow_todo.json")}))
        return
    scored = work / "scored.json"
    r = run([S / "score.py", cls, cache, scored])
    print(r.stdout.strip(), r.stderr.strip()[-300:])
    if r.returncode:
        print("score step failed; building without scores")
        scored = cls

    state = ROOT / "state" / f"{sale_date.isoformat()}.xlsx"
    out = work / f"Sheriff Sale {sale_date.isoformat()} Prep.xlsx"
    source = f"{Path(url).name or 'Sale Listings PDF'} (printed {meta.get('printed')})"
    cmd = [S / "build_workbook.py", scored, out, "--sale-date", sale_date.isoformat(), "--source", source]
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
    summary = {"ok": True, "sale_date": sale_date.isoformat(), "workbook": str(out), "state_file": str(state),
               "source": source, "list_printed": meta.get("printed"), **counts,
               "total_cases": meta.get("cases_parsed"), "changes": changes}
    if not a.no_state:  # data for the CRM's Sheriff Sale page (pushed by the GitHub workflow)
        r = run([S / "crm_payload.py", scored, json.dumps(summary), cache, ROOT / "state" / "crm.json"])
        print(r.stdout.strip(), r.stderr.strip()[-300:])
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
