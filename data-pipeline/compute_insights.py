"""Pre-compute per-(fund, stock) insights into HoldingInsights.

Mirrors the logic that web/lib/db.ts used to do at request time:
  - first_buy_quarter        : oldest filing quarter the position appears in
  - last_activity_quarter    : most recent HoldingChanges row
  - last_activity_type       : NEW / ADDED / REDUCED / SOLD
  - est_avg_cost             : weighted by share additions, priced at the
                               quarter's avg close from StockPrices (else
                               13F implied per-share)
  - trend                    : pattern from last 3 changes
  - position_predates_window : first observation = fund's oldest filing

Computes for every (fund, stock) pair that currently has shares > 0 in the
fund's latest filing. Idempotent: INSERT OR REPLACE.

Run after sec_crawler.py and fetch_stock_prices.py.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "hedge_data.db"


def compute_for_fund(conn, fund_id: int) -> int:
    cur = conn.cursor()

    oldest_q = cur.execute(
        """SELECT quarter FROM Filings WHERE fund_id = ?
           ORDER BY period_of_report ASC LIMIT 1""",
        (fund_id,),
    ).fetchone()
    oldest_quarter = oldest_q[0] if oldest_q else None

    # Current holdings (in the latest filing)
    current = cur.execute(
        """SELECT stock_id FROM Holdings
           WHERE filing_id = (
             SELECT id FROM Filings WHERE fund_id = ?
             ORDER BY period_of_report DESC LIMIT 1
           )""",
        (fund_id,),
    ).fetchall()

    n = 0
    for (stock_id,) in current:
        history = cur.execute(
            """SELECT fi.quarter, h.shares, h.value, sp.avg_close
               FROM Holdings h
               JOIN Filings fi ON fi.id = h.filing_id
               LEFT JOIN StockPrices sp ON sp.stock_id = h.stock_id AND sp.quarter = fi.quarter
               WHERE fi.fund_id = ? AND h.stock_id = ?
               ORDER BY fi.period_of_report ASC""",
            (fund_id, stock_id),
        ).fetchall()
        if not history:
            continue

        first_buy_quarter = history[0][0]
        position_predates_window = 1 if first_buy_quarter == oldest_quarter else 0

        added_shares = 0
        added_value = 0.0
        prev_shares = 0
        prev_value = 0.0
        for q, shares, value, avg_close in history:
            if shares > prev_shares:
                delta_sh = shares - prev_shares
                delta_val = max(0.0, value - prev_value)
                if avg_close and avg_close > 0:
                    per_share = avg_close
                else:
                    per_share = delta_val / delta_sh if delta_sh > 0 else 0
                added_shares += delta_sh
                added_value += delta_sh * per_share
            prev_shares = shares
            prev_value = value

        est_avg_cost = (added_value / added_shares) if added_shares > 0 else None

        # Recent changes (last 3 quarters)
        recent = cur.execute(
            """SELECT change_type, quarter FROM HoldingChanges
               WHERE fund_id = ? AND stock_id = ?
               ORDER BY quarter DESC LIMIT 3""",
            (fund_id, stock_id),
        ).fetchall()

        last_activity_quarter = recent[0][1] if recent else None
        last_activity_type = recent[0][0] if recent else None

        # Trend
        trend = "Stable"
        if recent:
            types = [r[0] for r in recent]
            if types[0] == "NEW":
                trend = "Building"
            else:
                add_n = sum(1 for t in types if t == "ADDED")
                red_n = sum(1 for t in types if t == "REDUCED")
                if add_n == len(types) and len(types) >= 2:
                    trend = "Accumulating"
                elif red_n == len(types) and len(types) >= 2:
                    trend = "Exiting"
                elif add_n > red_n:
                    trend = "Accumulating"
                elif red_n > add_n:
                    trend = "Reducing"

        cur.execute(
            """INSERT OR REPLACE INTO HoldingInsights
               (fund_id, stock_id, first_buy_quarter, last_activity_quarter,
                last_activity_type, est_avg_cost, trend, position_predates_window,
                computed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (fund_id, stock_id, first_buy_quarter, last_activity_quarter,
             last_activity_type, est_avg_cost, trend, position_predates_window),
        )
        n += 1
    return n


def main():
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")
    cur = conn.cursor()
    cur.execute("SELECT id, manager_name FROM Funds ORDER BY id")
    funds = cur.fetchall()

    # Optional: clear previous compute for funds we'll recompute (idempotent
    # anyway since we INSERT OR REPLACE per (fund, stock); but if a position
    # was sold-out since last compute we want it gone).
    cur.execute("DELETE FROM HoldingInsights")
    print(f"Cleared previous HoldingInsights")

    total = 0
    for fund_id, mgr in funds:
        n = compute_for_fund(conn, fund_id)
        total += n
        print(f"  {mgr:<25} {n:>5} insights")
        conn.commit()

    print(f"\n[DONE] {total:,} insights cached")
    conn.close()


if __name__ == "__main__":
    main()
