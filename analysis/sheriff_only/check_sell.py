"""Out-of-sample checks for the sell-chance model: bands on later months, and the Nov 2, 2026 prep list."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fit_sell import *  # noqa
import openpyxl
rows, by, sales = load()
pop = build(rows)
for test_from in ["2026-05-01", "2026-11-01"]:
    tr = [c for c in pop if c["sale_date"] < test_from]; te = [c for c in pop if c["sale_date"] >= test_from]
    m, names, firms, plfs = fit(tr); p = predict(m, names, firms, plfs, te)
    print(f"== trained before {test_from}, tested on {len(te)} cleared listings after")
    for lo_, hi_, lab in [(0.6, 1.01, "High (60%+)"), (0.3, 0.6, "Medium (30-60%)"), (0, 0.3, "Low (under 30%)")]:
        k = [i for i, x in enumerate(p) if lo_ <= x < hi_]
        print(f"   {lab:16} n={len(k):3}  outside buyer won {np.mean([te[i]['y'] for i in k]) if k else 0:.0%}")
# Nov 2 prep list: the 104 OK to Sell properties the workbook listed on Nov 1, model trained on Jan 2025 - Oct 2026
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
wb = openpyxl.load_workbook(os.path.join(REPO, "state", "2026-11-02.xlsx"), read_only=True)
D = list(wb["_Data"].iter_rows(values_only=True)); H = D[0]; D = [dict(zip(H, r)) for r in D[1:]]
res = {c["case_no"]: c for c in rows if c["sale_date"] == "2026-11-02"}
ok = [res[d["case_no"]] for d in D if d["bucket"] == "ok" and d["case_no"] in res]
tr = [c for c in pop if c["sale_date"] < "2026-11-01"]
m, names, firms, plfs = fit(tr); p = predict(m, names, firms, plfs, ok)
print(f"== Nov 2 prep list, {len(ok)} OK to Sell properties (model trained on earlier sales)")
for lo_, hi_, lab in [(0.6, 1.01, "High"), (0.3, 0.6, "Medium"), (0, 0.3, "Low")]:
    k = [i for i, x in enumerate(p) if lo_ <= x < hi_]
    C = collections.Counter(ok[i]["outcome"] for i in k)
    print(f"   {lab:7} n={len(k):3}  outside buyer {C['sold_3p']:2}  plaintiff {C['plaintiff_overbid']+C['plaintiff_costs']:2}  postponed {C['postponed']:2}  stayed {C['stayed']:2}")
print("   expected outside-buyer wins", round(float(sum(p))), "actual", sum(1 for c in ok if c["outcome"] == "sold_3p"))
