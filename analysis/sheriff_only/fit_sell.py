"""Fit the "chance an outside buyer wins" model from the Sheriff's own results (no outside values).

Population: residential listings the Sheriff's notes cleared for that sale date ("OK TO SELL <date>" /
"ALL DOCS RCVD <date>"), Jan 2025 - Nov 2026. Target: an outside (third-party) buyer won at that sale
(forfeited bids count: the auction happened and an outside buyer won it).
Features are things the pre-sale list already shows: sale type, owner type, FORF / FHA / bankruptcy /
reassessed damages in the notes, months on the list, the plaintiff's law firm and the plaintiff.

Writes ../../reference/sell_model.json (used by scripts/sell_chance.py) and prints the out-of-sample test.
Usage: python3 -I fit_sell.py [--test-from 2026-05-01]
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base import *  # noqa
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from sell_chance import features, firm_key, plaintiff_key  # noqa: E402  (same feature code as the live pipeline)

MIN_FIRM, MIN_PLF = 25, 20


def build(rows):
    pop = [c for c in rows if c.get("residential") and c["sd"] in c["ok_dates"]]
    for c in pop:
        c["y"] = 1 if c["outcome"] == "sold_3p" else 0
    return pop


def vocab(train):
    fc = collections.Counter(firm_key(c) for c in train)
    pc = collections.Counter(plaintiff_key(c) for c in train)
    return ({k for k, v in fc.items() if v >= MIN_FIRM and k},
            {k for k, v in pc.items() if v >= MIN_PLF and k})


def matrix(pop, names):
    X = np.zeros((len(pop), len(names)))
    idx = {n: i for i, n in enumerate(names)}
    for r, c in enumerate(pop):
        for f, v in c["_f"].items():
            if f in idx:
                X[r, idx[f]] = v
    return X


def fit(train, C=0.5):
    firms, plfs = vocab(train)
    for c in train:
        c["_f"] = features(c, firms, plfs)
    names = sorted({f for c in train for f in c["_f"]})
    X = matrix(train, names); y = np.array([c["y"] for c in train])
    m = LogisticRegression(C=C, max_iter=2000).fit(X, y)
    return m, names, firms, plfs


def predict(m, names, firms, plfs, pop):
    for c in pop:
        c["_f"] = features(c, firms, plfs)
    return m.predict_proba(matrix(pop, names))[:, 1]


def base_rate(train, test):
    g = collections.defaultdict(list)
    for c in train: g[c["grp"]].append(c["y"])
    allm = sum(c["y"] for c in train) / len(train)
    return np.array([sum(g[c["grp"]]) / len(g[c["grp"]]) if g.get(c["grp"]) else allm for c in test])


def report(name, y, p):
    print(f"  {name:28} AUC {roc_auc_score(y, p):.3f}  Brier {brier_score_loss(y, p):.3f}")


if __name__ == "__main__":
    test_from = sys.argv[sys.argv.index("--test-from") + 1] if "--test-from" in sys.argv else "2026-05-01"
    rows, by, sales = load()
    pop = build(rows)
    tr = [c for c in pop if c["sale_date"] < test_from]; te = [c for c in pop if c["sale_date"] >= test_from]
    y = np.array([c["y"] for c in te])
    print(f"population {len(pop)} cleared residential listings; train {len(tr)} (before {test_from}), test {len(te)}")
    print(f"outside-buyer rate: train {np.mean([c['y'] for c in tr]):.3f}, test {y.mean():.3f}")
    m, names, firms, plfs = fit(tr)
    p = predict(m, names, firms, plfs, te)
    print("OUT OF SAMPLE")
    report("sale type only (base rates)", y, base_rate(tr, te))
    report("full model", y, p)
    print("  calibration (test, by predicted band):")
    for lo, hi in [(0, .15), (.15, .3), (.3, .5), (.5, .7), (.7, 1.01)]:
        k = [i for i, x in enumerate(p) if lo <= x < hi]
        if k:
            print(f"    predicted {lo:.0%}-{min(hi,1):.0%}: n={len(k):3}  predicted avg {np.mean(p[k]):.0%}  actual {np.mean(y[k]):.0%}")
    # final model on everything
    m, names, firms, plfs = fit(pop)
    coef = {n: round(float(w), 4) for n, w in zip(names, m.coef_[0])}
    out = {"_readme": "Chance an outside buyer wins a cleared residential property at the sale. Logistic model fit by "
                      "analysis/sheriff_only/fit_sell.py on the Sheriff's results (cleared listings, Jan 2025 - Nov 2026). "
                      "Refit after new results are added.",
           "fitted": dt.date.today().isoformat(), "n": len(pop), "outside_rate": round(float(np.mean([c['y'] for c in pop])), 4),
           "intercept": round(float(m.intercept_[0]), 4), "coef": coef, "firms": sorted(firms), "plaintiffs": sorted(plfs),
           "bands": {"High": 0.6, "Medium": 0.3}}
    mp = os.path.join(REPO, "reference", "sell_model.json")
    if os.path.exists(mp) and "bank_bid" in json.load(open(mp)):  # keep the section written by fit_bank.py
        out["bank_bid"] = json.load(open(mp))["bank_bid"]
    json.dump(out, open(mp, "w"), indent=1)
    print("\nFINAL MODEL (all data) coefficients, log-odds:")
    for n, w in sorted(coef.items(), key=lambda kv: -abs(kv[1])):
        print(f"  {w:+.2f}  {n}")
