"""The CRM Deal Calculator's BRRRR refi optimizer, in Python, for the preliminary score.

Mirrors src/lib/dealCalc.js (total cash to close, holding tax/insurance, reserves), src/lib/refiMetrics.js and
src/lib/refiOptimizer.js: try every LTV x points x loan type, keep structures with at least $200/mo cash flow
and DSCR 1.1, pick the one that leaves the least cash in the deal. Uses the calculator's default assumptions
(reference/calc_defaults.json) and the Sheriff page's rules (rehab contingency max(10%, $10k), hard money
75% of purchase + 100% of rehab, state/local tax 3.07% of rent).
"""
import json
from pathlib import Path

CFG = json.load(open(Path(__file__).resolve().parent.parent / "reference" / "calc_defaults.json"))
D = {k: v for k, v in CFG["defaults"].items()}
O = CFG["optimizer"]
SH = CFG["sheriff"]


def f(k):
    try:
        return float(D[k])
    except (KeyError, ValueError):
        return 0.0


def mortgage_payment(principal, rate_pct, months):
    if principal <= 0:
        return 0.0
    mr = rate_pct / 100 / 12
    return principal / months if mr == 0 else principal * mr / (1 - (1 + mr) ** -months)


def io_payment(principal, rate_pct):
    return principal * rate_pct / 100 / 12 if principal > 0 else 0.0


def optimize(purchase, arv, rehab, rent):
    """Returns dict with best (or None), n_passing, best_any (highest cash flow when none pass), cash_to_close."""
    if not (arv and arv > 0 and rent and rent > 0 and purchase and purchase > 0):
        return None
    rehab = rehab or 0.0
    contingency = max(rehab * SH["rehab_contingency_pct"], SH["rehab_contingency_min"]) if rehab > 0 else 0.0
    hm_loan = 0.0 if D.get("hm_financing") == "cash" else round(f("purchase_ltv_percent") / 100 * purchase + f("rehab_ltv_percent") / 100 * rehab)
    # purchase closing: itemized if any, else flat closing_costs
    itemized = f("title_escrow_fees") + purchase * f("transfer_tax_pct") / 100 + f("attorney_fees") + f("recording_fees") + f("other_purchase_fees")
    purchase_closing = itemized if itemized > 0 else f("closing_costs")
    points_cost = f("hm_points_override") if f("hm_points_override") > 0 else hm_loan * f("hm_points") / 100
    loan_fees = f("appraisal_fee") + f("underwriting_fee") + points_cost + f("other_lender_fees")
    loan_to_rehab = min(rehab, hm_loan)
    unfinanced_purchase = purchase - (hm_loan - loan_to_rehab)
    unfinanced_rehab = rehab - loan_to_rehab
    cash_to_close = unfinanced_purchase + unfinanced_rehab + purchase_closing + loan_fees + contingency

    monthly_tax = f("property_taxes_annual") / 12
    monthly_ins = f("insurance_annual") / 12
    hoa = f("hoa_monthly")
    state_local = round(rent * SH["state_local_tax_pct_of_rent"])
    maint = rent * f("maintenance_reserve_monthly") / 100 if D.get("maintenance_reserve_mode") == "percent" else f("maintenance_reserve_monthly")
    capex = rent * f("capex_reserve_monthly") / 100 if D.get("capex_reserve_mode", "percent") == "percent" else f("capex_reserve_monthly")
    vacancy = rent * f("vacancy_rate") / 100
    misc = f("misc_reserve_monthly")

    combos = []
    for ltv in O["ltv_options"]:
        for pts in O["points_options"]:
            for lt in O["loan_types"]:
                loan = ltv / 100 * arv
                pts_cost = pts * O["point_cost_pct"] / 100 * loan
                orig = O["origination_pct"] / 100 * loan
                rate = max(O["base_rate"] - pts * O["rate_cut_per_point"], 0)
                pay = io_payment(loan, rate) if lt["kind"] == "io" else mortgage_payment(loan, rate, lt["term_months"])
                returned = loan - pts_cost - orig - hm_loan
                cash_left = cash_to_close - returned
                cf = rent - pay - maint - capex - vacancy - misc - monthly_ins - monthly_tax - hoa - state_local
                pitia = pay + monthly_tax + monthly_ins + hoa + state_local
                dscr = rent * 12 / (pitia * 12) if pitia > 0 else 0
                combos.append({"ltv": ltv, "points": pts, "loan_type": lt["label"], "rate": round(rate, 2), "refi_loan": round(loan),
                               "payment": round(pay), "cash_left": round(cash_left), "cash_flow": round(cf), "dscr": round(dscr, 2),
                               "_cf": cf, "_dscr": dscr, "_left": cash_left})
    passing = sorted([c for c in combos if c["_cf"] >= O["min_cash_flow"] and c["_dscr"] >= O["min_dscr"]], key=lambda c: c["_left"])
    for c in combos:
        for k in ("_cf", "_dscr", "_left"):
            c.pop(k)
    return {"best": passing[0] if passing else None, "n_passing": len(passing),
            "best_any": max(combos, key=lambda c: c["cash_flow"]), "cash_to_close": round(cash_to_close), "hm_loan": hm_loan}


def describe(r):
    b = r["best"]
    if b:
        return (f"best refi {b['ltv']}% LTV {b['loan_type']}, {b['points']} pts @ {b['rate']:.1f}%: "
                f"${b['cash_left']:,.0f} left in the deal, ${b['cash_flow']:,.0f}/mo, DSCR {b['dscr']:.2f}")
    a = r["best_any"]
    return f"no refi reaches ${O['min_cash_flow']}/mo and DSCR {O['min_dscr']} (best ${a['cash_flow']:,.0f}/mo at {a['ltv']}% {a['loan_type']})"


if __name__ == "__main__":
    import sys
    p, a, rh, rt = map(float, sys.argv[1:5])
    r = optimize(p, a, rh, rt)
    print(json.dumps(r, indent=1)); print(describe(r))
