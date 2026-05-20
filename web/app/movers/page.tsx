import Link from "next/link";
import Card from "@/components/Card";
import { ChangeBadge } from "@/components/Badge";
import { getTopMovers } from "@/lib/db";

export const dynamic = "force-dynamic";

function fmtMoney(n: number | null | undefined): string {
  if (n == null) return "—";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1e9)  return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6)  return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3)  return `${sign}$${(abs / 1e3).toFixed(2)}K`;
  return `${sign}$${abs.toLocaleString()}`;
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

export default function MoversPage() {
  const movers = getTopMovers(100);

  return (
    <>
      <div className="text-xs text-muted mb-4">
        <Link href="/" className="text-sky">← Back to investors</Link>
      </div>

      <section className="mb-5">
        <h1 className="text-2xl font-semibold text-slate tracking-tight">Top movers</h1>
        <p className="text-muted text-sm mt-1 max-w-2xl">
          Largest position changes across all tracked investors in the latest reporting
          period, ranked by dollar magnitude.
        </p>
      </section>

      <Card
        title="Latest quarter activity"
        subtitle={
          movers.length
            ? `${movers.length} largest moves (${movers[0].quarter})`
            : "Awaiting data"
        }
        pad={false}
      >
        {movers.length === 0 ? (
          <div className="p-6 text-bad text-sm">
            No quarter-over-quarter data yet — at least 2 filings per fund required.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm zebra">
              <thead>
                <tr className="text-muted text-xs uppercase tracking-wide bg-bg border-b border-line">
                  <th className="text-right px-3 py-2.5 font-medium w-10">#</th>
                  <th className="text-left  px-3 py-2.5 font-medium w-24">Change</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Ticker</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Company</th>
                  <th className="text-left  px-3 py-2.5 font-medium">Investor</th>
                  <th className="text-right px-3 py-2.5 font-medium">Value Before</th>
                  <th className="text-right px-3 py-2.5 font-medium">Value After</th>
                  <th className="text-right px-3 py-2.5 font-medium">% Δ</th>
                </tr>
              </thead>
              <tbody>
                {movers.map((m, i) => (
                  <tr key={i} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2 text-right text-muted tabular-nums">{i + 1}</td>
                    <td className="px-3 py-2">
                      <ChangeBadge type={m.change_type} />
                    </td>
                    <td className="px-3 py-2 font-semibold text-navy">{m.ticker ?? "—"}</td>
                    <td className="px-3 py-2 text-slate">{m.name}</td>
                    <td className="px-3 py-2">
                      <Link
                        href={`/funds/${m.cik}`}
                        className="text-sky hover:text-navy"
                      >
                        {m.manager_name ?? m.fund_name}
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(m.value_before)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(m.value_after)}</td>
                    <td
                      className={`px-3 py-2 text-right tabular-nums font-medium ${
                        m.pct_change == null
                          ? "text-muted"
                          : m.pct_change > 0
                            ? "text-good"
                            : m.pct_change < 0
                              ? "text-bad"
                              : "text-muted"
                      }`}
                    >
                      {fmtPct(m.pct_change)}
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
