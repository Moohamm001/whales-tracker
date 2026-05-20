# Whales Tracker

**See what Warren Buffett, Bill Ackman, and 10 other famous investors are buying and selling — straight from their official filings to the U.S. government.**

A self-hosted clone of HedgeFollow.com.

---

## What's the idea?

Every three months, anyone in the U.S. who manages more than $100 million in stocks
has to publicly disclose their holdings to the SEC (the U.S. financial regulator).
These public reports are called **13F filings**.

The problem: 13F filings are huge XML documents on a government website. Useful info
is in there, but you can't really "browse" them.

Whales Tracker turns those filings into a clean dashboard so you can answer questions
like:

- What's in Warren Buffett's portfolio right now?
- Did Bill Ackman buy or sell Uber last quarter?
- Which famous investors own Apple? How much?
- What's the biggest move across all hedge funds this quarter?

---

## Who's being tracked?

Twelve well-known investors and the firms they run:

| Investor | Firm | Known for |
|---|---|---|
| Warren Buffett | Berkshire Hathaway | The "Oracle of Omaha" — long-term value investing |
| Ray Dalio | Bridgewater Associates | World's biggest hedge fund — macro / risk-parity |
| Bill Ackman | Pershing Square | Activist investor — concentrated bets |
| Jim Simons | Renaissance Technologies | Quant fund — 66% annual returns for decades |
| Michael Burry | Scion Asset Management | Predicted the 2008 crisis (*The Big Short*) |
| David Einhorn | Greenlight Capital | Famous for shorting Lehman before it collapsed |
| George Soros | Soros Fund Management | "Broke the Bank of England" in 1992 |
| David Tepper | Appaloosa LP | Distressed debt — owns the Carolina Panthers |
| Chase Coleman | Tiger Global | Tech / growth investing |
| Ken Griffin | Citadel Advisors | Multi-strategy giant — Wall St powerhouse |
| Larry Fink | BlackRock | World's largest asset manager (~$10T) |
| Stanley Druckenmiller | Duquesne Family Office | Managed Soros's flagship fund |

---

## What you can see on the site

**Home page**
A list of all 12 investors with their portfolio sizes, plus a "Most-held stocks"
panel showing what these investors agree on (usually the big tech names).

**Each investor's page**
- A short bio
- Total portfolio value, with how it's changed over 1, 3, and 5 years
- Every stock they own — sorted by how much money is in it — with:
  - **% of portfolio** — how concentrated this bet is
  - **Estimated average cost per share** — roughly what they paid
  - **First buy** — when they first showed up in our records
  - **Last activity** — did they add, trim, or sell out recently?
  - **Trend** — are they accumulating, exiting, or holding steady?
- A list of every change they made last quarter (new buys, sells, top-ups, trims)

**Each stock's page**
Picks a ticker (say `AAPL`) and shows *every* tracked investor who owns it,
ranked by position size. Great for seeing who's making the same bet as someone famous.

**Top Movers**
The 100 biggest position changes across every tracked investor for the most
recent quarter — useful for spotting trends in real time.

---

## A few important caveats

This isn't a stock-picking tool. A couple of things to keep in mind:

- **Data is 45 days late.** The SEC gives funds 45 days after quarter-end to file,
  so what you see was true 1–4 months ago, not today.
- **Only U.S. stocks.** 13F filings only cover long positions in U.S. equities.
  They don't show shorts, bonds, private companies, real estate, or cash.
- **"Average cost" is an estimate.** The filings don't tell us what funds actually
  paid for stocks — they only show the value at the end of each quarter. We estimate
  cost by matching share increases to that quarter's average stock price.
  If you see a tooltip saying "position predates our window," it means the investor
  owned it before our oldest filing — the real cost basis could be much lower
  (e.g. Buffett bought Coca-Cola in 1988 at around $3/share).
- **Trend ≠ prediction.** When the site says "Exiting" it just means the last
  three filings showed reductions — not that the investor will definitely sell more.
- **Not investment advice.** This is a data tool. Don't bet your retirement on it.

---

## Why does this exist?

Mostly because HedgeFollow charges for some of this. Also because building it is
educational — there's a real data pipeline here (SEC scraping, ticker resolution,
price normalization, accounting math) that's interesting in itself.

---

## For developers

If you want to run this locally or contribute, here's the technical setup.

### Stack
- **Pipeline**: Python 3 standard library (`urllib`, `sqlite3`, `xml.etree`) + `yfinance` for stock prices
- **Database**: SQLite (`hedge_data.db`)
- **Frontend**: Next.js 14 + TypeScript + Tailwind CSS, server-rendered

### Layout

    whales-tracker/
    ├── data-pipeline/
    │   ├── setup_db.py            # create tables, seed 12 investors
    │   ├── sec_crawler.py         # fetch 13F-HR filings from SEC EDGAR
    │   ├── fetch_stock_prices.py  # fetch quarterly avg prices from Yahoo
    │   ├── compute_insights.py    # cache per-holding analytics
    │   ├── rebuild_changes.py     # rebuild quarter-over-quarter diffs
    │   └── fix_value_units.py     # one-shot data cleanup
    ├── web/                       # Next.js app
    └── hedge_data.db              # SQLite — gitignored

### First-time setup

    # 1. Create the database and seed it with the 12 investors
    python data-pipeline/setup_db.py

    # 2. Pull every 13F filing on record for each investor (10-25 min)
    python data-pipeline/sec_crawler.py
    #    Optional: --cik=0001067983 to do one fund

    # 3. Fetch ~10 years of quarterly stock prices (~30 min)
    python data-pipeline/fetch_stock_prices.py

    # 4. Pre-compute the average-cost / trend / first-buy stats
    python data-pipeline/compute_insights.py

    # 5. Run the website
    cd web && npm install && npm run dev
    #    Open http://localhost:3000

### Refreshing data

The pipeline is idempotent — you can re-run it any time. Each step skips work
it's already done.

    python data-pipeline/sec_crawler.py        # picks up new filings
    python data-pipeline/fetch_stock_prices.py # adds prices for new tickers
    python data-pipeline/compute_insights.py   # ALWAYS re-run after new filings

### API endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/api/funds` | All tracked funds |
| GET | `/api/funds/:cik/holdings` | A fund's current holdings + insights |
| GET | `/api/funds/:cik/changes` | A fund's last-quarter buys/sells |
| GET | `/api/movers?limit=50` | Biggest position changes across all funds |
| GET | `/api/stocks/:ticker` | Every tracked fund holding this stock |

### Pages

- `/` — investor directory + most-held stocks
- `/funds/[cik]` — manager dossier, holdings, recent activity, performance
- `/stocks/[ticker]` — who owns this stock
- `/movers` — biggest quarter-over-quarter moves

### SEC compliance

The crawler identifies itself with a real email in the User-Agent (SEC requires this).
Edit `USER_AGENT` near the top of `data-pipeline/sec_crawler.py` if you fork.
Requests are paced at ~5/sec — well below SEC's 10/sec ceiling.
