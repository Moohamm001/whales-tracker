import Database from "better-sqlite3";
import path from "node:path";

let _db: Database.Database | null = null;

export function db(): Database.Database {
  if (_db) return _db;
  const dbPath = path.resolve(process.cwd(), "..", "hedge_data.db");
  _db = new Database(dbPath, { readonly: true, fileMustExist: true });
  return _db;
}

// ---------- Funds ----------

export type Fund = {
  id: number;
  cik: string;
  name: string;
  manager_name: string | null;
  manager_bio: string | null;
  aum_billions: number | null;
  holdings_count: number;
  total_value: number;
  latest_quarter: string | null;
};

export function listFunds(): Fund[] {
  return db()
    .prepare(
      `
      SELECT
        f.id, f.cik, f.name, f.manager_name, f.manager_bio, f.aum_billions,
        COALESCE(latest.holdings_count, 0) AS holdings_count,
        COALESCE(latest.total_value, 0)    AS total_value,
        latest.quarter                     AS latest_quarter
      FROM Funds f
      LEFT JOIN (
        SELECT fund_id, quarter, total_value, holdings_count,
               ROW_NUMBER() OVER (PARTITION BY fund_id ORDER BY period_of_report DESC) AS rn
        FROM Filings
      ) latest ON latest.fund_id = f.id AND latest.rn = 1
      ORDER BY total_value DESC, f.id ASC
    `
    )
    .all() as Fund[];
}

export type FundDetail = Fund & { quarter: string | null; filings_count: number };

export function getFund(cik: string): FundDetail | null {
  const fund = db()
    .prepare("SELECT * FROM Funds WHERE cik = ?")
    .get(cik) as any;
  if (!fund) return null;

  const latest = db()
    .prepare(
      `SELECT quarter, total_value, holdings_count, period_of_report
       FROM Filings WHERE fund_id = ?
       ORDER BY period_of_report DESC LIMIT 1`
    )
    .get(fund.id) as any;

  const fcount = db()
    .prepare("SELECT COUNT(*) AS n FROM Filings WHERE fund_id = ?")
    .get(fund.id) as any;

  return {
    ...fund,
    holdings_count: latest?.holdings_count ?? 0,
    total_value: latest?.total_value ?? 0,
    latest_quarter: latest?.quarter ?? null,
    quarter: latest?.quarter ?? null,
    filings_count: fcount?.n ?? 0,
  };
}

// ---------- Holdings with insights ----------

export type HoldingInsight = {
  ticker: string | null;
  name: string;
  cusip: string;
  shares: number;
  value: number;
  pct_portfolio: number;
  // insights derived from filing history
  first_buy_quarter: string | null;
  position_predates_window: boolean;
  last_activity_quarter: string | null;
  last_activity_type: string | null;
  est_avg_cost: number | null;
  trend: "Accumulating" | "Reducing" | "Building" | "Exiting" | "Stable" | "New";
};

/**
 * Insights per current holding, derived from historical filings:
 *   - first_buy_quarter: oldest filing quarter for this (fund, stock)
 *   - last_activity_*: most recent HoldingChanges entry for this (fund, stock)
 *   - est_avg_cost: weighted-avg over share *additions* across all filings
 *       formula: sum(value_added_at_quarter) / sum(shares_added)
 *       fallback: current value / shares  (if no history)
 *   - trend: pattern over last 3 changes
 *       3 consecutive ADDED → "Accumulating"
 *       3 consecutive REDUCED → "Exiting"
 *       latest NEW → "Building"
 *       mixed but mostly ADDED → "Accumulating"
 *       mostly REDUCED → "Reducing"
 *       none → "Stable"
 */
/**
 * Read pre-computed insights from HoldingInsights (filled by
 * data-pipeline/compute_insights.py). A single JOIN replaces the N+1 history
 * walk we used to do per request — page loads drop from multi-second to <100ms
 * on funds with thousands of holdings.
 */
export function getHoldingsWithInsights(cik: string, limit: number = 200): HoldingInsight[] {
  const rows = db()
    .prepare(
      `SELECT s.ticker, s.name, s.cusip,
              h.shares, h.value, h.pct_portfolio,
              hi.first_buy_quarter,
              hi.last_activity_quarter,
              hi.last_activity_type,
              hi.est_avg_cost,
              hi.trend,
              hi.position_predates_window
       FROM Holdings h
       JOIN Stocks   s  ON s.id  = h.stock_id
       JOIN Filings  fi ON fi.id = h.filing_id
       JOIN Funds    f  ON f.id  = fi.fund_id
       LEFT JOIN HoldingInsights hi
              ON hi.fund_id = f.id AND hi.stock_id = h.stock_id
       WHERE f.cik = ?
         AND fi.period_of_report = (
           SELECT MAX(period_of_report) FROM Filings WHERE fund_id = f.id
         )
       ORDER BY h.value DESC
       LIMIT ?`
    )
    .all(cik, limit) as any[];

  return rows.map((r) => ({
    ticker: r.ticker,
    name: r.name,
    cusip: r.cusip,
    shares: r.shares,
    value: r.value,
    pct_portfolio: r.pct_portfolio,
    first_buy_quarter: r.first_buy_quarter ?? null,
    position_predates_window: !!r.position_predates_window,
    last_activity_quarter: r.last_activity_quarter ?? null,
    last_activity_type: r.last_activity_type ?? null,
    est_avg_cost: r.est_avg_cost ?? null,
    trend: (r.trend ?? "Stable") as HoldingInsight["trend"],
  }));
}

// ---------- Quarter-over-quarter changes (for fund detail "recent activity") ----------

export type Change = {
  ticker: string | null;
  name: string;
  change_type: "NEW" | "ADDED" | "REDUCED" | "SOLD";
  shares_before: number | null;
  shares_after: number | null;
  value_before: number | null;
  value_after: number | null;
  pct_change: number | null;
  quarter: string;
};

export function getChanges(cik: string, limit: number = 200): Change[] {
  return db()
    .prepare(
      `
      SELECT s.ticker, s.name, hc.change_type,
             hc.shares_before, hc.shares_after,
             hc.value_before, hc.value_after,
             hc.pct_change, hc.quarter
      FROM HoldingChanges hc
      JOIN Stocks s ON s.id = hc.stock_id
      JOIN Funds  f ON f.id = hc.fund_id
      WHERE f.cik = ?
        AND hc.quarter = (
          SELECT MAX(quarter) FROM HoldingChanges WHERE fund_id = f.id
        )
      ORDER BY
        CASE hc.change_type
          WHEN 'NEW'     THEN 1
          WHEN 'ADDED'   THEN 2
          WHEN 'REDUCED' THEN 3
          WHEN 'SOLD'    THEN 4
        END,
        COALESCE(hc.value_after, hc.value_before) DESC
      LIMIT ?
    `
    )
    .all(cik, limit) as Change[];
}

// ---------- Top movers across all funds ----------

export type TopMover = Change & {
  fund_name: string;
  manager_name: string | null;
  cik: string;
};

export function getTopMovers(limit = 50): TopMover[] {
  return db()
    .prepare(
      `
      SELECT s.ticker, s.name, hc.change_type,
             hc.shares_before, hc.shares_after,
             hc.value_before, hc.value_after,
             hc.pct_change, hc.quarter,
             f.name AS fund_name, f.manager_name, f.cik
      FROM HoldingChanges hc
      JOIN Stocks s ON s.id = hc.stock_id
      JOIN Funds  f ON f.id = hc.fund_id
      WHERE hc.quarter = (SELECT MAX(quarter) FROM HoldingChanges)
      ORDER BY ABS(COALESCE(hc.value_after, 0) - COALESCE(hc.value_before, 0)) DESC
      LIMIT ?
    `
    )
    .all(limit) as TopMover[];
}

// ---------- Fund-level portfolio performance ----------

export type FundPerformance = {
  total_value: number;
  latest_quarter: string;
  value_1y_ago: number | null;
  value_3y_ago: number | null;
  value_5y_ago: number | null;
  change_1y_pct: number | null;
  change_3y_pct: number | null;
  change_5y_pct: number | null;
  // Total filings available — used to know if 10y data is even possible
  filings_count: number;
  oldest_quarter: string | null;
};

/**
 * Portfolio-value change over time, computed from 13F totals.
 *
 * IMPORTANT: this is NOT pure investment return. 13F portfolio value
 * conflates: (a) stock price movement on existing holdings, (b) cash inflows
 * from buys, (c) cash outflows from sells, (d) new positions. We label this
 * "Portfolio value change" in the UI rather than "Return".
 */
export function getFundPerformance(cik: string): FundPerformance | null {
  const conn = db();
  const fund = conn.prepare("SELECT id FROM Funds WHERE cik = ?").get(cik) as any;
  if (!fund) return null;

  const filings = conn
    .prepare(
      `SELECT quarter, period_of_report, total_value
       FROM Filings WHERE fund_id = ?
       ORDER BY period_of_report DESC`
    )
    .all(fund.id) as any[];

  if (filings.length === 0) return null;

  const latest = filings[0];

  // For each lookback, find the filing closest to (but not after) that target date.
  const findAt = (yearsAgo: number) => {
    const target = new Date(latest.period_of_report);
    target.setFullYear(target.getFullYear() - yearsAgo);
    const targetIso = target.toISOString().slice(0, 10);
    let best: any = null;
    for (const f of filings) {
      if (f.period_of_report <= targetIso) {
        best = f;
        break;
      }
    }
    return best;
  };

  const f1 = findAt(1);
  const f3 = findAt(3);
  const f5 = findAt(5);

  const pct = (older: any) => {
    if (!older || !older.total_value) return null;
    return ((latest.total_value - older.total_value) / older.total_value) * 100;
  };

  return {
    total_value: latest.total_value,
    latest_quarter: latest.quarter,
    value_1y_ago: f1?.total_value ?? null,
    value_3y_ago: f3?.total_value ?? null,
    value_5y_ago: f5?.total_value ?? null,
    change_1y_pct: pct(f1),
    change_3y_pct: pct(f3),
    change_5y_pct: pct(f5),
    filings_count: filings.length,
    oldest_quarter: filings[filings.length - 1]?.quarter ?? null,
  };
}

// ---------- Fund-level portfolio value series (for sparkline) ----------

export type FundSeries = { quarter: string; period_of_report: string; total_value: number }[];

// ---------- Stock-centric views ----------

export type StockHolder = {
  cik: string;
  fund_name: string;
  manager_name: string | null;
  shares: number;
  value: number;
  pct_portfolio: number;
  quarter: string;
  last_activity_quarter: string | null;
  last_activity_type: string | null;
};

export type StockSummary = {
  ticker: string | null;
  name: string;
  cusip: string;
  total_holders: number;
  total_value: number;
  total_shares: number;
  current_price: number | null;
  latest_quarter: string | null;
};

/** Look up a stock by ticker. Falls back to CUSIP if ticker not unique. */
export function getStockByTicker(ticker: string): StockSummary | null {
  const conn = db();
  const t = ticker.toUpperCase();

  // Multiple Stocks rows may share a ticker (CUSIP changes, ADRs, etc.).
  // Pick the one we have any data for.
  const stock = conn
    .prepare(
      `SELECT s.id, s.ticker, s.name, s.cusip
       FROM Stocks s
       WHERE UPPER(s.ticker) = ?
       LIMIT 1`
    )
    .get(t) as any;
  if (!stock) return null;

  // Aggregate current-quarter holdings using a CTE to compute each fund's
  // latest filing once. Replaces the O(N^2) nested subqueries.
  const agg = conn
    .prepare(
      `WITH latest AS (
         SELECT fi.id, fi.fund_id, fi.period_of_report
         FROM Filings fi
         WHERE fi.period_of_report = (
           SELECT MAX(period_of_report) FROM Filings WHERE fund_id = fi.fund_id
         )
       )
       SELECT COUNT(*) AS n, SUM(h.shares) AS shares, SUM(h.value) AS value,
              MAX(latest.period_of_report) AS latest
       FROM Holdings h
       JOIN latest ON latest.id = h.filing_id
       WHERE h.stock_id = ?`
    )
    .get(stock.id) as any;

  // Most recent close price we have
  const px = conn
    .prepare(
      `SELECT quarter_end_close FROM StockPrices
       WHERE stock_id = ? ORDER BY quarter DESC LIMIT 1`
    )
    .get(stock.id) as any;

  return {
    ticker: stock.ticker,
    name: stock.name,
    cusip: stock.cusip,
    total_holders: agg?.n ?? 0,
    total_value: agg?.value ?? 0,
    total_shares: agg?.shares ?? 0,
    current_price: px?.quarter_end_close ?? null,
    latest_quarter: agg?.latest ?? null,
  };
}

/** Every fund currently holding `ticker`, sorted by value desc. */
export function getStockHolders(ticker: string): StockHolder[] {
  const conn = db();
  const t = ticker.toUpperCase();
  return conn
    .prepare(
      `WITH latest AS (
         SELECT fi.id, fi.fund_id, fi.quarter
         FROM Filings fi
         WHERE fi.period_of_report = (
           SELECT MAX(period_of_report) FROM Filings WHERE fund_id = fi.fund_id
         )
       )
       SELECT f.cik, f.name AS fund_name, f.manager_name,
              h.shares, h.value, h.pct_portfolio, latest.quarter,
              hi.last_activity_quarter,
              hi.last_activity_type
       FROM Holdings h
       JOIN latest      ON latest.id = h.filing_id
       JOIN Funds   f   ON f.id      = latest.fund_id
       JOIN Stocks  s   ON s.id      = h.stock_id
       LEFT JOIN HoldingInsights hi
              ON hi.fund_id = f.id AND hi.stock_id = h.stock_id
       WHERE UPPER(s.ticker) = ?
       ORDER BY h.value DESC`
    )
    .all(t) as StockHolder[];
}

/** List of all stocks held by tracked funds (for an index page). */
export type StockListItem = {
  ticker: string | null;
  name: string;
  cusip: string;
  holders: number;
  total_value: number;
};

export function listMostHeldStocks(limit = 50): StockListItem[] {
  return db()
    .prepare(
      `SELECT s.ticker, s.name, s.cusip,
              COUNT(DISTINCT f.id) AS holders,
              SUM(h.value)        AS total_value
       FROM Holdings h
       JOIN Filings fi ON fi.id = h.filing_id
       JOIN Funds   f  ON f.id  = fi.fund_id
       JOIN Stocks  s  ON s.id  = h.stock_id
       WHERE fi.period_of_report = (
         SELECT MAX(period_of_report) FROM Filings WHERE fund_id = f.id
       )
       AND s.ticker IS NOT NULL
       GROUP BY s.id
       ORDER BY holders DESC, total_value DESC
       LIMIT ?`
    )
    .all(limit) as StockListItem[];
}


export function getFundSeries(cik: string): FundSeries {
  return db()
    .prepare(
      `SELECT fi.quarter, fi.period_of_report, fi.total_value
       FROM Filings fi
       JOIN Funds f ON f.id = fi.fund_id
       WHERE f.cik = ?
       ORDER BY fi.period_of_report ASC`
    )
    .all(cik) as FundSeries;
}
