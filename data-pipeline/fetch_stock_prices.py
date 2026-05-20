"""Fetch quarterly average closing prices via yfinance.

For each Stock with a non-null ticker, downloads daily history covering all
quarters our DB references and stores per-quarter mean + last close into
StockPrices. Idempotent — skips (stock_id, quarter) combinations already
present unless --force is supplied.

Used by the avg-cost estimator: when shares increase in a quarter, attribute
the new shares at that quarter's avg_close × delta_shares instead of using
the 13F quarter-end value (which masks intra-quarter price moves).

Tickers that yfinance can't resolve (delisted, foreign listings, etc.) are
left out; the avg-cost query falls back to 13F mark-to-market for those.
"""

import sqlite3
import sys
import time
from pathlib import Path

import yfinance as yf
import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "hedge_data.db"

# Suppress yfinance's repetitive progress bars and warnings
import logging
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def quarter_bounds(quarter: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """'2022Q1' -> (2022-01-01, 2022-03-31)"""
    y, q = quarter.split("Q")
    y = int(y); q = int(q)
    start_month = (q - 1) * 3 + 1
    end_month = q * 3
    start = pd.Timestamp(year=y, month=start_month, day=1)
    end = (start + pd.offsets.QuarterEnd()).normalize()
    return start, end


def quarters_for_year_range(start_year: int, end_year: int) -> list[str]:
    out = []
    for y in range(start_year, end_year + 1):
        for q in (1, 2, 3, 4):
            out.append(f"{y}Q{q}")
    return out


def get_targets(conn) -> dict[str, list[tuple[int, str]]]:
    """Return {ticker: [(stock_id, quarter), ...]} for prices we need.

    A target (stock_id, quarter) is needed when:
      - the stock has a ticker
      - the stock is referenced by a filing or change in that quarter
      - we don't already have StockPrices for it (unless --force)
    """
    cur = conn.cursor()
    # All quarters mentioned in Filings (we care about price for each historical quarter)
    cur.execute("SELECT DISTINCT quarter FROM Filings ORDER BY quarter")
    all_quarters = [r[0] for r in cur.fetchall()]

    # All stocks with tickers that appear in any Holdings
    cur.execute(
        """SELECT DISTINCT s.id, s.ticker
           FROM Stocks s
           JOIN Holdings h ON h.stock_id = s.id
           WHERE s.ticker IS NOT NULL AND s.ticker != ''
           ORDER BY s.ticker"""
    )
    stocks = cur.fetchall()
    print(f"Stocks with tickers: {len(stocks)}, quarters in scope: {len(all_quarters)}")

    # Existing prices to skip
    cur.execute("SELECT stock_id, quarter FROM StockPrices")
    have = set((r[0], r[1]) for r in cur.fetchall())

    targets: dict[str, list[tuple[int, str]]] = {}
    for stock_id, ticker in stocks:
        wanted = [(stock_id, q) for q in all_quarters if (stock_id, q) not in have]
        if wanted:
            targets.setdefault(ticker, []).extend(wanted)

    return targets


def fetch_ticker_prices(ticker: str, start_year: int, end_year: int) -> pd.DataFrame | None:
    """Download daily close history for a ticker over the year range."""
    try:
        t = yf.Ticker(ticker)
        df = t.history(
            start=f"{start_year}-01-01",
            end=f"{end_year}-12-31",
            interval="1d",
            auto_adjust=False,
        )
        if df.empty:
            return None
        return df
    except Exception as e:
        print(f"  [WARN] {ticker}: {e}")
        return None


def aggregate_quarterly(df: pd.DataFrame) -> dict[str, dict]:
    """{'2022Q1': {'avg_close': X, 'quarter_end_close': Y}}"""
    if df is None or df.empty:
        return {}
    out: dict[str, dict] = {}
    close = df["Close"]
    # Group by year + quarter
    grp = close.groupby([close.index.year, close.index.quarter])
    for (y, q), series in grp:
        if len(series) == 0:
            continue
        out[f"{y}Q{q}"] = {
            "avg_close": float(series.mean()),
            "quarter_end_close": float(series.iloc[-1]),
        }
    return out


def save_prices(conn, stock_id: int, quarters: dict[str, dict]):
    cur = conn.cursor()
    for q, vals in quarters.items():
        cur.execute(
            """INSERT OR IGNORE INTO StockPrices
               (stock_id, quarter, avg_close, quarter_end_close)
               VALUES (?, ?, ?, ?)""",
            (stock_id, q, vals.get("avg_close"), vals.get("quarter_end_close")),
        )


def main():
    args = sys.argv[1:]
    only_ticker = None
    limit_tickers = None
    for a in args:
        if a.startswith("--ticker="):
            only_ticker = a.split("=", 1)[1]
        elif a.startswith("--limit="):
            limit_tickers = int(a.split("=", 1)[1])

    # Wait up to 30s on a lock — the SEC crawler may be writing concurrently.
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000")

    # Determine the year range we need
    cur = conn.cursor()
    cur.execute("SELECT MIN(period_of_report), MAX(period_of_report) FROM Filings")
    pmin, pmax = cur.fetchone()
    if not pmin:
        print("No filings yet — run sec_crawler.py first")
        return
    start_year = int(pmin[:4])
    end_year = int(pmax[:4])
    print(f"Year range: {start_year}-{end_year}")

    targets = get_targets(conn)
    if only_ticker:
        targets = {k: v for k, v in targets.items() if k == only_ticker}
    tickers = sorted(targets.keys())
    if limit_tickers:
        tickers = tickers[:limit_tickers]

    print(f"Tickers to fetch: {len(tickers)} ({sum(len(v) for v in targets.values())} (stock,quarter) gaps)")
    if not tickers:
        print("Nothing to do.")
        return

    ok = 0
    skipped = 0
    for i, ticker in enumerate(tickers, 1):
        if i % 25 == 0 or i == 1 or i == len(tickers):
            print(f"  [{i}/{len(tickers)}] {ticker}")
        df = fetch_ticker_prices(ticker, start_year, end_year)
        if df is None or df.empty:
            skipped += 1
            continue
        q_data = aggregate_quarterly(df)
        # Apply to every (stock_id) that uses this ticker
        for stock_id, _quarter in targets[ticker]:
            save_prices(conn, stock_id, q_data)
        ok += 1
        # yfinance has aggressive rate limits — be polite
        if i % 50 == 0:
            for attempt in range(5):
                try:
                    conn.commit()
                    break
                except sqlite3.OperationalError as e:
                    print(f"  [WARN] commit blocked ({e}); retry {attempt+1}/5")
                    time.sleep(5)
            time.sleep(0.5)

    for attempt in range(5):
        try:
            conn.commit()
            break
        except sqlite3.OperationalError as e:
            print(f"  [WARN] final commit blocked ({e}); retry {attempt+1}/5")
            time.sleep(5)
    cur.execute("SELECT COUNT(*) FROM StockPrices")
    print(f"\n[DONE] Tickers fetched: {ok}, skipped: {skipped}")
    print(f"Total StockPrices rows: {cur.fetchone()[0]:,}")
    conn.close()


if __name__ == "__main__":
    main()
