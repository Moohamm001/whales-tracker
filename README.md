# Whales Tracker

A HedgeFollow clone — tracks famous investors' portfolios from SEC 13F-HR filings.
Old-school DOS / BBS aesthetic (CGA palette, box-drawing borders, CRT scanlines).

## Stack

- **Pipeline**: Python 3 standard library only (`urllib`, `sqlite3`, `xml.etree`)
- **DB**: SQLite (`hedge_data.db` at repo root)
- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind CSS + better-sqlite3
- **Tickers**: OpenFIGI (free, no API key — rate limited)

## Layout

    whales-tracker/
    ├── data-pipeline/
    │   ├── setup_db.py        # init schema + seed 12 famous investors
    │   └── sec_crawler.py     # fetch latest 13F-HR + Q-over-Q diffs
    ├── web/                   # Next.js app
    │   ├── app/               # pages + API routes
    │   ├── components/
    │   └── lib/db.ts          # read-only SQLite handle + queries
    └── hedge_data.db          # SQLite database (created by setup_db.py)

## Setup

    # 1. Initialize database + seed funds
    python data-pipeline/setup_db.py

    # 2. Pull latest 13F-HR filings from SEC EDGAR
    #    (also looks up CUSIP→ticker via OpenFIGI; cached locally)
    python data-pipeline/sec_crawler.py
    #    optional: --cik=0001067983  to run a single fund

    # 3. Run the dashboard
    cd web && npm install && npm run dev
    #    -> http://localhost:3000

## Investors tracked

Warren Buffett · Ray Dalio · Bill Ackman · Jim Simons · Michael Burry ·
David Einhorn · George Soros · David Tepper · Chase Coleman · Ken Griffin ·
Larry Fink · Stanley Druckenmiller

## Endpoints

- `GET /api/funds`                        — all funds
- `GET /api/funds/:cik/holdings`          — latest filing holdings
- `GET /api/funds/:cik/changes`           — Q-over-Q diffs
- `GET /api/movers?limit=50`              — biggest position changes across all funds

## SEC compliance

- The crawler uses a real identifying User-Agent (per SEC policy).
- Edit `USER_AGENT` in `data-pipeline/sec_crawler.py` if you fork this.
- Rate limit: pacing at ~5 req/s, below SEC's 10 req/s ceiling.
