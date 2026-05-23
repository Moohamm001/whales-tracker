"""Quick CLI sampler — prints top stocks per accumulation phase."""

import sqlite3
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DB = Path(__file__).resolve().parent.parent / "hedge_data.db"


def main():
    c = sqlite3.connect(DB)
    cur = c.cursor()

    print("=== EARLY ACCUMULATION: top 15 by holders-growth ===")
    cur.execute("""
        SELECT s.ticker, s.name, ap.current_holders_count, ap.holders_count_3q_ago,
               ap.holders_count_delta_3q, ap.total_smart_money_value,
               ap.total_smart_money_value_delta, ap.top_holder_by_conviction,
               ap.top_holder_by_conviction_pct, ap.new_entrants_last_quarter
        FROM StockAccumulationProfile ap JOIN Stocks s ON s.id = ap.stock_id
        WHERE ap.phase = 'early-accumulation' AND s.ticker IS NOT NULL
          AND ap.current_holders_count >= 2 AND ap.holders_count_delta_3q >= 1
        ORDER BY ap.holders_count_delta_3q DESC, ap.total_smart_money_value_delta DESC
        LIMIT 15""")
    for r in cur.fetchall():
        tkr, name, h, h3, dh, val, dval, conv, conv_pct, entrants = r
        print(f"  {tkr:8} {(name or '')[:30]:32} {h3}->{h} (+{dh})  "
              f"${val/1e6:>7.0f}M  d=${(dval or 0)/1e6:>+7.0f}M  "
              f"top:{(conv or '')[:18]:18} {conv_pct or 0:.1f}%")

    print()
    print("=== CONSENSUS-BUILD: top 10 by total $ ===")
    cur.execute("""
        SELECT s.ticker, s.name, ap.current_holders_count, ap.holders_count_delta_3q,
               ap.total_smart_money_value, ap.top_holder_by_conviction
        FROM StockAccumulationProfile ap JOIN Stocks s ON s.id = ap.stock_id
        WHERE ap.phase = 'consensus-build' AND s.ticker IS NOT NULL
        ORDER BY ap.total_smart_money_value DESC LIMIT 10""")
    for r in cur.fetchall():
        print(f"  {r[0]:8} {(r[1] or '')[:30]:32} {r[2]} hold (+{r[3]} 3Q)  "
              f"${r[4]/1e9:>5.1f}B  top:{r[5]}")

    print()
    print("=== DISTRIBUTION: top 10 (smart money exiting) ===")
    cur.execute("""
        SELECT s.ticker, s.name, ap.current_holders_count, ap.total_smart_money_value,
               ap.total_smart_money_value_delta, ap.exited_last_quarter
        FROM StockAccumulationProfile ap JOIN Stocks s ON s.id = ap.stock_id
        WHERE ap.phase = 'distribution' AND s.ticker IS NOT NULL
        ORDER BY ap.total_smart_money_value DESC LIMIT 10""")
    for r in cur.fetchall():
        print(f"  {r[0]:8} {(r[1] or '')[:30]:32} {r[2]} hold  "
              f"${r[3]/1e9:>5.1f}B  d=${(r[4] or 0)/1e6:+7.0f}M")

    print()
    print("=== PATTERN distribution across all PositionLifecycle rows ===")
    cur.execute("""SELECT pattern, COUNT(*) FROM PositionLifecycle
                   GROUP BY pattern ORDER BY 2 DESC""")
    for p, n in cur.fetchall():
        print(f"  {p:<22} {n:>6,}")

    print()
    print("=== HIGHEST CONVICTION positions across all funds ===")
    cur.execute("""
        SELECT f.manager_name, s.ticker, s.name,
               pl.current_pct_portfolio, pl.consecutive_adds,
               pl.pattern, pl.conviction_score, pl.unrealized_pnl_pct
        FROM PositionLifecycle pl
        JOIN Funds f ON f.id = pl.fund_id
        JOIN Stocks s ON s.id = pl.stock_id
        WHERE pl.phase != 'exited' AND s.ticker IS NOT NULL
        ORDER BY pl.conviction_score DESC, pl.current_pct_portfolio DESC LIMIT 15""")
    for r in cur.fetchall():
        mgr, tkr, name, pct, ca, pat, score, pnl = r
        pnl_s = f"{pnl:+.1f}%" if pnl is not None else "—"
        print(f"  {mgr[:20]:20} {tkr:8} {(name or '')[:25]:27} "
              f"{(pct or 0):>5.1f}% port  +{ca}Q in a row  {pat:<20} "
              f"score:{score} pnl:{pnl_s}")


if __name__ == "__main__":
    main()
