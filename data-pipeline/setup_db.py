"""Initialize the SQLite database for whales-tracker.

Schema:
  Funds         - hedge fund / investor profiles (CIK is the SEC identifier)
  Filings       - one row per 13F-HR filing (quarter snapshot)
  Stocks        - canonical stock data, keyed by CUSIP (ticker via OpenFIGI)
  Holdings      - shares + value for (filing, stock)
  HoldingChanges- per-quarter deltas vs. previous quarter (NEW/SOLD/ADDED/REDUCED)
  CusipCache    - OpenFIGI lookup cache so re-runs don't re-hit the API
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "hedge_data.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS Funds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cik             TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    manager_name    TEXT,
    manager_bio     TEXT,
    aum_billions    REAL,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Filings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id         INTEGER NOT NULL,
    accession_no    TEXT UNIQUE NOT NULL,
    quarter         TEXT NOT NULL,
    filed_date      TEXT,
    period_of_report TEXT,
    total_value     REAL,
    holdings_count  INTEGER,
    FOREIGN KEY (fund_id) REFERENCES Funds(id)
);

CREATE TABLE IF NOT EXISTS Stocks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cusip           TEXT UNIQUE NOT NULL,
    ticker          TEXT,
    name            TEXT
);

CREATE TABLE IF NOT EXISTS Holdings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filing_id       INTEGER NOT NULL,
    stock_id        INTEGER NOT NULL,
    shares          INTEGER NOT NULL,
    value           REAL NOT NULL,
    pct_portfolio   REAL,
    FOREIGN KEY (filing_id) REFERENCES Filings(id),
    FOREIGN KEY (stock_id) REFERENCES Stocks(id),
    UNIQUE (filing_id, stock_id)
);

CREATE TABLE IF NOT EXISTS HoldingChanges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id         INTEGER NOT NULL,
    stock_id        INTEGER NOT NULL,
    quarter         TEXT NOT NULL,
    change_type     TEXT NOT NULL,
    shares_before   INTEGER,
    shares_after    INTEGER,
    value_before    REAL,
    value_after     REAL,
    pct_change      REAL,
    FOREIGN KEY (fund_id) REFERENCES Funds(id),
    FOREIGN KEY (stock_id) REFERENCES Stocks(id),
    UNIQUE (fund_id, stock_id, quarter)
);

CREATE TABLE IF NOT EXISTS CusipCache (
    cusip           TEXT PRIMARY KEY,
    ticker          TEXT,
    name            TEXT,
    looked_up_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Quarterly average closing prices for each stock, used to estimate cost
-- basis more accurately than relying on 13F quarter-end mark-to-market.
-- Populated by data-pipeline/fetch_stock_prices.py via yfinance.
CREATE TABLE IF NOT EXISTS StockPrices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id        INTEGER NOT NULL,
    quarter         TEXT NOT NULL,           -- e.g. '2022Q1'
    avg_close       REAL,                    -- mean of daily closes in the quarter
    quarter_end_close REAL,                  -- close on the last trading day of the quarter
    fetched_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (stock_id) REFERENCES Stocks(id),
    UNIQUE (stock_id, quarter)
);

CREATE INDEX IF NOT EXISTS idx_holdings_filing ON Holdings(filing_id);
CREATE INDEX IF NOT EXISTS idx_filings_fund    ON Filings(fund_id);
CREATE INDEX IF NOT EXISTS idx_changes_fund    ON HoldingChanges(fund_id, quarter);
CREATE INDEX IF NOT EXISTS idx_prices_stock    ON StockPrices(stock_id, quarter);
"""


FAMOUS_FUNDS = [
    ("0001067983", "Berkshire Hathaway Inc",
     "Warren Buffett",
     "The Oracle of Omaha. Value investor since 1956. Largest individual shareholder of Berkshire Hathaway.",
     900.0),
    ("0001350694", "Bridgewater Associates LP",
     "Ray Dalio",
     "Founder of the world's largest hedge fund. Author of 'Principles'. Macro / risk-parity strategy.",
     150.0),
    ("0001336528", "Pershing Square Capital Management",
     "Bill Ackman",
     "Activist investor. Known for concentrated long positions and high-profile shorts (Herbalife, MBIA).",
     18.0),
    ("0001037389", "Renaissance Technologies LLC",
     "Jim Simons",
     "Quantitative hedge fund founder. Medallion Fund posted ~66% annual returns over decades.",
     130.0),
    ("0001649339", "Scion Asset Management LLC",
     "Michael Burry",
     "Predicted the 2008 subprime crisis (The Big Short). Contrarian deep-value investor.",
     1.5),
    ("0001079114", "Greenlight Capital Inc",
     "David Einhorn",
     "Long-short value manager. Famously shorted Lehman Brothers before its collapse.",
     1.7),
    ("0001029160", "Soros Fund Management LLC",
     "George Soros",
     "Macro investor. 'Broke the Bank of England' in 1992 shorting the pound.",
     25.0),
    ("0001656456", "Appaloosa LP",
     "David Tepper",
     "Distressed-debt specialist. Owner of the Carolina Panthers.",
     14.0),
    ("0001167483", "Tiger Global Management LLC",
     "Chase Coleman",
     "Tiger Cub. Growth / tech investing including major private positions.",
     50.0),
    ("0001423053", "Citadel Advisors LLC",
     "Ken Griffin",
     "Multi-strategy giant. One of the most profitable hedge funds of all time.",
     65.0),
    ("0001364742", "BlackRock Inc.",
     "Larry Fink",
     "CEO of BlackRock. Largest asset manager in the world.",
     10000.0),
    ("0001536411", "Duquesne Family Office LLC",
     "Stanley Druckenmiller",
     "Managed Soros's Quantum Fund. Macro investor with 30+ years of positive returns.",
     5.0),
]


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(SCHEMA)

    for cik, name, manager, bio, aum in FAMOUS_FUNDS:
        cur.execute(
            """INSERT OR IGNORE INTO Funds (cik, name, manager_name, manager_bio, aum_billions)
               VALUES (?, ?, ?, ?, ?)""",
            (cik, name, manager, bio, aum),
        )

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM Funds")
    print(f"[OK] Database initialized at {DB_PATH}")
    print(f"[OK] Funds seeded: {cur.fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    init_db()
