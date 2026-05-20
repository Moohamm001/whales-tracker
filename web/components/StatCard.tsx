import React from "react";
import InfoTip from "./InfoTip";

type Props = {
  label: string;
  value: string;
  sub?: string;
  trend?: "up" | "down" | "neutral";
  info?: string;
};

export default function StatCard({ label, value, sub, trend, info }: Props) {
  const trendClass =
    trend === "up" ? "text-good" : trend === "down" ? "text-bad" : "text-muted";

  return (
    <div className="bg-card border border-line rounded shadow-card p-4">
      <div className="flex items-center gap-1 text-muted text-xs font-medium uppercase tracking-wide">
        <span>{label}</span>
        {info && <InfoTip text={info} />}
      </div>
      <div className={`mt-1 text-2xl font-semibold ${trendClass}`}>
        {value}
      </div>
      {sub && <div className="text-muted text-xs mt-1">{sub}</div>}
    </div>
  );
}
