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
export function getHoldingsWithInsights(cik: string): HoldingInsight[] {
  const conn = db();
  const fund = conn.prepare("SELECT id FROM Funds WHERE cik = ?").get(cik) as any;
  if (!fund) return [];

  const currentHoldings = conn
    .prepare(
      `SELECT s.id AS stock_id, s.ticker, s.name, s.cusip,
              h.shares, h.value, h.pct_portfolio
       FROM Holdings h
       JOIN Stocks  s  ON s.id = h.stock_id
       JOIN Filings fi ON fi.id = h.filing_id
       WHERE fi.fund_id = ?
         AND fi.period_of_report = (
           SELECT MAX(period_of_report) FROM Filings WHERE fund_id = ?
         )
       ORDER BY h.value DESC`
    )
    .all(fund.id, fund.id) as any[];

  // Per-stock: all (quarter, shares, value) tuples for this fund's filings,
  // LEFT JOINed with quarterly avg close price from StockPrices when available.
  const historyStmt = conn.prepare(
    `SELECT fi.quarter, fi.period_of_report, h.shares, h.value,
            sp.avg_close
     FROM Holdings h
     JOIN Filings fi ON fi.id = h.filing_id
     LEFT JOIN StockPrices sp
            ON sp.stock_id = h.stock_id AND sp.quarter = fi.quarter
     WHERE fi.fund_id = ? AND h.stock_id = ?
     ORDER BY fi.period_of_report ASC`
  );

  const recentChangesStmt = conn.prepare(
    `SELECT change_type, quarter
     FROM HoldingChanges
     WHERE fund_id = ? AND stock_id = ?
     ORDER BY quarter DESC LIMIT 3`
  );

  // Oldest filing quarter we have for the fund — used to flag positions that
  // pre-date our visible window.
  const oldestFundQuarter = (conn
    .prepare(
      `SELECT quarter FROM Filings WHERE fund_id = ?
       ORDER BY period_of_report ASC LIMIT 1`
    )
    .get(fund.id) as any)?.quarter ?? null;

  return currentHoldings.map((h) => {
    const history = historyStmt.all(fund.id, h.stock_id) as any[];
    const recent = recentChangesStmt.all(fund.id, h.stock_id) as any[];

    const first_buy_quarter = history.length ? history[0].quarter : null;
    // True if our window starts with the position already on the books (so
    // "first buy" is really the start of our data, not the actual purchase).
    const position_predates_window =
      first_buy_quarter !== null && first_buy_quarter === oldestFundQuarter;

    // Estimated avg cost: weighted by share additions across all quarters.
    // Prefer the quarterly average close from yfinance (StockPrices.avg_close)
    // over the 13F's quarter-end mark-to-market — closer to what the fund
    // actually paid intra-quarter.
    let added_shares = 0;
    let added_value = 0;
    let prev_shares = 0;
    let prev_value = 0;
    for (const row of history) {
      if (row.shares > prev_shares) {
        const delta_sh = row.shares - prev_shares;
        const delta_val = Math.max(0, row.value - prev_value);
        // Pick the most accurate per-share price available:
        //   1. yfinance quarterly avg close
        //   2. 13F implied per-share (delta_val / delta_sh) when shares > 0
        let per_share: number;
        if (row.avg_close && row.avg_close > 0) {
          per_share = row.avg_close;
        } else {
          per_share = delta_sh > 0 ? delta_val / delta_sh : 0;
        }
        added_shares += delta_sh;
        added_value  += delta_sh * per_share;
      }
      prev_shares = row.shares;
      prev_value  = row.value;
    }
    let est_avg_cost: number | null = null;
    if (added_shares > 0) {
      est_avg_cost = added_value / added_shares;
    } else if (h.shares > 0) {
      // Position only got reduced within our window, so we never observed a buy.
      // Don't fall back to current price — that's misleading. Return null and
      // let the UI render "—" with a tooltip explaining.
      est_avg_cost = null;
    }

    let last_activity_quarter: string | null = null;
    let last_activity_type: string | null = null;
    if (recent.length) {
      last_activity_quarter = recent[0].quarter;
      last_activity_type = recent[0].change_type;
    }

    // Trend
    let trend: HoldingInsight["trend"] = "Stable";
    if (recent.length > 0) {
      const types = recent.map((r) => r.change_type);
      if (types[0] === "NEW") {
        trend = "Building";
      } else {
        const addCount = types.filter((t) => t === "ADDED").length;
        const redCount = types.filter((t) => t === "REDUCED").length;
        if (addCount === types.length && types.length >= 2) {
          trend = "Accumulating";
        } else if (redCount === types.length && types.length >= 2) {
          trend = "Exiting";
        } else if (addCount > redCount) {
          trend = "Accumulating";
        } else if (redCount > addCount) {
          trend = "Reducing";
        }
      }
    }

    return {
      ticker: h.ticker,
      name: h.name,
      cusip: h.cusip,
      shares: h.shares,
      value: h.value,
      pct_portfolio: h.pct_portfolio,
      first_buy_quarter,
      position_predates_window,
      last_activity_quarter,
      last_activity_type,
      est_avg_cost,
      trend,
    };
  });
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

export function getChanges(cik: string): Change[] {
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
    `
    )
    .all(cik) as Change[];
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
