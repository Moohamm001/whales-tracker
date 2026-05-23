"""Non-destructive migration: add the insight layer to an existing DB.

What this adds (idempotent — safe to re-run):

  Funds                 + fund_type, style_tags, cap_focus,
                          avg_position_size_pct, avg_holding_quarters,
                          alpha_1y, alpha_3y, alpha_5y, hit_rate_top10,
                          is_specialist
  Stocks                + market_cap_usd, market_cap_bucket, sector,
                          industry, float_shares, avg_daily_volume_usd,
                          info_fetched_at
  PositionLifecycle     NEW — one row per (fund, stock) telling the whole
                          accumulation/exit story
  StockAccumulationProfile NEW — one row per stock summarising aggregate
                          whale activity + phase classification
  StockActivityEvent    NEW — narrative event log (quarter, fund, stock,
                          event_type, narrative)

After running this, populate with:
  python data-pipeline/compute_position_lifecycle.py
  python data-pipeline/compute_accumulation.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "hedge_data.db"


# Each entry: (table, column, type, default-sql-fragment)
NEW_COLUMNS = [
    # Fund classification & skill (populated incrementally)
    ("Funds", "fund_type",              "TEXT"),
    ("Funds", "style_tags",             "TEXT"),     # comma-separated
    ("Funds", "cap_focus",              "TEXT"),     # micro/small/mid/large/all
    ("Funds", "is_specialist",          "INTEGER DEFAULT 0"),
    ("Funds", "avg_position_size_pct",  "REAL"),
    ("Funds", "avg_holding_quarters",   "REAL"),
    ("Funds", "alpha_1y",               "REAL"),
    ("Funds", "alpha_3y",               "REAL"),
    ("Funds", "alpha_5y",               "REAL"),
    ("Funds", "hit_rate_top10",         "REAL"),

    # Stock classification (populated by fetch_market_caps.py)
    ("Stocks", "market_cap_usd",        "REAL"),
    ("Stocks", "market_cap_bucket",     "TEXT"),     # micro/small/mid/large/mega
    ("Stocks", "sector",                "TEXT"),
    ("Stocks", "industry",              "TEXT"),
    ("Stocks", "float_shares",          "REAL"),
    ("Stocks", "avg_daily_volume_usd",  "REAL"),
    ("Stocks", "info_fetched_at",       "TEXT"),
]


NEW_TABLES = """
-- One row per (fund, stock) telling the full accumulation/exit story.
-- Populated by compute_position_lifecycle.py from the full filing history.
CREATE TABLE IF NOT EXISTS PositionLifecycle (
    fund_id                  INTEGER NOT NULL,
    stock_id                 INTEGER NOT NULL,

    -- Entry signals
    first_buy_quarter        TEXT,
    first_buy_shares         INTEGER,
    first_buy_value          REAL,
    first_buy_pct_portfolio  REAL,
    position_predates_window INTEGER DEFAULT 0,

    -- Cumulative pattern
    add_quarter_count        INTEGER DEFAULT 0,
    reduce_quarter_count     INTEGER DEFAULT 0,
    consecutive_adds         INTEGER DEFAULT 0,
    consecutive_reduces      INTEGER DEFAULT 0,
    total_added_shares       INTEGER DEFAULT 0,
    total_added_value        REAL DEFAULT 0,
    total_reduced_shares     INTEGER DEFAULT 0,

    -- Current state (from latest filing)
    current_shares           INTEGER DEFAULT 0,
    current_value            REAL DEFAULT 0,
    current_pct_portfolio    REAL,

    -- Cost & P&L (estimates from quarterly avg close)
    est_avg_cost             REAL,
    mark_price               REAL,
    unrealized_pnl_pct       REAL,

    -- Classification
    pattern                  TEXT,    -- probe / pyramid / linear-accumulate / re-entry / single-shot / distribute / stable
    phase                    TEXT,    -- building / holding / trimming / exited
    conviction_score         INTEGER, -- 0–100 composite
    holding_quarters         INTEGER, -- number of quarters position has been open
    last_activity_quarter    TEXT,
    last_activity_type       TEXT,

    computed_at              TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (fund_id, stock_id)
);

-- One row per stock summarising aggregate whale activity.
-- Populated by compute_accumulation.py.
CREATE TABLE IF NOT EXISTS StockAccumulationProfile (
    stock_id                       INTEGER PRIMARY KEY,
    current_holders_count          INTEGER DEFAULT 0,
    holders_count_1q_ago           INTEGER DEFAULT 0,
    holders_count_2q_ago           INTEGER DEFAULT 0,
    holders_count_3q_ago           INTEGER DEFAULT 0,
    holders_count_delta_3q         INTEGER DEFAULT 0,
    new_entrants_last_quarter      TEXT,    -- JSON array of manager names
    exited_last_quarter            TEXT,    -- JSON array of manager names
    top_holder_by_dollars          TEXT,
    top_holder_by_dollars_value    REAL,
    top_holder_by_conviction       TEXT,
    top_holder_by_conviction_pct   REAL,
    total_smart_money_value        REAL DEFAULT 0,
    total_smart_money_value_delta  REAL DEFAULT 0,
    avg_holding_quarters_across    REAL,
    phase                          TEXT,
       /* undiscovered / early-accumulation / consensus-build /
          crowded / topping / distribution */
    first_smart_buyer              TEXT,
    first_smart_buy_quarter        TEXT,
    computed_at                    TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Narrative event log. One row per (fund, stock, quarter) interesting event.
-- Populated by compute_accumulation.py.
CREATE TABLE IF NOT EXISTS StockActivityEvent (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id        INTEGER NOT NULL,
    fund_id         INTEGER NOT NULL,
    quarter         TEXT NOT NULL,
    event_type      TEXT NOT NULL,   -- NEW / ADDED / REDUCED / SOLD / FIRST_WHALE / CONSENSUS_FORMING
    magnitude_pct   REAL,            -- e.g. +40 for "doubled" or -25 for "trimmed quarter"
    pct_portfolio   REAL,            -- position size as % of fund portfolio after event
    narrative       TEXT,            -- pre-rendered string for UI
    importance      INTEGER DEFAULT 0, -- 0=low, 1=med, 2=high (for filtering feed)
    FOREIGN KEY (stock_id) REFERENCES Stocks(id),
    FOREIGN KEY (fund_id) REFERENCES Funds(id),
    UNIQUE (stock_id, fund_id, quarter, event_type)
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_stock   ON PositionLifecycle(stock_id);
CREATE INDEX IF NOT EXISTS idx_lifecycle_phase   ON PositionLifecycle(phase);
CREATE INDEX IF NOT EXISTS idx_lifecycle_pattern ON PositionLifecycle(pattern);
CREATE INDEX IF NOT EXISTS idx_accum_phase       ON StockAccumulationProfile(phase);
CREATE INDEX IF NOT EXISTS idx_activity_stock    ON StockActivityEvent(stock_id, quarter);
CREATE INDEX IF NOT EXISTS idx_activity_fund     ON StockActivityEvent(fund_id, quarter);
CREATE INDEX IF NOT EXISTS idx_activity_imp      ON StockActivityEvent(importance, quarter);
CREATE INDEX IF NOT EXISTS idx_stocks_mcap       ON Stocks(market_cap_bucket);
CREATE INDEX IF NOT EXISTS idx_stocks_sector     ON Stocks(sector);
"""


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def add_columns(cur):
    added = 0
    for table, col, col_type in NEW_COLUMNS:
        if not column_exists(cur, table, col):
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            print(f"  + {table}.{col} {col_type}")
            added += 1
    print(f"[OK] Added {added} new columns (existing columns untouched)")


def create_tables(cur):
    cur.executescript(NEW_TABLES)
    print("[OK] Created new tables / indexes (CREATE TABLE IF NOT EXISTS)")


def main():
    if not DB_PATH.exists():
        print(f"[FAIL] DB not found at {DB_PATH}")
        print("       Run setup_db.py first.")
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    add_columns(cur)
    create_tables(cur)
    conn.commit()

    # Sanity check
    for tbl in ("PositionLifecycle", "StockAccumulationProfile", "StockActivityEvent"):
        cnt = cur.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:<30} {cnt:>8,} rows")
    conn.close()


if __name__ == "__main__":
    main()
