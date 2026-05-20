import React from "react";

type Variant =
  | "new"
  | "added"
  | "reduced"
  | "sold"
  | "accumulating"
  | "building"
  | "reducing-trend"
  | "exiting"
  | "stable"
  | "neutral"
  | "info";

const STYLES: Record<Variant, string> = {
  new:          "bg-good/10  text-good  border-good/30",
  added:        "bg-good/10  text-good  border-good/30",
  reduced:      "bg-warn/10  text-warn  border-warn/30",
  sold:         "bg-bad/10   text-bad   border-bad/30",
  accumulating: "bg-good/10  text-good  border-good/30",
  building:     "bg-info/10  text-info  border-info/30",
  "reducing-trend": "bg-warn/10 text-warn border-warn/30",
  exiting:      "bg-bad/10   text-bad   border-bad/30",
  stable:       "bg-muted/10 text-muted border-muted/30",
  neutral:      "bg-muted/10 text-muted border-muted/30",
  info:         "bg-info/10  text-info  border-info/30",
};

export default function Badge({
  variant = "neutral",
  children,
}: {
  variant?: Variant;
  children: React.ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${STYLES[variant]}`}
    >
      {children}
    </span>
  );
}

export function ChangeBadge({ type }: { type: "NEW" | "ADDED" | "REDUCED" | "SOLD" }) {
  const variant = type.toLowerCase() as Variant;
  const labels = { NEW: "New", ADDED: "Added", REDUCED: "Reduced", SOLD: "Sold out" };
  return <Badge variant={variant}>{labels[type]}</Badge>;
}

export function TrendBadge({
  trend,
}: {
  trend: "Accumulating" | "Reducing" | "Building" | "Exiting" | "Stable" | "New";
}) {
  const map: Record<string, Variant> = {
    Accumulating: "accumulating",
    Reducing: "reducing-trend",
    Building: "building",
    Exiting: "exiting",
    Stable: "stable",
    New: "building",
  };
  return <Badge variant={map[trend]}>{trend}</Badge>;
}
