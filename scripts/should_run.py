"""Decide whether today is an update day for the next sheriff sale.

Sales are on the first Monday of each month. Update schedule:
  * weekly (every 7 days) until the week before the sale: 28, 21, 14 days out ... and 7 days out
  * every other day in the final week: 5, 3 and 1 days out
So for a Monday sale: the Monday a week before, then Wed, Fri, Sun.

Usage: python3 -I should_run.py [--today YYYY-MM-DD]
Prints JSON {"run": bool, "sale_date": ..., "days_until": ..., "reason": ...}. Exit code is always 0.
Dates use US Eastern time (the sale is in Pittsburgh).
"""
import argparse, datetime as dt, json
from zoneinfo import ZoneInfo


def first_monday(y, m):
    d = dt.date(y, m, 1)
    return d + dt.timedelta(days=(0 - d.weekday()) % 7)


def next_sale(today):
    for k in range(0, 3):
        y, m = today.year + (today.month - 1 + k) // 12, (today.month - 1 + k) % 12 + 1
        s = first_monday(y, m)
        if s >= today:
            return s


def decide(today):
    sale = next_sale(today)
    d = (sale - today).days
    if d in (1, 3, 5) or (d >= 7 and d % 7 == 0):
        return {"run": True, "sale_date": sale.isoformat(), "days_until": d, "reason": "scheduled update day"}
    return {"run": False, "sale_date": sale.isoformat(), "days_until": d, "reason": "not an update day"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--today")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(ZoneInfo("America/New_York")).date()
    print(json.dumps(decide(today)))
