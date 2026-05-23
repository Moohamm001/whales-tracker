"""Populate PositionLifecycle — one row per (fund, stock) telling the
whole accumulation story.

For every (fund, stock) pair that has ever appeared in a filing, we walk
the full history in chronological order and derive:

  Entry         : first_buy_quarter, first_buy_shares/value/pct_portfolio
                  position_predates_window (open before our oldest filing)
  Build/exit    : add_quarter_count, reduce_quarter_count
                  consecutive_adds, consecutive_reduces
                  total_added_shares/value, total_reduced_shares
  Current state : current_shares, current_value, current_pct_portfolio
  Cost / P&L    : est_avg_cost (weighted by share *additions*, priced at
                  the quarter's avg_close), mark_price, unrealized_pnl_pct
  Pattern       : probe / pyramid / linear-accumulate / re-entry /
                  single-shot / distribute / stable
  Phase         : building / holding / trimming / exited
  Conviction    : 0–100 composite of size×consistency×skill

Composite conviction (0-100):
   30 pts   position size relative to fund's avg position (max at 2x avg)
   25 pts   consecutive_adds (max at 4+)
   20 pts   currently in fund's top 10 (binary)
   15 pts   pct_portfolio absolute (max at 5%)
   10 pts   fund's hit_rate_top10 (if computed; defaults to 0.5)

Idempotent: TRUNCATE then INSERT in a single transaction.

Run after sec_crawler.py + fetch_stock_prices.py.
"""

import sqlite3
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).resolve().parent.parent / "hedge_data.db"


def quarters_between(q_start: str, q_end: str) -> int:
    """Inclusive count, e.g. 2023Q1..2023Q4 -> 4."""
    if not q_start or not q_end:
        return 0
    y1, q1 = q_start.split("Q"); y2, q2 = q_end.split("Q")
    return (int(y2) - int(y1)) * 4 + (int(q2) - int(q1)) + 1


def classify_pattern(history: list[dict]) -> str:
    """Identify the accumulation pattern from share movements.

    history: list of {quarter, shares, value} chronological.
    Returns one of: probe, pyramid, linear-accumulate, re-entry,
                    single-shot, distribute, stable.
    """
    if not history:
        return "stable"
    shares = [h["shares"] for h in history]
    deltas = [shares[i] - shares[i-1] for i in range(1, len(shares))]
    n = len(history)

    # Detect re-entry: shares went to 0 mid-history and came back > 0
    zeroed = any(s == 0 for s in shares[:-1])
    if zeroed and shares[-1] > 0:
        return "re-entry"

    # Number of adds / reduces
    adds = [d for d in deltas if d > 0]
    reduces = [d for d in deltas if d < 0]

    # Most recent reductions ≥ 2 in a row → distribute
    if len(deltas) >= 2 and deltas[-1] < 0 and deltas[-2] < 0:
        return "distribute"

    # Single-shot: initial buy, no subsequent adds, ≥3 quarters in
    if n >= 3 and len(adds) <= 1 and len(reduces) == 0:
        return "single-shot"

    # Probe: just one quarter of holding, small position
    if n == 1:
        return "probe"

    # Pyramid: ≥3 adds, sized monotonically increasing
    if len(adds) >= 3:
        sorted_check = all(adds[i] >= adds[i-1] * 0.7 for i in range(1, len(adds)))
        if sorted_check:
            return "pyramid"

    # Linear accumulate: ≥3 consecutive add quarters
    consec = 0
    max_consec = 0
    for d in deltas:
        if d > 0:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0
    if max_consec >= 3:
        return "linear-accumulate"

    # If ≥2 add quarters total but pattern not clean → call it pyramid-loose
    if len(adds) >= 2 and len(adds) > len(reduces):
        return "pyramid"

    return "stable"


def classify_phase(current_shares: int, consecutive_adds: int,
                   consecutive_reduces: int, history: list[dict]) -> str:
    if current_shares == 0:
        return "exited"
    if consecutive_reduces >= 2:
        return "trimming"
    if consecutive_adds >= 1:
        return "building"
    return "holding"


def conviction_score(current_pct_portfolio: float,
                     avg_pos_size_pct: float,
                     consecutive_adds: int,
                     in_top10: bool,
                     hit_rate: float) -> int:
    score = 0.0
    # Size relative to fund's avg position
    if avg_pos_size_pct and avg_pos_size_pct > 0:
        ratio = (current_pct_portfolio or 0) / avg_pos_size_pct
        score += min(ratio / 2.0, 1.0) * 30   # max at 2x
    # Consecutive adds
    score += min(consecutive_adds / 4.0, 1.0) * 25
    # Top 10
    if in_top10:
        score += 20
    # Absolute portfolio %
    score += min((current_pct_portfolio or 0) / 5.0, 1.0) * 15
    # Skill weight
    score += (hit_rate or 0.5) * 10
    return int(round(score))


def fund_avg_position_size(cur, fund_id: int) -> float | None:
    """Mean pct_portfolio across all current holdings."""
    row = cur.execute(
        """SELECT AVG(pct_portfolio) FROM Holdings h
           JOIN Filings fi ON fi.id = h.filing_id
           WHERE fi.fund_id = ?
             AND fi.period_of_report = (
               SELECT MAX(period_of_report) FROM Filings WHERE fund_id = ?
             )""",
        (fund_id, fund_id),
    ).fetchone()
    return row[0] if row and row[0] else None


def fund_top10_stocks(cur, fund_id: int) -> set[int]:
    rows = cur.execute(
        """SELECT h.stock_id FROM Holdings h
           JOIN Filings fi ON fi.id = h.filing_id
           WHERE fi.fund_id = ?
             AND fi.period_of_report = (
               SELECT MAX(period_of_report) FROM Filings WHERE fund_id = ?
             )
           ORDER BY h.value DESC
           LIMIT 10""",
        (fund_id, fund_id),
    ).fetchall()
    return {r[0] for r in rows}


def fund_oldest_quarter(cur, fund_id: int) -> str | None:
    row = cur.execute(
        """SELECT quarter FROM Filings WHERE fund_id = ?
           ORDER BY period_of_report ASC LIMIT 1""",
        (fund_id,),
    ).fetchone()
    return row[0] if row else None


def latest_mark_price(cur, stock_id: int) -> float | None:
    row = cur.execute(
        """SELECT quarter_end_close FROM StockPrices
           WHERE stock_id = ? ORDER BY quarter DESC LIMIT 1""",
        (stock_id,),
    ).fetchone()
    return row[0] if row and row[0] else None


def compute_for_fund(conn, fund_id: int, manager: str) -> int:
    cur = conn.cursor()

    avg_pos_size = fund_avg_position_size(cur, fund_id)
    top10 = fund_top10_stocks(cur, fund_id)
    oldest_q = fund_oldest_quarter(cur, fund_id)
    hit_rate_row = cur.execute(
        "SELECT hit_rate_top10 FROM Funds WHERE id = ?", (fund_id,)
    ).fetchone()
    hit_rate = hit_rate_row[0] if hit_rate_row and hit_rate_row[0] else 0.5

    # Every stock the fund has *ever* held — full history per (fund, stock)
    stock_rows = cur.execute(
        """SELECT DISTINCT h.stock_id
           FROM Holdings h
           JOIN Filings fi ON fi.id = h.filing_id
           WHERE fi.fund_id = ?""",
        (fund_id,),
    ).fetchall()

    n = 0
    for (stock_id,) in stock_rows:
        history_rows = cur.execute(
            """SELECT fi.quarter, fi.period_of_report,
                      h.shares, h.value, h.pct_portfolio, sp.avg_close
               FROM Holdings h
               JOIN Filings fi ON fi.id = h.filing_id
               LEFT JOIN StockPrices sp
                      ON sp.stock_id = h.stock_id AND sp.quarter = fi.quarter
               WHERE fi.fund_id = ? AND h.stock_id = ?
               ORDER BY fi.period_of_report ASC""",
            (fund_id, stock_id),
        ).fetchall()
        if not history_rows:
            continue

        history = [
            {"quarter": r[0], "period": r[1], "shares": r[2],
             "value": r[3], "pct": r[4], "avg_close": r[5]}
            for r in history_rows
        ]

        first = history[0]
        last = history[-1]
        first_buy_quarter = first["quarter"]
        first_buy_shares = first["shares"]
        first_buy_value  = first["value"]
        first_buy_pct    = first["pct"]
        position_predates_window = 1 if first_buy_quarter == oldest_q else 0

        # Walk deltas for adds / reduces / cost basis
        add_q = 0; red_q = 0
        consec_adds = 0; consec_reds = 0
        max_consec_adds = 0; max_consec_reds = 0
        total_added_sh = 0; total_added_val = 0.0
        total_reduced_sh = 0
        prev_shares = 0; prev_val = 0.0

        for h in history:
            sh = h["shares"]; val = h["value"]
            if sh > prev_shares:
                delta = sh - prev_shares
                # Price per share for this addition
                if h["avg_close"] and h["avg_close"] > 0:
                    per_share = h["avg_close"]
                else:
                    delta_val = max(0.0, val - prev_val)
                    per_share = delta_val / delta if delta > 0 else 0
                total_added_sh += delta
                total_added_val += delta * per_share
                add_q += 1
                consec_adds += 1
                consec_reds = 0
                max_consec_adds = max(max_consec_adds, consec_adds)
            elif sh < prev_shares:
                total_reduced_sh += prev_shares - sh
                red_q += 1
                consec_reds += 1
                consec_adds = 0
                max_consec_reds = max(max_consec_reds, consec_reds)
            else:
                # unchanged — break consecutive runs
                consec_adds = 0
                consec_reds = 0
            prev_shares = sh
            prev_val = val

        est_avg_cost = (total_added_val / total_added_sh) if total_added_sh > 0 else None
        mark_price = latest_mark_price(cur, stock_id)
        unrealized_pnl_pct = None
        if est_avg_cost and mark_price and est_avg_cost > 0:
            unrealized_pnl_pct = (mark_price - est_avg_cost) / est_avg_cost * 100.0

        # Most recent change (might be older than last_filing if no Δ since)
        recent_change = cur.execute(
            """SELECT quarter, change_type FROM HoldingChanges
               WHERE fund_id = ? AND stock_id = ?
               ORDER BY quarter DESC LIMIT 1""",
            (fund_id, stock_id),
        ).fetchone()
        last_act_q  = recent_change[0] if recent_change else None
        last_act_t  = recent_change[1] if recent_change else None

        current_shares = last["shares"]
        current_value = last["value"]
        current_pct = last["pct"]

        pattern = classify_pattern(history)
        phase = classify_phase(current_shares, consec_adds, consec_reds, history)
        in_top10 = stock_id in top10
        score = conviction_score(
            current_pct or 0, avg_pos_size or 0,
            consec_adds, in_top10, hit_rate,
        )
        holding_q = quarters_between(first_buy_quarter, last["quarter"])

        cur.execute(
            """INSERT OR REPLACE INTO PositionLifecycle
               (fund_id, stock_id,
                first_buy_quarter, first_buy_shares, first_buy_value, first_buy_pct_portfolio,
                position_predates_window,
                add_quarter_count, reduce_quarter_count,
                consecutive_adds, consecutive_reduces,
                total_added_shares, total_added_value, total_reduced_shares,
                current_shares, current_value, current_pct_portfolio,
                est_avg_cost, mark_price, unrealized_pnl_pct,
                pattern, phase, conviction_score, holding_quarters,
                last_activity_quarter, last_activity_type,
                computed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (fund_id, stock_id,
             first_buy_quarter, first_buy_shares, first_buy_value, first_buy_pct,
             position_predates_window,
             add_q, red_q,
             consec_adds, consec_reds,
             total_added_sh, total_added_val, total_reduced_sh,
             current_shares, current_value, current_pct,
             est_avg_cost, mark_price, unrealized_pnl_pct,
             pattern, phase, score, holding_q,
             last_act_q, last_act_t),
        )
        n += 1

    return n


def update_fund_avg_holding(conn):
    """Average holding-period in quarters across positions still open."""
    cur = conn.cursor()
    rows = cur.execute(
        """SELECT fund_id, AVG(holding_quarters) FROM PositionLifecycle
           WHERE phase != 'exited' GROUP BY fund_id"""
    ).fetchall()
    for fund_id, avg_hold in rows:
        cur.execute(
            """UPDATE Funds SET avg_holding_quarters = ?,
                      avg_position_size_pct = (
                        SELECT AVG(current_pct_portfolio) FROM PositionLifecycle
                        WHERE fund_id = Funds.id AND phase != 'exited'
                      )
               WHERE id = ?""",
            (avg_hold, fund_id),
        )


def main():
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")
    cur = conn.cursor()
    cur.execute("DELETE FROM PositionLifecycle")
    print("Cleared previous PositionLifecycle")

    funds = cur.execute("SELECT id, manager_name FROM Funds ORDER BY id").fetchall()
    total = 0
    for fund_id, mgr in funds:
        n = compute_for_fund(conn, fund_id, mgr or "")
        total += n
        print(f"  {(mgr or '—'):<28} {n:>5} positions")
        conn.commit()

    update_fund_avg_holding(conn)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM PositionLifecycle")
    print(f"\n[DONE] {total:,} PositionLifecycle rows")
    # Distribution
    rows = cur.execute(
        """SELECT phase, COUNT(*) FROM PositionLifecycle GROUP BY phase ORDER BY 2 DESC"""
    ).fetchall()
    print("Phase distribution:")
    for phase, c in rows:
        print(f"  {phase:<12} {c:>6,}")
    rows = cur.execute(
        """SELECT pattern, COUNT(*) FROM PositionLifecycle GROUP BY pattern ORDER BY 2 DESC"""
    ).fetchall()
    print("Pattern distribution:")
    for p, c in rows:
        print(f"  {p:<20} {c:>6,}")
    conn.close()


if __name__ == "__main__":
    main()
