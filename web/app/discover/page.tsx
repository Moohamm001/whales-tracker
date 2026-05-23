import Link from "next/link";
import Card from "@/components/Card";
import StatCard from "@/components/StatCard";
import PhaseBadge from "@/components/PhaseBadge";
import {
  getDiscoveryStocks,
  getPhaseCounts,
  listSectors,
  type Phase,
  type DiscoveryFilters,
} from "@/lib/db";

export const dynamic = "force-dynamic";

function fmtMoney(n: number | null | undefined): string {
  if (n == null || !n) return "—";
  const a = Math.abs(n);
  const s = n < 0 ? "-" : "";
  if (a >= 1e12) return `${s}$${(a / 1e12).toFixed(2)}T`;
  if (a >= 1e9)  return `${s}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6)  return `${s}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3)  return `${s}$${(a / 1e3).toFixed(1)}K`;
  return `${s}$${a.toFixed(0)}`;
}

function parseEntrants(s: string | null | undefined): string[] {
  if (!s) return [];
  try {
    const v = JSON.parse(s);
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

type SP = { [k: string]: string | string[] | undefined };

export default function DiscoverPage({ searchParams }: { searchParams: SP }) {
  const phase = (typeof searchParams.phase === "string" ? searchParams.phase : "early-accumulation") as
    Phase | "any";
  const cap_bucket = (typeof searchParams.cap === "string" ? searchParams.cap : "any") as
    DiscoveryFilters["cap_bucket"];
  const sector = (typeof searchParams.sector === "string" ? searchParams.sector : "any") as
    string | "any";
  const min_holders = searchParams.min ? Math.max(1, parseInt(String(searchParams.min))) : 2;
  const max_holders = searchParams.max ? parseInt(String(searchParams.max)) : undefined;
  const min_growth = searchParams.grow ? parseInt(String(searchParams.grow)) : 1;

  const stocks = getDiscoveryStocks({
    phase,
    cap_bucket,
    sector,
    min_holders,
    max_holders,
    min_holders_growth_3q: min_growth,
    limit: 200,
  });

  const phaseCounts = getPhaseCounts();
  const sectors = listSectors();

  // Helper: build href that preserves other filters but flips one
  const href = (overrides: Record<string, string | undefined>) => {
    const sp = new URLSearchParams();
    const set = (k: string, v: string | undefined | number) => {
      if (v == null || v === "" || v === "any") return;
      sp.set(k, String(v));
    };
    set("phase", overrides.phase ?? phase);
    set("cap", overrides.cap ?? cap_bucket);
    set("sector", overrides.sector ?? sector);
    set("min", overrides.min ?? String(min_holders));
    if (max_holders != null) set("max", overrides.max ?? String(max_holders));
    set("grow", overrides.grow ?? String(min_growth));
    const qs = sp.toString();
    return qs ? `/discover?${qs}` : "/discover";
  };

  const PHASE_OPTIONS: { value: Phase | "any"; label: string; desc: string }[] = [
    { value: "early-accumulation", label: "Early accumulation", desc: "1–3 smart holders, new entrants present" },
    { value: "consensus-build",    label: "Consensus building", desc: "Holders rising 2+ Q in a row" },
    { value: "crowded",            label: "Crowded",            desc: "≥7 holders, growth slowing" },
    { value: "topping",            label: "Topping",            desc: "Trimming present, holders flat" },
    { value: "distribution",       label: "Distribution",       desc: "Multiple trimmers, value down" },
    { value: "any",                label: "Any phase",          desc: "" },
  ];

  const earlyCount = phaseCounts.find((p) => p.phase === "early-accumulation")?.count ?? 0;
  const consensusCount = phaseCounts.find((p) => p.phase === "consensus-build")?.count ?? 0;
  const distCount = phaseCounts.find((p) => p.phase === "distribution")?.count ?? 0;
  const toppingCount = phaseCounts.find((p) => p.phase === "topping")?.count ?? 0;

  return (
    <>
      <section className="mb-6">
        <h1 className="text-2xl font-semibold text-slate tracking-tight">
          Smart-money discovery
        </h1>
        <p className="text-muted text-sm mt-1 max-w-3xl">
          Find stocks <strong>before</strong> they get crowded. Filter by accumulation phase to see
          where tracked investors are quietly building positions, where consensus is forming,
          and where smart money is heading for the exits.
        </p>
      </section>

      {/* Phase summary */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <StatCard
          label="Early accumulation"
          value={earlyCount.toLocaleString()}
          sub="1–3 holders, new entrants"
          info="Most actionable bucket: a few smart funds opening positions before broader recognition. Edge window is widest here."
        />
        <StatCard
          label="Consensus building"
          value={consensusCount.toLocaleString()}
          sub="holders rising 2+ Q"
          info="Multiple smart funds independently arriving at the same name. Strongest aggregate signal."
        />
        <StatCard
          label="Topping"
          value={toppingCount.toLocaleString()}
          sub="trimming + holders flat"
          info="Position is mature, some funds beginning to take profits. Often a 1-2 quarter warning before broader exit."
        />
        <StatCard
          label="Distribution"
          value={distCount.toLocaleString()}
          sub="multiple trimmers"
          info="Smart money is selling. Aggregate dollar value declining quarter-over-quarter."
        />
      </section>

      {/* Phase tabs */}
      <Card title="Phase" pad={false} className="mb-5">
        <div className="px-5 py-3 flex flex-wrap gap-2">
          {PHASE_OPTIONS.map((opt) => {
            const active = phase === opt.value;
            return (
              <Link
                key={opt.value}
                href={href({ phase: opt.value })}
                className={`px-3 py-1.5 rounded text-sm border transition-colors hover:no-underline ${
                  active
                    ? "bg-navy text-white border-navy"
                    : "bg-card text-slate border-line hover:bg-bg"
                }`}
                title={opt.desc}
              >
                {opt.label}
              </Link>
            );
          })}
        </div>
      </Card>

      {/* Secondary filters */}
      <Card pad={false} className="mb-5">
        <div className="px-5 py-3 grid grid-cols-1 md:grid-cols-4 gap-3 text-sm">
          <div>
            <label className="text-muted text-xs uppercase tracking-wide block mb-1">Market cap</label>
            <div className="flex flex-wrap gap-1">
              {["any", "micro", "small", "mid", "large", "mega"].map((b) => (
                <Link
                  key={b}
                  href={href({ cap: b })}
                  className={`px-2 py-1 rounded text-xs border hover:no-underline ${
                    cap_bucket === b
                      ? "bg-navy text-white border-navy"
                      : "bg-card text-slate border-line hover:bg-bg"
                  }`}
                >
                  {b}
                </Link>
              ))}
            </div>
            <p className="text-muted text-xs mt-1">
              Run <code className="font-mono text-[10px]">fetch_market_caps.py</code> to enable cap filtering.
            </p>
          </div>

          <div>
            <label className="text-muted text-xs uppercase tracking-wide block mb-1">Min holders</label>
            <div className="flex flex-wrap gap-1">
              {[1, 2, 3, 4, 5].map((n) => (
                <Link
                  key={n}
                  href={href({ min: String(n) })}
                  className={`px-2 py-1 rounded text-xs border hover:no-underline ${
                    min_holders === n
                      ? "bg-navy text-white border-navy"
                      : "bg-card text-slate border-line hover:bg-bg"
                  }`}
                >
                  ≥{n}
                </Link>
              ))}
            </div>
          </div>

          <div>
            <label className="text-muted text-xs uppercase tracking-wide block mb-1">Holders growth (3Q)</label>
            <div className="flex flex-wrap gap-1">
              {[0, 1, 2, 3].map((n) => (
                <Link
                  key={n}
                  href={href({ grow: String(n) })}
                  className={`px-2 py-1 rounded text-xs border hover:no-underline ${
                    min_growth === n
                      ? "bg-navy text-white border-navy"
                      : "bg-card text-slate border-line hover:bg-bg"
                  }`}
                >
                  ≥+{n}
                </Link>
              ))}
            </div>
          </div>

          <div>
            <label className="text-muted text-xs uppercase tracking-wide block mb-1">Sector</label>
            {sectors.length === 0 ? (
              <p className="text-muted text-xs">
                Run <code className="font-mono text-[10px]">fetch_market_caps.py</code> to enable.
              </p>
            ) : (
              <div className="flex flex-wrap gap-1 max-h-20 overflow-y-auto">
                <Link
                  href={href({ sector: "any" })}
                  className={`px-2 py-1 rounded text-xs border hover:no-underline ${
                    sector === "any"
                      ? "bg-navy text-white border-navy"
                      : "bg-card text-slate border-line hover:bg-bg"
                  }`}
                >
                  any
                </Link>
                {sectors.map((s) => (
                  <Link
                    key={s}
                    href={href({ sector: s })}
                    className={`px-2 py-1 rounded text-xs border hover:no-underline ${
                      sector === s
                        ? "bg-navy text-white border-navy"
                        : "bg-card text-slate border-line hover:bg-bg"
                    }`}
                  >
                    {s}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* Results */}
      <Card
        title={`${stocks.length} stock${stocks.length === 1 ? "" : "s"} matching`}
        subtitle="Sorted by 3Q holders-growth, then aggregate dollar inflow"
        pad={false}
      >
        {stocks.length === 0 ? (
          <div className="p-6 text-muted text-sm">
            No stocks match the current filters. Try widening the phase or lowering the holders
            growth threshold.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm zebra">
              <thead>
                <tr className="text-muted text-xs uppercase tracking-wide bg-bg border-b border-line">
                  <th className="text-left  px-3 py-2.5 font-medium">Ticker</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Company</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Mkt cap</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Sector</th>
                  <th className="text-center px-3 py-2.5 font-medium">Holders</th>
                  <th className="text-center px-3 py-2.5 font-medium">3Q growth</th>
                  <th className="text-right px-3 py-2.5 font-medium">Smart $</th>
                  <th className="text-right px-3 py-2.5 font-medium">$ Δ</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Top conviction</th>
                  <th className="text-left  px-3 py-2.5 font-medium">New this Q</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Phase</th>
                </tr>
              </thead>
              <tbody>
                {stocks.map((s) => {
                  const entrants = parseEntrants(s.new_entrants_last_quarter);
                  return (
                    <tr key={s.cusip} className="border-b border-line/60 last:border-0">
                      <td className="px-3 py-2 font-semibold text-navy">
                        <Link href={`/stocks/${s.ticker}`} className="hover:text-sky">
                          {s.ticker}
                        </Link>
                      </td>
                      <td className="px-3 py-2 text-slate text-xs">{s.name}</td>
                      <td className="px-3 py-2 text-xs">
                        {s.market_cap_bucket ? (
                          <span className="text-muted capitalize">{s.market_cap_bucket}</span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs text-muted">{s.sector ?? "—"}</td>
                      <td className="px-3 py-2 text-center tabular-nums">
                        {s.current_holders_count}
                      </td>
                      <td className="px-3 py-2 text-center tabular-nums">
                        <span className={
                          s.holders_count_delta_3q > 0 ? "text-good font-semibold" :
                          s.holders_count_delta_3q < 0 ? "text-bad" : "text-muted"
                        }>
                          {s.holders_count_delta_3q > 0 ? "+" : ""}{s.holders_count_delta_3q}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium">
                        {fmtMoney(s.total_smart_money_value)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-xs">
                        <span className={
                          (s.total_smart_money_value_delta ?? 0) > 0 ? "text-good" :
                          (s.total_smart_money_value_delta ?? 0) < 0 ? "text-bad" : "text-muted"
                        }>
                          {(s.total_smart_money_value_delta ?? 0) > 0 ? "+" : ""}
                          {fmtMoney(s.total_smart_money_value_delta)}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-xs text-slate">
                        {s.top_holder_by_conviction ?? "—"}
                        {s.top_holder_by_conviction_pct ? (
                          <span className="text-muted ml-1">
                            ({s.top_holder_by_conviction_pct.toFixed(1)}%)
                          </span>
                        ) : null}
                      </td>
                      <td className="px-3 py-2 text-xs text-slate">
                        {entrants.length === 0 ? (
                          <span className="text-muted">—</span>
                        ) : (
                          <span title={entrants.join(", ")}>
                            {entrants.slice(0, 2).join(", ")}
                            {entrants.length > 2 ? `, +${entrants.length - 2}` : ""}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2"><PhaseBadge phase={s.phase} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <p className="mt-6 text-xs text-muted leading-relaxed max-w-3xl">
        Discovery uses derived <code className="font-mono">StockAccumulationProfile</code> data
        computed from full 13F history. Phase labels are backward-looking pattern detectors —
        they describe the visible smart-money behaviour, not a prediction of future price.
        13F data lags reality by 45 days. Not investment advice.
      </p>
    </>
  );
}
