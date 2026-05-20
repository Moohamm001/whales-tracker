import Link from "next/link";
import { notFound } from "next/navigation";
import Card from "@/components/Card";
import StatCard from "@/components/StatCard";
import InfoTip from "@/components/InfoTip";
import { ChangeBadge, TrendBadge } from "@/components/Badge";
import {
  getFund,
  getHoldingsWithInsights,
  getChanges,
  getFundPerformance,
} from "@/lib/db";

export const dynamic = "force-dynamic";

function fmtMoney(n: number | null | undefined): string {
  if (n == null) return "—";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9)  return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6)  return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3)  return `${sign}$${(abs / 1e3).toFixed(2)}K`;
  return `${sign}$${abs.toLocaleString()}`;
}

function fmtPrice(n: number | null | undefined): string {
  if (n == null) return "—";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(n: number | null | undefined, signed = true): string {
  if (n == null) return "—";
  const s = signed ? (n > 0 ? "+" : "") : "";
  return `${s}${n.toFixed(1)}%`;
}

function fmtShares(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString();
}

function initialsBg(name: string): string {
  const palette = ["#1abc9c", "#16a085", "#27ae60", "#3498db", "#2980b9",
                   "#9b59b6", "#8e44ad", "#34495e", "#f39c12", "#d35400", "#c0392b"];
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return palette[Math.abs(h) % palette.length];
}

function initials(name: string): string {
  return name.split(/\s+/).map((s) => s[0]).filter(Boolean).slice(0, 2).join("").toUpperCase();
}

export default function FundPage({ params }: { params: { cik: string } }) {
  const fund = getFund(params.cik);
  if (!fund) notFound();

  const holdings = getHoldingsWithInsights(params.cik);
  const changes = getChanges(params.cik);
  const perf = getFundPerformance(params.cik);
  const mgr = fund.manager_name ?? fund.name;

  return (
    <>
      <div className="text-xs text-muted mb-4">
        <Link href="/" className="text-sky">← Back to investors</Link>
      </div>

      {/* Manager hero */}
      <Card className="mb-5" pad={false}>
        <div className="p-6 flex flex-col md:flex-row md:items-center gap-5">
          <div
            className="w-20 h-20 rounded-full flex items-center justify-center text-white text-2xl font-semibold shrink-0"
            style={{ background: initialsBg(mgr) }}
          >
            {initials(mgr)}
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl font-semibold text-slate tracking-tight">
              {mgr}
            </h1>
            <div className="text-sm text-muted mt-0.5">{fund.name}</div>
            {fund.manager_bio && (
              <p className="text-sm text-slate/80 mt-2 leading-relaxed">
                {fund.manager_bio}
              </p>
            )}
            <div className="flex flex-wrap gap-x-6 gap-y-1 mt-3 text-xs text-muted">
              <span><span className="text-slate font-medium">CIK:</span> {fund.cik}</span>
              <span><span className="text-slate font-medium">Latest:</span> {fund.latest_quarter ?? "—"}</span>
              <span><span className="text-slate font-medium">Filings on file:</span> {fund.filings_count}</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Stat row */}
      <section className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
        <StatCard
          label="Portfolio value"
          value={fmtMoney(fund.total_value)}
          sub={fund.latest_quarter ?? ""}
        />
        <StatCard
          label="Positions"
          value={(fund.holdings_count ?? 0).toLocaleString()}
          sub="long equity"
        />
        <StatCard
          label="1y value Δ"
          value={fmtPct(perf?.change_1y_pct)}
          trend={
            perf?.change_1y_pct == null
              ? "neutral"
              : perf.change_1y_pct >= 0 ? "up" : "down"
          }
          sub={perf?.value_1y_ago ? `from ${fmtMoney(perf.value_1y_ago)}` : "insufficient history"}
          info="Change in total 13F portfolio value vs. a filing ~1 year ago. This is NOT a pure return — it includes buys, sells, new positions, AND price moves."
        />
        <StatCard
          label="3y value Δ"
          value={fmtPct(perf?.change_3y_pct)}
          trend={
            perf?.change_3y_pct == null
              ? "neutral"
              : perf.change_3y_pct >= 0 ? "up" : "down"
          }
          sub={perf?.value_3y_ago ? `from ${fmtMoney(perf.value_3y_ago)}` : "insufficient history"}
          info="13F portfolio value change vs. ~3 years ago. Includes capital flows, not just price performance."
        />
        <StatCard
          label="5y value Δ"
          value={fmtPct(perf?.change_5y_pct)}
          trend={
            perf?.change_5y_pct == null
              ? "neutral"
              : perf.change_5y_pct >= 0 ? "up" : "down"
          }
          sub={perf?.value_5y_ago ? `from ${fmtMoney(perf.value_5y_ago)}` : "insufficient history"}
          info="13F portfolio value change vs. ~5 years ago. Includes capital flows, not just price performance."
        />
      </section>

      {/* Holdings */}
      <Card
        title="Holdings"
        subtitle={`${holdings.length} positions in latest filing (${fund.latest_quarter ?? "—"})`}
        right={
          <span className="text-[11px]">
            sorted by value
          </span>
        }
        pad={false}
      >
        {holdings.length === 0 ? (
          <div className="p-6 text-bad text-sm">No holdings yet — run the crawler.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm zebra">
              <thead>
                <tr className="text-muted text-xs uppercase tracking-wide bg-bg border-b border-line">
                  <th className="text-right px-3 py-2.5 font-medium w-10">#</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Ticker</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Company</th>
                  <th className="text-right px-3 py-2.5 font-medium">Shares</th>
                  <th className="text-right px-3 py-2.5 font-medium">Value</th>
                  <th className="text-right px-3 py-2.5 font-medium">% Port</th>
                  <th className="text-right px-3 py-2.5 font-medium">
                    <span className="inline-flex items-center gap-1">
                      Est. Avg Cost
                      <InfoTip text="Estimated cost per share, weighted by share additions over the position's lifetime. New shares added in a quarter are valued at that quarter's average closing price (from Yahoo Finance), giving a closer approximation to actual buy price than 13F's quarter-end mark-to-market. Shows '—' if the position only shrank within our visible history (no observed buys)." />
                    </span>
                  </th>
                  <th className="text-center px-3 py-2.5 font-medium">First Buy</th>
                  <th className="text-center px-3 py-2.5 font-medium">Last Activity</th>
                  <th className="text-center px-3 py-2.5 font-medium">
                    <span className="inline-flex items-center gap-1">
                      Trend
                      <InfoTip text="Pattern from the last 3 quarterly changes. NOT a prediction. 'Accumulating' = recent adds. 'Reducing' = recent trims. 'Building' = newly opened. 'Exiting' = recent trims, likely heading to zero." />
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((h, i) => (
                  <tr key={h.cusip} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2 text-right text-muted tabular-nums">{i + 1}</td>
                    <td className="px-3 py-2 font-semibold text-navy">{h.ticker ?? "—"}</td>
                    <td className="px-3 py-2 text-slate">{h.name}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtShares(h.shares)}</td>
                    <td className="px-3 py-2 text-right tabular-nums font-medium text-slate">
                      {fmtMoney(h.value)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted">
                      {h.pct_portfolio.toFixed(2)}%
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {h.est_avg_cost == null ? (
                        <span className="tt text-muted">
                          —
                          <span className="tt-body">
                            No buys observed within our 10-year window.
                            Position likely opened earlier.
                          </span>
                        </span>
                      ) : (
                        <span className={h.position_predates_window ? "tt" : ""}>
                          {fmtPrice(h.est_avg_cost)}
                          {h.position_predates_window && (
                            <span className="tt-body">
                              Position was already on the books in {h.first_buy_quarter}
                              {" "}(start of our window). Real cost basis may be much lower
                              if Berkshire opened this position before 2016.
                            </span>
                          )}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-center text-xs text-muted">
                      {h.first_buy_quarter ? (
                        h.position_predates_window ? (
                          <span className="tt">
                            ≤ {h.first_buy_quarter}
                            <span className="tt-body">
                              Visible in our oldest filing for this fund —
                              actual purchase may pre-date our 10-year window.
                            </span>
                          </span>
                        ) : (
                          h.first_buy_quarter
                        )
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-3 py-2 text-center text-xs">
                      {h.last_activity_quarter ? (
                        <span className="inline-flex items-center gap-1">
                          <span className="text-muted">{h.last_activity_quarter}</span>
                          {h.last_activity_type && (
                            <ChangeBadge type={h.last_activity_type as any} />
                          )}
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <TrendBadge trend={h.trend} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Recent activity / changes */}
      <Card
        title="Recent activity"
        subtitle={
          changes.length
            ? `${changes.length} position changes in ${changes[0].quarter}`
            : "No prior-quarter data on file"
        }
        pad={false}
        className="mt-5"
      >
        {changes.length === 0 ? (
          <div className="p-6 text-muted text-sm">
            Need at least 2 filings to compute quarter-over-quarter changes.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm zebra">
              <thead>
                <tr className="text-muted text-xs uppercase tracking-wide bg-bg border-b border-line">
                  <th className="text-left  px-3 py-2.5 font-medium w-24">Change</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Ticker</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Company</th>
                  <th className="text-right px-3 py-2.5 font-medium">Shares Before</th>
                  <th className="text-right px-3 py-2.5 font-medium">Shares After</th>
                  <th className="text-right px-3 py-2.5 font-medium">Value After</th>
                  <th className="text-right px-3 py-2.5 font-medium">% Chg (shares)</th>
                </tr>
              </thead>
              <tbody>
                {changes.map((c, i) => (
                  <tr key={i} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2">
                      <ChangeBadge type={c.change_type} />
                    </td>
                    <td className="px-3 py-2 font-semibold text-navy">{c.ticker ?? "—"}</td>
                    <td className="px-3 py-2 text-slate">{c.name}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtShares(c.shares_before)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtShares(c.shares_after)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(c.value_after)}</td>
                    <td
                      className={`px-3 py-2 text-right tabular-nums font-medium ${
                        c.pct_change == null
                          ? "text-muted"
                          : c.pct_change > 0
                            ? "text-good"
                            : c.pct_change < 0
                              ? "text-bad"
                              : "text-muted"
                      }`}
                    >
                      {fmtPct(c.pct_change)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
