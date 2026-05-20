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

## How it works (methodology)

This section explains exactly where every number on the site comes from, and how
we calculate it. None of it is magic — it's all derived from three public data
sources combined with some arithmetic.

### Where we get the data

We use **three free public data sources**. No paid feeds, no scraping of anyone's
proprietary site.

#### 1. SEC EDGAR — the 13F filings themselves

This is the U.S. Securities and Exchange Commission's public filing system.
By law, every institutional investor managing more than $100 million in U.S.
equities must file a **13F-HR** report listing their holdings within 45 days
of each quarter's end.

- **What we fetch**:
  - The submissions index for each investor:
    `https://data.sec.gov/submissions/CIK{10-digit-CIK}.json`
    This returns metadata for that fund's recent filings (last ~1000 of any
    form type). For older filings, the same JSON points to "archive" files at
    `https://data.sec.gov/submissions/CIK{...}-submissions-NNN.json` —
    we follow those too, so Berkshire goes back to 1998.
  - For each 13F-HR, the filing's index:
    `https://www.sec.gov/Archives/edgar/data/{CIK}/{accession-no-dashes}/index.json`
  - The actual holdings XML inside that filing (usually named `informationtable.xml`
    or `*infotable*.xml`).
- **Rules we follow**:
  - SEC requires a `User-Agent` header that identifies you with name + email.
    Ours is set in `data-pipeline/sec_crawler.py` at the top — edit before
    you run this.
  - SEC limits requests to **10/sec**. We pace at ~5/sec for safety.
- **Code**: `data-pipeline/sec_crawler.py`

Each 13F-HR XML row gives us, for one holding:

| Field | What it is |
|---|---|
| `nameOfIssuer` | The company name (e.g. "APPLE INC") |
| `cusip` | A 9-char code identifying the exact security |
| `value` | Total market value held at quarter-end |
| `sshPrnamt` | Number of shares (or principal amount for bonds) |
| `sshPrnamtType` | `SH` for shares, `PRN` for principal — we keep only `SH` |

#### 2. OpenFIGI — converting CUSIPs to tickers

The SEC filing identifies stocks by CUSIP, not ticker. So a row says "037833100,
\$50B held" rather than "AAPL, \$50B". To make that readable we translate CUSIPs
into tickers via [OpenFIGI](https://www.openfigi.com/), Bloomberg's free
identifier-mapping API.

- **Endpoint**: `POST https://api.openfigi.com/v3/mapping`
- **Body**: `[{"idType": "ID_CUSIP", "idValue": "037833100"}]`
- **Response**: an array with ticker, security name, exchange code, etc.
- **Rate limits (unauthenticated)**: 25 requests per 6 seconds, 10 lookups per
  request. We batch 10-at-a-time and pace at 0.3s/batch.
- We **cache every lookup** in a `CusipCache` table so we never repeat the
  same query, even across runs. After the first crawl most CUSIPs are cached
  (~4,000+ unique CUSIPs in our DB).
- If OpenFIGI rate-limits us 3 times in a row for one fund, we open a "circuit
  breaker" — skip remaining lookups for that fund (failed ones get retried on
  the next run). This prevents a giant fund like Renaissance (with thousands
  of new CUSIPs) from stalling the whole crawl.
- **Code**: `data-pipeline/sec_crawler.py` → `lookup_cusips_openfigi()`

#### 3. Yahoo Finance — historical stock prices

To estimate what a fund actually *paid* for a stock (vs. what it was worth at
quarter-end), we need real price history. We use the
[yfinance](https://github.com/ranaroussi/yfinance) Python library, which
scrapes Yahoo Finance.

- For every ticker that appears in any holding, we download daily closes for
  the full year range our database covers (~25 years).
- We then **aggregate to quarterly statistics**:
  - `avg_close` — mean of all daily closes within the quarter
  - `quarter_end_close` — close on the last trading day of the quarter
- Stored in the `StockPrices` table, keyed by `(stock_id, quarter)`.
- Tickers Yahoo can't resolve (bonds, delisted, foreign listings, crypto
  pairs that snuck through OpenFIGI) are silently skipped — for those, the
  avg-cost calculation falls back to 13F implied price.
- **Code**: `data-pipeline/fetch_stock_prices.py`

### Calculations explained

Once we have the raw data, the interesting numbers are all derived. Here's
exactly how, in the order they appear on the site.

#### Value normalization (thousands vs. dollars)

The SEC changed its 13F rules in late 2022: filings for periods ending
2022-12-31 onward must report values in **whole dollars**. Earlier filings
reported in **thousands of dollars** — but adoption was uneven (Bridgewater
and Pershing Square were already in dollars in 2016; Berkshire stayed in
thousands until 2022-Q3).

To detect what scale we're in, we compute the **average implied per-share
price** across the filing's holdings:

    avg_per_share = mean(value / shares) over all positions with shares > 0

- If `avg_per_share < $5`, the filing is in thousands → we multiply every
  value by 1000.
- Otherwise we leave it.

This threshold works because no real equity portfolio averages below $5/share
when its values are in dollars (even penny-stock funds rarely do).

**Code**: `data-pipeline/sec_crawler.py` → `normalize_values()`
**One-shot rescue**: `data-pipeline/fix_value_units.py` (if old buggy data
remains in your DB from before this fix).

#### CUSIP aggregation

A single 13F sometimes lists the same stock multiple times (different
discretion buckets, multiple sub-advisors). We sum shares and values across
all rows that share a CUSIP before inserting, so each (filing, stock) pair
is exactly one row in our `Holdings` table.

**Code**: `data-pipeline/sec_crawler.py` → `aggregate_by_cusip()`

#### % of portfolio

For a given holding `h` in filing `f`:

    pct_portfolio = h.value / SUM(h.value across all holdings in f) × 100

So if Buffett has \$57B of AAPL in a $263B portfolio, AAPL is 21.99% of his
portfolio. Computed at write-time and stored in `Holdings.pct_portfolio`.

#### Quarter-over-quarter changes

For each filing, we compare it to the **immediately preceding** filing for
the same fund:

| Outcome | Change type |
|---|---|
| Stock in current but not previous | `NEW` |
| Stock in previous but not current | `SOLD` |
| Shares increased | `ADDED` |
| Shares decreased | `REDUCED` |
| Shares identical | no row written |

Percentage change is:

    pct_change = (shares_after - shares_before) / shares_before × 100

(Or `-100%` for SOLD, `null` for NEW.)

Stored in the `HoldingChanges` table, one row per (fund, stock, quarter).

**Code**: `data-pipeline/sec_crawler.py` → `compute_changes()` and
`backfill_changes()`. Standalone rebuild: `data-pipeline/rebuild_changes.py`.

#### Estimated average cost per share

This is the trickiest one because **13F doesn't contain purchase price**.
A fund could have bought all their shares on the first day of the quarter
at $100 or the last day at $150 — the filing only shows the quarter-end
value. So any "avg cost" you see anywhere (here, HedgeFollow, WhaleWisdom)
is an estimate.

Our approach: for each (fund, stock) pair, walk through every quarter we
have a filing for, in chronological order. Whenever shares went **up**
from the previous quarter, attribute the new shares at the **average
closing price of that quarter** (from Yahoo Finance), like this:

    for each quarter in history:
        if shares > prev_shares:
            delta_shares = shares - prev_shares
            per_share_price = StockPrices.avg_close for this quarter
                              (fallback: filing_value_change / delta_shares)
            added_shares += delta_shares
            added_value  += delta_shares × per_share_price
        prev_shares = shares

    est_avg_cost = added_value / added_shares

Reductions don't change the cost basis (standard accounting — when you sell
some shares the per-share cost of the remaining ones is unchanged).

**Special case**: if no buys are observed within our window (only reductions
or no change), `est_avg_cost = null` and the UI shows "—" with a tooltip
explaining "no buys observed."

**Why this can differ from HedgeFollow**:
- They have data going back to a position's inception. Buffett bought KO in
  1988 at ~\$3/share, AXP in 1991 at ~\$8 — our data only goes back to 1998 at
  earliest, so for positions held throughout we mark them "≤ {oldest_quarter}"
  and explicitly flag that the real cost is likely lower.
- They may use VWAP or intraday data; we use daily-close average.

**Code**: `data-pipeline/compute_insights.py`

#### First buy quarter

The quarter of the **oldest filing** in our database that lists this stock
for this fund. If that equals the fund's oldest filing overall, we set
`position_predates_window = true` so the UI shows `≤ {quarter}` with a
tooltip.

#### Last activity

The quarter of the **most recent `HoldingChanges` row** for this (fund, stock).
The change type (`NEW`/`ADDED`/`REDUCED`/`SOLD`) is shown as a badge.

#### Trend

Pattern recognition from the last 3 changes:

| Recent changes | Trend |
|---|---|
| Most recent is `NEW` | **Building** |
| All `ADDED` (≥2 in a row) | **Accumulating** |
| All `REDUCED` (≥2 in a row) | **Exiting** |
| More `ADDED` than `REDUCED` | **Accumulating** |
| More `REDUCED` than `ADDED` | **Reducing** |
| No changes at all | **Stable** |

**Important**: this is a backward-looking pattern, **not a prediction**.
"Exiting" means recent quarters showed reductions — it does not mean the
investor will keep selling.

#### Portfolio value change (1y / 3y / 5y)

For each lookback (1, 3, 5 years), we find the filing closest to
`today - N years` (without going past it) and compute:

    pct_change = (current_value - historical_value) / historical_value × 100

**Important caveat**: this is **not a pure investment return**. The portfolio
value changes because of (a) stocks going up or down in price, (b) the fund
buying or selling, (c) opening or closing positions. We label this on the
site as "value Δ" rather than "return" and tooltip the difference.

#### Most-held stocks (home page)

For each stock currently held in any fund's latest filing:

    holders = COUNT(DISTINCT fund_id)
    total_value = SUM(value across all funds)

Sorted by `holders` descending, then `total_value` descending. So a stock
held by 10 of our 12 investors ranks above one held by 6, regardless of
dollar size.

#### Stock-centric view ("who owns AAPL?")

For a given ticker, we list every (fund, stock) row whose:

- `stock.ticker = $TICKER`
- The row is in the fund's most recent filing

…sorted by `value` descending. Last activity comes from the cached
`HoldingInsights` table so the query stays fast even for popular stocks
held by many funds.

### Data freshness & refresh cycle

- **13F-HR filings** are released ~45 days after each quarter ends. So if
  today is May 15, the most recent filings cover positions as of March 31.
- We **never** auto-refresh. To pull new data:
  1. `python data-pipeline/sec_crawler.py` (idempotent — skips filings
     already in our DB)
  2. `python data-pipeline/fetch_stock_prices.py` (adds prices for new
     tickers and new quarters)
  3. `python data-pipeline/compute_insights.py` — **must** re-run after a
     new crawl, otherwise the new data won't show up properly on fund pages

### Database schema (for the curious)

| Table | What's in it |
|---|---|
| `Funds` | The 12 investors — CIK, manager name, bio, AUM estimate |
| `Filings` | One row per 13F-HR — quarter, total value, holdings count |
| `Stocks` | One row per (CUSIP, ticker, name) — populated by OpenFIGI |
| `Holdings` | The core data — for each (filing, stock): shares, value, % of portfolio |
| `HoldingChanges` | Q-over-Q diffs — NEW/ADDED/REDUCED/SOLD per (fund, stock, quarter) |
| `StockPrices` | Quarterly avg + end-of-quarter close per stock, from Yahoo |
| `CusipCache` | Memoized OpenFIGI lookups so re-runs are fast |
| `HoldingInsights` | Pre-computed per-(fund, stock) stats (avg cost, trend, etc.) — populated by `compute_insights.py` |

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
