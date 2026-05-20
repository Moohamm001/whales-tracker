import Link from "next/link";
import Card from "@/components/Card";
import StatCard from "@/components/StatCard";
import { listFunds, listMostHeldStocks } from "@/lib/db";

export const dynamic = "force-dynamic";

function fmtMoney(n: number): string {
  if (!n) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6)  return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString()}`;
}

function initialsBg(name: string): string {
  // Stable hash → palette
  const palette = ["#1abc9c", "#16a085", "#27ae60", "#2ecc71", "#3498db", "#2980b9",
                   "#9b59b6", "#8e44ad", "#34495e", "#f39c12", "#d35400", "#c0392b",
                   "#16a085", "#7f8c8d"];
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return palette[Math.abs(h) % palette.length];
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((s) => s[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export default function HomePage() {
  const funds = listFunds();
  const hasData = funds.some((f) => f.total_value > 0);
  const totalAum = funds.reduce((s, f) => s + (f.total_value || 0), 0);
  const totalPositions = funds.reduce((s, f) => s + (f.holdings_count || 0), 0);
  const fundsWithData = funds.filter((f) => f.total_value > 0).length;
  const popular = listMostHeldStocks(15);

  return (
    <>
      {/* Hero */}
      <section className="mb-6">
        <h1 className="text-2xl font-semibold text-slate tracking-tight">
          Hedge fund &amp; super-investor portfolios
        </h1>
        <p className="text-muted text-sm mt-1 max-w-2xl">
          Track quarterly 13F-HR filings from {funds.length} of the most-followed investors.
          See top holdings, position changes, estimated cost basis, and historical trends.
        </p>
      </section>

      {/* Stat row */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <StatCard
          label="Investors tracked"
          value={`${fundsWithData} / ${funds.length}`}
          sub="with at least one filing"
        />
        <StatCard
          label="Combined AUM"
          value={fmtMoney(totalAum)}
          sub="latest filed quarter"
          info="Sum of latest 13F portfolio values across all tracked investors. Excludes non-13F assets (private equity, bonds, etc.)."
        />
        <StatCard
          label="Tracked positions"
          value={totalPositions.toLocaleString()}
          sub="across all funds"
        />
        <StatCard
          label="Data source"
          value="SEC 13F-HR"
          sub="updated 45 days after quarter end"
          info="13F-HR filings are public reports US institutional managers (>$100M AUM) must file 45 days after each quarter-end. Long equity positions only."
        />
      </section>

      {/* Fund directory */}
      <Card
        title="Investor directory"
        subtitle="Click an investor to view holdings, recent activity, and trends."
        pad={false}
      >
        {!hasData ? (
          <div className="p-6 text-bad text-sm">
            No filings ingested yet. Run{" "}
            <code className="font-mono text-xs bg-bg px-1 py-0.5 rounded">
              python data-pipeline/sec_crawler.py
            </code>{" "}
            to pull data from SEC EDGAR.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm zebra">
              <thead>
                <tr className="text-muted text-xs uppercase tracking-wide bg-bg border-b border-line">
                  <th className="text-left  px-4 py-2.5 font-medium">Investor</th>
                  <th className="text-left  px-4 py-2.5 font-medium">Fund</th>
                  <th className="text-right px-4 py-2.5 font-medium">Portfolio Value</th>
                  <th className="text-right px-4 py-2.5 font-medium">Positions</th>
                  <th className="text-center px-4 py-2.5 font-medium">Latest Quarter</th>
                </tr>
              </thead>
              <tbody>
                {funds.map((f) => (
                  <tr key={f.cik} className="border-b border-line/60 last:border-0">
                    <td className="px-4 py-3">
                      <Link
                        href={`/funds/${f.cik}`}
                        className="flex items-center gap-3 hover:no-underline"
                      >
                        <span
                          className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0"
                          style={{ background: initialsBg(f.manager_name ?? f.name) }}
                        >
                          {initials(f.manager_name ?? f.name)}
                        </span>
                        <span className="font-semibold text-navy">
                          {f.manager_name ?? "—"}
                        </span>
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-muted">{f.name}</td>
                    <td className="px-4 py-3 text-right font-semibold text-slate tabular-nums">
                      {fmtMoney(f.total_value)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {f.holdings_count?.toLocaleString() || "—"}
                    </td>
                    <td className="px-4 py-3 text-center text-muted text-xs">
                      {f.latest_quarter ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Most-held stocks */}
      {popular.length > 0 && (
        <Card
          title="Most-held stocks"
          subtitle="Stocks held by the highest number of tracked investors"
          pad={false}
          className="mt-5"
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm zebra">
              <thead>
                <tr className="text-muted text-xs uppercase tracking-wide bg-bg border-b border-line">
                  <th className="text-left  px-4 py-2.5 font-medium">Ticker</th>
                  <th className="text-left  px-4 py-2.5 font-medium">Company</th>
                  <th className="text-right px-4 py-2.5 font-medium">Holders</th>
                  <th className="text-right px-4 py-2.5 font-medium">Combined value</th>
                </tr>
              </thead>
              <tbody>
                {popular.map((s) => (
                  <tr key={s.cusip} className="border-b border-line/60 last:border-0">
                    <td className="px-4 py-2 font-semibold text-navy">
                      <Link href={`/stocks/${s.ticker}`} className="hover:text-sky">
                        {s.ticker}
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-slate">{s.name}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{s.holders}</td>
                    <td className="px-4 py-2 text-right tabular-nums font-medium">
                      {fmtMoney(s.total_value)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Methodology note */}
      <p className="mt-6 text-xs text-muted leading-relaxed max-w-3xl">
        13F-HR filings disclose long US equity positions of institutional managers
        with &gt;$100M AUM, filed 45 days after each quarter-end. Whales Tracker
        derives historical trends, cost-basis estimates, and quarter-over-quarter
        changes purely from these public filings. Estimates are not actual cost basis
        and should not be used for investment decisions.
      </p>
    </>
  );
}
