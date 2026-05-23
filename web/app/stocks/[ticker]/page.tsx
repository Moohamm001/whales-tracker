import Link from "next/link";
import { notFound } from "next/navigation";
import Card from "@/components/Card";
import StatCard from "@/components/StatCard";
import { ChangeBadge } from "@/components/Badge";
import PhaseBadge, { PatternBadge, ConvictionStars } from "@/components/PhaseBadge";
import {
  getStockByTicker,
  getStockAccumulation,
  getStockHolderDetails,
  getStockActivityFeed,
} from "@/lib/db";

export const dynamic = "force-dynamic";

function fmtMoney(n: number | null | undefined): string {
  if (n == null || !n) return "—";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9)  return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6)  return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3)  return `${sign}$${(abs / 1e3).toFixed(1)}K`;
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

function fmtPct(n: number | null | undefined, digits = 1): string {
  if (n == null) return "—";
  const s = n > 0 ? "+" : "";
  return `${s}${n.toFixed(digits)}%`;
}

function holdingPeriod(q: number | null | undefined): string {
  if (q == null) return "—";
  if (q < 4) return `${q}Q`;
  const years = (q / 4).toFixed(1);
  return `${years}y`;
}

export default function StockPage({ params }: { params: { ticker: string } }) {
  const stock = getStockByTicker(params.ticker);
  if (!stock) notFound();
  const accumulation = getStockAccumulation(params.ticker);
  const holders = getStockHolderDetails(params.ticker);
  const events = getStockActivityFeed(params.ticker, 25);

  const phaseDescription: Record<string, string> = {
    "early-accumulation":
      "A small group of smart funds are quietly opening positions. Edge window is widest here — broader market hasn't recognised this name yet.",
    "consensus-build":
      "Multiple smart funds are independently arriving at the same conclusion. Strongest aggregate signal, but the edge starts to compress as more participants join.",
    "crowded":
      "Many tracked funds hold this name and growth is slowing. The easy alpha has been captured; positioning is now consensus.",
    "topping":
      "Some funds are beginning to trim while holder count stays flat. Often a 1-2 quarter warning that smart money is starting to walk.",
    "distribution":
      "Multiple funds are actively trimming and aggregate dollar value is declining. Smart money is exiting.",
    "holding":
      "Position established, no significant net buying or selling activity across tracked funds.",
    "undiscovered":
      "Few or no tracked funds currently hold this name.",
  };

  return (
    <>
      <div className="text-xs text-muted mb-4">
        <Link href="/" className="text-sky">← Back to investors</Link>
        <span className="mx-2 text-muted/50">|</span>
        <Link href="/discover" className="text-sky">Discover screen</Link>
      </div>

      {/* Hero with phase */}
      <Card className="mb-5" pad={false}>
        <div className="p-6">
          <div className="flex items-baseline gap-3 flex-wrap">
            <h1 className="text-3xl font-bold text-navy tracking-tight">
              {stock.ticker ?? "—"}
            </h1>
            <span className="text-muted text-sm">{stock.name}</span>
            {accumulation && <PhaseBadge phase={accumulation.phase} />}
          </div>
          <div className="text-xs text-muted mt-1">CUSIP: {stock.cusip}</div>
          {accumulation && (
            <p className="mt-3 text-sm text-slate max-w-3xl leading-relaxed">
              {phaseDescription[accumulation.phase] ?? ""}
            </p>
          )}
        </div>
      </Card>

      {/* Stat row */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <StatCard
          label="Tracked holders"
          value={(accumulation?.current_holders_count ?? stock.total_holders ?? 0).toString()}
          sub={
            accumulation
              ? `${accumulation.holders_count_3q_ago} → ${accumulation.holders_count_2q_ago} → ${accumulation.holders_count_1q_ago} → ${accumulation.current_holders_count}`
              : "across tracked funds"
          }
          info="Number of tracked funds holding this stock in their latest filing. The 3Q trend shows whether smart-money interest is growing or shrinking."
        />
        <StatCard
          label="Combined value held"
          value={fmtMoney(accumulation?.total_smart_money_value ?? stock.total_value)}
          sub={
            accumulation
              ? `Δ ${fmtMoney(accumulation.total_smart_money_value_delta)} vs 1Q ago`
              : (stock.latest_quarter ?? "")
          }
          info="Aggregate dollar value across all tracked funds' latest filings. Δ is change vs ~1 quarter ago."
        />
        <StatCard
          label="Top conviction"
          value={accumulation?.top_holder_by_conviction ?? "—"}
          sub={
            accumulation?.top_holder_by_conviction_pct
              ? `${accumulation.top_holder_by_conviction_pct.toFixed(2)}% of their portfolio`
              : ""
          }
          info="The tracked investor for whom this position is the highest % of their portfolio. Conviction ≠ dollar size — a small fund with a 10% bet shows more conviction than a giant fund with a 0.5% position."
        />
        <StatCard
          label="First smart buyer"
          value={accumulation?.first_smart_buyer ?? "—"}
          sub={accumulation?.first_smart_buy_quarter ?? ""}
          info="The first tracked fund to ever open a position in this name. Useful for seeing who was 'early' to a thesis."
        />
      </section>

      {/* Accumulation narrative panel */}
      {accumulation && (
        <Card title="Accumulation summary" className="mb-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
            <div>
              <h3 className="text-xs uppercase tracking-wide text-muted mb-2">
                Holder dynamics
              </h3>
              <ul className="space-y-1.5 text-slate">
                <li>
                  <strong className="tabular-nums">
                    {accumulation.holders_count_3q_ago} → {accumulation.current_holders_count}
                  </strong>{" "}
                  holders over the last 3 quarters
                  <span className={
                    "ml-2 text-xs font-semibold " +
                    (accumulation.holders_count_delta_3q > 0 ? "text-good"
                      : accumulation.holders_count_delta_3q < 0 ? "text-bad" : "text-muted")
                  }>
                    ({accumulation.holders_count_delta_3q > 0 ? "+" : ""}
                    {accumulation.holders_count_delta_3q})
                  </span>
                </li>
                <li>
                  Average holding period:{" "}
                  <strong>{holdingPeriod(accumulation.avg_holding_quarters_across)}</strong>
                  {" "}across current holders
                </li>
                {accumulation.new_entrants_last_quarter.length > 0 && (
                  <li>
                    <span className="text-good font-semibold">+ New this quarter:</span>{" "}
                    {accumulation.new_entrants_last_quarter.join(", ")}
                  </li>
                )}
                {accumulation.exited_last_quarter.length > 0 && (
                  <li>
                    <span className="text-bad font-semibold">− Exited this quarter:</span>{" "}
                    {accumulation.exited_last_quarter.join(", ")}
                  </li>
                )}
              </ul>
            </div>
            <div>
              <h3 className="text-xs uppercase tracking-wide text-muted mb-2">
                Dollar flow
              </h3>
              <ul className="space-y-1.5 text-slate">
                <li>
                  Total smart money in name:{" "}
                  <strong className="tabular-nums">{fmtMoney(accumulation.total_smart_money_value)}</strong>
                </li>
                <li>
                  Quarter-over-quarter Δ:{" "}
                  <strong className={
                    "tabular-nums " +
                    ((accumulation.total_smart_money_value_delta ?? 0) > 0 ? "text-good"
                      : (accumulation.total_smart_money_value_delta ?? 0) < 0 ? "text-bad" : "text-muted")
                  }>
                    {(accumulation.total_smart_money_value_delta ?? 0) > 0 ? "+" : ""}
                    {fmtMoney(accumulation.total_smart_money_value_delta)}
                  </strong>
                </li>
                <li>
                  Top by dollars: <strong>{accumulation.top_holder_by_dollars ?? "—"}</strong>
                  {" "}({fmtMoney(accumulation.top_holder_by_dollars_value)})
                </li>
                <li>
                  Top by conviction: <strong>{accumulation.top_holder_by_conviction ?? "—"}</strong>
                  {accumulation.top_holder_by_conviction_pct && (
                    <span className="text-muted">
                      {" "}({accumulation.top_holder_by_conviction_pct.toFixed(1)}% of portfolio)
                    </span>
                  )}
                </li>
              </ul>
            </div>
          </div>
        </Card>
      )}

      {/* Who is building */}
      <Card
        title="Who is holding & building this stock"
        subtitle={`${holders.length} fund(s) — sorted by conviction score`}
        pad={false}
        className="mb-5"
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
                  <th className="text-left  px-3 py-2.5 font-medium">Investor</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Style</th>
                  <th className="text-center px-3 py-2.5 font-medium">First buy</th>
                  <th className="text-center px-3 py-2.5 font-medium">Held</th>
                  <th className="text-center px-3 py-2.5 font-medium">Pattern</th>
                  <th className="text-right px-3 py-2.5 font-medium">% Port</th>
                  <th className="text-right px-3 py-2.5 font-medium">Value</th>
                  <th className="text-right px-3 py-2.5 font-medium">Est. cost</th>
                  <th className="text-right px-3 py-2.5 font-medium">P&L est.</th>
                  <th className="text-center px-3 py-2.5 font-medium">Conviction</th>
                  <th className="text-center px-3 py-2.5 font-medium">Last activity</th>
                </tr>
              </thead>
              <tbody>
                {holders.map((h) => (
                  <tr key={h.cik} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2">
                      <Link href={`/funds/${h.cik}`} className="font-semibold text-navy hover:text-sky">
                        {h.manager_name ?? h.fund_name}
                      </Link>
                      <div className="text-xs text-muted">{h.fund_name}</div>
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {h.fund_type && (
                        <span className="text-slate capitalize">{h.fund_type}</span>
                      )}
                      {h.cap_focus && (
                        <span className="text-muted">/{h.cap_focus}</span>
                      )}
                      {!h.fund_type && <span className="text-muted">—</span>}
                    </td>
                    <td className="px-3 py-2 text-center text-xs text-muted tabular-nums">
                      {h.first_buy_quarter ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-center text-xs tabular-nums">
                      {holdingPeriod(h.holding_quarters)}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <PatternBadge pattern={h.pattern} />
                      {h.consecutive_adds != null && h.consecutive_adds >= 2 && (
                        <div className="text-[10px] text-good mt-0.5">
                          +{h.consecutive_adds}Q in a row
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums font-medium">
                      {h.pct_portfolio?.toFixed(2) ?? "—"}%
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(h.value)}</td>
                    <td className="px-3 py-2 text-right text-xs text-muted tabular-nums">
                      {h.est_avg_cost ? fmtPrice(h.est_avg_cost) : "—"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-xs">
                      <span className={
                        (h.unrealized_pnl_pct ?? 0) > 0 ? "text-good font-medium" :
                        (h.unrealized_pnl_pct ?? 0) < 0 ? "text-bad font-medium" : "text-muted"
                      }>
                        {h.unrealized_pnl_pct != null ? fmtPct(h.unrealized_pnl_pct) : "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-center">
                      <ConvictionStars score={h.conviction_score} />
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Activity timeline */}
      {events.length > 0 && (
        <Card
          title="Activity timeline"
          subtitle="Recent quarter-by-quarter buys, sells, and entries from tracked funds"
          pad={false}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm zebra">
              <thead>
                <tr className="text-muted text-xs uppercase tracking-wide bg-bg border-b border-line">
                  <th className="text-left  px-3 py-2.5 font-medium w-24">Quarter</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Event</th>
                  <th className="text-right px-3 py-2.5 font-medium">% Port after</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e, i) => (
                  <tr
                    key={`${e.cik}-${e.quarter}-${e.event_type}-${i}`}
                    className={`border-b border-line/60 last:border-0 ${
                      e.importance >= 2 ? "bg-good/5" : ""
                    }`}
                  >
                    <td className="px-3 py-2 text-muted tabular-nums">{e.quarter}</td>
                    <td className="px-3 py-2 text-slate">
                      <Link href={`/funds/${e.cik}`} className="text-navy hover:text-sky font-medium">
                        {e.manager_name ?? e.fund_name}
                      </Link>{" "}
                      <span className="text-muted text-xs">— </span>
                      <ChangeBadge type={e.event_type as any} />
                      {e.magnitude_pct != null && (
                        <span className={
                          "ml-2 text-xs tabular-nums " +
                          (e.magnitude_pct > 0 ? "text-good" : e.magnitude_pct < 0 ? "text-bad" : "text-muted")
                        }>
                          {e.magnitude_pct > 0 ? "+" : ""}{e.magnitude_pct.toFixed(0)}%
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-xs">
                      {e.pct_portfolio != null ? `${e.pct_portfolio.toFixed(1)}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <p className="mt-6 text-xs text-muted leading-relaxed max-w-3xl">
        Conviction scores, patterns, and phase labels are derived from full 13F history. The
        score combines position size relative to the fund's typical bet, consecutive add quarters,
        top-10 ranking in the portfolio, and absolute portfolio weight. Pattern detection looks
        for probe/pyramid/linear/single-shot/re-entry/distribute signatures across the share-count
        timeline. P&L estimates use yfinance quarter-end close vs. an estimated cost basis built
        from each quarter's average close at the time shares were added. Not investment advice.
      </p>
    </>
  );
}
