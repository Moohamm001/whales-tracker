import Link from "next/link";
import { notFound } from "next/navigation";
import Card from "@/components/Card";
import StatCard from "@/components/StatCard";
import { ChangeBadge } from "@/components/Badge";
import { getStockByTicker, getStockHolders } from "@/lib/db";

export const dynamic = "force-dynamic";

function fmtMoney(n: number | null | undefined): string {
  if (n == null || !n) return "—";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9)  return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6)  return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3)  return `${sign}$${(abs / 1e3).toFixed(2)}K`;
  return `${sign}$${abs.toLocaleString()}`;
}

function fmtShares(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString();
}

function fmtPrice(n: number | null | undefined): string {
  if (n == null) return "—";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function StockPage({ params }: { params: { ticker: string } }) {
  const stock = getStockByTicker(params.ticker);
  if (!stock) notFound();
  const holders = getStockHolders(params.ticker);

  return (
    <>
      <div className="text-xs text-muted mb-4">
        <Link href="/" className="text-sky">← Back to investors</Link>
      </div>

      {/* Hero */}
      <Card className="mb-5" pad={false}>
        <div className="p-6">
          <div className="flex items-baseline gap-3">
            <h1 className="text-3xl font-bold text-navy tracking-tight">
              {stock.ticker ?? "—"}
            </h1>
            <span className="text-muted text-sm">{stock.name}</span>
          </div>
          <div className="text-xs text-muted mt-1">CUSIP: {stock.cusip}</div>
        </div>
      </Card>

      {/* Stat row */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <StatCard
          label="Tracked holders"
          value={(stock.total_holders ?? 0).toString()}
          sub="of 12 investors"
        />
        <StatCard
          label="Combined value held"
          value={fmtMoney(stock.total_value)}
          sub={stock.latest_quarter ?? ""}
          info="Sum of value across tracked investors' latest 13F filings."
        />
        <StatCard
          label="Combined shares"
          value={fmtShares(stock.total_shares)}
          sub="across tracked funds"
        />
        <StatCard
          label="Last close"
          value={fmtPrice(stock.current_price)}
          sub="quarter-end close"
          info="Quarter-end closing price from the most recent quarter we have yfinance data for."
        />
      </section>

      {/* Holders table */}
      <Card
        title="Investors holding this stock"
        subtitle={`${holders.length} fund(s) — sorted by position size`}
        pad={false}
      >
        {holders.length === 0 ? (
          <div className="p-6 text-bad text-sm">
            None of our tracked investors hold this stock right now.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm zebra">
              <thead>
                <tr className="text-muted text-xs uppercase tracking-wide bg-bg border-b border-line">
                  <th className="text-right px-3 py-2.5 font-medium w-10">#</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Investor</th>
                  <th className="text-right px-3 py-2.5 font-medium">Shares</th>
                  <th className="text-right px-3 py-2.5 font-medium">Value</th>
                  <th className="text-right px-3 py-2.5 font-medium">% of Portfolio</th>
                  <th className="text-center px-3 py-2.5 font-medium">Last Activity</th>
                </tr>
              </thead>
              <tbody>
                {holders.map((h, i) => (
                  <tr key={h.cik} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2 text-right text-muted tabular-nums">{i + 1}</td>
                    <td className="px-3 py-2">
                      <Link href={`/funds/${h.cik}`} className="font-semibold text-navy hover:text-sky">
                        {h.manager_name ?? h.fund_name}
                      </Link>
                      <div className="text-xs text-muted">{h.fund_name}</div>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtShares(h.shares)}</td>
                    <td className="px-3 py-2 text-right tabular-nums font-medium">{fmtMoney(h.value)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{h.pct_portfolio.toFixed(2)}%</td>
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
