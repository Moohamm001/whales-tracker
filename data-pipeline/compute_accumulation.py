"""Populate StockAccumulationProfile + StockActivityEvent.

For every stock currently held by ≥1 tracked fund, compute:

  Aggregate state
    current_holders_count            now
    holders_count_{1,2,3}q_ago       trend (1Q/2Q/3Q lookback)
    holders_count_delta_3q           how much the smart-money crowd grew
    new_entrants_last_quarter        JSON list of manager names
    exited_last_quarter              JSON list of manager names

  Concentration / leaders
    top_holder_by_dollars            biggest $ position
    top_holder_by_conviction         largest pct_portfolio holder
    total_smart_money_value          sum across tracked funds
    total_smart_money_value_delta    Δ vs 1Q ago
    avg_holding_quarters_across      mean holding period

  Provenance
    first_smart_buyer                earliest-known tracked-fund holder
    first_smart_buy_quarter

  Classification
    phase                            undiscovered / early-accumulation /
                                     consensus-build / crowded / topping /
                                     distribution

The StockActivityEvent feed is a derived, denormalised narrative log
suitable for showing as a timeline on the stock page. We synthesise one
row per (stock, fund, quarter, event_type) — generating both the
HoldingChanges-driven events (NEW/ADDED/REDUCED/SOLD) and special markers
like FIRST_WHALE and CONSENSUS_FORMING.

Idempotent: TRUNCATE+INSERT.

Run AFTER compute_position_lifecycle.py.
"""

import json
import sqlite3
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).resolve().parent.parent / "hedge_data.db"


def quarter_offset(quarter: str, n: int) -> str:
    """'2024Q3' minus 2 -> '2024Q1'.  n is number of quarters to go back."""
    y, q = quarter.split("Q")
    y, q = int(y), int(q)
    total = y * 4 + (q - 1) - n
    new_y = total // 4
    new_q = (total % 4) + 1
    return f"{new_y}Q{new_q}"


# ---------------------------------------------------------------------------
# Phase classifier
# ---------------------------------------------------------------------------
def classify_phase(holders_now: int, h_1q: int, h_2q: int, h_3q: int,
                   value_delta: float, new_entrants: int,
                   trimmers: int) -> str:
    # Distribution: ≥2 trimmers AND aggregate value dropping
    if trimmers >= 2 and value_delta < 0:
        return "distribution"
    # Topping: trimmer present + holders flat
    if trimmers >= 1 and holders_now == h_1q:
        return "topping"
    # Crowded: many holders AND growth slowing
    if holders_now >= 7 and (holders_now - h_3q) <= 1:
        return "crowded"
    # Consensus-build: holders rising 2+ Q in a row AND new entrants present
    if holders_now > h_1q and h_1q >= h_2q and new_entrants > 0:
        return "consensus-build"
    # Early accumulation: 1-3 holders, all opened recently, positions growing
    if 1 <= holders_now <= 3 and new_entrants > 0:
        return "early-accumulation"
    if holders_now <= 1:
        return "undiscovered"
    return "holding"


def gather_filings_index(conn) -> dict:
    """Map fund_id → ordered list of (quarter, period_of_report, filing_id)."""
    cur = conn.cursor()
    rows = cur.execute(
        """SELECT fund_id, quarter, period_of_report, id
           FROM Filings ORDER BY fund_id, period_of_report"""
    ).fetchall()
    out: dict[int, list[tuple]] = defaultdict(list)
    for fund_id, q, p, fid in rows:
        out[fund_id].append((q, p, fid))
    return out


def latest_quarter_global(conn) -> str:
    return conn.execute(
        "SELECT MAX(period_of_report) FROM Filings"
    ).fetchone()[0]


# ---------------------------------------------------------------------------
# Main per-stock computation
# ---------------------------------------------------------------------------
def compute_stock_profile(cur, stock_id: int, latest_q_global: str,
                          fund_manager: dict[int, str]) -> dict | None:
    """Return the StockAccumulationProfile row for one stock, or None if
    nobody currently holds it."""

    # Current holders (latest filing per fund)
    holders_now_rows = cur.execute(
        """WITH latest AS (
             SELECT fi.id, fi.fund_id, fi.quarter, fi.period_of_report
             FROM Filings fi
             WHERE fi.period_of_report = (
               SELECT MAX(period_of_report) FROM Filings WHERE fund_id = fi.fund_id
             )
           )
           SELECT latest.fund_id, latest.quarter, h.shares, h.value,
                  h.pct_portfolio, latest.period_of_report
           FROM Holdings h
           JOIN latest ON latest.id = h.filing_id
           WHERE h.stock_id = ?
           ORDER BY h.value DESC""",
        (stock_id,),
    ).fetchall()

    if not holders_now_rows:
        return None

    current_holders = len(holders_now_rows)
    total_value = sum(r[3] or 0 for r in holders_now_rows)

    # Top holder by dollars and by conviction (%-of-portfolio)
    top_dollar = holders_now_rows[0]
    top_dollar_mgr = fund_manager.get(top_dollar[0], "—")
    top_dollar_val = top_dollar[3]

    by_pct = sorted(holders_now_rows, key=lambda r: r[4] or 0, reverse=True)
    top_conv = by_pct[0]
    top_conv_mgr = fund_manager.get(top_conv[0], "—")
    top_conv_pct = top_conv[4]

    # Average holding quarters across these holders
    fund_ids = [r[0] for r in holders_now_rows]
    placeholders = ",".join("?" * len(fund_ids))
    avg_hold_row = cur.execute(
        f"""SELECT AVG(holding_quarters) FROM PositionLifecycle
            WHERE stock_id = ? AND fund_id IN ({placeholders})""",
        (stock_id, *fund_ids),
    ).fetchone()
    avg_hold = avg_hold_row[0] if avg_hold_row else None

    # Historical holder counts (1Q, 2Q, 3Q ago)
    # We need any fund whose filing closest to the lookback target had shares > 0
    def holders_at(quarters_back: int) -> tuple[int, float]:
        """Return (count, total_value) of distinct funds holding this stock
        at their filing-quarter closest to `quarters_back` ago (without going past)."""
        # For each fund: find the filing closest to (latest - quarters_back),
        # then check whether they held this stock in that filing.
        rows = cur.execute(
            f"""SELECT fund_id, COUNT(*) c, COALESCE(SUM(h.value), 0) v FROM (
                  SELECT fi.fund_id, h.shares, h.value
                  FROM Filings fi
                  JOIN Holdings h ON h.filing_id = fi.id
                  WHERE h.stock_id = ?
                    AND fi.period_of_report = (
                      SELECT MAX(period_of_report)
                      FROM Filings
                      WHERE fund_id = fi.fund_id
                        AND period_of_report < ?
                    )
                ) sub
                JOIN Holdings h ON h.shares = sub.shares AND h.value = sub.value
                WHERE shares > 0
                GROUP BY fund_id""",
            (stock_id, latest_q_global),
        ).fetchall()
        # We over-fetch; let's do it cleaner with a single query that uses
        # window functions on dates strictly < target.
        return -1, 0.0  # placeholder

    # Cleaner: enumerate each fund's filing chronology and snapshot at the
    # given period-of-report cutoff.
    def holders_count_at_quarter(target_quarter: str) -> tuple[int, float, set]:
        """Distinct funds that held this stock as of a filing whose
        period_of_report <= target_quarter, picking each fund's *latest*
        such filing. Returns (count, total_value, set_of_fund_ids)."""
        rows = cur.execute(
            """WITH last_at AS (
                 SELECT fund_id, MAX(period_of_report) AS p
                 FROM Filings WHERE period_of_report <= ?
                 GROUP BY fund_id
               ),
               held AS (
                 SELECT fi.fund_id, h.value
                 FROM Filings fi
                 JOIN last_at ON last_at.fund_id = fi.fund_id
                            AND last_at.p = fi.period_of_report
                 JOIN Holdings h ON h.filing_id = fi.id
                 WHERE h.stock_id = ? AND h.shares > 0
               )
               SELECT fund_id, value FROM held""",
            (target_quarter, stock_id),
        ).fetchall()
        ids = {r[0] for r in rows}
        return len(ids), sum(r[1] or 0 for r in rows), ids

    # 1Q ago / 2Q / 3Q targets are "the day before previous quarter-end"
    # We approximate by stepping the latest period_of_report back by 90/180/270 days.
    def days_back(target: str, days: int) -> str:
        from datetime import datetime, timedelta
        dt = datetime.fromisoformat(target) - timedelta(days=days)
        return dt.date().isoformat()

    p1 = days_back(latest_q_global, 90)
    p2 = days_back(latest_q_global, 180)
    p3 = days_back(latest_q_global, 270)
    h1_count, h1_val, h1_ids = holders_count_at_quarter(p1)
    h2_count, _h2_val, _h2_ids = holders_count_at_quarter(p2)
    h3_count, _h3_val, _h3_ids = holders_count_at_quarter(p3)

    # New entrants / exited last quarter
    now_ids = set(fund_ids)
    new_entrants = sorted(now_ids - h1_ids)
    exited = sorted(h1_ids - now_ids)
    new_entrant_names = [fund_manager.get(i, "—") for i in new_entrants]
    exited_names = [fund_manager.get(i, "—") for i in exited]

    # Trimmers = funds in lifecycle table with phase=trimming for this stock
    trimmers_row = cur.execute(
        f"""SELECT COUNT(*) FROM PositionLifecycle
           WHERE stock_id = ? AND phase = 'trimming' AND fund_id IN ({placeholders})""",
        (stock_id, *fund_ids),
    ).fetchone()
    trimmers = trimmers_row[0] if trimmers_row else 0

    value_delta = total_value - h1_val

    phase = classify_phase(
        holders_now=current_holders,
        h_1q=h1_count, h_2q=h2_count, h_3q=h3_count,
        value_delta=value_delta,
        new_entrants=len(new_entrants),
        trimmers=trimmers,
    )

    # First smart buyer ever (any quarter, any tracked fund)
    first_buyer_row = cur.execute(
        """SELECT pl.fund_id, pl.first_buy_quarter
           FROM PositionLifecycle pl
           WHERE pl.stock_id = ?
           ORDER BY pl.first_buy_quarter ASC LIMIT 1""",
        (stock_id,),
    ).fetchone()
    first_buyer = fund_manager.get(first_buyer_row[0], "—") if first_buyer_row else None
    first_buyer_q = first_buyer_row[1] if first_buyer_row else None

    return {
        "stock_id": stock_id,
        "current_holders_count": current_holders,
        "holders_count_1q_ago": h1_count,
        "holders_count_2q_ago": h2_count,
        "holders_count_3q_ago": h3_count,
        "holders_count_delta_3q": current_holders - h3_count,
        "new_entrants_last_quarter": json.dumps(new_entrant_names),
        "exited_last_quarter": json.dumps(exited_names),
        "top_holder_by_dollars": top_dollar_mgr,
        "top_holder_by_dollars_value": top_dollar_val,
        "top_holder_by_conviction": top_conv_mgr,
        "top_holder_by_conviction_pct": top_conv_pct,
        "total_smart_money_value": total_value,
        "total_smart_money_value_delta": value_delta,
        "avg_holding_quarters_across": avg_hold,
        "phase": phase,
        "first_smart_buyer": first_buyer,
        "first_smart_buy_quarter": first_buyer_q,
    }


# ---------------------------------------------------------------------------
# Activity events
# ---------------------------------------------------------------------------
def fmt_money(n: float | None) -> str:
    if not n: return "—"
    a = abs(n); s = "-" if n < 0 else ""
    if a >= 1e9: return f"{s}${a/1e9:.2f}B"
    if a >= 1e6: return f"{s}${a/1e6:.0f}M"
    if a >= 1e3: return f"{s}${a/1e3:.0f}K"
    return f"{s}${a:.0f}"


def build_event_narrative(event_type: str, manager: str, magnitude: float | None,
                          pct_portfolio: float | None) -> str:
    pct_str = f" ({pct_portfolio:.1f}% portfolio)" if pct_portfolio else ""
    if event_type == "NEW":
        return f"{manager} initiated — new position{pct_str}"
    if event_type == "ADDED":
        if magnitude and magnitude > 50:
            return f"{manager} added aggressively (+{magnitude:.0f}% shares){pct_str}"
        if magnitude:
            return f"{manager} added (+{magnitude:.0f}% shares){pct_str}"
        return f"{manager} added shares{pct_str}"
    if event_type == "REDUCED":
        if magnitude:
            return f"{manager} trimmed ({magnitude:.0f}% shares){pct_str}"
        return f"{manager} trimmed{pct_str}"
    if event_type == "SOLD":
        return f"{manager} exited the position"
    if event_type == "FIRST_WHALE":
        return f"{manager} became the first tracked whale to open this stock"
    if event_type == "CONSENSUS_FORMING":
        return f"{manager} joined — multiple whales now building"
    return f"{manager}: {event_type}"


def event_importance(event_type: str, pct_portfolio: float | None) -> int:
    if event_type in ("NEW", "FIRST_WHALE"):
        return 2 if (pct_portfolio or 0) >= 2 else 1
    if event_type == "CONSENSUS_FORMING":
        return 2
    if event_type == "ADDED":
        return 2 if (pct_portfolio or 0) >= 3 else 1
    if event_type == "SOLD":
        return 1
    if event_type == "REDUCED":
        return 0
    return 0


def populate_activity_events(conn, fund_manager: dict[int, str]):
    cur = conn.cursor()
    cur.execute("DELETE FROM StockActivityEvent")

    # 1) Generate one event per HoldingChanges row
    rows = cur.execute(
        """SELECT hc.fund_id, hc.stock_id, hc.quarter, hc.change_type,
                  hc.pct_change, h.pct_portfolio
           FROM HoldingChanges hc
           LEFT JOIN Filings fi ON fi.fund_id = hc.fund_id AND fi.quarter = hc.quarter
           LEFT JOIN Holdings h ON h.filing_id = fi.id AND h.stock_id = hc.stock_id
           ORDER BY hc.quarter"""
    ).fetchall()

    inserted = 0
    for fund_id, stock_id, q, ctype, pct_change, pct_port in rows:
        mgr = fund_manager.get(fund_id, "—")
        narr = build_event_narrative(ctype, mgr, pct_change, pct_port)
        imp = event_importance(ctype, pct_port)
        cur.execute(
            """INSERT OR IGNORE INTO StockActivityEvent
               (stock_id, fund_id, quarter, event_type, magnitude_pct,
                pct_portfolio, narrative, importance)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (stock_id, fund_id, q, ctype, pct_change, pct_port, narr, imp),
        )
        inserted += 1
    conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main():
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")
    cur = conn.cursor()

    latest_q = latest_quarter_global(conn)
    print(f"Latest period_of_report: {latest_q}")

    fund_manager = {
        row[0]: (row[1] or row[2] or "—")
        for row in cur.execute("SELECT id, manager_name, name FROM Funds").fetchall()
    }

    # Every stock currently held by ≥1 fund in its latest filing
    cur.execute(
        """SELECT DISTINCT h.stock_id
           FROM Holdings h
           JOIN Filings fi ON fi.id = h.filing_id
           WHERE fi.period_of_report = (
             SELECT MAX(period_of_report) FROM Filings WHERE fund_id = fi.fund_id
           )"""
    )
    stock_ids = [r[0] for r in cur.fetchall()]
    print(f"Stocks to profile: {len(stock_ids):,}")

    cur.execute("DELETE FROM StockAccumulationProfile")

    done = 0
    for stock_id in stock_ids:
        profile = compute_stock_profile(cur, stock_id, latest_q, fund_manager)
        if not profile:
            continue
        cur.execute(
            """INSERT OR REPLACE INTO StockAccumulationProfile
               (stock_id, current_holders_count,
                holders_count_1q_ago, holders_count_2q_ago, holders_count_3q_ago,
                holders_count_delta_3q,
                new_entrants_last_quarter, exited_last_quarter,
                top_holder_by_dollars, top_holder_by_dollars_value,
                top_holder_by_conviction, top_holder_by_conviction_pct,
                total_smart_money_value, total_smart_money_value_delta,
                avg_holding_quarters_across, phase,
                first_smart_buyer, first_smart_buy_quarter,
                computed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (profile["stock_id"], profile["current_holders_count"],
             profile["holders_count_1q_ago"], profile["holders_count_2q_ago"],
             profile["holders_count_3q_ago"], profile["holders_count_delta_3q"],
             profile["new_entrants_last_quarter"], profile["exited_last_quarter"],
             profile["top_holder_by_dollars"], profile["top_holder_by_dollars_value"],
             profile["top_holder_by_conviction"], profile["top_holder_by_conviction_pct"],
             profile["total_smart_money_value"], profile["total_smart_money_value_delta"],
             profile["avg_holding_quarters_across"], profile["phase"],
             profile["first_smart_buyer"], profile["first_smart_buy_quarter"]),
        )
        done += 1
        if done % 2000 == 0:
            conn.commit()
            print(f"  ... {done:,} profiles")

    conn.commit()
    print(f"[OK] {done:,} StockAccumulationProfile rows")

    print("Building activity events …")
    n_events = populate_activity_events(conn, fund_manager)
    print(f"[OK] {n_events:,} StockActivityEvent rows")

    # Phase distribution
    rows = cur.execute(
        """SELECT phase, COUNT(*) FROM StockAccumulationProfile
           GROUP BY phase ORDER BY 2 DESC"""
    ).fetchall()
    print("\nPhase distribution:")
    for phase, c in rows:
        print(f"  {phase:<22} {c:>6,}")

    conn.close()


if __name__ == "__main__":
    main()
