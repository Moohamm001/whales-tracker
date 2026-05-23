"""Fetch market cap, sector, industry, float for each tracked stock.

Why: needed to filter the Discovery screen by cap-segment ("show only
small/microcap accumulation"). Without this, every stock looks the same
size to the UI.

Buckets:
   < $300M   →  micro
   $300M-2B  →  small
   $2B-10B   →  mid
   $10B-200B →  large
   > $200B   →  mega

Slow — pulls one yfinance .info per ticker. ~3000 tickers / hour.
Idempotent: skips tickers updated in the last 7 days unless --force.

Run:
  python data-pipeline/fetch_market_caps.py
  python data-pipeline/fetch_market_caps.py --limit=500       # batch
  python data-pipeline/fetch_market_caps.py --ticker=AAPL     # one
"""

import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

DB_PATH = Path(__file__).resolve().parent.parent / "hedge_data.db"


def bucket(mcap: float | None) -> str | None:
    if mcap is None or mcap <= 0:
        return None
    if mcap < 3e8:   return "micro"
    if mcap < 2e9:   return "small"
    if mcap < 1e10:  return "mid"
    if mcap < 2e11:  return "large"
    return "mega"


def get_tickers_to_fetch(conn, force: bool = False, limit: int | None = None):
    cur = conn.cursor()
    if force:
        cur.execute(
            """SELECT id, ticker FROM Stocks
               WHERE ticker IS NOT NULL AND ticker != ''
               ORDER BY id"""
        )
    else:
        cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
        cur.execute(
            """SELECT id, ticker FROM Stocks
               WHERE ticker IS NOT NULL AND ticker != ''
                 AND (info_fetched_at IS NULL OR info_fetched_at < ?)
               ORDER BY id""",
            (cutoff,),
        )
    rows = cur.fetchall()
    if limit:
        rows = rows[:limit]
    return rows


def fetch_one(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        mcap  = info.get("marketCap")
        sec   = info.get("sector")
        ind   = info.get("industry")
        fl    = info.get("floatShares")
        # ADV in dollars ≈ avg-volume * price
        adv = None
        if info.get("averageDailyVolume10Day") and info.get("regularMarketPrice"):
            adv = info["averageDailyVolume10Day"] * info["regularMarketPrice"]
        return {
            "market_cap_usd": float(mcap) if mcap else None,
            "market_cap_bucket": bucket(mcap),
            "sector": sec,
            "industry": ind,
            "float_shares": float(fl) if fl else None,
            "avg_daily_volume_usd": float(adv) if adv else None,
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    force = "--force" in sys.argv
    only = None
    limit = None
    for a in sys.argv[1:]:
        if a.startswith("--ticker="): only = a.split("=", 1)[1].upper()
        if a.startswith("--limit="):  limit = int(a.split("=", 1)[1])

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    cur = conn.cursor()

    targets = get_tickers_to_fetch(conn, force=force, limit=limit)
    if only:
        targets = [r for r in targets if (r[1] or "").upper() == only]

    print(f"Tickers to fetch: {len(targets)}")
    if not targets:
        return

    ok = 0; skipped = 0
    for i, (stock_id, ticker) in enumerate(targets, 1):
        if i % 50 == 0 or i == 1 or i == len(targets):
            print(f"  [{i}/{len(targets)}] {ticker}")
        info = fetch_one(ticker)
        if "error" in info:
            skipped += 1
            continue
        cur.execute(
            """UPDATE Stocks
               SET market_cap_usd = COALESCE(?, market_cap_usd),
                   market_cap_bucket = COALESCE(?, market_cap_bucket),
                   sector = COALESCE(?, sector),
                   industry = COALESCE(?, industry),
                   float_shares = COALESCE(?, float_shares),
                   avg_daily_volume_usd = COALESCE(?, avg_daily_volume_usd),
                   info_fetched_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (info["market_cap_usd"], info["market_cap_bucket"],
             info["sector"], info["industry"],
             info["float_shares"], info["avg_daily_volume_usd"],
             stock_id),
        )
        ok += 1
        if i % 100 == 0:
            conn.commit()
            time.sleep(0.3)

    conn.commit()
    cur.execute(
        """SELECT market_cap_bucket, COUNT(*) FROM Stocks
           WHERE market_cap_bucket IS NOT NULL
           GROUP BY market_cap_bucket ORDER BY 2 DESC"""
    )
    print(f"\n[DONE] Fetched {ok}, skipped {skipped}")
    print("Cap bucket distribution:")
    for b, c in cur.fetchall():
        print(f"  {b:<10} {c:>6,}")
    conn.close()


if __name__ == "__main__":
    main()
