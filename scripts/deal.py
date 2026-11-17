"""Sheriff-sale underwriting: flip and BRRRR MAOs, profit / cash left at a price, and the flip and BRRRR scores.

All assumptions are in reference/deal_model.json (the user's numbers) and reference/transfer_tax.json. The CRM popup
runs the same math in src/lib/sheriffDeal.js; keep the two in step.

Flip:  profit(P) = ARV x (1 - sale costs) - P - buy closing - transfer tax - rehab - contingency - holding - hard money
BRRRR: cash left(P) = cash in (10% down + closing + transfer tax + contingency + hard-money points and interest + holding)
                      - cash back at refi (refi loan - refi costs - hard-money payoff)
       The refi is the optimizer's pick: of every LTV x points x loan type with >= $200/mo cash flow and DSCR >= 1.1,
       the one that returns the most cash (least left in the deal). Which one wins does not depend on the price.
Hard money = 90% of the price + 100% of rehab, 2.5 points, 11% interest-only for 6 months.
Buy costs: $300 closing + $200 sheriff closing fee. Transfer tax (county assessed value x CLR x rates) is off
(include_transfer_tax in deal_model.json).
"""
import json
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "reference"
M = json.load(open(REF / "deal_model.json"))
TT = json.load(open(REF / "transfer_tax.json"))
TT_RATES = {x["municipality"]: TT["state_rate"] + x["muni_rate"] + x["school_rate"] for x in TT["municipalities"]}


def rehab_for(sqft, arv):
    R = M["rehab"]
    r = (sqft or R["default_sqft"]) * R["per_sqft"]
    if arv and arv >= R["premium_arv_at"]:
        r *= R["premium_factor"]
    return round(r, -2)


def contingency_for(rehab):
    R = M["rehab"]
    return max(rehab * R["contingency_pct"], R["contingency_min"]) if rehab > 0 else 0.0


def transfer_rate(tax_municipality):
    return TT_RATES.get(tax_municipality)


def transfer_tax(assessed, rate):
    if not assessed or rate is None:
        return None
    return round(assessed * TT["clr"] * rate)


def _hm(P, rehab):
    H = M["hard_money"]
    loan = H["purchase_ltv"] * P + H["rehab_ltv"] * rehab
    points = loan * H["points_pct"] / 100
    interest = loan * H["rate_pct"] / 100 / 12 * H["hold_months"]
    return loan, points, interest


def flip_at(P, arv, rehab, tt):
    loan, points, interest = _hm(P, rehab)
    cont = contingency_for(rehab)
    holding = M["holding_per_month"] * M["hard_money"]["hold_months"]
    sale = arv * M["flip_sale_cost_pct"]
    profit = arv - sale - P - M["buy_closing_flat"] - M["sheriff_closing_fee"] - (tt or 0) - rehab - cont - holding - points - interest
    return {"price": P, "arv": arv, "sale_costs": sale, "buy_closing": M["buy_closing_flat"], "sheriff_fee": M["sheriff_closing_fee"],
            "transfer_tax": tt or 0, "rehab": rehab, "contingency": cont, "holding": holding, "hm_loan": loan, "hm_points": points,
            "hm_interest": interest, "profit": profit}


def _solve(fn, target, increasing):
    """fn is linear in P; return P where fn(P) == target."""
    f0, f1 = fn(0.0), fn(100000.0)
    slope = (f1 - f0) / 100000.0
    return (target - f0) / slope


def flip_maos(arv, rehab, tt):
    return [{"target": t, "mao": round(_solve(lambda P: flip_at(P, arv, rehab, tt)["profit"], t, False))}
            for t in M["targets"]["flip_profit"]]


def _payment(loan, rate, lt):
    if loan <= 0:
        return 0.0
    if lt["kind"] == "io":
        return loan * rate / 100 / 12
    mr = rate / 100 / 12
    return loan / lt["term_months"] if mr == 0 else loan * mr / (1 - (1 + mr) ** -lt["term_months"])


def refi_options(arv, rent):
    """All refi structures with their cash flow; passing ones sorted by most cash returned (least left)."""
    R, O = M["refi"], M["operating"]
    tax, ins = O["property_taxes_annual"] / 12, O["insurance_annual"] / 12
    opex = rent * (O["maintenance_pct"] + O["capex_pct"] + O["vacancy_pct"]) / 100 + O["misc_monthly"]
    state_local = round(rent * O["state_local_pct_of_rent"] / 100)
    out = []
    for ltv in R["ltv_options"]:
        for pts in R["points_options"]:
            for lt in R["loan_types"]:
                loan = ltv / 100 * arv
                rate = max(R["base_rate"] - pts * R["rate_cut_per_point"], 0)
                pay = _payment(loan, rate, lt)
                costs = loan * (R["cost_pct"] + pts * R["point_cost_pct"]) / 100 + R["cost_flat"]
                cf = rent - pay - opex - ins - tax - O["hoa_monthly"] - state_local
                pitia = pay + tax + ins + O["hoa_monthly"] + state_local
                dscr = rent / pitia if pitia > 0 else 0
                out.append({"ltv": ltv, "points": pts, "loan_type": lt["label"], "rate": rate, "refi_loan": loan, "refi_costs": costs,
                            "payment": pay, "cash_flow": cf, "dscr": dscr, "net": loan - costs})
    passing = [o for o in out if o["cash_flow"] >= R["min_cash_flow"] and o["dscr"] >= R["min_dscr"]]
    passing.sort(key=lambda o: -o["net"])  # stable: ties keep LTV x points x type order
    return passing, out


def brrrr_at(P, arv, rehab, tt, refi):
    loan, points, interest = _hm(P, rehab)
    H = M["hard_money"]
    cont = contingency_for(rehab)
    holding = M["holding_per_month"] * H["hold_months"]
    down = P - H["purchase_ltv"] * P + rehab - H["rehab_ltv"] * rehab
    cash_in = down + M["buy_closing_flat"] + M["sheriff_closing_fee"] + (tt or 0) + cont + points + interest + holding
    cash_back = refi["refi_loan"] - refi["refi_costs"] - loan
    return {"price": P, "down_payment": down, "buy_closing": M["buy_closing_flat"], "sheriff_fee": M["sheriff_closing_fee"],
            "transfer_tax": tt or 0, "contingency": cont,
            "hm_loan": loan, "hm_points": points, "hm_interest": interest, "holding": holding, "cash_in": cash_in,
            "refi_loan": refi["refi_loan"], "refi_costs": refi["refi_costs"], "cash_back": cash_back, "cash_left": cash_in - cash_back}


def brrrr_maos(arv, rehab, tt, refi):
    return [{"target": t, "mao": round(_solve(lambda P: brrrr_at(P, arv, rehab, tt, refi)["cash_left"], t, True))}
            for t in M["targets"]["brrrr_cash_left"]]


def _piecewise(x, pts):
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def flip_score(profit):
    return round(_piecewise(profit, M["scores"]["flip_points"]))


def brrrr_score(cash_left):
    return 0 if cash_left is None else round(_piecewise(cash_left, M["scores"]["brrrr_points"]))


def underwrite(price, arv, sqft, rent, assessed, tax_municipality):
    """Everything for one property at a given price. Returns a flat dict for the score / workbook / CRM."""
    rehab = rehab_for(sqft, arv)
    rate = transfer_rate(tax_municipality)
    tt = transfer_tax(assessed, rate) if M.get("include_transfer_tax", True) else None
    f = flip_at(price, arv, rehab, tt)
    out = {"rehab_est": rehab, "contingency": round(contingency_for(rehab)), "transfer_rate": rate, "assessed_value": assessed,
           "transfer_tax": tt, "flip_profit": round(f["profit"]), "flip_score": flip_score(f["profit"])}
    for m in flip_maos(arv, rehab, tt):
        out[f"mao_flip_{m['target'] // 1000}k"] = m["mao"]
    passing, allo = refi_options(arv, rent) if rent else ([], [])
    best = passing[0] if passing else None
    if best:
        b = brrrr_at(price, arv, rehab, tt, best)
        out.update({"brrrr_cash_left": round(b["cash_left"]), "brrrr_score": brrrr_score(b["cash_left"]),
                    "refi_terms": f"{best['ltv']}% LTV, {best['loan_type']}, {best['points']} pts @ {best['rate']:.1f}%",
                    "refi_cash_flow": round(best["cash_flow"]), "refi_dscr": round(best["dscr"], 2), "refi_ok": True})
        for m in brrrr_maos(arv, rehab, tt, best):
            out[f"mao_brrrr_{m['target'] // 1000}k"] = m["mao"]
    else:
        top = max(allo, key=lambda o: o["cash_flow"]) if allo else None
        out.update({"brrrr_cash_left": None, "brrrr_score": 0, "refi_ok": False if rent else None,
                    "refi_cash_flow": round(top["cash_flow"]) if top else None,
                    "refi_terms": (f"no refi reaches ${M['refi']['min_cash_flow']}/mo (best ${top['cash_flow']:,.0f}/mo at {top['ltv']}% {top['loan_type']})"
                                   if top else "no rent estimate")})
    return out


if __name__ == "__main__":
    import sys
    P, arv, sqft, rent = map(float, sys.argv[1:5])
    assessed = float(sys.argv[5]) if len(sys.argv) > 5 else None
    print(json.dumps(underwrite(P, arv, sqft, rent, assessed, sys.argv[6] if len(sys.argv) > 6 else "Penn Hills Twp"), indent=1))
